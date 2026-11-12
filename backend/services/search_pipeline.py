import os
import time
from typing import Dict, Any, Union
from PIL import Image
from models.search_schemas import EcomSearchQuery, ProductCandidate
from services.query_generator import QueryGenerator
from services.shopee_searcher import ShopeeWebSearcher
from services.reranker import MultimodalReranker

class TapAISearchPipeline:
    """
    Pipeline tìm kiếm sản phẩm cốt lõi (Core Multimodal AI Search Pipeline):
    1. VLM Query Generator (Gemini 3.5 Flash-Lite): Nhận ảnh crop vật thể từ SAM 3 / Extension, sinh từ khóa chuẩn e-commerce.
    2. Shopee/Lazada Searcher (Serper API): Tìm kiếm 20-25 sản phẩm ứng viên từ sàn TMĐT.
    3. Multimodal VLM Reranker (Gemini + Optuna + Seasonality): Đối chiếu thị giác, tính điểm xếp hạng kết hợp hoa hồng thương mại.
    """
    def __init__(self):
        print("🚀 Đang khởi động TapAISearchPipeline (Core VLM & Search Engine)...")
        self.query_generator = QueryGenerator()
        self.searcher = ShopeeWebSearcher()
        self.reranker = MultimodalReranker()
        print("✅ Pipeline cốt lõi đã sẵn sàng phục vụ!\n")

    async def process_image(
        self,
        image_input: Union[str, Image.Image],
        object_id: str = "obj_01",
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        Xử lý toàn diện một vật thể:
        Ảnh crop -> Gemini VLM -> Serper Search -> Gemini Rerank -> Top K Sản phẩm
        """
        t0 = time.perf_counter()

        # Đảm bảo có đường dẫn file ảnh
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Không tìm thấy file ảnh: {image_input}")
            temp_path = image_input
            cleanup_temp = False
        else:
            pil_image = image_input.convert("RGB")
            temp_path = f"./temp_{object_id}_{int(time.time()*1000)}.jpg"
            pil_image.save(temp_path)
            cleanup_temp = True

        try:
            print(f"🔍 Bắt đầu quy trình tìm kiếm AI cho vật thể '{object_id}'...")

            # 1. Phân tích ảnh sinh từ khóa qua VLM (Gemini 3.5 Flash-Lite)
            t_a = time.perf_counter()
            query_info = self.query_generator.generate_from_image(temp_path)
            t_b = time.perf_counter()
            print(f"   [1/3] VLM Query Gen: {query_info.exact_query} (trong {t_b - t_a:.2f}s)")

            # 2. Quét sản phẩm sàn TMĐT qua Serper (Shopee/Lazada)
            max_search_results = max(25, top_k + 5)
            raw_candidates = await self.searcher.search_products(query_info, max_results=max_search_results)
            t_c = time.perf_counter()
            print(f"   [2/3] Web Searcher: Thu được {len(raw_candidates)} ứng viên (trong {t_c - t_b:.2f}s)")

            # 3. Rerank bằng VLM đối chiếu trực quan (Gemini + Optuna + Seasonality)
            top_products = await self.reranker.rerank(temp_path, query_info, raw_candidates, top_k=top_k)
            t_d = time.perf_counter()
            print(f"   [3/3] VLM Reranker: Hoàn thành Top {len(top_products)} sản phẩm (trong {t_d - t_c:.2f}s)")

            total_latency_ms = (t_d - t0) * 1000

            return {
                "object_id": object_id,
                "latency_ms": round(total_latency_ms, 2),
                "detected_category": query_info.category_path,
                "exact_query": query_info.exact_query,
                "products": [p.model_dump() for p in top_products]
            }
        finally:
            if cleanup_temp and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
