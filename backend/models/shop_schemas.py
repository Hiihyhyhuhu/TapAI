from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
import re
from pydantic import BaseModel, Field, field_validator

PHONE_REGEX = re.compile(r"^(?:\+?84|0)(?:3|5|7|8|9)\d{8}$")

class VerificationResponse(BaseModel):
    id: str
    shop_id: str
    business_license_url: str
    shop_screenshot_url: str
    shop_url_submitted: str
    status: str
    admin_note: Optional[str] = None
    reviewed_by: Optional[str] = None
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VerificationStatusResponse(BaseModel):
    shop_id: str
    shop_status: str
    has_pending_verification: bool
    latest_verification: Optional[VerificationResponse] = None
    history: List[VerificationResponse] = []


class ShopProfileUpdateRequest(BaseModel):
    shop_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    phone: Optional[str] = Field(default=None, description="Số điện thoại liên hệ")
    shop_url: Optional[str] = Field(default=None, description="Link shop trên sàn")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        clean = re.sub(r"[\s\-\.]", "", v)
        if not PHONE_REGEX.match(clean):
            raise ValueError("Số điện thoại không hợp lệ")
        return clean

    @field_validator("shop_url")
    @classmethod
    def validate_shop_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Đường dẫn shop phải bắt đầu bằng http:// hoặc https://")
        return v.strip()


class AdminReviewRequest(BaseModel):
    action: Literal["approve", "reject", "resubmit_required"] = Field(
        description="Quyết định: approve (duyệt), reject (từ chối), resubmit_required (yêu cầu nộp lại)"
    )
    admin_note: Optional[str] = Field(
        default=None,
        description="Ghi chú phản hồi cho shop (bắt buộc khi từ chối hoặc yêu cầu nộp lại)"
    )


class AdminShopStatusUpdateRequest(BaseModel):
    status: Literal["unverified", "pending_review", "verified", "suspended", "rejected"]
    reason: Optional[str] = Field(default=None, description="Lý do cập nhật trạng thái shop")


class SignContractRequest(BaseModel):
    otp_code: str = Field(..., description="Mã OTP ký số điện tử (E-Signature)")


class WalletDepositRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Số tiền nạp vào ví ký quỹ (VNĐ)")



class ShopListItem(BaseModel):
    id: str
    email: str
    phone: str
    shop_name: str
    platform: str
    shop_url: str
    status: str
    email_verified: bool
    phone_verified: bool
    created_at: datetime
    has_pending_verification: bool = False

    class Config:
        from_attributes = True


class ShopListResponse(BaseModel):
    total: int
    page: int
    limit: int
    shops: List[ShopListItem]


class AdminStatsResponse(BaseModel):
    total_shops: int
    verified_shops: int
    pending_verifications: int
    suspended_shops: int
    rejected_shops: int
    total_products: int
    total_clicks: int
    total_conversions: int

