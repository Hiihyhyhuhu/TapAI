from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Shop
from models.tracking_schemas import (
    ReportOverviewResponse,
    DailyReportResponse,
    ProductReportResponse,
)
from services.report_service import (
    get_shop_overview,
    get_shop_daily_metrics,
    get_shop_product_performance,
)
from middleware.auth_middleware import get_current_verified_shop

router = APIRouter(prefix="/api/v1/reports", tags=["Reports & Analytics (Shop Dashboard)"])

@router.get(
    "/overview",
    response_model=ReportOverviewResponse,
    summary="Báo cáo tổng quan số liệu kinh doanh của shop (Clicks, Đơn hàng, GMV, Hoa hồng, CVR)"
)
def get_overview_report(
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    return get_shop_overview(db=db, shop=current_shop)


@router.get(
    "/daily",
    response_model=DailyReportResponse,
    summary="Biểu đồ biến động clicks, đơn hàng và hoa hồng theo từng ngày"
)
def get_daily_report(
    days: int = Query(7, ge=1, le=90, description="Khoảng thời gian thống kê (mặc định 7 ngày gần nhất, tối đa 90 ngày)"),
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    d = days if isinstance(days, int) else 7
    return get_shop_daily_metrics(db=db, shop=current_shop, days=d)


@router.get(
    "/products",
    response_model=ProductReportResponse,
    summary="Bảng thống kê hiệu quả kinh tế và tỷ lệ chuyển đổi của từng sản phẩm"
)
def get_products_report(
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    return get_shop_product_performance(db=db, shop=current_shop)

