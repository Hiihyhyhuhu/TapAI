from .base_adapter import BasePlatformAdapter
from .shopee_adapter import ShopeeAdapter
from .tiktok_adapter import TikTokShopAdapter

shopee_adapter = ShopeeAdapter()
tiktok_adapter = TikTokShopAdapter()

def get_adapter_for_url(url: str) -> BasePlatformAdapter:
    """Tự động phân tích URL và trả về Adapter tương ứng."""
    clean = url.lower().strip()
    if "shopee.vn" in clean or "shp.ee" in clean:
        return shopee_adapter
    elif "tiktok.com" in clean or "tiktok" in clean:
        return tiktok_adapter
    # Mặc định fallback về ShopeeAdapter
    return shopee_adapter

