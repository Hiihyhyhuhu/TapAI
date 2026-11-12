import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models import (
    AffiliateProduct,
    MerchantShop,
    Merchant,
    Shop,
    SyncStatus,
    PlatformType,
    utc_now,
)
from services.adapters import get_adapter_for_url

def import_product_by_url(
    db: Session,
    shop_id: str,
    product_url: str,
    cpc_bid: float = 2000.0,
    daily_budget: float = 100000.0
) -> AffiliateProduct:
    """
    Luồng 1-Click Import & CPC Bidding (Stage 2):
    Chủ Shop dán Product URL trên Web Portal và thiết lập Committed CPC Bid / Daily Budget.
    Hệ thống tự động:
    1. Nhận diện sàn TMĐT và bóc tách platform_item_id.
    2. Quét thông tin (Tên, Ảnh, Giá) và mức hoa hồng thực tế trên sàn.
    3. Phân loại trạng thái:
       - ELIGIBLE nếu Contract == ACTIVE và Wallet_Balance >= Min_CPC
       - PAUSED_NO_BUDGET nếu Wallet_Balance < Min_CPC
    4. Lưu vào bảng affiliate_products.
    """
    clean_url = product_url.strip()
    adapter = get_adapter_for_url(clean_url)

    # 1. Quét dữ liệu từ sàn
    item_data = adapter.fetch_product_and_commission(clean_url)
    platform = item_data["platform"]
    item_id = item_data["platform_item_id"]

    # 2. Phân loại trạng thái theo Stage 2
    legacy_shop = db.query(Shop).filter(Shop.id == shop_id).first()
    is_contract_active = legacy_shop and legacy_shop.contract_status == "ACTIVE"
    wallet_bal = float(legacy_shop.wallet_balance or 0.0) if legacy_shop else 0.0
    has_wallet_budget = wallet_bal >= float(cpc_bid)

    total_rate = float(item_data["total_commission_rate"])
    if total_rate <= 0.0:
        sync_status = SyncStatus.NO_COMMISSION
        priority_score = 0.0000
    elif is_contract_active and has_wallet_budget:
        sync_status = "ELIGIBLE"
        priority_score = round(float(cpc_bid) / 1000.0 + (total_rate / 100.0), 4)
    elif not has_wallet_budget:
        sync_status = "PAUSED_NO_BUDGET"
        priority_score = 0.0000
    else:
        sync_status = SyncStatus.ACTIVE
        priority_score = round(total_rate / 100.0, 4)

    # 2.5. Đảm bảo tính toàn vẹn Foreign Key cho bảng merchant_shops (PostgreSQL Compliance)
    m_shop = db.query(MerchantShop).filter(MerchantShop.id == shop_id).first()
    if not m_shop:
        legacy_shop = db.query(Shop).filter(Shop.id == shop_id).first()
        m_owner = db.query(Merchant).first()
        if not m_owner:
            m_owner = Merchant(
                email=legacy_shop.email if legacy_shop else "merchant_auto@tapai.vn",
                password_hash="placeholder_pwd",
                business_name=legacy_shop.shop_name if legacy_shop else "Tap AI Merchant"
            )
            db.add(m_owner)
            db.flush()

        raw_plat_shop_id = item_data.get("platform_shop_id") or f"shop_{shop_id[:8]}"
        existing_plat_shop = db.query(MerchantShop).filter(
            MerchantShop.platform == platform,
            MerchantShop.platform_shop_id == raw_plat_shop_id
        ).first()
        if existing_plat_shop and existing_plat_shop.id != shop_id:
            raw_plat_shop_id = f"{raw_plat_shop_id}_{shop_id[:8]}"

        m_shop = MerchantShop(
            id=shop_id,
            merchant_id=m_owner.id,
            platform=platform,
            platform_shop_id=raw_plat_shop_id,
            shop_name=legacy_shop.shop_name if legacy_shop else "Auto Shop",
            shop_url=legacy_shop.shop_url if legacy_shop else clean_url,
            is_verified=True
        )
        db.add(m_shop)
        db.flush()

    # 3. Kiểm tra xem sản phẩm đã có trong cơ sở dữ liệu chưa (Upsert)
    existing = db.query(AffiliateProduct).filter(
        AffiliateProduct.platform == platform,
        AffiliateProduct.platform_item_id == item_id
    ).first()

    now = utc_now()
    if existing:
        existing.shop_id = shop_id
        existing.original_url = clean_url
        existing.title = item_data["title"]
        existing.image_url = item_data["image_url"]
        existing.current_price = item_data["current_price"]
        existing.platform_base_rate = item_data["platform_base_rate"]
        existing.seller_extra_rate = item_data["seller_extra_rate"]
        existing.total_commission_rate = total_rate
        existing.cpc_bid = float(cpc_bid)
        existing.daily_budget = float(daily_budget)
        existing.sync_status = sync_status
        existing.priority_score = priority_score
        existing.last_synced_at = now
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        return existing

    new_prod = AffiliateProduct(
        shop_id=shop_id,
        platform=platform,
        platform_item_id=item_id,
        original_url=clean_url,
        title=item_data["title"],
        image_url=item_data["image_url"],
        current_price=item_data["current_price"],
        platform_base_rate=item_data["platform_base_rate"],
        seller_extra_rate=item_data["seller_extra_rate"],
        total_commission_rate=total_rate,
        cpc_bid=float(cpc_bid),
        daily_budget=float(daily_budget),
        today_spent=0.0,
        sync_status=sync_status,
        priority_score=priority_score,
        last_synced_at=now,
        created_at=now,
        updated_at=now
    )
    db.add(new_prod)
    db.commit()
    db.refresh(new_prod)
    return new_prod


def sync_product_now(db: Session, product_id: str) -> AffiliateProduct:
    """
    Nút 'Làm mới mức hoa hồng' (Sync Now) trên Web Portal:
    Khi Shop vừa vào Kênh Người Bán Shopee/TikTok chỉnh tăng % hoa hồng,
    Shop bấm nút này để hệ thống quét lại ngay lập tức và nâng thứ hạng.
    """
    product = db.query(AffiliateProduct).filter(AffiliateProduct.id == product_id).first()
    if not product:
        legacy = db.query(Shop).join(Product, Product.shop_id == Shop.id).filter(Product.id == product_id).first()
        legacy_prod = db.query(Product).filter(Product.id == product_id).first()
        if legacy_prod:
            return import_product_by_url(db=db, shop_id=legacy_prod.shop_id, product_url=legacy_prod.product_url)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy sản phẩm"
        )

    adapter = get_adapter_for_url(product.original_url)
    item_data = adapter.fetch_product_and_commission(
        product.original_url,
        platform_item_id=product.platform_item_id
    )

    total_rate = float(item_data["total_commission_rate"])
    now = utc_now()

    product.title = item_data["title"]
    product.current_price = item_data["current_price"]
    product.platform_base_rate = item_data["platform_base_rate"]
    product.seller_extra_rate = item_data["seller_extra_rate"]
    product.total_commission_rate = total_rate

    # Kiểm tra điều kiện Stage 2 (Hợp đồng & Ví ký quỹ)
    shop = db.query(Shop).filter(Shop.id == product.shop_id).first()
    is_contract_active = shop and shop.contract_status == "ACTIVE"
    wallet_bal = float(shop.wallet_balance or 0.0) if shop else 0.0
    cpc_bid = float(getattr(product, "cpc_bid", 2000.0) or 2000.0)
    has_wallet_budget = wallet_bal >= cpc_bid

    if total_rate <= 0.0:
        product.sync_status = SyncStatus.NO_COMMISSION
        product.priority_score = 0.0000
    elif is_contract_active and has_wallet_budget:
        product.sync_status = "ELIGIBLE"
        product.priority_score = round(cpc_bid / 1000.0 + (total_rate / 100.0), 4)
    elif not has_wallet_budget:
        product.sync_status = "PAUSED_NO_BUDGET"
        product.priority_score = 0.0000
    else:
        product.sync_status = SyncStatus.ACTIVE
        product.priority_score = round(total_rate / 100.0, 4)

    product.last_synced_at = now
    product.updated_at = now

    db.commit()
    db.refresh(product)
    return product


def sync_all_active_products(db: Session) -> Dict[str, Any]:
    """
    Cronjob tự động chạy mỗi 6 giờ:
    Quét lại toàn bộ các sản phẩm để phát hiện kịp thời các thay đổi % hoa hồng
    mà Shop đã chỉnh trên sàn TMĐT.
    """
    products = db.query(AffiliateProduct).all()
    updated_count = 0
    active_count = 0
    no_comm_count = 0

    for prod in products:
        try:
            adapter = get_adapter_for_url(prod.original_url)
            data = adapter.fetch_product_and_commission(
                prod.original_url,
                platform_item_id=prod.platform_item_id
            )
            total = float(data["total_commission_rate"])
            prod.platform_base_rate = data["platform_base_rate"]
            prod.seller_extra_rate = data["seller_extra_rate"]
            prod.total_commission_rate = total
            prod.last_synced_at = utc_now()

            # Kiểm tra điều kiện Stage 2 (Hợp đồng & Ví ký quỹ)
            shop = db.query(Shop).filter(Shop.id == prod.shop_id).first()
            is_contract_active = shop and shop.contract_status == "ACTIVE"
            wallet_bal = float(shop.wallet_balance or 0.0) if shop else 0.0
            cpc_bid = float(getattr(prod, "cpc_bid", 2000.0) or 2000.0)
            has_wallet_budget = wallet_bal >= cpc_bid

            if total <= 0.0:
                prod.sync_status = SyncStatus.NO_COMMISSION
                prod.priority_score = 0.0
                no_comm_count += 1
            elif is_contract_active and has_wallet_budget:
                prod.sync_status = "ELIGIBLE"
                prod.priority_score = round(cpc_bid / 1000.0 + (total / 100.0), 4)
                active_count += 1
            elif not has_wallet_budget:
                prod.sync_status = "PAUSED_NO_BUDGET"
                prod.priority_score = 0.0
                no_comm_count += 1
            else:
                prod.sync_status = SyncStatus.ACTIVE
                prod.priority_score = round(total / 100.0, 4)
                active_count += 1

            updated_count += 1
        except Exception as e:
            print(f"⚠️ Lỗi quét hoa hồng cho sản phẩm {prod.id}: {e}")

    db.commit()
    return {
        "total_scanned": updated_count,
        "active_with_commission": active_count,
        "no_commission": no_comm_count,
        "timestamp": utc_now().isoformat()
    }

