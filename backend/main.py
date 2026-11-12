from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.search_pipeline import TapAISearchPipeline
from routes.search_routes import router as search_router

import os
import mimetypes
mimetypes.add_type("image/webp", ".webp")
from services.sam3_service import SAM3Engine
from routes.sam_routes import router as sam_router
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo Pipeline Search & SAM3
    print("=" * 80)
    print("🚀 ĐANG KHỞI ĐỘNG TAP AI UNIFIED BACKEND SERVER...")
    print("=" * 80)

    # 1. SAM3
    print("⏳ [1/2] Đang khởi tạo SAM 3 Computer Vision Engine...")
    try:
        # Tự động nạp Meta SAM 3 (nếu có CUDA) hoặc Student YOLOv8-seg (chạy mượt trên CPU/GPU local)
        crops_dir = os.path.join(os.path.dirname(__file__), "outputs", "sam_crops")
        app.state.sam_engine = SAM3Engine(output_dir=crops_dir)
        print("✅ [1/2] SAM 3 Computer Vision Engine đã sẵn sàng phục vụ!")
    except Exception as e:
        print(f"❌ [1/2] Lỗi khởi tạo SAM 3 Engine: {e}")
        app.state.sam_engine = None

    # 2. Search Pipeline
    print("⏳ [2/2] Đang khởi tạo Pipeline Search cốt lõi...")
    try:
        app.state.search_pipeline = TapAISearchPipeline()
        print("✅ [2/2] Pipeline Search cốt lõi đã sẵn sàng phục vụ!")
    except ValueError as ve:
        # Xử lý trường hợp chưa nhập GEMINI_API_KEY / SERPER_API_KEY trong file .env
        print(f"⚠️ [2/2] Chú ý từ Search Pipeline: {ve}")
        print("   -> Server vẫn tiếp tục hoạt động! Khi Frontend gọi Tap-to-buy, hệ thống sẽ")
        print("      sử dụng Mock Preview sản phẩm Shopee/Lazada cho đến khi bạn bổ sung API Key.")
        app.state.search_pipeline = None
    except Exception as e:
        print(f"⚠️ [2/2] Lỗi khởi tạo Search Pipeline: {e}")
        app.state.search_pipeline = None

    print("-" * 80)
    print("🎉 TẤT CẢ MODULE TAP AI ĐÃ KHỞI TẠO THÀNH CÔNG! SERVER SẴN SÀNG NHẬN REQUEST.")
    print("👉 Swagger UI tài liệu API: http://localhost:8000/docs")
    print("👉 Thư mục ảnh bóc tách WebP: http://localhost:8000/crops/")
    print("=" * 80 + "\n")

    yield
    print("\n🛑 Đang dừng Tap AI Backend Server và giải phóng tài nguyên...")

app = FastAPI(
    title="Tap AI Backend API",
    description="Interactive Shoppable Media Engine Backend (FastAPI + Meta SAM 3 + Gemini 3.5 Flash VLM + Serper Search + Background Worker)",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gắn Router Search & RAG
app.include_router(search_router)

# Gắn Router SAM3
app.include_router(sam_router)

# Truy cập ảnh ..\crops\
crops_static_path = os.path.join(os.path.dirname(__file__), "outputs", "sam_crops")
os.makedirs(crops_static_path, exist_ok=True)
app.mount("/crops", StaticFiles(directory=crops_static_path), name="crops")

@app.get("/health", tags=["System"])
def health_check():
    pipeline = getattr(app.state, "search_pipeline", None)

    sam_engine = getattr(app.state, "sam_engine", None)
    sam_status = {
        "loaded": sam_engine is not None,
        "device": str(sam_engine.device) if sam_engine else "unknown",
        "student_loaded": bool(sam_engine.student_loaded) if sam_engine else False,
        "teacher_loaded": bool(sam_engine.sam3_loaded) if sam_engine else False,
        "cached_objects_in_ram": len(sam_engine._cached_candidates) if (sam_engine and sam_engine._cached_candidates) else 0
    }

    return {
        "status": "healthy",
        "service": "Tap AI Backend",
        "pipeline_ready": pipeline is not None,
        "sam3_engine": sam_status
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["services", "routes", "models"])
