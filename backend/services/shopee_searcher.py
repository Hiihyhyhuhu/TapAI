import re
import os
import asyncio
import httpx
from typing import List, Dict, Optional
from urllib.parse import urlparse
from dotenv import load_dotenv
from models.search_schemas import EcomSearchQuery, ProductCandidate

load_dotenv()

# Regex tách giá tiền Việt Nam Đồng
PRICE_REGEX = re.compile(
    r"(?:₫\s*\d{1,3}(?:[.,]\d{3})+|\d{1,3}(?:[.,]\d{3})+\s*(?:₫|đ|vnđ|vnd))",
    re.IGNORECASE,
)

# Các đường dẫn danh mục/tìm kiếm chung KHÔNG phải trang sản phẩm đơn lẻ
EXCLUDED_PATHS = (
    "/search", "/mall", "/list/", "/campaigns/", "/m/", "/blog/", "/events/", "/tag/", "/find/"
)

class ShopeeWebSearcher:
    """Module B: Quét và thu thập link sản phẩm Shopee/Lazada thực tế qua Serper API"""
    def __init__(self):
        self.api_key = os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise ValueError("Thiếu SERPER_API_KEY trong file .env!")
        self.headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

    @staticmethod
    def parse_ecommerce_url(url: str) -> Optional[Dict[str, str]]:
        """Chỉ nhận link gốc trực tiếp của Shopee.vn hoặc Lazada.vn và lọc sạch tham số rác"""
        if not url:
            return None
        
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path

        if "shopee.vn" in domain:
            platform = "Shopee"
        elif "lazada.vn" in domain:
            platform = "Lazada"
        else:
            return None

        # Loại bỏ trang chủ hoặc các trang danh mục/tìm kiếm chung
        if not path or path == "/" or any(path.lower().startswith(ex) for ex in EXCLUDED_PATHS):
            return None

        # 1. Bắt chuẩn link sản phẩm Shopee (-i.shopid.itemid hoặc /product/shopid/itemid)
        sp_match = re.search(r"(?:-i\.(\d+)\.(\d+)|/product/(\d+)/(\d+))", path)
        if sp_match:
            item_id = sp_match.group(2) or sp_match.group(4)
            return {"platform": platform, "unique_id": f"sp_{item_id}", "clean_url": f"https://shopee.vn{path}"}

        # 2. Bắt chuẩn link sản phẩm Lazada (-i123456.html)
        lz_match = re.search(r"-i(\d+)", path)
        if lz_match:
            return {"platform": platform, "unique_id": f"lz_{lz_match.group(1)}", "clean_url": f"https://www.lazada.vn{path}"}

        # 3. Các link chi tiết sản phẩm khác thuộc domain sàn
        if len(path) > 12:
            clean_url = f"https://{parsed.netloc}{path}"
            return {"platform": platform, "unique_id": f"{platform.lower()}_{abs(hash(path)) % 10000000}", "clean_url": clean_url}

        return None

    @staticmethod
    def extract_price(text: str) -> str:
        """Tách giá tiền từ tiêu đề hoặc đoạn mô tả của Google"""
        if not text:
            return "Xem trên sàn"
        match = PRICE_REGEX.search(text)
        return match.group(0).strip() if match else "Xem trên sàn"

    async def _fetch_serper(self, client: httpx.AsyncClient, endpoint: str, query: str, num: int = 20) -> dict:
        """Hàm gọi API Serper bất đồng bộ"""
        url = f"https://google.serper.dev/{endpoint}"
        payload = {
            "q": query,
            "gl": "vn",
            "hl": "vi",
            "num": num
        }
        try:
            resp = await client.post(url, headers=self.headers, json=payload, timeout=10.0)
            if resp.status_code != 200:
                print(f"   ⚠️ Cảnh báo Serper ({endpoint}): HTTP {resp.status_code} - {resp.text}")
                return {}
            return resp.json()
        except Exception as e:
            print(f"   ⚠️ Lỗi kết nối Serper ({endpoint}): {e}")
            return {}

    async def search_products(self, query_obj: EcomSearchQuery, max_results: int = 12) -> List[ProductCandidate]:
        """
        Kết hợp Google Images (Lấy đúng cặp Link Shopee + Ảnh gốc Shopee CDN)
        và Google Web/Shopping (Bổ sung Giá bán).
        """
        candidates_map: Dict[str, ProductCandidate] = {}
        shopping_prices: List[str] = []

        async with httpx.AsyncClient() as client:
            for current_query in [query_obj.exact_query, query_obj.broad_query]:
                ecom_query = f"{current_query} shopee.vn"

                img_task = self._fetch_serper(client, "images", ecom_query, num=25)
                web_task = self._fetch_serper(client, "search", ecom_query, num=15)
                shop_task = self._fetch_serper(client, "shopping", current_query, num=10)

                img_data, web_data, shop_data = await asyncio.gather(img_task, web_task, shop_task)

                # Thu thập giá thực tế từ Google Shopping cho dòng sản phẩm này
                for s_item in shop_data.get("shopping", []):
                    if s_item.get("price"):
                        shopping_prices.append(s_item["price"])

                # 1. Quét Google Images (Nguồn chuẩn nhất vì mỗi ảnh gắn liền với đúng link sản phẩm đó)
                for img_item in img_data.get("images", []):
                    thumb_url = img_item.get("imageUrl") or img_item.get("thumbnailUrl") or ""
                    if not thumb_url or "fbsbx.com" in thumb_url:
                        continue

                    prod_meta = self.parse_ecommerce_url(img_item.get("link", ""))
                    if not prod_meta:
                        continue

                    uid = prod_meta["unique_id"]
                    title = img_item.get("title", "").replace(" | Shopee Việt Nam", "").replace(" | Lazada.vn", "").strip()

                    candidates_map[uid] = ProductCandidate(
                        item_id=uid,
                        title=title,
                        price=self.extract_price(title),
                        platform=prod_meta["platform"],
                        product_url=prod_meta["clean_url"],
                        thumbnail_url=thumb_url,
                        query_used=current_query
                    )

                # 2. Quét Google Web Search để bổ sung giá tiền từ snippet
                for item in web_data.get("organic", []):
                    prod_meta = self.parse_ecommerce_url(item.get("link", ""))
                    if not prod_meta:
                        continue

                    uid = prod_meta["unique_id"]
                    title = item.get("title", "").replace(" | Shopee Việt Nam", "").replace(" | Lazada.vn", "").strip()
                    snippet = item.get("snippet", "")
                    price_found = self.extract_price(f"{title} {snippet}")
                    thumb = item.get("imageUrl") or ""

                    if uid in candidates_map:
                        if candidates_map[uid].price == "Xem trên sàn" and price_found != "Xem trên sàn":
                            candidates_map[uid].price = price_found
                    elif thumb and "fbsbx.com" not in thumb:
                        candidates_map[uid] = ProductCandidate(
                            item_id=uid,
                            title=title,
                            price=price_found,
                            platform=prod_meta["platform"],
                            product_url=prod_meta["clean_url"],
                            thumbnail_url=thumb,
                            query_used=current_query
                        )

                # Gán giá tham khảo nếu sản phẩm chưa có giá hiển thị
                valid_list = list(candidates_map.values())
                for idx, prod in enumerate(valid_list):
                    if prod.price == "Xem trên sàn" and shopping_prices:
                        prod.price = f"~{shopping_prices[idx % len(shopping_prices)]}"

                if len(valid_list) >= 8:
                    return valid_list[:max_results]

        return list(candidates_map.values())[:max_results]
