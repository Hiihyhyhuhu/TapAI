import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from database.models import (
    Shop,
    Product,
    AffiliateProduct,
    Commission,
    Click,
    ClickTracking,
    Conversion,
    ProductStatus,
    ConversionStatus,
    CommissionType,
    utc_now,
)

def hash_ip(ip: Optional[str]) -> Optional[str]:
    """Băm ẩn danh địa chỉ IP của người dùng để tuân thủ bảo vệ quyền riêng tư."""
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()

def anonymize_ip_display(ip: Optional[str]) -> str:
    """Hiển thị IP ẩn danh dạng 113.161.***.***"""
    if not ip:
        return "127.0.***.***"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.***.***"
    return "127.0.***.***"

def record_click(
    db: Session,
    product_id: str,
    user_session_id: Optional[str] = None,
    source_type: str = "video",
    referral_url: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Click:
    """Ghi nhận lượt click 'Mua ngay' từ Extension và sinh link chuyển hướng gắn mã tracking."""
    # 1. Kiểm tra sản phẩm tồn tại
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.status != ProductStatus.DELETED
    ).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sản phẩm không tồn tại hoặc đã bị xóa")

    # 2. Tạo mã click_id duy nhất và đính kèm tham số tracking vào link sàn
    click_id = uuid.uuid4().hex
    clean_url = product.product_url.strip()
    sep = "&" if "?" in clean_url else "?"
    redirect_url = f"{clean_url}{sep}tap_ref={click_id}&sub_id={click_id}"

    # 3. Lưu vào Database
    click = Click(
        id=click_id,
        product_id=product.id,
        shop_id=product.shop_id,
        user_session_id=user_session_id,
        source_type=source_type or "video",
        referral_url=referral_url,
        user_agent=user_agent,
        ip_hash=hash_ip(client_ip),
        redirect_url=redirect_url,
        clicked_at=utc_now()
    )
    db.add(click)
    db.commit()
    db.refresh(click)

    return click

def record_conversion(
    db: Session,
    click_id: Optional[str],
    order_id: str,
    order_value: float,
    status_str: str = "confirmed"
) -> Conversion:
    """
    Ghi nhận đơn hàng thành công qua Webhook/Postback:
    - Đảm bảo tính IDEMPOTENCY: nếu trùng order_id hoặc click_id, cập nhật trạng thái đơn (Upsert), không raise 409.
    - Hỗ trợ ORPHAN ORDER: nếu click_id không tồn tại, vẫn lưu đơn hàng đối soát (shop_id = None), không raise 404.
    """
    clean_order_id = str(order_id).strip()
    now = utc_now()
    is_confirmed = (status_str.lower() in [ConversionStatus.CONFIRMED, "completed"])

    # 1. Idempotency Check: Kiểm tra đơn hàng hoặc lượt click đã tồn tại chưa
    existing_conversion = None
    if click_id:
        existing_conversion = db.query(Conversion).filter(Conversion.click_id == click_id).first()
    if not existing_conversion and clean_order_id:
        existing_conversion = db.query(Conversion).filter(
            or_(Conversion.platform_order_id == clean_order_id, Conversion.order_id == clean_order_id)
        ).first()

    if existing_conversion:
        existing_conversion.order_value = order_value
        existing_conversion.status = ConversionStatus.CONFIRMED if is_confirmed else ConversionStatus.PENDING
        if is_confirmed and not getattr(existing_conversion, "completed_at", None):
            existing_conversion.completed_at = now
        if hasattr(existing_conversion, "updated_at"):
            existing_conversion.updated_at = now
        db.commit()
        db.refresh(existing_conversion)
        return existing_conversion

    # 2. Khớp lượt click (Hỗ trợ Orphan Order nếu click_id không có trong hệ thống)
    click = db.query(Click).filter(Click.id == click_id).first() if click_id else None
    product_id = click.product_id if click else None
    shop_id = click.shop_id if click else None

    # 3. Tính toán hoa hồng dựa trên cấu hình sản phẩm
    commission_earned = 0.0
    if product_id:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and product.commissions:
            comm = product.commissions[0]
            if comm.commission_type == CommissionType.FIXED_AMOUNT:
                commission_earned = float(comm.extra_fixed_amount or 0.0)
            else:
                total_rate = float(comm.platform_rate or 0.0) + float(comm.extra_rate or 0.0)
                commission_earned = round(order_value * (total_rate / 100.0), 2)
        else:
            aff_prod = db.query(AffiliateProduct).filter(AffiliateProduct.id == product_id).first()
            if aff_prod and aff_prod.total_commission_rate:
                commission_earned = round(order_value * (float(aff_prod.total_commission_rate) / 100.0), 2)
            else:
                commission_earned = round(order_value * 0.05, 2)
    else:
        # Orphan Order: Tính hoa hồng tạm tính 5% chờ hậu kiểm
        commission_earned = round(order_value * 0.05, 2)

    # 4. Lưu bản ghi conversion
    conversion = Conversion(
        click_id=click.id if click else click_id,
        product_id=product_id or "orphan_product",
        shop_id=shop_id,
        order_id=clean_order_id,
        order_value=order_value,
        commission_earned=commission_earned,
        status=ConversionStatus.CONFIRMED if is_confirmed else ConversionStatus.PENDING,
        converted_at=now,
        confirmed_at=now if is_confirmed else None
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)

    return conversion

def get_click_detail(db: Session, click_id: str, shop_id: Optional[str] = None) -> Click:
    """Tra cứu thông tin chi tiết của 1 lượt click."""
    query = db.query(Click).filter(Click.id == click_id)
    if shop_id:
        query = query.filter(Click.shop_id == shop_id)
    click = query.first()
    if not click:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lượt click")
    return click


# ==============================================================================
# STAGE 4: ANTI-FRAUD CLICK GATEWAY & REAL-TIME CPC BILLING
# ==============================================================================

def handle_cpc_redirect_gateway(
    db: Session,
    product_id: str,
    ext_uid: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    test_fraud: Optional[str] = None
) -> Dict[str, Any]:
    """
    Xử lý chuyển hướng người dùng từ Extension Sidebar sang trang sản phẩm gian hàng:
    - Kiểm tra bộ lọc Anti-Fraud:
      + Bot User-Agent (cào dữ liệu / tool tự động)
      + Duplicate Click Window (30s) cho cùng sản phẩm và IP / User
      + IP Rate Limit (>10 click / 10s)
    - Nếu INVALID / DUPLICATE: Chuyển hướng ngay, Chi phí = 0 VNĐ.
    - Nếu VALID UNIQUE: Khấu trừ thời gian thực ví ký quỹ của Shop, tự động ngắt feed nếu ví <= 0.
    """
    # 1. Tìm sản phẩm
    prod = db.query(AffiliateProduct).filter(AffiliateProduct.id == product_id).first()
    if not prod:
        prod = db.query(Product).filter(
            Product.id == product_id,
            Product.status != ProductStatus.DELETED
        ).first()

    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sản phẩm không tồn tại hoặc đã bị xóa")

    target_url = getattr(prod, "original_url", None) or getattr(prod, "product_url", None) or "https://shopee.vn"
    cpc_bid = float(getattr(prod, "cpc_bid", 2000.0) or 2000.0)
    shop_id = prod.shop_id
    shop = db.query(Shop).filter(Shop.id == shop_id).first()

    now = utc_now()
    cutoff_30s = now - timedelta(seconds=30)
    cutoff_10s = now - timedelta(seconds=10)

    # 2. Bộ lọc Anti-Fraud Filter
    is_valid_unique = True
    fraud_reason = None

    ua_lower = (user_agent or "").lower()
    bot_signatures = ["bot", "crawl", "spider", "curl", "wget", "python-requests", "headless", "scraper", "postman"]

    if test_fraud == "bot" or any(sig in ua_lower for sig in bot_signatures):
        is_valid_unique = False
        fraud_reason = "BOT_DETECTED"
    elif test_fraud == "duplicate":
        is_valid_unique = False
        fraud_reason = "DUPLICATE_WINDOW"
    else:
        # Kiểm tra trùng lặp trong cửa sổ 30 giây (Duplicate Click Window)
        recent_duplicate = db.query(Click).filter(
            Click.product_id == prod.id,
            Click.clicked_at >= cutoff_30s
        )
        if ext_uid:
            recent_duplicate = recent_duplicate.filter(
                or_(Click.user_session_id == ext_uid, Click.client_ip == client_ip)
            )
        elif client_ip:
            recent_duplicate = recent_duplicate.filter(Click.client_ip == client_ip)

        if recent_duplicate.first():
            is_valid_unique = False
            fraud_reason = "DUPLICATE_WINDOW"
        elif client_ip:
            # Kiểm tra tần suất IP Rate Limit (>10 click / 10s)
            recent_ip_count = db.query(Click).filter(
                Click.client_ip == client_ip,
                Click.clicked_at >= cutoff_10s
            ).count()
            if recent_ip_count >= 10:
                is_valid_unique = False
                fraud_reason = "IP_RATE_LIMIT"

    # 3. Ghi nhận Click & Trừ ví ký quỹ
    click_id = uuid.uuid4().hex
    cpc_deducted = 0.0

    if is_valid_unique:
        cpc_deducted = cpc_bid
        if shop:
            shop.wallet_balance = max(0.0, float(shop.wallet_balance or 0.0) - cpc_bid)
            shop.total_cpc_spent = float(shop.total_cpc_spent or 0.0) + cpc_bid
            if float(shop.wallet_balance) <= 0.0:
                # Ngắt trạng thái sản phẩm do hết ví
                if hasattr(prod, "sync_status"):
                    prod.sync_status = "PAUSED_NO_BUDGET"
                if hasattr(prod, "status"):
                    prod.status = "PAUSED_NO_BUDGET"
        if hasattr(prod, "today_spent"):
            prod.today_spent = float(prod.today_spent or 0.0) + cpc_bid

    # Tạo đường dẫn chuyển hướng có gắn mã tracking đối soát (chuẩn sub_id1 cho Shopee / TikTok)
    sep = "&" if "?" in target_url else "?"
    redirect_url = f"{target_url}{sep}tap_ref={click_id}&sub_id={click_id}&sub_id1={click_id}&cpc_trace=1"

    new_click = Click(
        id=click_id,
        product_id=prod.id,
        shop_id=shop_id,
        user_session_id=ext_uid,
        source_type="EXTENSION_GATEWAY",
        referral_url=f"/r/{prod.id}",
        user_agent=user_agent,
        ip_hash=hash_ip(client_ip),
        client_ip=client_ip,
        redirect_url=redirect_url,
        committed_cpc_at_click=cpc_bid,
        cpc_deducted=cpc_deducted,
        is_valid_unique=is_valid_unique,
        fraud_reason=fraud_reason,
        clicked_at=now
    )
    db.add(new_click)

    new_tracking = ClickTracking(
        click_id=click_id,
        product_id=prod.id,
        shop_id=shop_id,
        ext_user_id=ext_uid,
        source_context="EXTENSION_GATEWAY",
        generated_short_url=redirect_url,
        committed_cpc_at_click=cpc_bid,
        cpc_deducted=cpc_deducted,
        is_valid_unique=is_valid_unique,
        fraud_reason=fraud_reason,
        client_ip=client_ip,
        clicked_at=now
    )
    db.add(new_tracking)

    db.commit()

    return {
        "click_id": click_id,
        "product_id": prod.id,
        "redirect_url": redirect_url,
        "is_valid_unique": is_valid_unique,
        "fraud_reason": fraud_reason,
        "cpc_bid": cpc_bid,
        "cpc_deducted": cpc_deducted,
        "wallet_balance": float(shop.wallet_balance or 0.0) if shop else 0.0
    }


def get_cpc_click_ledger(
    db: Session,
    shop_id: str,
    limit: int = 50
) -> Dict[str, Any]:
    """Lấy danh sách các lượt click đối soát thời gian thực dành cho bảng Click Ledger."""
    clicks = db.query(Click).filter(Click.shop_id == shop_id).order_by(desc(Click.clicked_at)).limit(limit).all()

    items = []
    valid_count = 0
    fraud_count = 0
    total_spent = 0.0

    for c in clicks:
        if c.is_valid_unique:
            valid_count += 1
        else:
            fraud_count += 1
        deducted = float(c.cpc_deducted or 0.0)
        total_spent += deducted

        prod_title = "Sản phẩm"
        if c.product:
            prod_title = getattr(c.product, "title", None) or getattr(c.product, "name", "Sản phẩm")
        else:
            aff = db.query(AffiliateProduct).filter(AffiliateProduct.id == c.product_id).first()
            if aff:
                prod_title = aff.title

        items.append({
            "click_id": c.id,
            "product_id": c.product_id,
            "product_title": prod_title,
            "ext_uid": c.user_session_id or "anonymous_guest",
            "ip_anonymized": anonymize_ip_display(c.client_ip),
            "is_valid_unique": bool(c.is_valid_unique),
            "fraud_reason": c.fraud_reason,
            "committed_cpc": float(c.committed_cpc_at_click or 2000.0),
            "cpc_deducted": deducted,
            "clicked_at": c.clicked_at.isoformat() if c.clicked_at else None
        })

    shop = db.query(Shop).filter(Shop.id == shop_id).first()

    return {
        "total_clicks": len(clicks),
        "valid_clicks": valid_count,
        "fraud_clicks": fraud_count,
        "total_cpc_spent": total_spent,
        "wallet_balance": float(shop.wallet_balance or 0.0) if shop else 0.0,
        "items": items,
        "clicks": items
    }


