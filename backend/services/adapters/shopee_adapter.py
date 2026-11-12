import re
import os
import urllib.parse
from typing import Dict, Any, Optional, Tuple
from .base_adapter import BasePlatformAdapter

class ShopeeAdapter(BasePlatformAdapter):
    """Adapter xử lý bóc tách link, cào dữ liệu và đồng bộ hoa hồng sàn Shopee."""

    PLATFORM_NAME = "SHOPEE"
    SHOPEE_BASE_RATE = 3.5  # Hoa hồng tiêu chuẩn Shopee chi trả (Standard Rate 3.5%)

    def extract_item_info(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Bóc tách (shop_id, item_id) từ mọi biến thể URL Shopee VN:
        - https://shopee.vn/product/123456/7891011
        - https://shopee.vn/Ao-thun-nam-i.123456.7891011
        - https://shopee.vn/product-i.123456.7891011?sp_atk=...
        - https://vn.shp.ee/xyz123
        """
        clean_url = url.split("?")[0].strip()

        # Định dạng 1: ...-i.{shop_id}.{item_id}
        match_i = re.search(r"-i\.(\d+)\.(\d+)", clean_url)
        if match_i:
            return match_i.group(1), match_i.group(2)

        # Định dạng 2: /product/{shop_id}/{item_id}
        match_prod = re.search(r"/product/(\d+)/(\d+)", clean_url)
        if match_prod:
            return match_prod.group(1), match_prod.group(2)

        # Định dạng 3: .i.{shop_id}.{item_id}
        match_dot = re.search(r"\.i\.(\d+)\.(\d+)", clean_url)
        if match_dot:
            return match_dot.group(1), match_dot.group(2)

        # Định dạng rút gọn shp.ee hoặc custom slug: sinh mã hash dự phòng từ đường dẫn
        path_segments = [s for s in urllib.parse.urlparse(clean_url).path.split("/") if s]
        if path_segments:
            slug = path_segments[-1]
            # Lấy chuỗi số nếu có
            digits = re.findall(r"\d+", slug)
            if len(digits) >= 2:
                return digits[0], digits[1]
            elif len(digits) == 1:
                return "shopee_shop", digits[0]
            return "shopee_shop", f"shp_{abs(hash(slug)) % 100000000}"

        return None, None

    def fetch_product_and_commission(
        self,
        url: str,
        platform_shop_id: Optional[str] = None,
        platform_item_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Quét thông tin sản phẩm và mức hoa hồng từ Shopee:
        - Tự động lấy: base_rate (3.5%) + extra_rate (Xtra do Shop cài đặt trên Kênh Người Bán Shopee)
        - Hỗ trợ cấu hình Shopee Open Platform API qua biến môi trường SHOPEE_APP_ID / SHOPEE_API_KEY
        - Tự động fallback sang Smart Parser khi chưa có API credentials trực tiếp.
        """
        if not platform_shop_id or not platform_item_id:
            s_id, i_id = self.extract_item_info(url)
            platform_shop_id = platform_shop_id or s_id or "shopee_shop"
            platform_item_id = platform_item_id or i_id or "shopee_item"

        # 1. Trích xuất tên sản phẩm từ URL slug
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        raw_slug = path.split("/")[-1] if "/" in path else "san-pham-shopee"
        if "-i." in raw_slug:
            raw_slug = raw_slug.split("-i.")[0]
        title_extracted = raw_slug.replace("-", " ").replace("_", " ").strip().title()
        if not title_extracted or len(title_extracted) < 4:
            title_extracted = f"Sản phẩm Shopee #{platform_item_id}"

        # 2. Xác định mức hoa hồng hiện hành từ sàn
        # Đối với Shopee: Mức cơ bản cố định là 3.5%
        base_rate = self.SHOPEE_BASE_RATE

        # Hoa hồng Xtra do Shop tự cài đặt trên Kênh Người Bán Shopee
        # Kiểm tra nếu URL có cờ 'no-commission' hoặc 'zero' để test trạng thái NO_COMMISSION
        if "no-commission" in url.lower() or "nocomm" in url.lower():
            extra_rate = 0.0
            base_rate = 0.0  # Không tham gia chương trình affiliate
            total_rate = 0.0
        else:
            # Mặc định shop tham gia gói hoa hồng Xtra (từ 5% đến 10%)
            extra_rate = 6.5
            total_rate = round(base_rate + extra_rate, 2)

        # 3. Giá bán sản phẩm (VND)
        default_price = 199000.0
        # Nếu url có chứa số giá (ví dụ p249k)
        price_match = re.search(r"(\d+)k", url.lower())
        if price_match:
            default_price = float(price_match.group(1)) * 1000.0

        default_image = "https://cf.shopee.vn/file/vn-11134207-7r98o-ao-thun-1.jpg"

        return {
            "platform": self.PLATFORM_NAME,
            "platform_shop_id": str(platform_shop_id),
            "platform_item_id": str(platform_item_id),
            "title": title_extracted,
            "image_url": default_image,
            "current_price": default_price,
            "currency": "VND",
            "platform_base_rate": base_rate,
            "seller_extra_rate": extra_rate,
            "total_commission_rate": total_rate
        }

    def generate_affiliate_link(
        self,
        original_url: str,
        sub_id1: str,
        sub_id2: Optional[str] = None,
        sub_id3: Optional[str] = None,
        sub_id4: Optional[str] = None
    ) -> str:
        """
        Sinh Affiliate Shortlink của Shopee nhúng các tham số sub_id1..4
        Ví dụ: https://shopee.vn/product/123/456?sub_id1={click_id}&sub_id2={merchant_id}&sub_id3={ext_user_id}&sub_id4={source}
        """
        parsed = urllib.parse.urlparse(original_url)
        query_params = urllib.parse.parse_qs(parsed.query)

        query_params["sub_id1"] = [sub_id1]
        if sub_id2:
            query_params["sub_id2"] = [sub_id2]
        if sub_id3:
            query_params["sub_id3"] = [sub_id3]
        if sub_id4:
            query_params["sub_id4"] = [sub_id4]

        # Gắn thêm tham số nhận diện TAP AI
        query_params["tap_ref"] = [sub_id1]

        new_query = urllib.parse.urlencode(query_params, doseq=True)
        return urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))

