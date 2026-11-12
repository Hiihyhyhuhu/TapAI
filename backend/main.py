from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.connection import init_db
from routes.search_routes import router as search_router
from routes.auth_routes import router as auth_router
from routes.shop_routes import router as shop_router
from routes.admin_routes import router as admin_router
from routes.product_routes import router as product_router
from routes.tracking_routes import router as tracking_router
from routes.report_routes import router as report_router
from routes.reconciliation_routes import router as reconciliation_router
from fastapi.staticfiles import StaticFiles

import os
import mimetypes
mimetypes.add_type("image/webp", ".webp")
from services.sam3_service import SAM3Engine
from routes.sam_routes import router as sam_router
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 80)
    print("🚀 ĐANG KHỞI ĐỘNG TAP AI UNIFIED BACKEND SERVER...")
    print("=" * 80)

    # 1. Khởi tạo Database Tables (Affiliate Portal)
    try:
        init_db()
        print("💾 Database tables (Affiliate Portal) đã sẵn sàng.")
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo Database tables: {e}")

    # Tạo thư mục uploads
    uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # 2. SAM3 Computer Vision Engine
    print("⏳ [1/2] Đang khởi tạo SAM 3 Computer Vision Engine...")
    try:
        crops_dir = os.path.join(os.path.dirname(__file__), "outputs", "sam_crops")
        app.state.sam_engine = SAM3Engine(output_dir=crops_dir)
        print("✅ [1/2] SAM 3 Computer Vision Engine đã sẵn sàng phục vụ!")
    except Exception as e:
        print(f"❌ [1/2] Lỗi khởi tạo SAM 3 Engine: {e}")
        app.state.sam_engine = None

    # 3. Search Pipeline
    print("⏳ [2/2] Đang khởi tạo Pipeline Search cốt lõi...")
    api_key = os.getenv("GEMINI_API_KEY")
    skip_pipeline = os.getenv("SKIP_PIPELINE_INIT", "false").lower() in ("true", "1", "yes")
    if api_key and not skip_pipeline:
        try:
            from services.search_pipeline import TapAISearchPipeline
            app.state.search_pipeline = TapAISearchPipeline()
            print("✅ [2/2] Pipeline Search cốt lõi đã sẵn sàng phục vụ!")
        except Exception as e:
            print(f"⚠️ [2/2] Chú ý từ Search Pipeline: {e}")
            app.state.search_pipeline = None
    else:
        print("⏩ [2/2] Bỏ qua khởi tạo Search Pipeline (chưa cấu hình GEMINI_API_KEY hoặc Test Mode).")
        app.state.search_pipeline = None

    print("-" * 80)
    print("🎉 TẤT CẢ MODULE TAP AI ĐÃ KHỞI TẠO THÀNH CÔNG! SERVER SẴN SÀNG NHẬN REQUEST.")
    print("👉 Swagger UI tài liệu API: http://localhost:8000/docs")
    print("👉 Merchant Web Portal: http://localhost:8000/portal/index.standalone.html")
    print("=" * 80 + "\n")
    yield
    print("\n🛑 Đang dừng Tap AI Backend Server và giải phóng tài nguyên...")

app = FastAPI(
    title="Tap AI Backend API",
    description="Interactive Shoppable Media Engine & Affiliate Portal Backend (FastAPI + Meta SAM 3 + Gemini 3.5 Flash VLM + Serper Search + Background Worker)",
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

# Mount Static Files (Uploads)
uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Mount Static Files (Portal Frontend)
portal_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "portal"))
if os.path.isdir(portal_dir):
    app.mount("/portal", StaticFiles(directory=portal_dir, html=True), name="portal")

from fastapi.responses import RedirectResponse, Response

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    svg_data = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#10B981"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'''
    return Response(content=svg_data, media_type="image/svg+xml")

@app.get("/", tags=["System"])
def root_redirect():
    return RedirectResponse(url="/portal/index.standalone.html")

@app.get("/dashboard", tags=["System"])
def dashboard_redirect():
    return RedirectResponse(url="/portal/index.standalone.html")

# Gắn Routers
app.include_router(search_router)
app.include_router(auth_router)
app.include_router(shop_router)
app.include_router(admin_router)
app.include_router(product_router)
app.include_router(tracking_router)
app.include_router(report_router)
app.include_router(reconciliation_router)

from routes.tracking_routes import redirect_to_affiliate
from database.connection import get_db
from fastapi import Depends, Request, Query
from typing import Optional

# ==============================================================================
# DIRECT MERCHANT PORTAL - STAGE 4: REDIRECT GATEWAY
# GET https://portal.domain.com/r/{product_id}?ext_uid={user_id}
# ==============================================================================
@app.get("/r/{product_id}", tags=["Tracking Engine (Clicks & Conversions)"], summary="STAGE 4: Redirect Gateway chuyển hướng người dùng từ Extension Sidebar")
def direct_cpc_redirect_gateway(
    product_id: str,
    request: Request,
    ext_uid: Optional[str] = Query(None, description="Mã người dùng Extension"),
    test_fraud: Optional[str] = Query(None, description="bot | duplicate (Dành cho thử nghiệm QA)"),
    db = Depends(get_db)
):
    from services.tracking_service import handle_cpc_redirect_gateway
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")
    res = handle_cpc_redirect_gateway(
        db=db,
        product_id=product_id,
        ext_uid=ext_uid,
        client_ip=client_ip,
        user_agent=user_agent,
        test_fraud=test_fraud
    )
    return RedirectResponse(url=res["redirect_url"], status_code=302)

@app.get("/api/v1/redirect/{product_id}", tags=["Tracking Engine (Clicks & Conversions)"], summary="Alias trực tiếp cho luồng redirect từ Extension Sidebar")
def direct_affiliate_redirect(
    product_id: str,
    request: Request,
    ext_user_id: Optional[str] = Query(None, alias="ext_uid"),
    source: str = "EXTENSION_SIDEBAR",
    test_fraud: Optional[str] = None,
    db = Depends(get_db)
):
    return redirect_to_affiliate(product_id=product_id, request=request, ext_user_id=ext_user_id, source=source, test_fraud=test_fraud, db=db)

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
