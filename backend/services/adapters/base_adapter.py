from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple

class BasePlatformAdapter(ABC):
    """Giao diện trừu tượng (Interface) cho Adapter đồng bộ dữ liệu từ các sàn TMĐT."""

    @abstractmethod
    def extract_item_info(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Bóc tách (shop_id, item_id) từ URL sản phẩm.
        Trả về: (platform_shop_id, platform_item_id)
        """
        pass

    @abstractmethod
    def fetch_product_and_commission(
        self,
        url: str,
        platform_shop_id: Optional[str] = None,
        platform_item_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Quét thông tin sản phẩm và hoa hồng hiện hành từ Sàn.
        Trả về từ điển chuẩn:
        {
            "platform": "SHOPEE" | "TIKTOK_SHOP",
            "platform_shop_id": str,
            "platform_item_id": str,
            "title": str,
            "image_url": str,
            "current_price": float,
            "currency": "VND",
            "platform_base_rate": float,   # % Cố định Sàn chi trả (VD Shopee Standard 3.5%)
            "seller_extra_rate": float,    # % Xtra / Plan do Shop cài đặt trên Kênh Người Bán
            "total_commission_rate": float # Tổng % hoa hồng thực tế (= base + extra)
        }
        """
        pass

    @abstractmethod
    def generate_affiliate_link(
        self,
        original_url: str,
        sub_id1: str, # click_id
        sub_id2: Optional[str] = None, # merchant_id
        sub_id3: Optional[str] = None, # ext_user_id
        sub_id4: Optional[str] = None  # source_platform
    ) -> str:
        """Sinh Affiliate Shortlink có gắn đầy đủ sub_id để Sàn ghi nhận đơn hàng."""
        pass

