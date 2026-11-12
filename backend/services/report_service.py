from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models import (
    Shop,
    Product,
    Click,
    Conversion,
    AffiliateProduct,
    ClickTracking,
    SyncStatus,
    ProductStatus,
    ConversionStatus,
    OrderStatus,
    utc_now,
)
from models.tracking_schemas import (
    ReportOverviewResponse,
    DailyMetricItem,
    DailyReportResponse,
    ProductPerformanceItem,
    ProductReportResponse,
)

def get_shop_overview(db: Session, shop: Shop) -> ReportOverviewResponse:
    """Tổng hợp toàn bộ chỉ số KPI quan trọng cho trang Dashboard của Shop."""
    # 1. Tổng số sản phẩm đang hoạt động (kết hợp affiliate_products và products cũ)
    aff_prod_count = db.query(AffiliateProduct).filter(
        AffiliateProduct.shop_id == shop.id
    ).count()
    legacy_prod_count = db.query(Product).filter(
        Product.shop_id == shop.id,
        Product.status != ProductStatus.DELETED
    ).count()
    total_products = aff_prod_count + legacy_prod_count

    # 2. Tổng số lượt click "Mua ngay" (kết hợp click_trackings mới và clicks cũ)
    aff_clicks = db.query(ClickTracking).filter(ClickTracking.shop_id == shop.id).count()
    legacy_clicks = db.query(Click).filter(Click.shop_id == shop.id).count()
    total_clicks = aff_clicks + legacy_clicks

    # 3. Tổng hợp chuyển đổi đơn hàng
    conversions = db.query(Conversion).filter(Conversion.shop_id == shop.id).all()
    total_conversions = len(conversions)
    total_order_value = sum(float(c.order_value) for c in conversions)
    total_commission = sum(float(c.commission_earned) for c in conversions)
    pending_comm = sum(float(c.commission_earned) for c in conversions if c.status in [ConversionStatus.PENDING, OrderStatus.PENDING])
    confirmed_comm = sum(float(c.commission_earned) for c in conversions if c.status in [ConversionStatus.CONFIRMED, OrderStatus.COMPLETED])

    # 4. Tỷ lệ chuyển đổi (Conversion Rate)
    cvr = round((total_conversions / total_clicks * 100), 2) if total_clicks > 0 else 0.0

    return ReportOverviewResponse(
        shop_id=shop.id,
        shop_name=shop.shop_name,
        total_products=total_products,
        total_clicks=total_clicks,
        total_conversions=total_conversions,
        total_order_value=round(total_order_value, 2),
        total_commission_earned=round(total_commission, 2),
        pending_commission=round(pending_comm, 2),
        confirmed_commission=round(confirmed_comm, 2),
        conversion_rate_percent=cvr
    )

def get_shop_daily_metrics(db: Session, shop: Shop, days: int = 7) -> DailyReportResponse:
    """Thống kê chi tiết theo từng ngày phục vụ vẽ biểu đồ Clicks, Đơn hàng và Hoa hồng."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days - 1)

    # Khởi tạo bản đồ ngày mặc định
    daily_map: Dict[str, Dict[str, Any]] = {}
    for i in range(days):
        d_str = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        daily_map[d_str] = {
            "clicks": 0,
            "conversions": 0,
            "order_value": 0.0,
            "commission_earned": 0.0
        }

    # 1. Gom nhóm Clicks (từ cả click_trackings mới và clicks cũ)
    aff_clicks = db.query(ClickTracking).filter(
        ClickTracking.shop_id == shop.id,
        ClickTracking.clicked_at >= start_date
    ).all()
    for c in aff_clicks:
        if c.clicked_at:
            d = c.clicked_at.strftime("%Y-%m-%d")
            if d in daily_map:
                daily_map[d]["clicks"] += 1

    legacy_clicks = db.query(Click).filter(
        Click.shop_id == shop.id,
        Click.clicked_at >= start_date
    ).all()
    for c in legacy_clicks:
        if c.clicked_at:
            d = c.clicked_at.strftime("%Y-%m-%d")
            if d in daily_map:
                daily_map[d]["clicks"] += 1

    # 2. Gom nhóm Conversions
    conversions = db.query(Conversion).filter(
        Conversion.shop_id == shop.id,
        Conversion.converted_at >= start_date
    ).all()
    for conv in conversions:
        if conv.converted_at:
            d = conv.converted_at.strftime("%Y-%m-%d")
            if d in daily_map:
                daily_map[d]["conversions"] += 1
                daily_map[d]["order_value"] += float(conv.order_value)
                daily_map[d]["commission_earned"] += float(conv.commission_earned)

    items = [
        DailyMetricItem(
            date=d,
            clicks=vals["clicks"],
            conversions=vals["conversions"],
            order_value=round(vals["order_value"], 2),
            commission_earned=round(vals["commission_earned"], 2)
        )
        for d, vals in sorted(daily_map.items())
    ]

    return DailyReportResponse(
        shop_id=shop.id,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=now.strftime("%Y-%m-%d"),
        daily_metrics=items,
        dates=[m.date for m in items],
        clicks=[m.clicks for m in items],
        conversions=[m.conversions for m in items]
    )

def get_shop_product_performance(db: Session, shop: Shop) -> ProductReportResponse:
    """Xếp hạng hiệu quả kinh doanh của từng sản phẩm (Doanh số & Hoa hồng tạo ra)."""
    # Lấy cả affiliate_products và products legacy
    aff_products = db.query(AffiliateProduct).filter(
        AffiliateProduct.shop_id == shop.id
    ).all()
    legacy_products = db.query(Product).filter(
        Product.shop_id == shop.id,
        Product.status != ProductStatus.DELETED
    ).all()

    performance_list: List[ProductPerformanceItem] = []

    # 1. Duyệt affiliate_products
    for ap in aff_products:
        clicks_count = db.query(ClickTracking).filter(ClickTracking.product_id == ap.id).count()
        convs = db.query(Conversion).filter(Conversion.product_id == ap.id).all()
        total_orders = len(convs)
        total_gmv = sum(float(c.order_value) for c in convs)
        total_comm = sum(float(c.commission_earned) for c in convs)
        cvr = round((total_orders / clicks_count * 100), 2) if clicks_count > 0 else 0.0

        performance_list.append(
            ProductPerformanceItem(
                product_id=ap.id,
                product_name=ap.title,
                price=float(ap.current_price),
                platform=ap.platform,
                clicks=clicks_count,
                conversions=total_orders,
                order_value=round(total_gmv, 2),
                commission_earned=round(total_comm, 2),
                conversion_rate_percent=cvr
            )
        )

    # 2. Duyệt legacy products
    for p in legacy_products:
        clicks_count = db.query(Click).filter(Click.product_id == p.id).count()
        convs = db.query(Conversion).filter(Conversion.product_id == p.id).all()
        total_orders = len(convs)
        total_gmv = sum(float(c.order_value) for c in convs)
        total_comm = sum(float(c.commission_earned) for c in convs)
        cvr = round((total_orders / clicks_count * 100), 2) if clicks_count > 0 else 0.0

        performance_list.append(
            ProductPerformanceItem(
                product_id=p.id,
                product_name=p.name,
                price=float(p.price),
                platform=p.platform,
                clicks=clicks_count,
                conversions=total_orders,
                order_value=round(total_gmv, 2),
                commission_earned=round(total_comm, 2),
                conversion_rate_percent=cvr
            )
        )

    # Sắp xếp sản phẩm theo hoa hồng tạo ra giảm dần
    performance_list.sort(key=lambda x: x.commission_earned, reverse=True)

    return ProductReportResponse(
        shop_id=shop.id,
        total_products=len(performance_list),
        products=performance_list
    )

