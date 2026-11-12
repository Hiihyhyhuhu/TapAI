from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.search_pipeline import TapAISearchPipeline
from routes.search_routes import router as search_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo Pipeline Search cốt lõi
    print("🚀 Đang khởi động Tap AI Backend Server...")
    app.state.search_pipeline = TapAISearchPipeline()
    print("✅ Tap AI Backend đã sẵn sàng phục vụ!\n")
    yield
    print("🛑 Đang dừng server và giải phóng tài nguyên...")

app = FastAPI(
    title="Tap AI Backend API",
    description="Interactive Shoppable Media Engine Backend (FastAPI + Gemini 3.5 Flash VLM + Serper Search + Background Worker)",
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

@app.get("/health", tags=["System"])
def health_check():
    pipeline = getattr(app.state, "search_pipeline", None)
    return {
        "status": "healthy",
        "service": "Tap AI Backend",
        "pipeline_ready": pipeline is not None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["services", "routes", "models"])
