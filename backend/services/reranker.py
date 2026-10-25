import os
import io
import asyncio
import httpx
from PIL import Image
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from models.search_schemas import EcomSearchQuery, ProductCandidate

load_dotenv()

class CandidateEvaluation(BaseModel):
    item_id: str
    match_score: float = Field(
        description="Điểm tương đồng từ 0.0 đến 1.0 dựa trên mức độ giống với món đồ trong ảnh gốc (1.0 là hoàn toàn trùng khớp mẫu)."
    )
    reason: str = Field(
        description="Giải thích ngắn gọn 1 câu lý do: đánh giá kiểu dáng, hoa văn/họa tiết, phối màu, chi tiết thiết kế so với ảnh gốc."
    )

class RerankOutput(BaseModel):
    evaluations: List[CandidateEvaluation]

class MultimodalReranker:
    """Module C: Thẩm định và Reranking trực quan bằng Vision-LLM (Gemini)"""
    def __init__(self, model_name: str = "gemini-3.5-flash-lite"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Thiếu GEMINI_API_KEY trong file .env!")
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    async def _download_image(self, client: httpx.AsyncClient, url: str) -> Optional[Image.Image]:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = await client.get(url, headers=headers, timeout=5.0, follow_redirects=True)
            if resp.status_code == 200:
                return Image.open(io.BytesIO(resp.content)).convert("RGB")
        except Exception:
            pass
        return None

    async def rerank(
        self,
        crop_image_path: str,
        query_obj: EcomSearchQuery,
        candidates: List[ProductCandidate],
        top_k: int = 5
    ) -> List[ProductCandidate]:
        """
        Dùng Vision-LLM (Gemini) trực tiếp đối chiếu ảnh crop gốc với ảnh sản phẩm sàn:
        - So khớp sâu về kiểu dáng, hoa văn, màu sắc, chi tiết (khóa kéo vs cúc).
        - Miễn nhiễm hoàn toàn với viền khung freeship, logo shop và bẫy nhồi từ khóa.
        """
        if not candidates:
            return []

        if not os.path.exists(crop_image_path):
            raise FileNotFoundError(f"Không tìm thấy ảnh crop tại: {crop_image_path}")

        # 1. Tải song song toàn bộ ảnh thumbnail của các ứng viên
        async with httpx.AsyncClient() as client:
            tasks = [self._download_image(client, c.thumbnail_url) for c in candidates]
            downloaded_imgs = await asyncio.gather(*tasks)

        target_img = Image.open(crop_image_path).convert("RGB")

        # 2. Xây dựng prompt đa phương thức gửi cho VLM
        contents = [
            "Bạn là chuyên gia thẩm định và đối soát hình ảnh sản phẩm thời trang Thương mại điện tử (Shopee, Lazada).",
            "Dưới đây là [ẢNH MỤC TIÊU CẦN TÌM] (Target Image): món đồ trong bức ảnh đầu tiên này.",
            target_img,
            f"Thông tin phân tích món đồ: Danh mục [{query_obj.category_path}], Từ khóa [{query_obj.exact_query}].",
            "\nTiếp theo là danh sách các sản phẩm ứng viên tìm được từ sàn. Hãy quan sát thật kỹ món đồ trong [ẢNH MỤC TIÊU] và đối chiếu với từng ảnh ứng viên:\n"
            "1. TIÊU CHÍ ĐÁNH GIÁ CỐT LÕI:\n"
            "   - Kiểu dáng thiết kế: phom áo, loại cổ áo (VD: cổ bẻ có khóa kéo zip vs cardigan cài cúc vs cổ tròn), độ dài tay.\n"
            "   - Hoa văn & Họa tiết: sọc ngang vs sọc caro/kim cương vs họa tiết in vs trơn.\n"
            "   - Phối màu sắc: thứ tự và vị trí các dải màu (VD: trắng/đen/đỏ).\n"
            "   - Chi tiết: khóa kéo zip kim loại, túi áo, bo gấu...\n"
            "2. BỎ QUA HOÀN TOÀN: Người mẫu, dáng đứng, phông nền, khung viền Shopee (Freeship Xtra, Mall, voucher, chữ sale...).\n"
            "3. THANG ĐIỂM (0.0 đến 1.0):\n"
            "   - 0.90 - 1.00: Cùng mẫu thiết kế, giống hệt về kiểu dáng, họa tiết sọc và khóa kéo.\n"
            "   - 0.70 - 0.89: Rất giống kiểu dáng chính, chỉ khác biệt nhỏ không đáng kể.\n"
            "   - 0.40 - 0.69: Cùng dòng sản phẩm nhưng khác hoa văn (khác cách phối màu hoặc sọc khác).\n"
            "   - 0.00 - 0.39: Khác kiểu dáng (VD: áo cardigan thay vì áo khóa kéo, sọc caro thay vì sọc ngang).\n"
        ]

        for idx, (cand, img) in enumerate(zip(candidates, downloaded_imgs), 1):
            if img is not None:
                contents.append(f"\n--- [Ứng viên #{idx}] Item ID: {cand.item_id} ---")
                contents.append(f"Tiêu đề: {cand.title}")
                contents.append(img)
            else:
                cand.match_score = 0.0
                cand.match_reason = "Không tải được ảnh sản phẩm để thẩm định."

        # 3. Gọi Gemini VLM để thẩm định và chấm điểm
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RerankOutput,
                    temperature=0.1,
                ),
            )
            vlm_eval = RerankOutput.model_validate_json(response.text)
            eval_map = {item.item_id: item for item in vlm_eval.evaluations}

            for cand in candidates:
                if cand.item_id in eval_map:
                    ev = eval_map[cand.item_id]
                    cand.match_score = round(ev.match_score, 4)
                    cand.match_reason = ev.reason

        except Exception as e:
            print(f"⚠️ Lỗi trong quá trình VLM Reranking: {e}")

        # 4. Sắp xếp giảm dần theo match_score
        ranked = sorted(candidates, key=lambda x: x.match_score or 0.0, reverse=True)
        return ranked[:top_k]
