import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models import (
    AffiliateProduct,
    MerchantShop,
    ClickTracking,
    SyncStatus,
    utc_now,
)
from services.adapters import get_adapter_for_url

# Bộ đệm Caching In-Memory cho Shortlinks: (item_id, ext_user_id, time_bucket_1h) -> short_url
_SHORTLINK_CACHE: Dict[str, Tuple[str, float]] = {}
CACHE_TTL_SECONDS = 3600  # 1 giờ (time_bucket_1h)

def _get_cache_key(item_id: str, ext_user_id: Optional[str]) -> str:
    user_part = ext_user_id or "anonymous"
    # Gom nhóm theo khoảng thời gian 1 giờ (time bucket)
    time_bucket = int(time.time() // CACHE_TTL_SECONDS)
    return f"{item_id}:{user_part}:{time_bucket}"

def wrap_affiliate_link(
    db: Session,
    product_id: str,
    ext_user_id: Optional[str] = None,
    source_platform: str = "FB_REELS"
) -> Dict[str, Any]:
    """
    Phân hệ Bọc Link Động & Định danh Lượt Click (Dynamic Link Wrapper & Sub-ID Generator):
    - sub_id1: click_id (UUID duy nhất của lượt click).
    - sub_id2: merchant_id (ID của Shop trong hệ thống).
    - sub_id3: ext_user_id (ID ẩn danh của người dùng Extension).
    - sub_id4: source_platform (FB_REELS, FB_FEED, TIKTOK_VIDEO...).
    - Lưu vào bảng click_trackings.
    - Tối ưu Caching theo (item_id, ext_user_id, time_bucket_1h).
    """
    # 1. Tìm sản phẩm trong hệ thống
    product = db.query(AffiliateProduct).filter(AffiliateProduct.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy sản phẩm"
        )

    shop = product.shop
    merchant_id = shop.merchant_id if shop else "unknown_merchant"
    shop_id = shop.id if shop else "unknown_shop"

    # 2. Sinh click_id duy nhất
    click_id = uuid.uuid4().hex

    # 3. Sinh link qua Adapter của sàn tương ứng với sub_id1 luôn gắn với click_id mới
    adapter = get_adapter_for_url(product.original_url)
    short_url = adapter.generate_affiliate_link(
        original_url=product.original_url,
        sub_id1=click_id,
        sub_id2=merchant_id,
        sub_id3=ext_user_id,
        sub_id4=source_platform
    )

    # 5. Lưu bản ghi lượt click vào bảng click_trackings
    click_log = ClickTracking(
        click_id=click_id,
        product_id=product.id,
        shop_id=shop_id,
        ext_user_id=ext_user_id,
        source_context=source_platform,
        generated_short_url=short_url,
        clicked_at=utc_now()
    )
    db.add(click_log)
    db.commit()

    return {
        "click_id": click_id,
        "product_id": product.id,
        "shop_id": shop_id,
        "merchant_id": merchant_id,
        "generated_short_url": short_url,
        "sub_id_breakdown": {
            "sub_id1": click_id,
            "sub_id2": merchant_id,
            "sub_id3": ext_user_id,
            "sub_id4": source_platform
        },
        "cached": is_cached,
        "clicked_at": click_log.clicked_at.isoformat()
    }

