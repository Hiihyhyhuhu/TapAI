import os
from typing import Dict, Any

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    from celery import Celery
    celery_app = Celery(
        "tap_ai_worker",
        broker=REDIS_URL,
        backend=REDIS_URL
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Ho_Chi_Minh",
        enable_utc=True,
    )

    @celery_app.task(name="process_video_celery_task", bind=True)
    def process_video_celery_task(self, payload_dict: Dict[str, Any]):
        """
        Celery Task chạy ngầm xử lý video batch trên cluster worker riêng.
        """
        import asyncio
        from models.search_schemas import VideoBatchRequest
        from services.search_pipeline import TapAISearchPipeline
        from services.task_manager import task_manager

        payload = VideoBatchRequest.model_validate(payload_dict)
        pipeline = TapAISearchPipeline()
        task_id = self.request.id

        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            task_manager.run_video_pipeline(task_id, payload, pipeline)
        )
        return {"status": "SUCCESS", "task_id": task_id, "video_id": payload.video_id}

except ImportError:
    celery_app = None
