import os
import time
import json
from typing import Dict, Any, Union, Optional, List
from PIL import Image
from models.search_schemas import EcomSearchQuery, ProductCandidate
from services.query_generator import QueryGenerator
from services.shopee_searcher import ShopeeWebSearcher
from services.reranker import MultimodalReranker
from services.rag_cache import ProductRAGCache

class TapAISearchPipeline:
    """
    Pipeline tích hợp 4 Module của Khanh (Search & RAG):
    1. Embed & RAG Cache Check (Module D - DINOv2 + Qdrant)
    2. VLM Query Generator (Module A - Gemini)
    3. Shopee/Lazada Web Searcher (Module B - Serper)
    4. Multimodal VLM Reranker (Module C - Gemini)
    5. Save to Cache với Quality Gate (Module D)
    """
    def __init__(self, cache_storage: str = "./qdrant_storage"):
        self.rag_cache = ProductRAGCache(storage_path=cache_storage)
        self.query_generator = QueryGenerator()
        self.searcher = ShopeeWebSearcher()
        self.reranker = MultimodalReranker()

    async def process_image(
        self,
        image_input: Union[str, Image.Image],
        object_id: str = "obj_01",
        use_cache: bool = True,
        cache_threshold: float = 0.88,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()

        # Đảm bảo có đối tượng PIL và trích xuất vector embedding
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Không tìm thấy file ảnh: {image_input}")
            pil_image = Image.open(image_input).convert("RGB")
            temp_path = image_input
        else:
            pil_image = image_input.convert("RGB")
            temp_path = f"./temp_{object_id}_{int(time.time()*1000)}.jpg"
            pil_image.save(temp_path)

        # 1. Trích xuất vector ảnh crop DINOv2
        v_crop = self.rag_cache.embedder.embed_image(pil_image)

        # 2. Kiểm tra RAG Vector Cache (Module D)
        if use_cache:
            cache_result = self.rag_cache.search_cache(v_crop, score_threshold=cache_threshold)
            if cache_result:
                t_cache = time.perf_counter()
                latency_ms = (t_cache - t0) * 1000
                print(f"⚡ [CACHE HIT] Vật thể '{object_id}' đã có trong Vector DB! (Độ khớp: {cache_result['similarity_score']}) - Phản hồi trong {latency_ms:.2f}ms")
                
                if isinstance(image_input, Image.Image) and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

                return {
                    "object_id": object_id,
                    "cached": True,
                    "similarity_score": cache_result["similarity_score"],
                    "latency_ms": round(latency_ms, 2),
                    "detected_category": cache_result["category_path"],
                    "exact_query": cache_result["exact_query"],
                    "products": [p.model_dump() for p in cache_result["products"][:top_k]]
                }

        print(f"🔍 [CACHE MISS] Bắt đầu tìm kiếm mới cho vật thể '{object_id}'...")

        # 3. Phân tích ảnh sinh từ khóa qua VLM (Module A)
        t_a = time.perf_counter()
        query_info = self.query_generator.generate_from_image(temp_path)
        t_b = time.perf_counter()
        print(f"   [1/4] VLM Query Gen: {query_info.exact_query} (trong {t_b - t_a:.2f}s)")

        # 3.5. Kiểm tra đối soát với nguồn Sản phẩm Đối tác (Affiliate Portal DB)
        partner_candidates: List[ProductCandidate] = []
        try:
            from database.connection import SessionLocal
            from services.affiliate_service import find_matching_affiliate_products
            db = SessionLocal()
            try:
                matched_partners = find_matching_affiliate_products(
                    db=db,
                    query_text=query_info.exact_query,
                    category=query_info.category_path,
                    limit=3
                )
                for p in matched_partners:
                    imgs = json.loads(p.image_urls) if p.image_urls else []
                    thumb = imgs[0] if imgs else ""
                    partner_candidates.append(
                        ProductCandidate(
                            item_id=f"aff_{p.id}",
                            title=f"[Đối tác chính hãng] {p.name}",
                            price=f"{int(p.price):,} ₫",
                            platform=p.platform.capitalize(),
                            product_url=p.product_url,
                            thumbnail_url=thumb,
                            query_used=query_info.exact_query,
                            match_score=0.98,
                            match_reason="Sản phẩm từ Shop Đối tác chính hãng TAP AI — Ưu tiên hiển thị & Cam kết chất lượng"
                        )
                    )
                if partner_candidates:
                    print(f"   ✨ [PARTNER BOOST] Tìm thấy {len(partner_candidates)} sản phẩm đối tác liên kết phù hợp!")
            finally:
                db.close()
        except Exception as e:
            print(f"   ⚠️ Lỗi truy vấn Affiliate DB trong pipeline: {e}")

        # 4. Quét sản phẩm sàn TMĐT qua Serper (Module B)
        raw_candidates = await self.searcher.search_products(query_info, max_results=12)
        t_c = time.perf_counter()
        print(f"   [2/4] Web Searcher: Thu được {len(raw_candidates)} ứng viên (trong {t_c - t_b:.2f}s)")

        # 5. Rerank bằng VLM đối chiếu trực quan (Module C)
        top_products = await self.reranker.rerank(temp_path, query_info, raw_candidates, top_k=top_k)
        t_d = time.perf_counter()
        print(f"   [3/4] VLM Reranker: Hoàn thành Top {len(top_products)} sản phẩm (trong {t_d - t_c:.2f}s)")

        # 5.5. Tích hợp ưu tiên sản phẩm đối tác (Affiliate Partner Priority)
        if partner_candidates:
            # Gộp sản phẩm đối tác lên đầu, loại bỏ sản phẩm trùng URL
            partner_urls = {cp.product_url for cp in partner_candidates}
            merged_top = partner_candidates + [p for p in top_products if p.product_url not in partner_urls]
            top_products = merged_top[:top_k]
            print(f"   🎯 [FINAL RANKING] Đã ưu tiên hiển thị {len(partner_candidates)} sản phẩm đối tác lên hàng đầu!")

        # 6. Màng lọc chất lượng trước khi lưu Cache (Quality Gate)
        top_score = top_products[0].match_score if top_products else 0.0
        if top_products and top_score >= 0.75:
            point_id = self.rag_cache.save_cache(v_crop, top_products, query_info)
            print(f"💾 [CACHE SAVED] Đã lưu vector vật thể '{object_id}' vào Qdrant (Độ tin cậy: {top_score} >= 0.75, ID: {point_id})")
        else:
            print(f"⚠️ [CACHE SKIPPED] Bỏ qua lưu Cache vì kết quả chưa đủ tin cậy (Top score: {top_score} < 0.75) để tránh đầu độc Cache!")

        if isinstance(image_input, Image.Image) and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

        total_latency_ms = (t_d - t0) * 1000

        return {
            "object_id": object_id,
            "cached": False,
            "latency_ms": round(total_latency_ms, 2),
            "detected_category": query_info.category_path,
            "exact_query": query_info.exact_query,
            "products": [p.model_dump() for p in top_products]
        }
