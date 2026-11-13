import os
import io
import asyncio
import httpx
from enum import Enum
from PIL import Image
from typing import List, Optional, Dict, Any, Tuple
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from models.search_schemas import EcomSearchQuery, ProductCandidate

load_dotenv()

class MatchLevel(str, Enum):
    EXACT = "EXACT"        # Giống hệt hoặc chuẩn xác hoàn toàn
    CLOSE = "CLOSE"        # Rất giống, chỉ khác biệt nhỏ / là biến thể cùng mẫu
    DIFFERENT = "DIFFERENT"# Khác biệt rõ rệt

class CandidateRubricEvaluation(BaseModel):
    item_id: str = Field(
        description="Mã item_id chính xác (ví dụ 'sp_123456') hoặc SLOT_ID (ví dụ 'CAND_1') ghi ngay trên ảnh"
    )
    slot_id: Optional[str] = Field(
        default=None,
        description="Mã vị trí của ứng viên (ví dụ 'CAND_1', 'CAND_2') ghi trên ảnh"
    )
    silhouette_match: MatchLevel = Field(
        description="Kiểu dáng và phom dáng cốt lõi (VD: áo polo dài tay form rộng vs cardigan cài cúc vs áo phông)"
    )
    collar_neckline_match: MatchLevel = Field(
        description="Thiết kế cổ áo & cơ chế đóng mở (VD: cổ bẻ có khóa kéo zip vs cổ tròn vs cổ bẻ cài cúc)"
    )
    pattern_match: MatchLevel = Field(
        description="Họa tiết bề mặt vải (VD: sọc kẻ ngang vs kẻ sọc dọc vs caro vs trơn đơn sắc; đối chiếu cả Tiêu đề nếu là biến thể màu khác)"
    )
    color_palette_match: MatchLevel = Field(
        description="Tông màu và phối màu chủ đạo (nếu ảnh bìa màu khác nhưng Tiêu đề ghi rõ có biến thể màu mục tiêu thì đánh giá CLOSE/EXACT)"
    )
    key_details_match: bool = Field(
        description="Chi tiết đặc trưng điểm nhấn (khóa kéo zip kim loại, túi áo, bo gấu tay)"
    )
    reason: str = Field(
        description="Giải thích ngắn gọn 1 câu chỉ rõ tiêu chí giống hoặc khác biệt thị giác cụ thể (kèm ghi chú nếu Tiêu đề có biến thể đúng mẫu)"
    )

class RerankRubricOutput(BaseModel):
    evaluations: List[CandidateRubricEvaluation]

def compute_dhash(img: Image.Image, hash_size: int = 8) -> str:
    """Băm thị giác DHash 64-bit cực nhanh (0.1ms) để phát hiện ảnh trùng lặp xưởng / Taobao"""
    gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
    pixels = list(gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata())
    diff = []
    for row in range(hash_size):
        for col in range(hash_size):
            p_left = pixels[row * (hash_size + 1) + col]
            p_right = pixels[row * (hash_size + 1) + col + 1]
            diff.append(p_left > p_right)
    
    decimal_val = 0
    hex_parts = []
    for idx, val in enumerate(diff):
        if val:
            decimal_val += 2 ** (idx % 8)
        if (idx % 8) == 7:
            hex_parts.append(hex(decimal_val)[2:].rjust(2, "0"))
            decimal_val = 0
    return "".join(hex_parts)

def hamming_dist(h1: str, h2: str) -> int:
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except Exception:
        return 99

class MultimodalReranker:
    """
    Module C: Thẩm định và Reranking trực quan bằng Vision-LLM kết hợp Chuẩn hóa Rubric (Deterministic Scoring)
    - Cơ chế Model Cascade tự động chuyển đổi model dự phòng khi gặp 404/503.
    - Đọc cấu hình từ biến môi trường GEMINI_MODEL.
    - Báo lỗi minh bạch, tuyệt đối không gán điểm giả mạo khi API gặp sự cố.
    """
    def __init__(self, model_name: Optional[str] = None):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Thiếu GEMINI_API_KEY trong file .env!")
        self.client = genai.Client(api_key=api_key)
        
        env_model = os.getenv("GEMINI_MODEL", "").strip()
        candidates = [
            model_name or env_model,
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.8-flash",
            "gemini-flash-latest"
        ]
        self.model_cascade: List[str] = []
        for m in candidates:
            if m and m not in self.model_cascade:
                self.model_cascade.append(m)
        self.active_model = self.model_cascade[0]

    async def _download_image(self, client: httpx.AsyncClient, url: str) -> Optional[Image.Image]:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = await client.get(url, headers=headers, timeout=httpx.Timeout(3.0, connect=2.0), follow_redirects=True)
            if resp.status_code == 200:
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                img.thumbnail((384, 384))
                return img
        except Exception:
            pass
        return None

    @staticmethod
    def compute_rubric_score(eval_item: CandidateRubricEvaluation) -> float:
        """
        Tính điểm tương đồng xác định (Deterministic Rubric Scoring) bằng Python:
        - Trọng số minh bạch:
          + Silhouette (Phom dáng): 30%
          + Collar / Neckline (Cổ áo & khóa zip): 25%
          + Pattern (Họa tiết sọc ngang/caro/trơn): 25%
          + Color Palette (Phối màu sắc & Biến thể): 10%
          + Key Details (Chi tiết điểm nhấn): 10%
        """
        LEVEL_WEIGHTS = {
            MatchLevel.EXACT: 1.0,
            MatchLevel.CLOSE: 0.65,
            MatchLevel.DIFFERENT: 0.0
        }

        # Nếu khác phom dáng hoàn toàn (ví dụ: áo thay vì quần, hoặc polo thay vì hoodie chui đầu), phạt nặng
        if eval_item.silhouette_match == MatchLevel.DIFFERENT:
            return 0.15

        s_sil = LEVEL_WEIGHTS.get(eval_item.silhouette_match, 0.0) * 0.30
        s_col = LEVEL_WEIGHTS.get(eval_item.collar_neckline_match, 0.0) * 0.25
        s_pat = LEVEL_WEIGHTS.get(eval_item.pattern_match, 0.0) * 0.25
        s_pal = LEVEL_WEIGHTS.get(eval_item.color_palette_match, 0.0) * 0.10
        s_det = (1.0 if eval_item.key_details_match else 0.0) * 0.10

        total_score = s_sil + s_col + s_pat + s_pal + s_det
        return round(max(0.0, min(1.0, total_score)), 4)

    @staticmethod
    def calculate_ranking_score(similarity_score: float, **kwargs) -> float:
        """Tính điểm xếp hạng tương thích ngược"""
        clamped = max(0.0, min(1.0, similarity_score))
        return round(clamped, 4)

    async def rerank(
        self,
        crop_image_path: str,
        query_obj: EcomSearchQuery,
        candidates: List[ProductCandidate],
        top_k: int = 5,
        **kwargs
    ) -> List[ProductCandidate]:
        """
        Dùng Vision-LLM (Gemini) trực tiếp đối chiếu ảnh crop gốc với ảnh sản phẩm sàn:
        - Mở rộng phễu tải ảnh (Top 16 ứng viên từ đa truy vấn Round-Robin).
        - Khử trùng lặp ảnh bằng DHash Perceptual Hashing trên RAM (nhận diện ảnh chung xưởng Taobao).
        - Đánh giá trực quan Micro-batching tối đa 6 ứng viên độc nhất/lượt (tránh suy giảm Attention & Index Shifting).
        - Đồng bộ điểm cho sản phẩm chung ảnh mẫu, khử hoàn toàn điểm trần 0.65 giả định.
        - Cơ chế Model Cascade tự động chuyển đổi sang model dự phòng khi gặp sự cố.
        """
        if not candidates:
            return []

        if not os.path.exists(crop_image_path):
            raise FileNotFoundError(f"Không tìm thấy ảnh crop tại: {crop_image_path}")

        # 1. Tải trước ảnh của Top 16 ứng viên để gom đủ đại diện từ detailed, medium, broad và lens
        download_pool = candidates[:16]
        async with httpx.AsyncClient() as client:
            tasks = [self._download_image(client, c.thumbnail_url) for c in download_pool]
            downloaded_imgs = await asyncio.gather(*tasks)

        # Khử trùng lặp bằng DHash: nhận diện các shop dùng chung ảnh xưởng Taobao
        unique_pool: List[Tuple[ProductCandidate, Image.Image]] = []
        seen_dhashes: List[Tuple[str, str]] = []  # Danh sách (hash, item_id)
        duplicate_of: Dict[str, str] = {}         # duplicate_item_id -> representative_item_id

        for cand, img in zip(download_pool, downloaded_imgs):
            if img is not None:
                img_hash = compute_dhash(img)
                rep_id = None
                for prev_h, prev_id in seen_dhashes:
                    if hamming_dist(img_hash, prev_h) <= 4:
                        rep_id = prev_id
                        break
                if rep_id:
                    duplicate_of[cand.item_id] = rep_id
                    continue

                seen_dhashes.append((img_hash, cand.item_id))
                unique_pool.append((cand, img))
                if len(unique_pool) >= 6:
                    break

        with Image.open(crop_image_path) as target_file:
            target_img = target_file.convert("RGB")
            target_img.thumbnail((448, 448))

        # 2. Xây dựng prompt Rubric chuẩn xác kèm giải pháp Variant Mismatch & Dual Identifier Anti-Index Shifting
        contents = [
            "Bạn là chuyên gia thẩm định thị giác sản phẩm Thương mại điện tử (Shopee, Lazada).",
            "Nhiệm vụ: Đối chiếu tỉ mỉ [ẢNH MỤC TIÊU CẦN TÌM] với từng [ẢNH ỨNG VIÊN] thu thập từ sàn TMĐT.",
            "\nQUY TẮC BẮT BUỘC ĐỂ TRÁNH LỆCH CHỈ MỤC (ANTI-INDEX SHIFTING - ĐỊNH DANH KÉP):",
            "1. Quan sát độc lập từng ứng viên theo thứ tự được trình bày bên dưới.",
            "2. Trong kết quả trả về, bạn PHẢI điền chính xác trường 'slot_id' (ví dụ 'CAND_1', 'CAND_2') VÀ trường 'item_id' (ví dụ 'sp_123456') ghi ngay trên bức ảnh của ứng viên đó.",
            "3. Bỏ qua hoàn toàn: Người mẫu (mặt mũi, dáng đứng), phông nền, khung viền khuyến mãi của Shopee (Freeship Xtra, Mall, voucher sale).",
            "\nQUY TẮC XỬ LÝ LỆCH ẢNH BÌA PHÂN LOẠI HÀNG (VARIANT MISMATCH):",
            "- Nhiều chủ shop trên Shopee bán cùng một mẫu áo với nhiều màu sắc/họa tiết (phân loại hàng: Đen, Đỏ, Trắng, Sọc kẻ...) trong cùng 1 link sản phẩm, nhưng ảnh bìa đại diện ngoài kết quả tìm kiếm lại chỉ hiển thị 1 màu đơn sắc.",
            "- Nếu kiểu dáng cốt lõi (silhouette_match) và cổ áo (collar_neckline_match) của ứng viên KHỚP TỐT với mục tiêu:",
            "  -> Hãy đọc kỹ TIÊU ĐỀ (Title) của ứng viên: nếu Tiêu đề có chứa các từ khóa chỉ họa tiết hoặc màu sắc của ảnh mục tiêu (ví dụ: 'kẻ ngang', 'phối sọc', 'sọc kẻ', 'trắng đỏ đen', 'nhiều màu'), shop này ĐANG CÓ BIẾN THỂ ĐÚNG MẪU trong link bán hàng.",
            "  -> Khi đó: Đánh giá pattern_match hoặc color_palette_match là CLOSE hoặc EXACT (thay vì DIFFERENT), và ghi rõ trong 'reason': 'Ảnh bìa hiển thị màu khác nhưng tiêu đề xác nhận có biến thể đúng mẫu.'",
            "\n4. Đánh giá rời rạc theo đúng 5 tiêu chí Rubric chuẩn (EXACT, CLOSE, DIFFERENT; True/False):",
            "   - silhouette_match: Kiểu dáng & phom dáng cốt lõi (EXACT / CLOSE / DIFFERENT).",
            "   - collar_neckline_match: Thiết kế cổ áo / khóa kéo zip / cơ chế mở cổ (EXACT / CLOSE / DIFFERENT).",
            "   - pattern_match: Họa tiết bề mặt (sọc ngang vs sọc dọc vs caro vs trơn đơn sắc).",
            "   - color_palette_match: Thứ tự và tông màu sắc chủ đạo.",
            "   - key_details_match: Chi tiết điểm nhấn (khóa kéo kim loại, túi, bo gấu tay) (true / false).",
            "\n[ẢNH MỤC TIÊU CẦN TÌM] (Target Image):",
            target_img,
            f"Ngữ cảnh sản phẩm: Danh mục [{query_obj.category_path}], Kiểu dáng [{query_obj.item_type}], Từ khóa sàn [{query_obj.medium_query or query_obj.exact_query}].\n"
        ]

        valid_candidate_ids = set()
        for idx, (cand, img) in enumerate(unique_pool, 1):
            contents.append(f"\n==========================================")
            contents.append(f"📦 [ỨNG VIÊN #{idx}] - SLOT_ID: \"CAND_{idx}\" | ITEM_ID: \"{cand.item_id}\"")
            contents.append(f"Tiêu đề: {cand.title}")
            contents.append(img)
            contents.append(f"==========================================")
            valid_candidate_ids.add(cand.item_id)

        # 3. Gọi Gemini VLM qua cơ chế Model Cascade tự động thử lại
        if valid_candidate_ids:
            vlm_success = False
            last_error = None

            for model_cand in self.model_cascade:
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.client.models.generate_content,
                            model=model_cand,
                            contents=contents,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=RerankRubricOutput,
                                temperature=0.0,
                            ),
                        ),
                        timeout=12.0
                    )
                    vlm_eval = RerankRubricOutput.model_validate_json(response.text)

                    # Xây dựng từ điển tra cứu định danh kép (Dual Identifier Maps) chống lệch chỉ mục tuyệt đối
                    item_id_map: Dict[str, CandidateRubricEvaluation] = {}
                    slot_map: Dict[str, CandidateRubricEvaluation] = {}

                    for ev_item in vlm_eval.evaluations:
                        raw_id = (ev_item.item_id or "").strip()
                        if raw_id:
                            item_id_map[raw_id.lower()] = ev_item
                            # Nếu VLM điền nhầm slot_id vào trường item_id (VD: CAND_1)
                            clean_slot = raw_id.upper().replace("CANDIDATE_", "CAND_").replace("CANDIDATE", "CAND_")
                            if "CAND" in clean_slot:
                                slot_map[clean_slot] = ev_item
                            digits = "".join(filter(str.isdigit, raw_id))
                            if digits:
                                slot_map[f"CAND_{digits}"] = ev_item
                                slot_map[digits] = ev_item

                        raw_slot = (ev_item.slot_id or "").strip().upper()
                        if raw_slot:
                            clean_slot = raw_slot.replace("CANDIDATE_", "CAND_").replace("CANDIDATE", "CAND_")
                            slot_map[clean_slot] = ev_item
                            digits = "".join(filter(str.isdigit, clean_slot))
                            if digits:
                                slot_map[f"CAND_{digits}"] = ev_item
                                slot_map[digits] = ev_item

                    evaluated_scores: Dict[str, float] = {}

                    # 1. Chấm điểm trực tiếp bằng Định danh kép (Chỉ lặp trên unique_pool, tuyệt đối không dùng index thô)
                    for slot_idx, (cand, _) in enumerate(unique_pool, 1):
                        cand_id_norm = cand.item_id.strip().lower()
                        slot_key = f"CAND_{slot_idx}"

                        # Ưu tiên 1: Khớp chính xác theo item_id
                        ev = item_id_map.get(cand_id_norm)
                        # Ưu tiên 2: Khớp theo Slot ID gắn tường minh trong unique_pool
                        if not ev:
                            ev = slot_map.get(slot_key) or slot_map.get(str(slot_idx))

                        if ev:
                            calculated_score = self.compute_rubric_score(ev)
                            cand.match_score = calculated_score
                            cand.match_reason = ev.reason
                            cand.rubric_breakdown = {
                                "silhouette": ev.silhouette_match.value,
                                "collar_neckline": ev.collar_neckline_match.value,
                                "pattern": ev.pattern_match.value,
                                "color_palette": ev.color_palette_match.value,
                                "key_details": ev.key_details_match,
                                "model_used": model_cand,
                                "evaluation_type": "direct_vlm",
                                "matched_by": "item_id" if item_id_map.get(cand_id_norm) else "slot_id",
                                "slot_assigned": slot_key
                            }
                            evaluated_scores[cand.item_id] = calculated_score

                    # 2. Đồng bộ điểm có điều kiện cho các ứng viên dùng chung ảnh xưởng Taobao (DHash <= 4)
                    # Tối ưu giao diện Side Panel Chrome Extension: Giới hạn tối đa 1 bản sao/mẫu ảnh (MAX_CLONES = 1)
                    # để người dùng so sánh giá/shop mà không bị ngập tràn bởi 10 ảnh giống hệt nhau
                    clone_counts: Dict[str, int] = {}
                    MAX_CLONES_PER_REPRESENTATIVE = 1
                    synced_item_ids = set()

                    for cand in candidates:
                        if cand.item_id in duplicate_of:
                            rep_id = duplicate_of[cand.item_id]
                            rep_score = evaluated_scores.get(rep_id)

                            # Điều kiện đồng bộ:
                            # 1. Sản phẩm đại diện đạt độ tương đồng thị giác cao (rep_score >= 0.50)
                            # 2. Số lượng bản sao đồng bộ chưa vượt quá hạn ngạch (tối đa 1 bản sao trên Side Panel)
                            current_clones = clone_counts.get(rep_id, 0)
                            if rep_score is not None and rep_score >= 0.50 and current_clones < MAX_CLONES_PER_REPRESENTATIVE:
                                clone_counts[rep_id] = current_clones + 1
                                cand.match_score = max(0.0, round(rep_score - 0.005, 4))
                                cand.match_reason = f"Đồng bộ thị giác từ ảnh mẫu chung xưởng ({rep_id}). Bản sao so sánh giá/shop."
                                cand.rubric_breakdown = {
                                    "duplicate_of": rep_id,
                                    "evaluation_type": "dhash_shared_visual",
                                    "clone_rank": current_clones + 1,
                                    "model_used": model_cand
                                }
                                synced_item_ids.add(cand.item_id)

                    # 3. Phân rã điểm cho các ứng viên còn lại chưa thẩm định hoặc bản sao dư thừa (Không gán cứng 0.65!)
                    for idx, cand in enumerate(candidates):
                        if cand.item_id not in evaluated_scores and cand.item_id not in synced_item_ids:
                            decay_idx = max(0, idx - len(unique_pool))
                            decayed_score = max(0.18, round(0.38 - (decay_idx * 0.015), 4))
                            cand.match_score = decayed_score
                            if cand.item_id in duplicate_of:
                                cand.match_reason = f"Bản sao ảnh xưởng vượt hạn ngạch hiển thị (cùng mẫu với {duplicate_of[cand.item_id]}). Xếp theo từ khóa sàn."
                                cand.rubric_breakdown = {
                                    "evaluation_type": "excess_clone_fallback",
                                    "duplicate_of": duplicate_of[cand.item_id],
                                    "query_used": cand.query_used
                                }
                            else:
                                cand.match_reason = f"Ứng viên xếp theo từ khóa sàn ('{cand.query_used}'). Chưa qua thẩm định trực tiếp VLM."
                                cand.rubric_breakdown = {
                                    "evaluation_type": "keyword_fallback",
                                    "query_used": cand.query_used,
                                    "note": "Xếp hạng dự phòng từ khóa"
                                }

                    self.active_model = model_cand
                    vlm_success = True
                    break

                except Exception as e:
                    last_error = e
                    print(f"⚠️ [VLM Rerank Cascade] Model '{model_cand}' gặp sự cố ({type(e).__name__}: {e}). Đang thử model tiếp theo trong cascade...")
                    continue

            if not vlm_success:
                print(f"\n❌ [CRITICAL ERROR] Toàn bộ Gemini VLM models đều thất bại trong quá trình Rerank! Chi tiết lỗi: {last_error}")
                print("   -> BẬT BÁO LỖI MINH BẠCH (Không giả mạo điểm số thị giác!)\n")
                for idx, cand in enumerate(candidates):
                    cand.match_score = 0.50
                    cand.match_reason = f"⚠️ [LỖI API VLM: {last_error}]. Không thể đối chiếu hình ảnh, tạm thời xếp theo từ khóa sàn."
                    cand.rubric_breakdown = {
                        "status": "vlm_failed",
                        "error": str(last_error)
                    }

        # 4. Gán ranking_score trực tiếp từ match_score (Pure Similarity Match)
        for cand in candidates:
            cand.ranking_score = self.calculate_ranking_score(cand.match_score or 0.0)

        # 5. Sắp xếp giảm dần theo match_score (sản phẩm có điểm Rubric cao nhất đưa lên đầu)
        ranked = sorted(
            candidates, 
            key=lambda x: (x.match_score if x.match_score is not None else 0.0), 
            reverse=True
        )
        return ranked[:top_k]
