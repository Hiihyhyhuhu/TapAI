import io
import os
import cv2
import base64
import numpy as np
from typing import Optional, Dict, Any, Union, Tuple
from PIL import Image as PILImage

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, status
from fastapi.responses import JSONResponse

from models.sam_schemas import (
    ScanObjectsRequest,
    ScanObjectsResponse,
    TapToBuyRequest,
    TapToBuyResponse,
    HoverRequest,
    HoverResponse,
    SAMStatusResponse
)
from services.sam3_service import SAM3Engine

# Khởi tạo APIRouter với tiền tố chuẩn /api/v1/sam
router = APIRouter(prefix="/api/v1/sam", tags=["SAM 3 & Computer Vision Engine"])

# Singleton fallback instance phòng khi server không gắn engine vào app.state
_local_sam_engine: Optional[SAM3Engine] = None


def get_sam_engine(request: Request) -> SAM3Engine:
    """Lấy thể hiện SAM3Engine từ app.state hoặc singleton dự phòng"""
    global _local_sam_engine
    engine = getattr(request.app.state, "sam_engine", None)
    if engine is None:
        if _local_sam_engine is None:
            _local_sam_engine = SAM3Engine()
        engine = _local_sam_engine
    return engine


async def decode_image_from_request(
    file: Optional[UploadFile] = None,
    image_base64: Optional[str] = None
) -> Tuple[np.ndarray, str]:
    """
    Tiện ích giải mã ảnh từ File Upload hoặc chuỗi Base64 sang định dạng OpenCV BGR.
    Trả về Tuple[img_bgr, image_name].
    """
    image_name = "frame_input"

    # 1. Ưu tiên giải mã từ File Upload
    if file is not None and hasattr(file, "read"):
        content = await file.read()
        if content:
            nparr = np.frombuffer(content, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_bgr is not None:
                if file.filename:
                    image_name = os.path.splitext(file.filename)[0]
                return img_bgr, image_name

    # 2. Giải mã từ chuỗi Base64
    if image_base64 and len(image_base64.strip()) > 0:
        clean_b64 = image_base64.strip()
        if "," in clean_b64:
            clean_b64 = clean_b64.split(",", 1)[1]
        try:
            img_bytes = base64.b64decode(clean_b64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_bgr is not None:
                return img_bgr, image_name
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Dữ liệu ảnh Base64 không hợp lệ: {e}")

    raise HTTPException(
        status_code=400,
        detail="Thiếu dữ liệu ảnh! Vui lòng gửi kèm file ảnh hoặc trường 'image_base64'."
    )


# ============================================================================
# 1. KIỂM TRA TRẠNG THÁI MÔ HÌNH SAM 3
# ============================================================================
@router.get(
    "/status",
    summary="Kiểm tra trạng thái mô hình Teacher SAM 3, Student YOLO và GPU",
    response_model=SAMStatusResponse
)
def get_sam_status(request: Request):
    """
    Báo cáo trạng thái hoạt động:
      - Thiết bị phần cứng (CUDA GPU hoặc CPU)
      - Trạng thái nạp mô hình Teacher Meta SAM 3
      - Trạng thái nạp mô hình Student YOLO-Seg
      - Số lượng đối tượng đang lưu trong bộ nhớ đệm RAM
    """
    engine = get_sam_engine(request)
    cached_count = len(engine._cached_candidates) if engine._cached_candidates else 0
    return SAMStatusResponse(
        service="TAP AI SAM 3 & Computer Vision Engine",
        status="online",
        device=str(engine.device),
        vision_architecture="Meta SAM 3 (Promptable Concept Segmentation) + YOLO-World (Open-Vocabulary)",
        open_vocabulary_enabled=bool(getattr(engine, "is_open_vocabulary", False)),
        active_vocabulary=getattr(engine, "active_vocabulary", None),
        sam3_teacher_loaded=bool(engine.sam3_loaded),
        student_model_loaded=bool(engine.student_loaded),
        cached_candidates_count=cached_count,
        crops_output_dir=str(engine.output_dir)
    )


# ============================================================================
# 2. QUÉT TOÀN MÀN HÌNH REALTIME (SCREEN SCAN)
# ============================================================================
@router.post(
    "/scan-objects",
    summary="Quét màn hình realtime: phát hiện vật thể, xuất ảnh .webp trong suốt & Contours 60 FPS"
)
async def scan_objects_api(
    request: Request,
    file: Optional[UploadFile] = File(None, description="Tải file ảnh chụp màn hình trực tiếp"),
    extract_all_webp: Optional[bool] = Form(None)
):
    """
    Nhận ảnh chụp khung nhìn viewport từ Chrome Extension Client:
      1. Phân đoạn đa vật thể (Áo, Quần, Váy, Túi xách, Giày, v.v.).
      2. Nén và bóc tách từng vật thể ra định dạng .webp với NỀN TRONG SUỐT (Alpha Channel 4 chiều).
      3. Tạo mảng đỉnh đa giác Contour chuẩn hóa [0.0, 1.0] cho WebGL Canvas viền sáng 60 FPS.
      4. Lưu kết quả vào RAM Cache để người dùng di chuột là có ngay thông tin.
    """
    engine = get_sam_engine(request)
    content_type = request.headers.get("content-type", "")

    img_bgr = None
    extract_webp = True
    custom_vocab = None

    # Phân tích request dạng JSON hoặc Multipart
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Cấu trúc JSON không hợp lệ.")
        image_base64 = body.get("image_base64")
        extract_webp = body.get("extract_all_webp", True)
        custom_vocab = body.get("custom_vocabulary")
        img_bgr, _ = await decode_image_from_request(image_base64=image_base64)
    else:
        # Multipart / Form-data
        if extract_all_webp is not None:
            extract_webp = extract_all_webp
        form = await request.form()
        raw_vocab = form.get("custom_vocabulary")
        if raw_vocab:
            if isinstance(raw_vocab, str):
                import json
                try:
                    custom_vocab = json.loads(raw_vocab)
                except Exception:
                    custom_vocab = [v.strip() for v in raw_vocab.split(",") if v.strip()]
        img_bgr, _ = await decode_image_from_request(file=file)

    # Thực thi quét màn hình với Open-Vocabulary Engine
    result = engine.scan_screen_objects(
        image_source=img_bgr,
        extract_all_webp=extract_webp,
        custom_vocabulary=custom_vocab
    )
    return JSONResponse(content=result)


# ============================================================================
# 3. DI CHUỘT / HIT-TEST SIÊU NHẸ (HOVER < 5MS)
# ============================================================================
@router.post(
    "/segment-hover",
    summary="Hit-test di chuột tức thời trên RAM Cache (< 5ms) trả về viền sáng Contour"
)
async def segment_hover_api(request: Request):
    """
    Khi người dùng di chuột qua các vùng trên trang web:
    Extension gửi tọa độ (tap_x, tap_y) lên server.
    Server kiểm tra nhanh trong RAM Cache và trả về Contour của vật thể đang hover mà không cần chạy lại AI.
    """
    engine = get_sam_engine(request)
    content_type = request.headers.get("content-type", "")

    tap_x = 0.5
    tap_y = 0.5
    is_normalized = True

    if "application/json" in content_type:
        try:
            body = await request.json()
            tap_x = float(body.get("tap_x", 0.5))
            tap_y = float(body.get("tap_y", 0.5))
            is_normalized = bool(body.get("is_normalized", True))
        except Exception:
            raise HTTPException(status_code=400, detail="JSON body không hợp lệ.")
    else:
        form = await request.form()
        tap_x = float(form.get("tap_x", 0.5))
        tap_y = float(form.get("tap_y", 0.5))
        is_normalized = str(form.get("is_normalized", "true")).lower() in ["true", "1"]

    result = engine.hit_test_cached_objects(tap_x=tap_x, tap_y=tap_y, is_normalized=is_normalized)
    return JSONResponse(content=result)


# ============================================================================
# 4. CHẠM ĐỂ MUA (TAP TO BUY) & ĐỒNG BỘ VỚI BACKEND RAG
# ============================================================================
@router.post(
    "/tap-to-buy",
    summary="Chạm/Click vào vật thể: Bóc tách WebP trong suốt và tự động gọi RAG tìm sản phẩm"
)
async def tap_to_buy_api(
    request: Request,
    file: Optional[UploadFile] = File(None, description="Ảnh màn hình nếu có"),
    tap_x: Optional[float] = Form(None),
    tap_y: Optional[float] = Form(None),
    is_normalized: Optional[bool] = Form(None),
    send_to_rag: Optional[bool] = Form(None),
    rag_api_url: Optional[str] = Form(None)
):
    """
    Luồng xử lý cốt lõi của tính năng 'Tap anything, buy anywhere':
      1. Nhận điểm click chuột (tap_x, tap_y) và ảnh màn hình từ Chrome Extension.
      2. Bóc tách chính xác vật thể với NỀN TRONG SUỐT (.webp, 4 kênh BGRA, khử răng cưa).
      3. Rút gọn đường viền đa giác Contour chuẩn hóa [0.0, 1.0].
      4. Tự động chuyển tiếp ảnh WebP sang Backend Search & RAG Pipeline (in-memory hoặc webhook)
         để tìm kiếm link mua sắm Shopee/Lazada và trả về Side Panel cho người dùng.
    """
    engine = get_sam_engine(request)
    search_pipeline = getattr(request.app.state, "search_pipeline", None)
    content_type = request.headers.get("content-type", "")

    img_bgr = None
    target_x = 0.5
    target_y = 0.5
    norm_flag = True
    forward_rag = True
    custom_rag_url = None

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON body không hợp lệ.")

        image_base64 = body.get("image_base64")
        target_x = float(body.get("tap_x", 0.5))
        target_y = float(body.get("tap_y", 0.5))
        norm_flag = bool(body.get("is_normalized", True))
        forward_rag = bool(body.get("send_to_rag", True))
        custom_rag_url = body.get("rag_api_url")

        if image_base64:
            img_bgr, _ = await decode_image_from_request(image_base64=image_base64)
        elif engine._cached_img_bgr is not None:
            # Tái sử dụng frame đã cache trước đó
            img_bgr = engine._cached_img_bgr
        else:
            raise HTTPException(
                status_code=400,
                detail="Chưa có ảnh trong RAM Cache! Vui lòng gửi kèm 'image_base64' hoặc thực hiện scan trước."
            )
    else:
        # Form-data
        if tap_x is not None:
            target_x = float(tap_x)
        if tap_y is not None:
            target_y = float(tap_y)
        if is_normalized is not None:
            norm_flag = is_normalized
        if send_to_rag is not None:
            forward_rag = send_to_rag
        if rag_api_url is not None:
            custom_rag_url = rag_api_url

        if file is not None:
            img_bgr, _ = await decode_image_from_request(file=file)
        elif engine._cached_img_bgr is not None:
            img_bgr = engine._cached_img_bgr
        else:
            raise HTTPException(
                status_code=400,
                detail="Chưa có ảnh trong RAM Cache! Vui lòng upload file hoặc thực hiện scan trước."
            )

    # Thực hiện bóc tách và chuyển tiếp RAG
    result = await engine.tap_and_extract_item(
        image_source=img_bgr,
        tap_x=target_x,
        tap_y=target_y,
        is_normalized=norm_flag,
        send_to_rag=forward_rag,
        search_pipeline_instance=search_pipeline,
        rag_api_url=custom_rag_url
    )

    return JSONResponse(content=result)