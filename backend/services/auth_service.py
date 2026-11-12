import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

# JWT Settings
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "tapai-dev-secret-key-change-in-prod-1234567890")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
JWT_REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", "5"))

# Danh sách đen domain email tạm thời (Anti-Spam Layer 5)
DISPOSABLE_EMAIL_DOMAINS = {
    "yopmail.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
    "mailinator.com", "throwawaymail.com", "trashmail.com", "getairmail.com",
    "sharklasers.com", "grr.la", "guerrillamail.biz", "guerrillamail.net",
    "guerrillamail.org", "fakeinbox.com", "dispostable.com", "temp-mail.org",
    "generator.email", "mohmal.com", "mytemp.email"
}

def is_disposable_email(email: str) -> bool:
    """Kiểm tra xem email có thuộc domain dùng 1 lần (disposable) hay không."""
    try:
        domain = email.strip().split("@")[-1].lower()
        return domain in DISPOSABLE_EMAIL_DOMAINS
    except Exception:
        return False

def hash_password(password: str) -> str:
    """Hash mật khẩu bằng bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Kiểm tra mật khẩu khớp với hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def hash_token(token: str) -> str:
    """Hash token bằng SHA-256 để lưu trữ an toàn trong DB."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def generate_otp(length: int = 6) -> str:
    """Tạo mã OTP ngẫu nhiên an toàn gồm các chữ số."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))

def get_otp_expiry(minutes: int = OTP_EXPIRE_MINUTES) -> datetime:
    """Trả về mốc thời gian hết hạn OTP (UTC)."""
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)

def create_access_token(shop_id: str, extra_data: Optional[Dict[str, Any]] = None) -> str:
    """Tạo JWT access token (thời hạn ngắn, mặc định 15 phút)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_EXPIRE_MINUTES)
    payload = {
        "sub": shop_id,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra_data:
        payload.update(extra_data)
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def create_refresh_token(shop_id: str) -> str:
    """Tạo JWT refresh token (thời hạn dài, mặc định 7 ngày)."""
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_EXPIRE_DAYS)
    payload = {
        "sub": shop_id,
        "type": "refresh",
        "jti": secrets.token_hex(16),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
    """Giải mã và kiểm tra tính hợp lệ của token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        return payload
    except jwt.PyJWTError:
        return None

def send_mock_otp(target: str, otp: str, target_type: str = "Email"):
    """
    Giả lập gửi OTP ra Console trong môi trường phát triển (MVP).
    Trong môi trường production, tích hợp SMTP (Email) hoặc SMS API (Twilio/eSMS).
    """
    print(f"\n📨 [OTP NOTIFICATION] Đã gửi mã OTP đến {target_type} '{target}': 【 {otp} 】 (Hết hạn sau {OTP_EXPIRE_MINUTES} phút)\n")

