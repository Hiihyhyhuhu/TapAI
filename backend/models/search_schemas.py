from pydantic import BaseModel, Field
from typing import List, Optional

class EcomSearchQuery(BaseModel):
    """Cấu trúc truy vấn do VLM sinh ra từ ảnh crop vật thể SAM 3"""
    category_path: str = Field(
        description="Đường dẫn danh mục chuẩn Shopee (VD: 'Thời trang nữ > Áo len & Cardigan > Áo len')"
    )
    item_type: str = Field(
        description="Tên gọi cốt lõi của sản phẩm (VD: 'Áo len', 'Túi đeo chéo nữ')"
    )
    color: str = Field(
        description="Màu sắc chủ đạo bằng tiếng Việt (VD: 'đen', 'xanh rêu', 'trắng kem')"
    )
    style_and_material: List[str] = Field(
        description="2-4 từ khóa về kiểu dáng, chất liệu chuẩn văn phong Shopee (VD: ['form rộng', 'cổ bẻ', 'kéo khóa', 'kẻ sọc'])"
    )
    exact_query: str = Field(
        description="Câu truy vấn tìm kiếm chi tiết nhất (gộp item_type + chất liệu + kiểu dáng + màu sắc, dài 5-8 từ)"
    )
    broad_query: str = Field(
        description="Câu truy vấn ngắn gọn dự phòng (chỉ gồm item_type + màu sắc + 1 đặc điểm chính, dài 3-4 từ)"
    )

class ProductCandidate(BaseModel):
    """Cấu trúc 1 sản phẩm thu thập được từ Shopee/Lazada"""
    item_id: str
    title: str
    price: str
    platform: str          # "Shopee" hoặc "Lazada"
    product_url: str       # Link sạch dẫn thẳng tới trang mua hàng
    thumbnail_url: str     # Link ảnh sản phẩm để hiển thị & đưa vào Reranker
    query_used: str        # Truy vấn nào đã tìm ra sản phẩm này
    match_score: Optional[float] = 0.0
    match_reason: Optional[str] = None

class VideoDetection(BaseModel):
    """Dữ liệu bounding box/mask của 1 frame từ SAM 3"""
    object_id: str = Field(description="Mã định danh vật thể do SAM 3 gán (VD: obj_01, obj_02)")
    frame_index: int = Field(description="Vị trí khung hình trong video")
    bbox: List[float] = Field(description="Tọa độ bounding box [x1, y1, x2, y2]")
    confidence: Optional[float] = Field(default=1.0, description="Độ tự tin của mask/bbox")
    image_base64: str = Field(description="Ảnh crop vật thể định dạng base64")

class VideoBatchRequest(BaseModel):
    """Payload xử lý hàng loạt vật thể từ video kèm Deduplication"""
    video_id: str = Field(description="Mã video đang xử lý")
    detections: List[VideoDetection] = Field(description="Danh sách tất cả các detections của SAM 3 trong video")
    use_cache: bool = Field(default=True, description="Sử dụng Vector Cache để tăng tốc")
    top_k: int = Field(default=5, description="Số sản phẩm cần lấy cho mỗi vật thể")
