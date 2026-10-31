import io
import os
import json
import time
import base64
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from PIL import Image

from models.search_schemas import (
    VideoBatchRequest,
    VideoDetection,
    TaskStatusEnum,
    TaskStatusResponse,
    TapAIMetadata,
    MediaMetadata,
    TrackedObject,
    ProductCandidate,
    TimelineFrame,
    ObjectDetectionOverlay
)
from services.search_pipeline import TapAISearchPipeline

class VideoTaskManager:
    """
    Quản lý các tác vụ xử lý video dài chạy bất đồng bộ dưới nền (Background Worker Engine):
    - Đảm bảo HTTP request không bị treo (non-blocking).
    - Cung cấp API tra cứu tiến độ real-time (% hoàn thành & bước hiện tại).
    - Tự động đóng gói output thành chuẩn TapAIMetadata (metadata.json) hoàn chỉnh.
    """
    def __init__(self, output_dir: str = "./output_tasks"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.tasks: Dict[str, Dict[str, Any]] = {}

    def create_task(self, video_id: str, total_detections: int) -> str:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()
        self.tasks[task_id] = {
            "task_id": task_id,
            "video_id": video_id,
            "status": TaskStatusEnum.PENDING,
            "progress": 0.0,
            "current_step": "Đang xếp hàng chờ xử lý...",
            "created_at": now_str,
            "updated_at": now_str,
            "total_detections": total_detections,
            "unique_objects": 0,
            "result": None,
            "error": None
        }
        return task_id

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatusEnum] = None,
        progress: Optional[float] = None,
        current_step: Optional[str] = None,
        unique_objects: Optional[int] = None,
        result: Optional[TapAIMetadata] = None,
        error: Optional[str] = None
    ):
        if task_id not in self.tasks:
            return
        task = self.tasks[task_id]
        if status is not None:
            task["status"] = status
        if progress is not None:
            task["progress"] = round(progress, 2)
        if current_step is not None:
            task["current_step"] = current_step
        if unique_objects is not None:
            task["unique_objects"] = unique_objects
        if result is not None:
            task["result"] = result
        if error is not None:
            task["error"] = error
        task["updated_at"] = datetime.now().isoformat()

    def get_task(self, task_id: str) -> Optional[TaskStatusResponse]:
        if task_id not in self.tasks:
            meta_path = os.path.join(self.output_dir, f"{task_id}_metadata.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return TaskStatusResponse(
                        task_id=task_id,
                        video_id=data.get("media_info", {}).get("media_id", "unknown"),
                        status=TaskStatusEnum.COMPLETED,
                        progress=1.0,
                        current_step="Tải từ bộ nhớ đĩa",
                        created_at=data.get("generated_at", ""),
                        updated_at=data.get("generated_at", ""),
                        total_detections=0,
                        unique_objects=len(data.get("objects", {})),
                        result=TapAIMetadata.model_validate(data)
                    )
                except Exception:
                    pass
            return None

        t = self.tasks[task_id]
        return TaskStatusResponse(
            task_id=t["task_id"],
            video_id=t["video_id"],
            status=t["status"],
            progress=t["progress"],
            current_step=t["current_step"],
            created_at=t["created_at"],
            updated_at=t["updated_at"],
            total_detections=t["total_detections"],
            unique_objects=t["unique_objects"],
            result=t["result"],
            error=t["error"]
        )

    async def run_video_pipeline(
        self,
        task_id: str,
        payload: VideoBatchRequest,
        pipeline: TapAISearchPipeline
    ):
        """Worker chính xử lý pipeline video bất đồng bộ dưới nền"""
        try:
            self.update_task(
                task_id,
                status=TaskStatusEnum.PROCESSING,
                progress=0.05,
                current_step=f"Bắt đầu gom nhóm deduplication {len(payload.detections)} detections..."
            )

            # 1. DEDUPLICATION
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

            total_unique = len(grouped_objects)
            self.update_task(
                task_id,
                progress=0.10,
                current_step=f"Đã deduplicate thành {total_unique} vật thể duy nhất. Bắt đầu tìm kiếm sàn...",
                unique_objects=total_unique
            )

            # 2. XỬ LÝ SEARCH & RERANK
            tracked_objects: Dict[str, TrackedObject] = {}
            for idx, (obj_id, best_det) in enumerate(grouped_objects.items(), start=1):
                step_progress = 0.10 + (idx / total_unique) * 0.75
                self.update_task(
                    task_id,
                    progress=step_progress,
                    current_step=f"Đang xử lý vật thể [{idx}/{total_unique}]: '{obj_id}' (Frame {best_det.frame_index})..."
                )

                try:
                    clean_b64 = best_det.image_base64
                    if "," in clean_b64:
                        clean_b64 = clean_b64.split(",", 1)[1]
                    img_bytes = base64.b64decode(clean_b64)
                    pil_image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

                    search_res = await pipeline.process_image(
                        image_input=pil_image,
                        object_id=obj_id,
                        use_cache=payload.use_cache,
                        top_k=payload.top_k
                    )

                    candidates = [
                        ProductCandidate(
                            item_id=p.get("item_id", ""),
                            title=p.get("title", ""),
                            price=p.get("price", ""),
                            platform=p.get("platform", "Shopee"),
                            product_url=p.get("product_url", ""),
                            thumbnail_url=p.get("thumbnail_url", ""),
                            query_used=p.get("query_used", ""),
                            match_score=p.get("match_score", 0.0),
                            match_reason=p.get("match_reason")
                        )
                        for p in search_res.get("products", [])
                    ]

                    tracked_objects[obj_id] = TrackedObject(
                        object_id=obj_id,
                        label=search_res.get("exact_query", f"Sản phẩm {obj_id}"),
                        category=search_res.get("detected_category", "Thời trang"),
                        primary_color=None,
                        matched_products=candidates
                    )

                except Exception as ex:
                    print(f"⚠️ Lỗi khi xử lý vật thể '{obj_id}' trong task '{task_id}': {ex}")
                    tracked_objects[obj_id] = TrackedObject(
                        object_id=obj_id,
                        label=f"Vật thể {obj_id}",
                        category="Không xác định",
                        matched_products=[]
                    )

            # 3. TIMELINE TRACKING
            self.update_task(
                task_id,
                progress=0.90,
                current_step="Đang xây dựng timeline tọa độ 60 FPS cho video..."
            )

            frames_map: Dict[int, List[ObjectDetectionOverlay]] = {}
            for det in payload.detections:
                f_idx = det.frame_index
                if f_idx not in frames_map:
                    frames_map[f_idx] = []
                frames_map[f_idx].append(
                    ObjectDetectionOverlay(
                        object_id=det.object_id,
                        bbox=det.bbox,
                        confidence=det.confidence or 1.0,
                        polygon=det.polygon
                    )
                )

            fps = payload.fps or 30.0
            timeline: List[TimelineFrame] = []
            for f_idx in sorted(frames_map.keys()):
                ts = det.timestamp if det.timestamp is not None else round(f_idx / fps, 3)
                timeline.append(
                    TimelineFrame(
                        timestamp=ts,
                        frame_index=f_idx,
                        detections=frames_map[f_idx]
                    )
                )

            # 4. EXPORT TAP_AI_METADATA
            self.update_task(
                task_id,
                progress=0.95,
                current_step="Đang xuất file metadata.json hoàn chỉnh..."
            )

            media_info = MediaMetadata(
                media_id=payload.video_id,
                media_type="video",
                duration_sec=payload.duration_sec,
                fps=fps,
                resolution=payload.resolution
            )

            final_metadata = TapAIMetadata(
                version="1.0.0",
                generated_at=datetime.now().isoformat(),
                media_info=media_info,
                objects=tracked_objects,
                timeline=timeline
            )

            out_file = os.path.join(self.output_dir, f"{task_id}_metadata.json")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(final_metadata.model_dump_json(indent=2))

            video_alias_file = os.path.join(self.output_dir, f"{payload.video_id}_metadata.json")
            with open(video_alias_file, "w", encoding="utf-8") as f:
                f.write(final_metadata.model_dump_json(indent=2))

            print(f"🎉 [TASK COMPLETED] Task '{task_id}' (Video: '{payload.video_id}') đã hoàn tất thành công! Xuất file: {out_file}")

            self.update_task(
                task_id,
                status=TaskStatusEnum.COMPLETED,
                progress=1.0,
                current_step="Hoàn tất xử lý video!",
                result=final_metadata
            )

        except Exception as e:
            print(f"❌ [TASK FAILED] Task '{task_id}' thất bại: {e}")
            self.update_task(
                task_id,
                status=TaskStatusEnum.FAILED,
                error=str(e),
                current_step="Tác vụ gặp sự cố"
            )

task_manager = VideoTaskManager()
