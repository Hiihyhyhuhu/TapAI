from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# ============================================================================
# 1. CORE PIPELINE SCHEMAS (VLM Query & Candidate)
# ============================================================================

class EcomSearchQuery(BaseModel):
    """Cấu trúc truy vấn do VLM sinh ra từ ảnh crop"""
    category_path: str = Field(
        description="Đường dẫn danh mục chuẩn Shopee (VD: 'Thời trang nam > Áo khoác > Áo khoác bomber')"
    )
    item_type: str = Field(
        description="Tên gọi cốt lõi của sản phẩm (VD: 'Áo khoác bomber', 'Túi đeo chéo nữ')"
    )
    color: str = Field(
        description="Màu sắc chủ đạo bằng tiếng Việt (VD: 'đen', 'xanh rêu', 'trắng kem')"
    )
    style_and_material: List[str] = Field(
        description="2-4 từ khóa về kiểu dáng, chất liệu chuẩn văn phong Shopee (VD: ['form rộng', 'vải kaki', 'tay dài', 'hàn quốc'])"
    )
    exact_query: str = Field(
        description="Câu truy vấn tìm kiếm chi tiết nhất (gộp item_type + chất liệu + kiểu dáng + màu sắc, dài 5-8 từ)"
    )
    broad_query: str = Field(
        description="Câu truy vấn ngắn gọn dự phòng (chỉ gồm item_type + màu sắc + 1 đặc điểm chính, dài 3-4 từ)"
    )

class ProductCandidate(BaseModel):
    """Cấu trúc 1 sản phẩm thu thập được từ Shopee/Lazada"""
    item_id: str = Field(description="Mã định danh sản phẩm")
    title: str = Field(description="Tên hiển thị sản phẩm trên sàn")
    price: str = Field(description="Giá hiển thị (VD: '289.000₫' hoặc '~680.000₫')")
    platform: str = Field(default="Shopee", description="Nền tảng TMĐT (Shopee, Lazada, TikTok Shop)")
    product_url: str = Field(description="Link dẫn thẳng tới trang mua hàng (đã gắn mã hoặc link sạch)")
    thumbnail_url: str = Field(description="Link ảnh đại diện sản phẩm")
    query_used: str = Field(description="Truy vấn đã dùng để tìm ra sản phẩm này")
    match_score: Optional[float] = Field(default=0.0, description="Điểm tương đồng thị giác (0.0 - 1.0) do VLM Reranker chấm")
    match_reason: Optional[str] = Field(default=None, description="Lời giải thích vì sao sản phẩm này khớp với ảnh crop")
    commission_rate: Optional[float] = Field(default=0.05, description="Tỷ lệ hoa hồng Affiliate (VD: 0.05 = 5%, 0.15 = 15%)")
    ranking_score: Optional[float] = Field(default=None, description="Điểm xếp hạng tổng hợp theo biên Pareto (A*similarity + B*commission)")

# ============================================================================
# 2. CLIENT-SIDE CONTRACT: METADATA.JSON (Cho Chrome Extension & React UI)
# ============================================================================

class BBoxNormalized(BaseModel):
    """Tọa độ bounding box chuẩn hóa theo tỷ lệ (0.0 - 1.0) [ymin, xmin, ymax, xmax]"""
    ymin: float = Field(ge=0.0, le=1.0)
    xmin: float = Field(ge=0.0, le=1.0)
    ymax: float = Field(ge=0.0, le=1.0)
    xmax: float = Field(ge=0.0, le=1.0)

class ObjectDetectionOverlay(BaseModel):
    """Vị trí xuất hiện của 1 vật thể tại một khung hình cụ thể"""
    object_id: str = Field(description="Mã định danh vật thể khớp với bảng objects (VD: obj_01)")
    bbox: List[float] = Field(
        description="Tọa độ chuẩn hóa [ymin, xmin, ymax, xmax] theo tỷ lệ 0.0 - 1.0 để tự co giãn theo kích thước video/màn hình"
    )
    confidence: Optional[float] = Field(default=1.0, description="Độ tin cậy của SAM 3 tracking")
    polygon: Optional[List[List[float]]] = Field(
        default=None, 
        description="Danh sách tọa độ điểm [[x1, y1], [x2, y2], ...] phục vụ vẽ viền sáng Glowing Contours Canvas/WebGL"
    )

class TimelineFrame(BaseModel):
    """Dữ liệu tracking tại 1 mốc thời gian / frame"""
    timestamp: float = Field(description="Mốc thời gian tính bằng giây trong video")
    frame_index: int = Field(description="Thứ tự khung hình (0, 1, 2, ...)")
    detections: List[ObjectDetectionOverlay] = Field(description="Danh sách các vật thể xuất hiện trong khung hình này")

class TrackedObject(BaseModel):
    """Thông tin chi tiết của 1 vật thể để hiển thị trên Side Panel"""
    object_id: str = Field(description="Mã định danh duy nhất (VD: obj_sweater_01)")
    label: str = Field(description="Tên gọi ngắn gọn hiển thị trên badge (VD: 'Áo len dệt kim cổ bẻ')")
    category: str = Field(description="Đường dẫn danh mục (VD: 'Thời trang nữ > Áo len')")
    crop_image_url: Optional[str] = Field(default=None, description="Ảnh crop gốc của vật thể từ video để hiển thị đối chiếu ở header")
    primary_color: Optional[str] = Field(default=None, description="Màu sắc chủ đạo")
    matched_products: List[ProductCandidate] = Field(description="Top các sản phẩm gợi ý mua sắm trên sàn")

class MediaMetadata(BaseModel):
    """Thông số kỹ thuật của video/ảnh"""
    media_id: str = Field(description="ID định danh video hoặc ảnh")
    media_type: str = Field(default="video", description="'video' hoặc 'image'")
    duration_sec: Optional[float] = Field(default=None, description="Tổng thời lượng video (giây)")
    fps: Optional[float] = Field(default=30.0, description="Số khung hình/giây của video")
    resolution: Optional[List[int]] = Field(default=None, description="[width, height] gốc")

class TapAIMetadata(BaseModel):
    """
    Cấu trúc chuẩn file `metadata.json` bàn giao cho Chrome Extension (Hỷ):
    - `objects`: Dữ liệu sản phẩm cho React Side Panel trượt ra khi click.
    - `timeline`: Dữ liệu tọa độ cho Canvas / WebGL vẽ Glowing Contours chạy song song theo thời gian thực (60 FPS).
    """
    version: str = Field(default="1.0.0", description="Phiên bản chuẩn metadata format")
    generated_at: str = Field(description="Thời điểm tạo (ISO timestamp)")
    media_info: MediaMetadata
    objects: Dict[str, TrackedObject] = Field(description="Từ điển các vật thể, key là object_id")
    timeline: Optional[List[TimelineFrame]] = Field(
        default=None, 
        description="Timeline tracking cho video. Với ảnh tĩnh đơn lẻ, timeline chỉ chứa 1 frame duy nhất."
    )

# ============================================================================
# 3. FASTAPI REQUEST SCHEMAS (Hỗ trợ Base64 & URL cho Extension)
# ============================================================================

class MatchItemRequest(BaseModel):
    """Payload JSON cho endpoint /api/v1/match-item"""
    image_base64: Optional[str] = Field(
        default=None, 
        description="Chuỗi Base64 của ảnh crop (hỗ trợ cả prefix 'data:image/...;base64,' hoặc raw base64)"
    )
    image_url: Optional[str] = Field(
        default=None, 
        description="URL trực tiếp của ảnh trên web (Extension truyền trực tiếp img.src)"
    )
    object_id: str = Field(default="obj_01", description="Mã định danh vật thể")
    use_cache: bool = Field(default=True, description="Bật/tắt kiểm tra Vector Cache")
    cache_threshold: float = Field(default=0.88, description="Ngưỡng tương đồng cosine để tính là Cache Hit")
    top_k: int = Field(default=20, description="Số sản phẩm cần lấy (mặc định 20)")

class VideoDetection(BaseModel):
    object_id: str = Field(description="Mã định danh vật thể do SAM 3 gán (VD: obj_01, obj_02)")
    frame_index: int = Field(description="Vị trí khung hình trong video")
    bbox: List[float] = Field(description="Tọa độ bounding box [ymin, xmin, ymax, xmax] hoặc [x1, y1, x2, y2]")
    confidence: Optional[float] = Field(default=1.0, description="Độ tự tin của mask/bbox")
    image_base64: str = Field(description="Ảnh crop vật thể định dạng base64")
    timestamp: Optional[float] = Field(default=None, description="Mốc thời gian (giây) trong video")
    polygon: Optional[List[List[float]]] = Field(default=None, description="Tọa độ viền polygon từ SAM 3 mask")

class VideoBatchRequest(BaseModel):
    video_id: str = Field(description="Mã video đang xử lý")
    detections: List[VideoDetection] = Field(description="Danh sách tất cả các detections của SAM 3 trong video")
    use_cache: bool = Field(default=True, description="Sử dụng Vector Cache để tăng tốc")
    top_k: int = Field(default=20, description="Số sản phẩm cần lấy cho mỗi vật thể (mặc định 20)")
    fps: Optional[float] = Field(default=30.0, description="Tốc độ khung hình của video (FPS)")
    duration_sec: Optional[float] = Field(default=None, description="Tổng thời lượng video (giây)")
    resolution: Optional[List[int]] = Field(default=None, description="[width, height] của video gốc")
    async_mode: bool = Field(default=True, description="Chạy bất đồng bộ dưới nền (khuyến nghị True cho video dài)")

# ============================================================================
# 4. BACKGROUND TASK MANAGEMENT SCHEMAS (Celery / BackgroundTasks)
# ============================================================================

class TaskStatusEnum(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class TaskSubmitResponse(BaseModel):
    """Phản hồi tức thì khi gửi video batch vào hàng đợi ngầm"""
    task_id: str = Field(description="Mã định danh tác vụ để tra cứu tiến độ")
    video_id: str = Field(description="Mã video được gửi")
    status: TaskStatusEnum = Field(default=TaskStatusEnum.PENDING)
    message: str = Field(description="Thông báo trạng thái khởi tạo")
    status_url: str = Field(description="URL API để kiểm tra tiến độ")

class TaskStatusResponse(BaseModel):
    """Thông tin chi tiết tiến độ xử lý tác vụ"""
    task_id: str
    video_id: str
    status: TaskStatusEnum
    progress: float = Field(0.0, description="Tiến độ xử lý từ 0.0 đến 1.0 (0% - 100%)")
    current_step: Optional[str] = Field(None, description="Mô tả công đoạn đang chạy")
    created_at: str
    updated_at: str
    total_detections: int = 0
    unique_objects: int = 0
    result: Optional[TapAIMetadata] = Field(None, description="File metadata.json chuẩn hoàn chỉnh khi task COMPLETED")
    error: Optional[str] = Field(None, description="Thông báo lỗi nếu task FAILED")
