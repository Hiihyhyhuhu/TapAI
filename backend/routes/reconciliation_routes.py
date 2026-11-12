from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import MerchantShop, Conversion, OrderStatus
from services.reconciliation_service import (
    process_webhook_conversion,
    get_merchant_orders,
    get_reconciliation_summary,
    sync_platform_orders_cronjob,
)
from middleware.auth_middleware import get_current_shop

router = APIRouter(prefix="/api/v1/reconciliation", tags=["Reconciliation Engine (Đối soát & Nhận tiền)"])

@router.post(
    "/webhook/{platform}",
    status_code=status.HTTP_200_OK,
    summary="Webhook nhận dữ liệu đơn hàng đối soát tự động từ Sàn TMĐT / Affiliate Network"
)
async def platform_webhook(
    platform: str,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload phải là JSON hợp lệ")

    conversion = process_webhook_conversion(db=db, platform=platform, payload=payload)
    return {
        "success": True,
        "message": f"Ghi nhận đối soát đơn hàng '{conversion.platform_order_id}' thành công",
        "conversion_id": conversion.id,
        "order_status": conversion.order_status,
        "total_commission": float(conversion.total_commission_amount)
    }


@router.get(
    "/orders",
    summary="Bảng kê chi tiết đơn hàng đối soát dành cho Merchant Portal"
)
def list_orders(
    order_status: Optional[str] = Query(None, description="Lọc theo trạng thái: PENDING | COMPLETED | CANCELLED"),
    search: Optional[str] = Query(None, description="Tìm theo mã đơn, item_id, hoặc sub_id1/click_id"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    total, orders = get_merchant_orders(
        db=db,
        shop_id=current_shop.id,
        order_status=order_status,
        search=search,
        page=page,
        limit=limit
    )

    items = []
    for o in orders:
        product_title = o.product.title if o.product else f"Sản phẩm #{o.platform_item_id}"
        items.append({
            "id": o.id,
            "platform": o.platform,
            "platform_order_id": o.platform_order_id,
            "platform_item_id": o.platform_item_id,
            "product_title": product_title,
            "click_id": o.click_id,
            "order_gmv": float(o.order_gmv),
            "base_commission_amount": float(o.base_commission_amount),
            "extra_commission_amount": float(o.extra_commission_amount),
            "total_commission_amount": float(o.total_commission_amount),
            "order_status": o.order_status,
            "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None,
            "completed_at": o.completed_at.isoformat() if o.completed_at else None,
        })

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "orders": items
    }


@router.get(
    "/summary",
    summary="Thống kê tổng quan số tiền hoa hồng thực nhận của Shop"
)
def get_summary(
    current_shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    return get_reconciliation_summary(db=db, shop_id=current_shop.id)


@router.post(
    "/sync-orders",
    summary="Cronjob định kỳ kéo Conversion Report từ Sàn TMĐT về đối soát (mỗi 1 giờ)"
)
def trigger_sync_orders(
    platform: Optional[str] = Query(None, description="SHOPEE | TIKTOK_SHOP"),
    db: Session = Depends(get_db)
):
    return sync_platform_orders_cronjob(db=db, platform=platform)

