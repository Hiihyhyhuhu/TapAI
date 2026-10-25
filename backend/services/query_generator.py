import os
from dotenv import load_dotenv
from PIL import Image
from google import genai
from google.genai import types
from models.search_schemas import EcomSearchQuery

load_dotenv()

class QueryGenerator:
    """Module A: Trích xuất ngữ cảnh và sinh từ khóa chuẩn sàn TMĐT từ ảnh crop SAM 3"""
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Thiếu GEMINI_API_KEY trong file .env!")
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3.5-flash-lite"

    def generate_from_image(self, image_path: str) -> EcomSearchQuery:
        """Nhận đường dẫn ảnh crop và trả về đối tượng EcomSearchQuery"""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Không tìm thấy file ảnh tại: {image_path}")

        img = Image.open(image_path)

        prompt = """
        Bạn là chuyên gia phân loại danh mục sản phẩm Thương mại điện tử tại Việt Nam (Shopee, Lazada).
        Hãy quan sát món đồ chính trong bức ảnh này và tạo ra câu truy vấn tìm kiếm sản phẩm tương tự:
        1. Sử dụng chính xác các thuật ngữ mà các shop bán hàng tại Việt Nam dùng để đặt tiêu đề sản phẩm (ví dụ: 'form rộng', 'boxy', 'ulzzang', 'cạp cao', 'cổ bẻ', 'khóa kéo', 'kẻ sọc').
        2. Tuyệt đối KHÔNG dùng các từ thừa như: 'hình ảnh', 'chiếc', 'màu sắc', 'mua ở đâu'.
        3. Đảm bảo `exact_query` mô tả sát nhất kiểu dáng và màu sắc của món đồ trong ảnh.
        """

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[img, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EcomSearchQuery,
                temperature=0.1,
            ),
        )

        return EcomSearchQuery.model_validate_json(response.text)
