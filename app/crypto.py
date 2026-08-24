"""节点 SSH 凭据加密存储：Fernet(密钥派生自面板 SECRET_KEY)"""
import base64
import hashlib

from cryptography.fernet import Fernet

from . import config

_f = None


def _fernet() -> Fernet:
    global _f
    if _f is None:
        key = base64.urlsafe_b64encode(hashlib.sha256(config.SECRET_KEY.encode()).digest())
        _f = Fernet(key)
    return _f


def enc(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def dec(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
