"""帳號、密碼、JWT 與權限判斷（spec §15 RBAC）。

- 密碼：標準庫 scrypt＋隨機 salt，格式 `scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>`。
- JWT：HS256，放在 httpOnly cookie；payload 帶 sub（使用者 id）、ver（token_version）、exp。
  每次請求都回資料庫確認帳號仍啟用、ver 相符，停用或重設密碼後舊權杖立即失效。
- 資料集：檔名 `WJ<1-8>-<產品廠>-<線別>-數據庫-<MMDD>.xlsx` → `WJ1-DCS-PM1`。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import os
import re
import secrets
from dataclasses import dataclass

import jwt

log = logging.getLogger(__name__)

ROLE_SUPER = "super_admin"
ROLE_PLANT_ADMIN = "plant_admin"
ROLE_USER = "user"
ROLE_LABELS = {ROLE_SUPER: "最高權限管理者", ROLE_PLANT_ADMIN: "廠管理者", ROLE_USER: "一般使用者"}
PLANTS = tuple(f"WJ{i}" for i in range(1, 9))
PASSWORD_MIN_LENGTH = 8
TOKEN_HOURS = 12
COOKIE_NAME = "qcm_session"

# --------------------------------------------------------------------------- 密碼

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt), dklen=len(digest) // 2, n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual.hex(), digest)


def check_password_policy(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"密碼至少 {PASSWORD_MIN_LENGTH} 碼")


# --------------------------------------------------------------------------- JWT

def _load_secret() -> str:
    secret = os.getenv("QCM_JWT_SECRET", "").strip()
    if secret:
        return secret
    log.warning("未設定 QCM_JWT_SECRET，使用隨機金鑰；後端重啟後所有人都需重新登入。正式環境請設定。")
    return secrets.token_hex(32)


JWT_SECRET = _load_secret()


def issue_token(user_id: int, token_version: int, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    payload = {"sub": str(user_id), "ver": token_version, "iat": now, "exp": now + dt.timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    """驗證簽章與到期；失敗回 None。"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require": ["sub", "exp"]})
    except jwt.PyJWTError:
        return None


# --------------------------------------------------------------------------- 資料集與檔名

_FILENAME = re.compile(r"^(WJ[1-8])-([A-Za-z0-9]+)-([A-Za-z0-9]+)-數據庫-(\d{4})\.xlsx?$", re.IGNORECASE)
FILENAME_EXAMPLE = "WJ1-DCS-PM1-數據庫-1026.xlsx"


@dataclass(frozen=True)
class DatasetName:
    plant: str
    factory: str
    line: str
    date: str

    @property
    def key(self) -> str:
        return f"{self.plant}-{self.factory}-{self.line}"


def parse_dataset_filename(filename: str) -> DatasetName:
    """`WJ1-DCS-PM1-數據庫-1026.xlsx` → DatasetName；格式不符丟 ValueError（訊息可直接給使用者看）。"""
    name = os.path.basename(filename or "").strip()
    match = _FILENAME.match(name)
    if not match:
        raise ValueError(
            f"檔名「{name}」不符合格式：WJ<1-8>-<產品廠>-<線別>-數據庫-<月日>.xlsx，例：{FILENAME_EXAMPLE}"
        )
    plant, factory, line, date = match.groups()
    return DatasetName(plant.upper(), factory.upper(), line.upper(), date)


def dataset_plant(key: str) -> str:
    return key.split("-", 1)[0]


# --------------------------------------------------------------------------- 權限

def can_view_plant(role: str, user_plant: str | None, plant: str) -> bool:
    return role == ROLE_SUPER or (user_plant is not None and user_plant == plant)


def can_import(role: str, user_plant: str | None, plant: str) -> bool:
    if role == ROLE_SUPER:
        return True
    return role == ROLE_PLANT_ADMIN and user_plant == plant


def can_manage_user(actor_role: str, actor_plant: str | None, target_role: str, target_plant: str | None) -> bool:
    """能否新增或修改這個（角色, 廠）的帳號：super 全部；廠管理者只限自己廠的一般使用者。"""
    if actor_role == ROLE_SUPER:
        return True
    return actor_role == ROLE_PLANT_ADMIN and target_role == ROLE_USER and target_plant == actor_plant
