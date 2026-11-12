from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

class ClickRecordRequest(BaseModel):
    product_id: str = Field(description="Mã ID của sản phẩm được click")
    user_session_id: Optional[str] = Field(default=None, description="Mã phiên ẩn danh của người dùng trên Extension")
    source_type: Optional[str] = Field(default="video", description="Nguồn click: 'video' hoặc 'image'")
    referral_url: Optional[str] = Field(default=None, description="URL trang web người dùng đang xem khi click")


class ClickRecordResponse(BaseModel):
    click_id: str
    product_id: str
    shop_id: str
    redirect_url: str
    clicked_at: datetime


class ConversionRecordRequest(BaseModel):
    click_id: str = Field(description="Mã tracking click_id được đính kèm trong link affiliate")
    order_id: str = Field(description="Mã đơn hàng từ sàn TMĐT (Shopee/Lazada...)")
    order_value: float = Field(gt=0, description="Tổng giá trị đơn hàng (VND)")
    status: Optional[Literal["pending", "confirmed"]] = Field(
        default="confirmed",
        description="Trạng thái ban đầu: pending (chờ đối soát) hoặc confirmed (thành công)"
    )


class ConversionResponse(BaseModel):
    id: str
    click_id: str
    product_id: str
    shop_id: str
    order_id: str
    order_value: float
    commission_earned: float
    status: str
    converted_at: datetime
    confirmed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReportOverviewResponse(BaseModel):
    shop_id: str
    shop_name: str
    total_products: int
    total_clicks: int
    total_conversions: int
    total_order_value: float
    total_commission_earned: float
    pending_commission: float
    confirmed_commission: float
    conversion_rate_percent: float


class DailyMetricItem(BaseModel):
    date: str
    clicks: int
    conversions: int
    order_value: float
    commission_earned: float


class DailyReportResponse(BaseModel):
    shop_id: str
    start_date: str
    end_date: str
    daily_metrics: List[DailyMetricItem]
    dates: List[str] = Field(default_factory=list, description="Danh sách các ngày thống kê")
    clicks: List[int] = Field(default_factory=list, description="Danh sách số lượt click tương ứng mỗi ngày")
    conversions: List[int] = Field(default_factory=list, description="Danh sách số đơn hàng tương ứng mỗi ngày")


class ProductPerformanceItem(BaseModel):
    product_id: str
    product_name: str
    price: float
    platform: str
    clicks: int
    conversions: int
    order_value: float
    commission_earned: float
    conversion_rate_percent: float


class ProductReportResponse(BaseModel):
    shop_id: str
    total_products: int
    products: List[ProductPerformanceItem]

