import io
import base64
from typing import Dict, Any, Optional
from PIL import Image
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from models.search_schemas import VideoBatchRequest, VideoDetection

router = APIRouter(prefix="/api/v1", tags=["Search & RAG Engine"])

def get_pipeline(request: Request):
    pipeline = getattr(request.app.state, "search_pipeline", None)
    if not pipeline:
        raise HTTPException(status_code=503, detail="Search Pipeline chưa sẵn sàng")
    return pipeline

@router.post("/match-item", summary="Tìm kiếm sản phẩm tức thời cho 1 ảnh crop (Instant Image Tagging)")
async def match_single_item(
    request: Request,
    file: UploadFile = File(..., description="File ảnh crop vật thể từ SAM 3"),
    object_id: str = Form("obj_01", description="Mã định danh vật thể"),
    use_cache: bool = Form(True, description="Bật/tắt kiểm tra bộ nhớ đệm Vector DB"),
    cache_threshold: float = Form(0.88, description="Ngưỡng tương đồng cosine để coi là cache hit (0.0 - 1.0)"),
    top_k: int = Form(5, description="Số lượng sản phẩm trả về"),
):
    pipeline = get_pipeline(request)

    try:
        content = await file.read()
        pil_image = Image.open(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể đọc file ảnh: {e}")

    result = await pipeline.process_image(
        image_input=pil_image,
        object_id=object_id,
        use_cache=use_cache,
        cache_threshold=cache_threshold,
        top_k=top_k
    )

    return result

@router.post("/match-video-batch", summary="Xử lý hàng loạt vật thể từ video kèm Deduplication")
async def match_video_batch(request: Request, payload: VideoBatchRequest):
    """
    Xử lý deduplication:
    Trong 1 video, một vật thể (VD chiếc áo obj_01) xuất hiện ở 300 frames.
    Endpoint này tự động gom nhóm theo `object_id`, chọn ra 1 frame duy nhất có
    diện tích bbox (width * height) lớn nhất và ít bị che khuất nhất để xử lý tìm kiếm.
    """
    pipeline = get_pipeline(request)

    if not payload.detections:
        return {"video_id": payload.video_id, "total_objects": 0, "results": []}

    # 1. Deduplication: Gom nhóm theo object_id và chọn detection tốt nhất
    grouped_objects: Dict[str, VideoDetection] = {}

    for det in payload.detections:
        x1, y1, x2, y2 = det.bbox
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        score = area * (det.confidence or 1.0)

        if det.object_id not in grouped_objects:
            det._score = score
            grouped_objects[det.object_id] = det
        else:
            if score > getattr(grouped_objects[det.object_id], "_score", 0.0):
                det._score = score
                grouped_objects[det.object_id] = det

    print(f"🎬 [DEDUPLICATION] Video '{payload.video_id}' có {len(payload.detections)} detections gom lại thành {len(grouped_objects)} vật thể duy nhất.")

    # 2. Xử lý tìm kiếm cho từng vật thể đại diện duy nhất
    results = []
    for obj_id, best_det in grouped_objects.items():
        try:
            img_bytes = base64.b64decode(best_det.image_base64)
            pil_image = Image.open(io.BytesIO(img_bytes))

            res = await pipeline.process_image(
                image_input=pil_image,
                object_id=obj_id,
                use_cache=payload.use_cache,
                top_k=payload.top_k
            )
            res["best_frame_index"] = best_det.frame_index
            res["bbox"] = best_det.bbox
            results.append(res)
        except Exception as e:
            print(f"⚠️ Lỗi khi xử lý vật thể '{obj_id}': {e}")
            results.append({
                "object_id": obj_id,
                "error": str(e),
                "best_frame_index": best_det.frame_index
            })

    return {
        "video_id": payload.video_id,
        "total_detections_input": len(payload.detections),
        "unique_objects_processed": len(grouped_objects),
        "results": results
    }
