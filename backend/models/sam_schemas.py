from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class ScanObjectsRequest(BaseModel):
    """Payload JSON yêu cầu quét toàn màn hình (hỗ trợ Open-Vocabulary)"""
    image_base64: Optional[str] = Field(
        default=None,
        description="Chuỗi Base64 của ảnh chụp màn hình (kèm hoặc không kèm header 'data:image/...;base64,')"
    )
    extract_all_webp: bool = Field(
        default=True,
        description="True nếu muốn bóc tách và lưu ảnh WebP nền trong suốt cho toàn bộ vật thể tìm thấy"
    )
    custom_vocabulary: Optional[List[str]] = Field(
        default=None,
        description="Danh sách từ vựng mở tùy chỉnh (Open-Vocabulary Classes), ví dụ: ['sweater', 'handbag', 'smartphone', 'shoes', 'sunglasses', 'watch']"
    )


class DetectedObjectItem(BaseModel):
    """Thông tin 1 vật thể được bóc tách từ màn hình"""
    object_id: str = Field(description="Mã định danh vật thể duy nhất (VD: item_1_sweater)")
    category_hint: str = Field(description="Tên danh mục nhận diện (VD: sweater, handbag, shoes)")
    semantic_group: Optional[str] = Field(default="general", description="Gom nhóm ngữ nghĩa (VD: upper_body, bag)")
    confidence: float = Field(description="Độ tin cậy của mô hình nhận diện (0.0 - 1.0)")
    quality_score: Optional[float] = Field(default=None, description="Điểm chất lượng bóc tách mép viền (0 - 100)")
    bbox_pixel: List[int] = Field(description="Tọa độ BBox theo pixel thực tế: [x1, y1, x2, y2]")
    bbox_norm: List[float] = Field(description="Tọa độ BBox chuẩn hóa [0.0 - 1.0]: [x1, y1, x2, y2]")
    contour_norm: List[List[float]] = Field(
        description="Danh sách tọa độ các đỉnh polygon chuẩn hóa [0.0 - 1.0] cho WebGL 60 FPS"
    )
    crop_webp_path: str = Field(description="Đường dẫn lưu file ảnh .webp nền trong suốt trên server")
    crop_image_base64_webp: Optional[str] = Field(default=None, description="Chuỗi Base64 ảnh .webp nền trong suốt")
    crop_image_data_url_webp: Optional[str] = Field(
        default=None,
        description="Data URL chuẩn định dạng 'data:image/webp;base64,...' để render trực tiếp trên Frontend"
    )


class ScanObjectsResponse(BaseModel):
    """Phản hồi sau khi quét toàn màn hình"""
    status: str = Field(default="success")
    event_type: str = Field(default="screen_scan_segmentation")
    processing_time_ms: float = Field(description="Thời gian xử lý tính bằng mili-giây")
    resolution: Dict[str, int] = Field(description="Kích thước ảnh gốc {'width': w, 'height': h}")
    total_detected: int = Field(description="Tổng số lượng vật thể tìm thấy")
    items: List[DetectedObjectItem] = Field(description="Danh sách chi tiết các vật thể đã bóc tách")
    tap_ai_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Cấu trúc siêu dữ liệu metadata.json chuẩn 100% data contract phục vụ Frontend Side Panel"
    )


class TapToBuyRequest(BaseModel):
    """Payload JSON khi người dùng click chuột vào vật thể trên màn hình"""
    image_base64: Optional[str] = Field(
        default=None,
        description="Ảnh màn hình hiện tại (Base64). Nếu bỏ trống sẽ dùng frame gần nhất trong RAM Cache"
    )
    tap_x: float = Field(default=0.5, description="Tọa độ X của điểm click (chuẩn hóa 0.0 - 1.0 hoặc pixel)")
    tap_y: float = Field(default=0.5, description="Tọa độ Y của điểm click (chuẩn hóa 0.0 - 1.0 hoặc pixel)")
    is_normalized: bool = Field(default=True, description="True nếu tap_x và tap_y nằm trong khoảng [0.0, 1.0]")
    send_to_rag: bool = Field(
        default=True,
        description="True nếu muốn tự động chuyển tiếp ảnh WebP bóc tách sang Backend Search & RAG"
    )
    rag_api_url: Optional[str] = Field(
        default=None,
        description="Tùy chọn ghi đè URL webhook Backend RAG (nếu chạy microservice riêng)"
    )


class TapToBuyResponse(BaseModel):
    """Phản hồi sau khi chạm để mua"""
    status: str = Field(default="success")
    schema_version: str = Field(default="2.0-tap-ai-transparent-webp")
    event_type: str = Field(default="user_tap_extraction")
    extraction_mode: str = Field(description="Chế độ bóc tách: 'cache_hit' hoặc 'dynamic_point_decode'")
    processing_time_ms: float = Field(description="Thời gian xử lý tính bằng mili-giây")
    tap_coordinates: Dict[str, Any] = Field(description="Tọa độ click dạng pixel và chuẩn hóa")
    source_resolution: Dict[str, int] = Field(description="Độ phân giải ảnh {'width': w, 'height': h}")
    extracted_item: DetectedObjectItem = Field(description="Vật thể được chọn và bóc tách thành WebP trong suốt")
    rag_search_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Kết quả gợi ý sản phẩm và link mua hàng từ Shopee/Lazada do RAG trả về"
    )


class HoverRequest(BaseModel):
    """Payload JSON khi di chuột để nhận contour highlight tức thời"""
    tap_x: float = Field(default=0.5, description="Tọa độ X điểm di chuột")
    tap_y: float = Field(default=0.5, description="Tọa độ Y điểm di chuột")
    is_normalized: bool = Field(default=True, description="True nếu tọa độ thuộc [0.0, 1.0]")


class HoverResponse(BaseModel):
    """Phản hồi hit-test di chuột từ RAM Cache (<5ms)"""
    status: str
    hit: bool
    object_id: Optional[str] = None
    category_hint: Optional[str] = None
    semantic_group: Optional[str] = None
    confidence: Optional[float] = None
    bbox_norm: Optional[List[float]] = None
    contour_norm: Optional[List[List[float]]] = None
    tap_coordinates: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class SAMStatusResponse(BaseModel):
    """Thông tin trạng thái hoạt động của mô hình SAM 3 & Computer Vision"""
    service: str = Field(default="TAP AI SAM 3 & Computer Vision Engine")
    status: str = Field(default="online")
    device: str = Field(description="Thiết bị thực thi hiện tại: 'cuda' (GPU) hoặc 'cpu'")
    vision_architecture: str = Field(
        default="Meta SAM 3 (Promptable Concept Segmentation) + YOLO-World (Open-Vocabulary)",
        description="Kiến trúc Computer Vision hiện tại"
    )
    open_vocabulary_enabled: bool = Field(
        default=True,
        description="Trạng thái hỗ trợ từ vựng mở Open-Vocabulary"
    )
    active_vocabulary: Optional[List[str]] = Field(
        default=None,
        description="Danh sách từ vựng đang hoạt động trong bộ nhớ đệm"
    )
    sam3_teacher_loaded: bool = Field(description="Trạng thái nạp mô hình Teacher Meta SAM 3")
    student_model_loaded: bool = Field(description="Trạng thái nạp mô hình Student Open-Vocabulary / YOLO")
    cached_candidates_count: int = Field(description="Số lượng vật thể đang lưu sẵn trong RAM Cache")
    crops_output_dir: str = Field(description="Thư mục lưu trữ ảnh bóc tách .webp")