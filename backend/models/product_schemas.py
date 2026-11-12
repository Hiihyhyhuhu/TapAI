import json
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator
from urllib.parse import urlparse

class CommissionInput(BaseModel):
    commission_type: Literal["percentage", "fixed_amount"] = Field(
        default="percentage",
        description="'percentage' (theo %) hoặc 'fixed_amount' (số tiền cố định VND / đơn)"
    )
    extra_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Hoa hồng Xtra (%) do Shop tự nguyện thiết lập để ưu tiên hiển thị"
    )
    extra_fixed_amount: float = Field(
        default=0.0,
        ge=0.0,
        description="Số tiền hoa hồng cố định (VND) cho mỗi đơn hàng thành công"
    )


class ProductImportRequest(BaseModel):
    product_url: str = Field(description="Đường link sản phẩm trên sàn Shopee hoặc TikTok Shop để tự động cào hoa hồng")
    cpc_bid: Optional[float] = Field(default=2000.0, ge=500.0, description="Giá thầu CPC cam kết (VNĐ)")
    daily_budget: Optional[float] = Field(default=100000.0, ge=10000.0, description="Ngân sách ngày (VNĐ)")

    @field_validator("product_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean = v.strip()
        if not (clean.startswith("http://") or clean.startswith("https://")):
            raise ValueError("Đường dẫn sản phẩm phải bắt đầu bằng http:// hoặc https://")
        return clean


class ProductCreateRequest(BaseModel):
    name: Optional[str] = Field(default=None, description="Tên sản phẩm chuẩn tiêu đề sàn TMĐT")
    category: Optional[str] = Field(default=None, description="Danh mục sản phẩm")
    product_url: str = Field(description="Đường link dẫn thẳng đến trang mua hàng trên sàn TMĐT")
    platform: Optional[str] = Field(default=None, description="shopee | tiktok_shop")
    image_urls: Optional[List[str]] = Field(default=None, description="Danh sách URL ảnh sản phẩm")
    description: Optional[str] = Field(default=None, description="Mô tả tóm tắt đặc điểm sản phẩm")
    price: Optional[float] = Field(default=None, gt=0, description="Giá bán hiện tại của sản phẩm (VND)")
    commission: Optional[CommissionInput] = Field(default=None, description="Thiết lập mức hoa hồng (Tự động đồng bộ từ Sàn nếu để trống)")

    @field_validator("product_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean = v.strip()
        if not (clean.startswith("http://") or clean.startswith("https://")):
            raise ValueError("Đường dẫn sản phẩm phải bắt đầu bằng http:// hoặc https://")
        return clean

    @field_validator("image_urls")
    @classmethod
    def validate_images(cls, urls: List[str]) -> List[str]:
        if not urls:
            raise ValueError("Cần cung cấp ít nhất 1 ảnh sản phẩm")
        for u in urls:
            if not (u.startswith("http://") or u.startswith("https://") or u.startswith("/uploads/")):
                raise ValueError(f"URL ảnh '{u}' không hợp lệ")
        return urls


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=255)
    category: Optional[str] = Field(default=None, min_length=2, max_length=128)
    product_url: Optional[str] = None
    image_urls: Optional[List[str]] = None
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, gt=0)


class CommissionUpdateRequest(BaseModel):
    commission_type: Literal["percentage", "fixed_amount"] = "percentage"
    extra_rate: float = Field(ge=0.0, le=100.0, description="Mức hoa hồng % mới")
    extra_fixed_amount: float = Field(default=0.0, ge=0.0, description="Mức hoa hồng VND cố định mới")


class ProductStatusUpdateRequest(BaseModel):
    status: Literal["active", "paused"] = Field(description="'active' (bật hiển thị) hoặc 'paused' (tạm ẩn)")


class CpcBiddingUpdateRequest(BaseModel):
    cpc_bid: Optional[float] = Field(default=None, ge=500.0, description="Giá thầu CPC cam kết (VNĐ)")
    daily_budget: Optional[float] = Field(default=None, ge=10000.0, description="Ngân sách ngày tối đa (VNĐ)")



class CommissionResponse(BaseModel):
    id: str
    platform: str
    commission_type: str
    platform_rate: float
    extra_rate: float
    extra_fixed_amount: float
    total_rate: float
    min_rate: float

    class Config:
        from_attributes = True


class ProductDetailResponse(BaseModel):
    id: str
    shop_id: str
    shop_name: str
    name: str
    category: str
    product_url: str
    platform: str
    image_urls: List[str]
    thumbnail_url: str
    description: Optional[str] = None
    price: float
    currency: str
    status: str
    commission: Optional[CommissionResponse] = None
    platform_base_rate: float = 0.0
    seller_extra_rate: float = 0.0
    total_commission_rate: float = 0.0
    cpc_bid: float = 2000.0
    daily_budget: float = 100000.0
    today_spent: float = 0.0
    sync_status: str = "ACTIVE"
    export_file_name: Optional[str] = None
    export_download_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AutoSyncProductResponse(BaseModel):
    id: str
    shop_id: str
    platform: str
    platform_item_id: str
    title: str
    original_url: str
    image_url: Optional[str] = None
    current_price: float
    platform_base_rate: float
    seller_extra_rate: float
    total_commission_rate: float
    cpc_bid: float = 2000.0
    daily_budget: float = 100000.0
    today_spent: float = 0.0
    sync_status: str
    priority_score: float
    last_synced_at: datetime


class ProductListResponse(BaseModel):
    total: int
    page: int
    limit: int
    products: List[ProductDetailResponse]

