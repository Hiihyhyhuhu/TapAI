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
    """Module B: Quét và thu thập link sản phẩm Shopee/Lazada thực tế qua Serper API (Images, Web, Lens)"""
    def __init__(self):
        self.api_key = os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise ValueError("Thiếu SERPER_API_KEY trong file .env!")
        self.headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

    @staticmethod
    def clean_thumbnail_url(url: str) -> str:
        """Nâng cấp ảnh HD: Cắt bỏ hậu tố _tn (thumbnail chất lượng thấp) từ CDN Shopee"""
        if not url:
            return ""
        if "susercontent.com" in url or "shopeemobile.com" in url:
            return re.sub(r"_tn(?:_[0-9]+|\.webp)?$", "", url)
        return url

    @staticmethod
    def parse_ecommerce_url(url: str) -> Optional[Dict[str, str]]:
        """Nhận diện toàn diện các biến thể URL sản phẩm của Shopee và Lazada, loại trừ link rác"""
        if not url:
            return None
        
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path

        is_shopee = "shopee.vn" in domain or "shp.ee" in domain
        is_lazada = "lazada.vn" in domain

        if not is_shopee and not is_lazada:
            return None

        # Loại bỏ trang chủ hoặc các trang danh mục/tìm kiếm chung
        if not path or path == "/" or any(path.lower().startswith(ex) for ex in EXCLUDED_PATHS):
            return None

        # 1. Các biến thể Shopee:
        if is_shopee:
            # Biến thể A: /{slug}-i.{shopid}.{itemid} hoặc /product/{shopid}/{itemid} hoặc universal-link/
            sp_match = re.search(r"(?:-i\.(\d+)\.(\d+)|/product/(\d+)/(\d+))", path)
            if sp_match:
                shop_id = sp_match.group(1) or sp_match.group(3)
                item_id = sp_match.group(2) or sp_match.group(4)
                return {
                    "platform": "Shopee",
                    "unique_id": f"sp_{item_id}",
                    "clean_url": f"https://shopee.vn/product/{shop_id}/{item_id}" if shop_id else f"https://shopee.vn{path}"
                }
            # Biến thể B: Short links (vn.shp.ee/XYZ123)
            short_match = re.search(r"^/([a-zA-Z0-9_-]+)$", path)
            if "shp.ee" in domain and short_match:
                code = short_match.group(1)
                return {
                    "platform": "Shopee",
                    "unique_id": f"sp_short_{code}",
                    "clean_url": url
                }

        # 2. Các biến thể Lazada:
        if is_lazada:
            # Biến thể: -i{itemid}-s{skuid}.html hoặc -i{itemid}.html hoặc /products/...
            lz_match = re.search(r"-i(\d+)(?:-s\d+)?\.html?", path) or re.search(r"-i(\d+)", path)
            if lz_match:
                item_id = lz_match.group(1)
                return {
                    "platform": "Lazada",
                    "unique_id": f"lz_{item_id}",
                    "clean_url": f"https://www.lazada.vn{path}"
                }

        # 3. Fallback cho các đường dẫn chi tiết khác của sàn
        if len(path) > 15:
            platform = "Shopee" if is_shopee else "Lazada"
            clean_hash = abs(hash(path.split("?")[0])) % 100000000
            return {
                "platform": platform,
                "unique_id": f"{platform.lower()}_{clean_hash}",
                "clean_url": f"https://{parsed.netloc}{path}"
            }

        return None

    @staticmethod
    def extract_price(text: str) -> str:
        """Tách giá tiền từ tiêu đề hoặc đoạn mô tả của Google"""
        if not text:
            return "Xem trên sàn"
        match = PRICE_REGEX.search(text)
        return match.group(0).strip() if match else "Xem trên sàn"

    async def _fetch_serper(self, client: httpx.AsyncClient, endpoint: str, query: str, num: int = 35) -> dict:
        """Hàm gọi API Serper bất đồng bộ với timeout tối ưu để không làm nghẽn pipeline"""
        url = f"https://google.serper.dev/{endpoint}"
        payload = {
            "q": query,
            "gl": "vn",
            "hl": "vi",
            "num": num
        }
        try:
            resp = await client.post(url, headers=self.headers, json=payload, timeout=httpx.Timeout(4.5, connect=3.0))
            if resp.status_code != 200:
                return {}
            return resp.json()
        except Exception:
            return {}

    async def _fetch_lens(self, client: httpx.AsyncClient, img_target_url: str) -> List[dict]:
        """Gọi Serper Lens API để truy vết sản phẩm trực tiếp từ ảnh thị giác (Reverse Image Search)"""
        url = "https://google.serper.dev/lens"
        payload = {"url": img_target_url}
        try:
            resp = await client.post(url, headers=self.headers, json=payload, timeout=httpx.Timeout(10.0, connect=3.0))
            if resp.status_code == 200:
                return resp.json().get("organic", [])
        except Exception as e:
            print(f"   ⚠️ Lỗi kết nối Google Lens: {e}")
        return []

    async def search_products(
        self,
        query_obj: EcomSearchQuery,
        max_results: int = 25,
        image_url: Optional[str] = None
    ) -> List[ProductCandidate]:
        """
        Chiến lược thu thập đa kênh kết hợp Trộn luân phiên (Round-Robin Interleaving):
        - Bắn song song: detailed_query, medium_query, broad_query và Google Lens.
        - Trộn luân phiên (Round-Robin) giữa các kênh truy vấn để chống bẫy độc chiếm của truy vấn đầu tiên.
        - Tự động gỡ bỏ hậu tố _tn để lấy ảnh gốc HD sắc nét.
        """
        raw_queries = [
            query_obj.detailed_query,
            query_obj.medium_query,
            query_obj.broad_query,
            query_obj.exact_query
        ]
        queries_to_run: List[str] = []
        for q in raw_queries:
            clean_q = (q or "").strip()
            if clean_q and clean_q not in queries_to_run:
                queries_to_run.append(clean_q)

        if not queries_to_run:
            queries_to_run = ["thời trang xu hướng shopee"]

        active_queries = queries_to_run[:3]
        per_query_candidates: Dict[str, List[ProductCandidate]] = {q: [] for q in active_queries}
        lens_candidates: List[ProductCandidate] = []
        shopping_prices: List[str] = []

        async def _search_bundle(client: httpx.AsyncClient, q_text: str):
            ecom_query = f"{q_text} shopee.vn"
            img_task = self._fetch_serper(client, "images", ecom_query, num=35)
            web_task = self._fetch_serper(client, "search", ecom_query, num=20)
            shop_task = self._fetch_serper(client, "shopping", q_text, num=10)
            results = await asyncio.gather(img_task, web_task, shop_task)
            return q_text, results[0], results[1], results[2]

        async with httpx.AsyncClient() as client:
            bundle_tasks = [_search_bundle(client, q) for q in active_queries]
            
            lens_task = None
            if image_url and image_url.startswith("http"):
                lens_task = self._fetch_lens(client, image_url)

            if lens_task:
                bundle_results, lens_results = await asyncio.gather(
                    asyncio.gather(*bundle_tasks),
                    lens_task
                )
            else:
                bundle_results = await asyncio.gather(*bundle_tasks)
                lens_results = []

            # 1. Thu thập ứng viên từ Google Lens
            if lens_results:
                seen_lens_uids = set()
                for item in lens_results:
                    link = item.get("link", "")
                    prod_meta = self.parse_ecommerce_url(link)
                    if not prod_meta:
                        continue
                    uid = prod_meta["unique_id"]
                    if uid in seen_lens_uids:
                        continue
                    seen_lens_uids.add(uid)

                    raw_title = item.get("title") or ""
                    title = raw_title.replace(" | Shopee Việt Nam", "").replace(" | Lazada.vn", "").strip()
                    thumb_raw = item.get("imageUrl") or item.get("thumbnailUrl") or ""
                    thumb_hd = self.clean_thumbnail_url(thumb_raw)
                    if thumb_hd:
                        lens_candidates.append(ProductCandidate(
                            item_id=uid,
                            title=title,
                            price=self.extract_price(title),
                            platform=prod_meta["platform"],
                            product_url=prod_meta["clean_url"],
                            thumbnail_url=thumb_hd,
                            query_used="Google Lens (Visual Match)"
                        ))

            # 2. Thu thập ứng viên riêng biệt theo từng câu truy vấn
            for q_text, img_data, web_data, shop_data in bundle_results:
                seen_query_uids = set()
                c_list = per_query_candidates[q_text]

                for s_item in shop_data.get("shopping", []):
                    if s_item.get("price"):
                        shopping_prices.append(s_item["price"])

                # Google Images
                for img_item in img_data.get("images", []):
                    thumb_raw = img_item.get("imageUrl") or img_item.get("thumbnailUrl") or ""
                    if not thumb_raw or "fbsbx.com" in thumb_raw:
                        continue

                    prod_meta = self.parse_ecommerce_url(img_item.get("link", ""))
                    if not prod_meta:
                        continue

                    uid = prod_meta["unique_id"]
                    if uid in seen_query_uids:
                        continue
                    seen_query_uids.add(uid)

                    raw_title = img_item.get("title") or ""
                    title = raw_title.replace(" | Shopee Việt Nam", "").replace(" | Lazada.vn", "").strip()
                    thumb_hd = self.clean_thumbnail_url(thumb_raw)

                    c_list.append(ProductCandidate(
                        item_id=uid,
                        title=title,
                        price=self.extract_price(title),
                        platform=prod_meta["platform"],
                        product_url=prod_meta["clean_url"],
                        thumbnail_url=thumb_hd,
                        query_used=q_text
                    ))

                # Google Organic
                for item in web_data.get("organic", []):
                    prod_meta = self.parse_ecommerce_url(item.get("link", ""))
                    if not prod_meta:
                        continue

                    uid = prod_meta["unique_id"]
                    raw_title = item.get("title") or ""
                    title = raw_title.replace(" | Shopee Việt Nam", "").replace(" | Lazada.vn", "").strip()
                    snippet = item.get("snippet") or ""
                    price_found = self.extract_price(f"{title} {snippet}")
                    thumb_raw = item.get("imageUrl") or ""
                    thumb_hd = self.clean_thumbnail_url(thumb_raw)

                    # Cập nhật giá nếu có
                    existing = next((c for c in c_list if c.item_id == uid), None)
                    if existing:
                        if existing.price == "Xem trên sàn" and price_found != "Xem trên sàn":
                            existing.price = price_found
                    elif thumb_hd and "fbsbx.com" not in thumb_hd and uid not in seen_query_uids:
                        seen_query_uids.add(uid)
                        c_list.append(ProductCandidate(
                            item_id=uid,
                            title=title,
                            price=price_found,
                            platform=prod_meta["platform"],
                            product_url=prod_meta["clean_url"],
                            thumbnail_url=thumb_hd,
                            query_used=q_text
                        ))

        # 3. TRỘN LUÂN PHIÊN (ROUND-ROBIN INTERLEAVING) CHỐNG BẪY ĐỘC CHIẾM
        sources: List[List[ProductCandidate]] = []
        if lens_candidates:
            sources.append(lens_candidates)
        
        # Đưa detailed_query lên đầu vì chứa chi tiết sát nhất
        if query_obj.detailed_query in per_query_candidates and per_query_candidates[query_obj.detailed_query]:
            sources.append(per_query_candidates[query_obj.detailed_query])

        # Tiếp theo là medium_query
        if query_obj.medium_query in per_query_candidates and per_query_candidates[query_obj.medium_query] and per_query_candidates[query_obj.medium_query] not in sources:
            sources.append(per_query_candidates[query_obj.medium_query])

        # Các truy vấn còn lại (broad_query, exact_query)
        for q_t, c_list in per_query_candidates.items():
            if c_list and c_list not in sources:
                sources.append(c_list)

        interleaved_list: List[ProductCandidate] = []
        seen_all_uids = set()
        max_len = max((len(s) for s in sources), default=0)

        for col_idx in range(max_len):
            for s in sources:
                if col_idx < len(s):
                    cand = s[col_idx]
                    if cand.item_id not in seen_all_uids:
                        seen_all_uids.add(cand.item_id)
                        interleaved_list.append(cand)
                    if len(interleaved_list) >= max_results:
                        break
            if len(interleaved_list) >= max_results:
                break

        # Gán giá tham khảo nếu sản phẩm chưa có giá hiển thị
        for idx, prod in enumerate(interleaved_list):
            if prod.price == "Xem trên sàn" and shopping_prices:
                prod.price = f"~{shopping_prices[idx % len(shopping_prices)]}"

        return interleaved_list
