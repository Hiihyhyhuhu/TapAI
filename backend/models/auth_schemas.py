from datetime import datetime
from typing import Optional, Any
import re
from pydantic import BaseModel, Field, field_validator

PHONE_REGEX = re.compile(r"^(?:\+?84|0)(?:3|5|7|8|9)\d{8}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

class ShopRegisterRequest(BaseModel):
    email: str = Field(description="Email doanh nghiệp của shop")
    phone: str = Field(description="Số điện thoại Việt Nam hợp lệ (VD: 0912345678)")
    password: str = Field(min_length=6, description="Mật khẩu tối thiểu 6 ký tự")
    shop_name: str = Field(min_length=2, max_length=120, description="Tên hiển thị của shop trên sàn")
    platform: str = Field(default="shopee", description="shopee | lazada | tiki | tiktok_shop | other")
    shop_url: Optional[str] = Field(default=None, description="Đường link chính thức của shop trên sàn TMĐT")
    turnstile_token: Optional[str] = Field(default=None, description="Token chống bot từ Cloudflare Turnstile")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Định dạng email không hợp lệ (VD: contact@shopname.com)")
        return clean

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean_phone = re.sub(r"[\s\-\.]", "", v)
        if not PHONE_REGEX.match(clean_phone):
            if re.match(r"^0\d{9}$", clean_phone) or re.match(r"^\+?84\d{9}$", clean_phone):
                return clean_phone
            raise ValueError("Số điện thoại không hợp lệ (vui lòng nhập số 10 chữ số, VD: 0912345678)")
        return clean_phone

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        normalized = v.strip().lower()
        allowed = {"shopee", "lazada", "tiki", "tiktok_shop", "other"}
        if normalized not in allowed:
            return "shopee"
        return normalized

    @field_validator("shop_url")
    @classmethod
    def validate_shop_url(cls, v: Optional[str]) -> str:
        if not v or not v.strip():
            return "https://shopee.vn"
        clean = v.strip()
        if not (clean.startswith("http://") or clean.startswith("https://")):
            clean = f"https://{clean}"
        return clean


class VerifyEmailRequest(BaseModel):
    email: str
    otp_code: str = Field(min_length=4, max_length=8, description="Mã OTP gửi về email")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Định dạng email không hợp lệ")
        return clean


class VerifyPhoneRequest(BaseModel):
    phone: str
    otp_code: str = Field(min_length=4, max_length=8, description="Mã OTP gửi về SĐT")


class ResendOtpRequest(BaseModel):
    target: str = Field(description="Email hoặc số điện thoại cần nhận lại OTP")
    type: str = Field(description="'email' hoặc 'phone'")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("email", "phone"):
            raise ValueError("Loại OTP chỉ nhận 'email' hoặc 'phone'")
        return v


class LoginRequest(BaseModel):
    email_or_phone: str = Field(description="Email hoặc số điện thoại đã đăng ký")
    password: str = Field(description="Mật khẩu")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(description="JWT Refresh Token")


class ShopInfo(BaseModel):
    id: str
    email: str
    phone: str
    shop_name: str
    platform: str
    shop_url: str
    status: str
    email_verified: bool
    phone_verified: bool
    ownership_token: Optional[str] = None
    contract_status: Optional[str] = "PENDING"
    contract_signed_at: Optional[datetime] = None
    contract_hash: Optional[str] = None
    wallet_balance: Optional[float] = 1000000.0
    total_deposited: Optional[float] = 1000000.0
    total_cpc_spent: Optional[float] = 0.0
    created_at: datetime

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    shop: ShopInfo


class MessageResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
