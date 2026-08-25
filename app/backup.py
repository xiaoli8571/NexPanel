"""自动定时备份 + 恢复模块

支持两种后端：
1. S3 兼容对象存储（MinIO / AWS S3 / Cloudflare R2…）
2. WebDAV

配置存储在 settings 表：
- backup_enabled: "1"/"0"
- backup_interval_hours: int
- backup_type: "s3" / "webdav"
- backup_endpoint: S3 endpoint URL / WebDAV URL
- backup_region: S3 region (默认 us-east-1)
- backet_bucket: S3 bucket 名称 / WebDAV 路径前缀
- backup_access_key: S3 Access Key / WebDAV 用户名
- backup_secret_key: S3 Secret Key / WebDAV 密码
- backup_retention_days: 保留天数（>0 时自动清理旧备份）
- backup_last_run: 上次执行时间
- backup_last_result: 上次结果（"ok" / error message）

备份内容：data/panel.db + data/panel.db-wal（WAL 模式数据库）
"""
import asyncio
import json
import os
import pathlib
import shutil
import tempfile
import time
import traceback
import tarfile
import urllib.parse
from datetime import datetime, timedelta
from typing import Any

from . import config, db, notify

BACKUP_LOCK = {"v": False}
BACKUP_TASK: asyncio.Task | None = None


def get_settings() -> dict:
    """获取当前备份配置"""
    keys = ("backup_enabled", "backup_interval_hours", "backup_type",
            "backup_endpoint", "backup_region", "backup_bucket",
            "backup_access_key", "backup_secret_key",
            "backup_retention_days", "backup_last_run", "backup_last_result")
    result = {}
    for k in keys:
        row = db.one("SELECT value FROM settings WHERE key=?", (k,))
        result[k] = row["value"] if row else ""
    # 类型转换
    result["backup_enabled"] = result.get("backup_enabled", "0") == "1"
    try:
        result["backup_interval_hours"] = int(result.get("backup_interval_hours", "24"))
    except (ValueError, TypeError):
        result["backup_interval_hours"] = 24
    try:
        result["backup_retention_days"] = int(result.get("backup_retention_days", "30"))
    except (ValueError, TypeError):
        result["backup_retention_days"] = 30
    return result


def save_settings(data: dict):
    """保存备份配置"""
    for k, v in data.items():
        db.ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              k, str(v))


def _update_last_run(result: str):
    """记录备份执行结果"""
    now = db.now()
    db.ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
          "backup_last_run", now)
    db.ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
          "backup_last_result", result)
    # 记录到审计
    try:
        db.audit("system", "自动备份" if "ok" in result else "备份失败",
                 "system", result[:200])
    except Exception:
        pass


def _create_tgz() -> str:
    """创建数据库备份压缩包，返回临时文件路径"""
    data_dir = config.DATA_DIR
    db_path = config.DB_PATH

    # WAL 模式：先执行 checkpoint 确保数据完整性
    db.ex("PRAGMA wal_checkpoint(TRUNCATE)")

    tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
    try:
        with tarfile.open(fileobj=tmp, mode="w:gz") as tar:
            # 添加数据库文件
            for name in ("panel.db", "panel.db-wal", "panel.db-shm"):
                path = data_dir / name
                if path.exists():
                    tar.add(str(path), arcname=name)
            # 添加版本信息
            import pathlib
            ver_file = pathlib.Path(tmp.name + "_ver")
            try:
                ver_file.write_text(json.dumps({
                    "version": config.VERSION,
                    "created_at": db.now(),
                    "brand": config.BRAND,
                    "hostname": config.HOSTNAME,
                }))
                tar.add(str(ver_file), arcname="version.json")
            finally:
                try:
                    ver_file.unlink()
                except Exception:
                    pass
        return tmp.name
    except Exception:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        raise


def _upload_s3(filepath: str, filename: str) -> str:
    """上传到 S3 兼容对象存储，返回 成功/错误"""
    cfg = get_settings()
    endpoint = cfg.get("backup_endpoint", "").rstrip("/")
    bucket = cfg.get("backup_bucket", "nexpanel-backup")
    region = cfg.get("backup_region", "us-east-1")
    access_key = cfg.get("backup_access_key", "")
    secret_key = cfg.get("backup_secret_key", "")

    if not endpoint or not access_key or not secret_key:
        return "S3 配置不完整"

    try:
        import hashlib
        import hmac
        import urllib.request

        # 简单 S3 PUT 实现（纯标准库）
        file_size = os.path.getsize(filepath)
        key = f"backups/{filename}"

        # 构造 S3 PUT 请求
        url = f"{endpoint}/{bucket}/{key}"
        date = datetime.utcnow().strftime("%Y%m%d")
        amz_date = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        with open(filepath, "rb") as f:
            body = f.read()

        import io
        # SHA256 of body
        body_hash = hashlib.sha256(body).hexdigest()

        # 简单签名（实际项目建议用 boto3，但这里保持零依赖）
        # 使用标准的 AWS Signature V4
        service = "s3"
        algorithm = "AWS4-HMAC-SHA256"

        # 构建 canonical request
        canonical_uri = f"/{bucket}/{key}"
        canonical_querystring = ""
        canonical_headers = (
            f"host:{urllib.parse.urlparse(url).hostname}\n"
            f"x-amz-content-sha256:{body_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = (
            f"PUT\n{canonical_uri}\n{canonical_querystring}\n"
            f"{canonical_headers}\n{signed_headers}\n{body_hash}"
        )

        # 构建 string to sign
        credential_scope = f"{date}/{region}/{service}/aws4_request"
        string_to_sign = (
            f"{algorithm}\n{amz_date}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        # 计算签名
        def sign(key, msg):
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        date_key = sign(("AWS4" + secret_key).encode(), date)
        region_key = sign(date_key, region)
        service_key = sign(region_key, service)
        signing_key = sign(service_key, "aws4_request")
        signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

        authorization = (
            f"{algorithm} Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type": "application/gzip",
                "Content-Length": str(file_size),
                "Host": urllib.parse.urlparse(url).hostname,
                "x-amz-content-sha256": body_hash,
                "x-amz-date": amz_date,
                "Authorization": authorization,
            },
            method="PUT")
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = r.read().decode()
            return "ok"
    except Exception as e:
        return f"S3 上传失败: {str(e)[:200]}"


def _webdav_join(base: str, *parts: str) -> str:
    """安全拼接 WebDAV URL，保留协议双斜杠"""
    base = (base or "").rstrip("/")
    return base + "/" + "/".join(str(p).strip("/") for p in parts if p)


def _upload_webdav(filepath: str, filename: str) -> str:
    """上传到 WebDAV"""
    cfg = get_settings()
    url_base = cfg.get("backup_endpoint", "").rstrip("/")
    path_prefix = cfg.get("backup_bucket", "nexpanel-backup")
    username = cfg.get("backup_access_key", "")
    password = cfg.get("backup_secret_key", "")

    if not url_base or not username:
        return "WebDAV 配置不完整"

    try:
        import base64
        import urllib.request

        full_url = _webdav_join(url_base, path_prefix, filename)

        with open(filepath, "rb") as f:
            body = f.read()

        auth = base64.b64encode(f"{username}:{password}".encode()).decode()

        # 先尝试创建目录（已存在则忽略错误）
        try:
            dir_url = _webdav_join(url_base, path_prefix, "backups")
            mkcol_req = urllib.request.Request(
                dir_url, method="MKCOL",
                headers={"Authorization": f"Basic {auth}"})
            with urllib.request.urlopen(mkcol_req, timeout=15) as r:
                pass
        except Exception:
            pass  # 目录可能已存在

        req = urllib.request.Request(
            full_url, data=body,
            headers={
                "Content-Type": "application/gzip",
                "Authorization": f"Basic {auth}",
            },
            method="PUT")
        with urllib.request.urlopen(req, timeout=120) as r:
            return "ok"
    except Exception as e:
        return f"WebDAV 上传失败: {str(e)[:200]}"


def _cleanup_old_backups() -> str:
    """清理旧备份（TODO：需要列出远程备份，按日期删除）
    目前尚不支持自动清理远程旧备份，留待后续实现
    """
    return "ok"


def _validate_config(cfg: dict) -> str:
    """检查备份配置是否完整，返回空字符串表示完整，否则返回错误信息"""
    if cfg.get("backup_type") == "webdav":
        if not cfg.get("backup_endpoint") or not cfg.get("backup_access_key"):
            return "WebDAV 配置不完整：请填写 URL 和用户名"
    else:
        if not cfg.get("backup_endpoint") or not cfg.get("backup_access_key") or not cfg.get("backup_secret_key"):
            return "S3 配置不完整：请填写 Endpoint、Access Key 和 Secret Key"
    return ""


def do_backup() -> str:
    """执行一次完整备份流程，返回结果描述"""
    cfg = get_settings()
    if not cfg.get("backup_enabled", False):
        return "备份未启用"

    # 配置完整性校验（不发送告警，避免配置未填完时刷屏）
    err = _validate_config(cfg)
    if err:
        _update_last_run(err)
        return err

    filename = f"nexpanel-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    filepath = None
    try:
        # 创建压缩包
        filepath = _create_tgz()
        result = "ok"
        upload_func = _upload_webdav if cfg.get("backup_type") == "webdav" else _upload_s3

        # 上传
        result = upload_func(filepath, filename)
        if result != "ok":
            _update_last_run(result)
            return result

        # 清理旧备份
        _cleanup_old_backups()

        # 记录成功
        _update_last_run("ok")
        notify.notify("backup_success", "✅ 备份成功",
                      f"已备份到 {'WebDAV' if cfg.get('backup_type') == 'webdav' else 'S3'}",
                      f"文件名: {filename}")
        return "ok"
    except Exception as e:
        err = f"备份异常: {str(e)[:200]}"
        _update_last_run(err)
        notify.notify("backup_fail", "❌ 备份失败", str(e)[:400])
        return err
    finally:
        if filepath and os.path.exists(filepath):
            try:
                os.unlink(filepath)
            except Exception:
                pass


async def backup_loop():
    """后台定时备份循环"""
    while True:
        try:
            cfg = get_settings()
            if cfg.get("backup_enabled", False):
                # 配置不完整时降低检查频率，避免每 10 分钟失败一次
                err = _validate_config(cfg)
                if err:
                    await asyncio.sleep(1800)   # 30 分钟后再检查
                    continue
                hours = max(1, cfg.get("backup_interval_hours", 24))
                last_run = cfg.get("backup_last_run", "")
                should_run = True
                if last_run:
                    try:
                        last_dt = datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")
                        if datetime.now() - last_dt < timedelta(hours=hours):
                            should_run = False
                    except ValueError:
                        pass
                if should_run:
                    if not BACKUP_LOCK["v"]:
                        BACKUP_LOCK["v"] = True
                        try:
                            await asyncio.to_thread(do_backup)
                        finally:
                            BACKUP_LOCK["v"] = False
        except Exception as e:
            print(f"[backup] 调度异常: {e}", flush=True)
        # 每 10 分钟检查一次（配置完整时）
        await asyncio.sleep(600)


def start_scheduler():
    """启动定时备份调度器"""
    global BACKUP_TASK
    if BACKUP_TASK is None or BACKUP_TASK.done():
        BACKUP_TASK = asyncio.create_task(backup_loop())


def stop_scheduler():
    """停止定时备份调度器"""
    global BACKUP_TASK
    if BACKUP_TASK and not BACKUP_TASK.done():
        BACKUP_TASK.cancel()
    BACKUP_TASK = None


def restore_from_backup(filepath: str) -> str:
    """从本地备份文件恢复数据库
    filepath: 本地 .tar.gz 文件路径
    返回: "ok" 或错误描述
    """
    import tarfile
    data_dir = config.DATA_DIR
    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp()
        with tarfile.open(filepath, "r:gz") as tar:
            tar.extractall(path=tmp_dir)

        # 验证文件完整性
        db_file = pathlib.Path(tmp_dir) / "panel.db"
        if not db_file.exists():
            return "备份文件中缺少 panel.db"

        # 停止当前数据库连接
        db._conn.close()
        db._conn = None

        # 备份当前数据库（安全）
        backup_name = f"panel.db.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copy2(str(data_dir / "panel.db"), str(data_dir / backup_name))

        # 恢复文件
        for name in ("panel.db", "panel.db-wal", "panel.db-shm"):
            src = pathlib.Path(tmp_dir) / name
            if src.exists():
                shutil.copy2(str(src), str(data_dir / name))

        # 重新连接
        db.connect()
        db.init_schema()

        return "ok"
    except Exception as e:
        return f"恢复失败: {str(e)[:200]}"
    finally:
        if tmp_dir:
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass