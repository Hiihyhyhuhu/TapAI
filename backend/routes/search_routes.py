import io
import os
import base64
from typing import Dict, Any, Optional
from PIL import Image
import httpx
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, status, UploadFile, File, Form
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

_PROXY_CACHE: Dict[str, tuple] = {}
_PROXY_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.5), follow_redirects=True)

@router.get("/image-proxy", summary="Proxy hình ảnh tránh chặn CORS / Hotlinking của sàn TMĐT")
async def image_proxy(url: str):
    """
    Proxy trung gian giúp Chrome Extension và Web Player tải ảnh Shopee/Lazada
    mượt mà, tránh bị chặn bởi chính sách bảo mật CSP hoặc Referer hotlink.
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL không hợp lệ")

    # Kiểm tra RAM cache
    if url in _PROXY_CACHE:
        cached_content, cached_type = _PROXY_CACHE[url]
        from fastapi import Response
        return Response(
            content=cached_content,
            media_type=cached_type,
            headers={"Cache-Control": "public, max-age=86400, immutable"}
        )

    try:
        from fastapi import Response
        resp = await _PROXY_CLIENT.get(
            url, 
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://shopee.vn/"
            }
        )
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg")
        
        # Lưu cache tối đa 100 ảnh
        if len(_PROXY_CACHE) > 100:
            _PROXY_CACHE.pop(next(iter(_PROXY_CACHE)))
        _PROXY_CACHE[url] = (resp.content, content_type)

        return Response(
            content=resp.content, 
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400, immutable"}
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Không thể tải ảnh từ URL gốc: {e}")

@router.get("/ranking-mode", summary="Kiểm tra chế độ xếp hạng hiện tại của Search Engine")
def get_ranking_mode():
    return {
        "mode": "pure_similarity",
        "description": "Tối ưu hóa 100% độ tương đồng thị giác - trả về sản phẩm khớp nhất",
        "affiliate_enabled": False,
        "seasonality_enabled": False
    }

@router.get("/seasonality/status", deprecated=True, summary="[Deprecated] Endpoint mùa vụ cũ (đã chuyển sang Pure Similarity)")
def get_seasonality_status():
    return {
        "status": "deprecated",
        "mode": "pure_similarity",
        "message": "Optuna và Auto-Seasonality đã được loại bỏ. Hệ thống hiện tối ưu hóa trả về sản phẩm khớp nhất."
    }

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
    "/match-item/upload", 
    summary="[TEST TRỰC TIẾP] Tải file ảnh lên từ máy tính (Có nút chọn file)",
    response_model=Dict[str, Any]
)
async def match_single_item_upload(
    request: Request,
    file: UploadFile = File(..., description="Chọn file ảnh WebP/PNG/JPG từ máy tính của bạn"),
    object_id: str = Form("obj_01", description="Mã định danh vật thể"),
    top_k: int = Form(5, ge=1, le=20, description="Số sản phẩm cần lấy (mặc định 5, tối đa 20)")
):
    """
    Endpoint hỗ trợ tải file ảnh trực tiếp qua giao diện Swagger UI:
    - Bấm nút 'Try it out' -> Bấm 'Choose File' để chọn ảnh từ máy tính.
    - Hệ thống xử lý qua luồng cốt lõi: Gemini VLM -> Serper Shopee Searcher -> Gemini Reranker.
    """
    pipeline = get_pipeline(request)
    file_bytes = await file.read()
    pil_image = await extract_pil_image_from_sources(file_bytes=file_bytes)

    result = await pipeline.process_image(
        image_input=pil_image,
        object_id=object_id,
        top_k=top_k
    )
    return result

@router.post(
    "/match-item", 
    summary="Tìm kiếm sản phẩm tức thời cho 1 ảnh crop (JSON Base64 hoặc Image URL cho Extension)",
    response_model=Dict[str, Any]
)
async def match_single_item(
    request: Request,
    payload: MatchItemRequest
):
    """
    Endpoint JSON phục vụ Chrome Extension:
    - `image_base64`: Chuỗi Base64 của ảnh crop từ video player.
    - `image_url`: URL trực tiếp của ảnh trên web.
    """
    pipeline = getattr(request.app.state, "search_pipeline", None)
    if not pipeline:
        return {
            "object_id": payload.object_id,
            "query_used": "thời trang xu hướng Shopee",
            "search_status": "mock_preview",
            "message": "Search Pipeline đang chạy ở chế độ Mock Preview do chưa cấu hình GEMINI_API_KEY trong .env.",
            "products": [
                {
                    "item_id": f"sp_{payload.object_id}_1",
                    "title": "[Gợi ý RAG] Thời Trang Cao Cấp Xu Hướng Trẻ",
                    "price": "289.000₫",
                    "originalPrice": "420.000₫",
                    "thumbnail_url": payload.image_url or "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=500&auto=format&fit=crop&q=60",
                    "platform": "Shopee Mall",
                    "product_url": "https://shopee.vn",
                    "match_score": 0.94,
                    "commission_rate": 0.15
                },
                {
                    "item_id": f"sp_{payload.object_id}_2",
                    "title": "[Gợi ý RAG] Thiết Kế Tinh Tế Chính Hãng",
                    "price": "345.000₫",
                    "originalPrice": "490.000₫",
                    "thumbnail_url": "https://images.unsplash.com/photo-1542272604-780c96856592?w=500&auto=format&fit=crop&q=60",
                    "platform": "Lazada",
                    "product_url": "https://lazada.vn",
                    "match_score": 0.89,
                    "commission_rate": 0.10
                }
            ]
        }

    pil_image = await extract_pil_image_from_sources(
        image_base64=payload.image_base64,
        image_url=payload.image_url
    )

    result = await pipeline.process_image(
        image_input=pil_image,
        object_id=payload.object_id,
        top_k=payload.top_k,
        image_url=payload.image_url
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
