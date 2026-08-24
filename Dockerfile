# LXC Deck — 生产镜像
# 构建: docker build -t lxcdeck:latest .
# 运行: 见 docker-compose.yml
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LXCP_PORT=8080 \
    LXCP_DB=/data/panel.db

WORKDIR /app

# 先装依赖以利用层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY run.py ./
COPY app ./app
COPY web ./web

# 数据卷: SQLite 面板数据库
VOLUME ["/data"]
RUN mkdir -p /data

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('LXCP_PORT','8080')+'/api/meta', timeout=4).status==200 else 1)" || exit 1

CMD ["python", "run.py"]
