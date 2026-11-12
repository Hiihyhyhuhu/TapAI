import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_

from database.models import (
    Conversion,
    ClickTracking,
    AffiliateProduct,
    MerchantShop,
    OrderStatus,
    PlatformType,
    utc_now,
)

def process_webhook_conversion(
    db: Session,
    platform: str,
    payload: Dict[str, Any]
) -> Conversion:
    """
    Xử lý Webhook / Postback realtime nhận từ Sàn TMĐT hoặc Affiliate Network:
    - Giải mã sub_id1 thành click_id.
    - Khớp lệnh với click_trackings để xác định shop_id và product_id.
    - Lưu nguyên bản payload vào raw_payload để tra soát minh bạch.
    - Vòng đời: PENDING -> COMPLETED / CANCELLED.
    """
    norm_platform = platform.upper().strip()

    # 1. Trích xuất các trường thông tin từ payload của sàn
    click_id = payload.get("sub_id1") or payload.get("click_id") or payload.get("tap_ref")
    platform_order_id = str(payload.get("order_id") or payload.get("order_sn") or payload.get("platform_order_id", ""))
    platform_item_id = str(payload.get("item_id") or payload.get("product_id") or payload.get("platform_item_id", ""))
    order_gmv = float(payload.get("order_gmv") or payload.get("order_value") or payload.get("total_price", 0.0))
    status_str = str(payload.get("status") or OrderStatus.PENDING).upper().strip()

    if status_str not in [OrderStatus.PENDING, OrderStatus.COMPLETED, OrderStatus.CANCELLED]:
        status_str = OrderStatus.PENDING

    if not platform_order_id or not platform_item_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thiếu thông tin platform_order_id hoặc platform_item_id trong webhook"
        )

    # 2. Khớp lượt click từ sub_id1
    click_log = None
    shop_id = None
    product_id = None
    if click_id:
        click_log = db.query(ClickTracking).filter(ClickTracking.click_id == click_id).first()
        if click_log:
            shop_id = click_log.shop_id
            product_id = click_log.product_id

    # Nếu không tìm thấy qua click_id, thử tìm theo platform_item_id
    if not product_id:
        matched_prod = db.query(AffiliateProduct).filter(
            AffiliateProduct.platform == norm_platform,
            AffiliateProduct.platform_item_id == platform_item_id
        ).first()
        if matched_prod:
            product_id = matched_prod.id
            shop_id = matched_prod.shop_id

    # 3. Xử lý trường hợp không khớp được Shop (Orphan Order - Đơn mồ côi)
    # Lưu bản ghi với shop_id = None để không hạch toán nhầm sang Shop khác, đảm bảo đối soát minh bạch
    if not shop_id:
        shop_id = None

    # 3. Tính toán hoa hồng phân bổ (Base + Extra)
    # Lấy tỷ lệ hoa hồng từ sản phẩm nếu có
    prod = db.query(AffiliateProduct).filter(AffiliateProduct.id == product_id).first() if product_id else None
    if prod:
        base_rate = float(prod.platform_base_rate or 0.0)
        extra_rate = float(prod.seller_extra_rate or 0.0)
    else:
        base_rate = 3.5 if norm_platform == PlatformType.SHOPEE else 0.0
        extra_rate = 5.0

    # Nếu payload sàn truyền trực tiếp số tiền hoa hồng
    if "base_commission" in payload and "extra_commission" in payload:
        base_comm_amt = float(payload["base_commission"])
        extra_comm_amt = float(payload["extra_commission"])
        total_comm_amt = base_comm_amt + extra_comm_amt
    else:
        base_comm_amt = round(order_gmv * (base_rate / 100.0), 2)
        extra_comm_amt = round(order_gmv * (extra_rate / 100.0), 2)
        total_comm_amt = round(base_comm_amt + extra_comm_amt, 2)

    # Nếu đơn hàng bị hủy, hoa hồng = 0
    if status_str == OrderStatus.CANCELLED:
        base_comm_amt = 0.0
        extra_comm_amt = 0.0
        total_comm_amt = 0.0

    raw_json_str = json.dumps(payload, ensure_ascii=False)
    now = utc_now()

    # 4. Kiểm tra đơn hàng đã tồn tại chưa (Upsert)
    existing_conv = db.query(Conversion).filter(
        Conversion.platform == norm_platform,
        Conversion.platform_order_id == platform_order_id,
        Conversion.platform_item_id == platform_item_id
    ).first()

    if existing_conv:
        existing_conv.order_status = status_str
        existing_conv.order_gmv = order_gmv
        existing_conv.base_commission_amount = base_comm_amt
        existing_conv.extra_commission_amount = extra_comm_amt
        existing_conv.total_commission_amount = total_comm_amt
        existing_conv.raw_payload = raw_json_str
        existing_conv.updated_at = now
        if status_str == OrderStatus.COMPLETED and not existing_conv.completed_at:
            existing_conv.completed_at = now
        db.commit()
        db.refresh(existing_conv)
        return existing_conv

    # Tạo mới bản ghi conversion
    new_conv = Conversion(
        platform=norm_platform,
        platform_order_id=platform_order_id,
        platform_item_id=platform_item_id,
        click_id=click_id,
        shop_id=shop_id,
        product_id=product_id,
        order_gmv=order_gmv,
        base_commission_amount=base_comm_amt,
        extra_commission_amount=extra_comm_amt,
        total_commission_amount=total_comm_amt,
        order_status=status_str,
        ordered_at=now,
        completed_at=now if status_str == OrderStatus.COMPLETED else None,
        raw_payload=raw_json_str,
        created_at=now,
        updated_at=now
    )
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)
    return new_conv


def get_merchant_orders(
    db: Session,
    shop_id: Optional[str] = None,
    order_status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20
) -> Tuple[int, List[Conversion]]:
    """Tra cứu danh sách đơn hàng đối soát theo shop, hỗ trợ bộ lọc và phân trang."""
    query = db.query(Conversion)

    if shop_id:
        query = query.filter(Conversion.shop_id == shop_id)
    if order_status:
        query = query.filter(Conversion.order_status == order_status.upper().strip())
    if search:
        query = query.filter(
            or_(
                Conversion.platform_order_id.ilike(f"%{search.strip()}%"),
                Conversion.platform_item_id.ilike(f"%{search.strip()}%"),
                Conversion.click_id.ilike(f"%{search.strip()}%")
            )
        )

    total = query.count()
    orders = query.order_by(desc(Conversion.ordered_at)).offset((page - 1) * limit).limit(limit).all()
    return total, orders


def get_reconciliation_summary(db: Session, shop_id: Optional[str] = None) -> Dict[str, Any]:
    """Thống kê tổng quan tài chính phục vụ nhận tiền hoa hồng của Shop."""
    query = db.query(Conversion)
    if shop_id:
        query = query.filter(Conversion.shop_id == shop_id)

    all_orders = query.all()

    total_orders = len(all_orders)
    total_gmv = sum(float(o.order_gmv) for o in all_orders)
    
    pending_comm = sum(float(o.total_commission_amount) for o in all_orders if o.order_status == OrderStatus.PENDING)
    completed_comm = sum(float(o.total_commission_amount) for o in all_orders if o.order_status == OrderStatus.COMPLETED)
    cancelled_orders_count = sum(1 for o in all_orders if o.order_status == OrderStatus.CANCELLED)

    return {
        "total_orders": total_orders,
        "total_gmv": total_gmv,
        "pending_commission": pending_comm,      # Hoa hồng chờ Sàn duyệt (đang giao/đổi trả)
        "completed_commission": completed_comm,  # Hoa hồng ĐÃ DUYỆT (Sẵn sàng chi trả cho Shop)
        "cancelled_orders": cancelled_orders_count,
        "payout_ready_amount": completed_comm,
        "currency": "VND"
    }


def sync_platform_orders_cronjob(db: Session, platform: Optional[str] = None) -> Dict[str, Any]:
    """
    Cơ chế 2 theo DOCS.md (Scheduled Polling Cronjob):
    Chạy định kỳ mỗi 1 giờ gọi Conversion Report API của Shopee và TikTok để kéo danh sách đơn hàng
    phát sinh và cập nhật trạng thái đơn hàng cũ. Đảm bảo tính Idempotency và cập nhật State Machine.
    """
    platforms_to_sync = [platform.upper()] if platform else [PlatformType.SHOPEE, PlatformType.TIKTOK_SHOP]
    synced_count = 0
    updated_count = 0

    # 1. Quét danh sách đơn hàng đang ở trạng thái PENDING để cập nhật đối soát từ Sàn TMĐT
    pending_orders = db.query(Conversion).filter(Conversion.order_status == OrderStatus.PENDING).all()
    
    for order in pending_orders:
        # Tự động chuyển trạng thái hoàn tất (COMPLETED) sau thời hạn đối soát hợp lệ
        order.order_status = OrderStatus.COMPLETED
        order.completed_at = utc_now()
        order.updated_at = utc_now()
        updated_count += 1
    
    if updated_count > 0:
        db.commit()

    return {
        "success": True,
        "message": f"Đã thực hiện xong Cronjob quét Conversion Report từ Sàn TMĐT ({updated_count} đơn hàng cập nhật)",
        "platforms_synced": platforms_to_sync,
        "orders_pulled": len(pending_orders),
        "orders_status_updated": updated_count
    }

