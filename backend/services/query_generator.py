import os
from typing import Optional, List
from dotenv import load_dotenv
from PIL import Image
from google import genai
from google.genai import types
from models.search_schemas import EcomSearchQuery

load_dotenv()

class QueryGenerator:
    """
    Module A: Phân tích thị giác và sinh bộ truy vấn Đa cấp độ (Multi-Query Expansion)
    - Cơ chế Model Cascade tự động chuyển đổi model nếu gặp 404/503.
    - Đọc cấu hình từ biến môi trường GEMINI_MODEL.
    - Cảnh báo lỗi minh bạch, chống bẫy âm thầm suy biến (Silent Fallback Trap).
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
        # Khử trùng lặp và giữ nguyên thứ tự ưu tiên
        self.model_cascade: List[str] = []
        for m in candidates:
            if m and m not in self.model_cascade:
                self.model_cascade.append(m)
        self.active_model = self.model_cascade[0]

    def generate_from_image(self, image_path: str) -> EcomSearchQuery:
        """Nhận đường dẫn ảnh crop và trả về bộ truy vấn 3 cấp độ trong EcomSearchQuery"""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Không tìm thấy file ảnh tại: {image_path}")

        with Image.open(image_path) as img_file:
            img = img_file.convert("RGB")

        prompt = """
        Bạn là chuyên gia tối ưu hóa tìm kiếm (SEO & Merchandiser) hàng đầu trên Shopee, Lazada và TikTok Shop Việt Nam.
        Hãy quan sát món đồ chính trong bức ảnh này và tạo ra bộ truy vấn tìm kiếm ĐA CẤP ĐỘ (Multi-Query Expansion) chuẩn văn phong đặt tiêu đề của người bán hàng tại Việt Nam.

        1. BẢN ĐỊA HÓA TỪ VỰNG SÀN (E-COMMERCE SELLER LINGO):
           - Bắt buộc dùng đúng các thuật ngữ, từ lóng bán hàng thực tế mà chủ shop thường giật tít để tăng lượt click:
             * Kiểu áo: 'polo zip' (thay cho 'cổ bẻ khóa kéo'), 'cardigan', 'croptop', 'hoodie zip', 'bomber', 'blazer', 'sweater', 'gile', 'tanktop', 'babydoll'...
             * Phom dáng & style: 'form rộng', 'oversize', 'ulzzang', 'unisex', 'boxy', 'ống suông', 'cạp cao', 'ống loe', 'y2k', 'hàn quốc', 'basic'...
             * Họa tiết & chất vải: 'kẻ ngang', 'kẻ sọc', 'caro', 'gân tăm', 'len tăm', 'nỉ bông', 'dệt kim', 'da bóng', 'kaki', 'jean bò'...
           - TUYỆT ĐỐI TRÁNH:
             * Không dùng từ ngữ kỹ thuật dệt may mô tả cứng nhắc (như: 'sợi dệt tổng hợp', 'hàng may mặc').
             * Không liệt kê máy móc một chuỗi nhiều màu sắc (ví dụ: thay vì 'kẻ sọc đỏ đen trắng xanh' hãy dùng 'kẻ ngang' hoặc 'sọc phối màu').
             * Không dùng từ thừa như: 'hình ảnh', 'chiếc', 'màu sắc', 'chất lượng cao', 'mua ở đâu'.

        2. CHIẾN LƯỢC ĐA TRUY VẤN (MULTI-QUERY EXPANSION) TRÁNH BẪY ZERO-RECALL:
           - `broad_query` (Cấp 1 - Rộng: 2-3 từ): Tên món đồ + 1 đặc trưng bao quát lớn nhất (VD: 'áo len polo kẻ', 'quần jean ống suông', 'áo khoác bomber'). Đảm bảo 100% luôn tìm thấy hàng chục kết quả trên Shopee.
           - `medium_query` (Cấp 2 - Cân bằng: 3-5 từ): Tên món + từ lóng seller + phom dáng/style hot (VD: 'áo len polo zip kẻ ngang ulzzang form rộng'). Tỷ lệ khớp sản phẩm thị trường cao nhất.
           - `detailed_query` (Cấp 3 - Chi tiết: 5-7 từ): Bổ sung thêm đặc điểm điểm nhấn hoặc phối màu chủ đạo (VD: 'áo len polo zip kẻ sọc ngang đen trắng đỏ form rộng').
           - `exact_query`: Điền tương đương `detailed_query` hoặc `medium_query` để tương thích ngược.
        """

        last_error = None
        for model_cand in self.model_cascade:
            try:
                response = self.client.models.generate_content(
                    model=model_cand,
                    contents=[img, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=EcomSearchQuery,
                        temperature=0.1,
                    ),
                )
                self.active_model = model_cand
                result = EcomSearchQuery.model_validate_json(response.text)
                return result
            except Exception as e:
                last_error = e
                print(f"⚠️ [VLM QueryGen Cascade] Model '{model_cand}' gặp sự cố ({type(e).__name__}: {e}). Đang tự động chuyển sang model tiếp theo trong cascade...")
                continue

        # Nếu toàn bộ models trong cascade đều thất bại:
        print(f"\n❌ [CRITICAL ERROR] Toàn bộ các model Gemini trong cascade đều thất bại! Chi tiết lỗi: {last_error}")
        print("   -> BẮT BUỘC BẬT CHẾ ĐỘ DỰ PHÒNG KHẨN CẤP (Vui lòng kiểm tra lại GEMINI_API_KEY hoặc GEMINI_MODEL)!\n")

        # Trích xuất từ khóa thô dựa trên gợi ý tên file từ SAM 3
        base_name = os.path.basename(image_path).lower()
        detected_tag = "thời trang xu hướng"
        for tag in ["áo len", "áo khoác", "áo thun", "áo sơ mi", "quần jean", "quần short", "túi xách", "giày", "váy", "đầm"]:
            if tag.replace(" ", "_") in base_name or tag in base_name:
                detected_tag = tag
                break

        return EcomSearchQuery(
            category_path=f"[DỰ PHÒNG - LỖI VLM] Thời trang > {detected_tag.title()}",
            item_type=detected_tag.title(),
            color="đen trắng",
            style_and_material=["form rộng", "ulzzang", "hàn quốc"],
            broad_query=f"{detected_tag} form rộng",
            medium_query=f"{detected_tag} ulzzang form rộng hàn quốc",
            detailed_query=f"{detected_tag} ulzzang form rộng kẻ ngang phối màu",
            exact_query=f"{detected_tag} ulzzang form rộng kẻ ngang phối màu"
        )
