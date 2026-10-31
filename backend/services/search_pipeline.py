import os
import time
from typing import Dict, Any, Union, Optional
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
        print(f"   [1/3] VLM Query Gen: {query_info.exact_query} (trong {t_b - t_a:.2f}s)")

        # 4. Quét sản phẩm sàn TMĐT qua Serper (Module B)
        max_search_results = max(25, top_k + 5)
        raw_candidates = await self.searcher.search_products(query_info, max_results=max_search_results)
        t_c = time.perf_counter()
        print(f"   [2/3] Web Searcher: Thu được {len(raw_candidates)} ứng viên (trong {t_c - t_b:.2f}s)")

        # 5. Rerank bằng VLM đối chiếu trực quan (Module C)
        top_products = await self.reranker.rerank(temp_path, query_info, raw_candidates, top_k=top_k)
        t_d = time.perf_counter()
        print(f"   [3/3] VLM Reranker: Hoàn thành Top {len(top_products)} sản phẩm (trong {t_d - t_c:.2f}s)")

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
