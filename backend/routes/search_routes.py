import io
import os
import base64
from typing import Dict, Any, Optional
from PIL import Image
import httpx
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, status
from fastapi.responses import FileResponse, JSONResponse

from models.search_schemas import (
    VideoBatchRequest, 
    VideoDetection, 
    MatchItemRequest, 
    TapAIMetadata,
    TaskStatusEnum,
    TaskSubmitResponse,
    TaskStatusResponse
)
from services.task_manager import task_manager

router = APIRouter(prefix="/api/v1", tags=["Search & RAG Engine"])

@router.get("/image-proxy", summary="Proxy hình ảnh tránh chặn CORS / Hotlinking của sàn TMĐT")
async def image_proxy(url: str):
    """
    Proxy trung gian giúp Chrome Extension và Web Player tải ảnh Shopee/Lazada
    mượt mà, tránh bị chặn bởi chính sách bảo mật CSP hoặc Referer hotlink.
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL không hợp lệ")

    try:
        from fastapi import Response
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                url, 
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://shopee.vn/"
                }
            )
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(content=resp.content, media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Không thể tải ảnh từ URL gốc: {e}")

@router.get("/seasonality/status", summary="Kiểm tra chiến dịch mùa vụ và trọng số xếp hạng hiện tại")
def get_seasonality_status():
    from services.seasonality import SeasonalityEngine
    return SeasonalityEngine.get_weights()

def get_pipeline(request: Request):
    pipeline = getattr(request.app.state, "search_pipeline", None)
    if not pipeline:
        raise HTTPException(status_code=503, detail="Search Pipeline chưa sẵn sàng")
    return pipeline

async def extract_pil_image_from_sources(
    file_bytes: Optional[bytes] = None,
    image_base64: Optional[str] = None,
    image_url: Optional[str] = None
) -> Image.Image:
    # 1. Base64
    if image_base64 and len(image_base64.strip()) > 0:
        clean_b64 = image_base64.strip()
        if "," in clean_b64:
            clean_b64 = clean_b64.split(",", 1)[1]
        try:
            img_bytes = base64.b64decode(clean_b64)
            return Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Dữ liệu Base64 không hợp lệ: {e}")

    # 2. Image URL trực tiếp
    if image_url and len(image_url.strip()) > 0:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(image_url.strip())
                resp.raise_for_status()
                return Image.open(io.BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Không thể tải ảnh từ URL '{image_url}': {e}")

    # 3. File upload trực tiếp
    if file_bytes:
        try:
            return Image.open(io.BytesIO(file_bytes)).convert("RGB")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Không thể đọc file ảnh: {e}")

    raise HTTPException(
        status_code=400,
        detail="Thiếu dữ liệu ảnh! Vui lòng cung cấp 'image_base64', 'image_url', hoặc tải file lên."
    )

# ============================================================================
# 1. INSTANT MATCH (Hỗ trợ Base64, Image URL, File)
# ============================================================================
@router.post(
    "/match-item", 
    summary="Tìm kiếm sản phẩm tức thời cho 1 ảnh crop (Hỗ trợ Base64, Image URL, File)",
    response_model=Dict[str, Any]
)
async def match_single_item(request: Request):
    pipeline = get_pipeline(request)
    content_type = request.headers.get("content-type", "")

    file_bytes = None
    image_base64 = None
    image_url = None
    object_id = "obj_01"
    use_cache = True
    cache_threshold = 0.88
    top_k = 5

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON body không hợp lệ")
        image_base64 = body.get("image_base64")
        image_url = body.get("image_url")
        object_id = body.get("object_id", "obj_01")
        use_cache = body.get("use_cache", True)
        cache_threshold = float(body.get("cache_threshold", 0.88))
        top_k = int(body.get("top_k", 5))
    else:
        # Xử lý Multipart Form Data
        form = await request.form()
        image_base64 = form.get("image_base64")
        image_url = form.get("image_url")
        object_id = form.get("object_id", "obj_01")
        use_cache = str(form.get("use_cache", "true")).lower() in ["true", "1"]
        cache_threshold = float(form.get("cache_threshold", 0.88))
        top_k = int(form.get("top_k", 5))

        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            file_bytes = await uploaded_file.read()

    # Nạp ảnh thành PIL Image
    pil_image = await extract_pil_image_from_sources(
        file_bytes=file_bytes,
        image_base64=image_base64,
        image_url=image_url
    )

    result = await pipeline.process_image(
        image_input=pil_image,
        object_id=object_id,
        use_cache=use_cache,
        cache_threshold=cache_threshold,
        top_k=top_k
    )

    return result

# ============================================================================
# 2. BATCH VIDEO VỚI BACKGROUND WORKER
# ============================================================================
@router.post(
    "/match-video-batch", 
    summary="Xử lý hàng loạt vật thể từ video kèm Deduplication & Background Worker"
)
async def match_video_batch(
    payload: VideoBatchRequest,
    background_tasks: BackgroundTasks,
    request: Request
):
    pipeline = get_pipeline(request)

    if not payload.detections:
        return {"video_id": payload.video_id, "total_objects": 0, "results": []}

    # 1. Chế độ Chạy ngầm Bất đồng bộ (Async Background Mode)
    if payload.async_mode:
        task_id = task_manager.create_task(
            video_id=payload.video_id,
            total_detections=len(payload.detections)
        )

        background_tasks.add_task(
            task_manager.run_video_pipeline,
            task_id=task_id,
            payload=payload,
            pipeline=pipeline
        )

        base_url = str(request.base_url).rstrip("/")
        status_url = f"{base_url}/api/v1/tasks/{task_id}"

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=TaskSubmitResponse(
                task_id=task_id,
                video_id=payload.video_id,
                status=TaskStatusEnum.PENDING,
                message="Video đã được đưa vào hàng đợi xử lý ngầm thành công.",
                status_url=status_url
            ).model_dump()
        )

    # 2. Chế độ Đồng bộ Trực tiếp (Sync Mode)
    task_id = task_manager.create_task(video_id=payload.video_id, total_detections=len(payload.detections))
    await task_manager.run_video_pipeline(task_id, payload, pipeline)
    task_info = task_manager.get_task(task_id)
    return task_info.model_dump()

# ============================================================================
# 3. QUẢN LÝ TIẾN ĐỘ & DOWNLOAD METADATA
# ============================================================================
@router.get(
    "/tasks/{task_id}",
    summary="Kiểm tra tiến độ xử lý video ngầm theo task_id",
    response_model=TaskStatusResponse
)
def get_task_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tác vụ với mã '{task_id}'")
    return task

@router.get(
    "/tasks/{task_id}/download",
    summary="Tải về file metadata.json hoàn chỉnh của tác vụ"
)
def download_task_metadata(task_id: str):
    file_path = os.path.join(task_manager.output_dir, f"{task_id}_metadata.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Chưa có file metadata.json cho task '{task_id}'.")

    return FileResponse(
        path=file_path,
        media_type="application/json",
        filename=f"{task_id}_metadata.json"
    )
