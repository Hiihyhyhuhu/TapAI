# TAP AI - Backend Engine

Hệ thống xử lý tương tác video và tìm kiếm sản phẩm thương mại điện tử (**Shoppable Media Engine**) xây dựng trên nền tảng **FastAPI**.

---

## 🛠️ 1. Cấu trúc thư mục Backend

```text
backend/
├── main.py                     # Entrypoint khởi tạo server FastAPI & CORS middleware
├── requirements.txt            # Danh sách thư viện phụ thuộc (FastAPI, Qdrant, Optuna, v.v.)
├── .env.example                # Mẫu biến môi trường (API Keys)
├── metadata_sample.json        # Chuẩn Data Contract 20 sản phẩm mẫu cho Frontend Side Panel
├── routes/
│   └── search_routes.py        # API Endpoints: match-item, match-video-batch, tasks, proxy, seasonality
├── services/
│   ├── query_generator.py      # Module A: VLM Gemini trích xuất ngữ cảnh từ ảnh crop SAM 3
│   ├── shopee_searcher.py      # Module B: Quét và lọc link Shopee/Lazada thực tế qua Serper (Top 20-25)
│   ├── reranker.py             # Module C: Multimodal VLM Reranking & Optuna Pareto Multi-Objective Scoring
│   ├── seasonality.py          # Auto-Seasonality Engine (Tự động thích ứng mùa mua sắm & hoa hồng)
│   ├── rag_cache.py            # Module D: Bộ nhớ đệm Vector DB (Qdrant + Meta DINOv2)
│   ├── search_pipeline.py      # Pipeline tích hợp 4 module luồng Cache-First
│   ├── task_manager.py         # Dual-Engine: In-process Async Background Task Worker & Polling
│   └── celery_worker.py        # Dual-Engine: Celery + Redis production worker (dành cho scale lớn)
├── models/
│   └── search_schemas.py       # Pydantic Schemas (TapAIMetadata, MatchItemRequest, VideoBatchRequest...)
├── types/
│   └── search_schemas.py       # Xuất khẩu Types hỗ trợ typing
├── scripts/
│   ├── test_search_pipeline.py # Script test độc lập kiểm thử pipeline
│   ├── tune_ranking_optuna.py  # Script tối ưu đa mục tiêu (Pareto Front) bằng Optuna NSGA-II
│   └── test_images/            # Thư mục chứa ảnh mẫu test
│       └── sample.jpg
└── controllers/                # Dành cho logic mở rộng sau này
```

---

## 🚀 2. Cài đặt & Khởi động

### Bước 1: Chuẩn bị Môi trường ảo & Thư viện
```powershell
# Di chuyển vào thư mục backend
cd backend

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### Bước 2: Cấu hình API Keys
Sao chép `.env.example` thành `.env` và điền các API Keys:
```env
GEMINI_API_KEY=your_gemini_api_key_here
SERPER_API_KEY=your_serper_api_key_here
QDRANT_HOST=localhost
QDRANT_PORT=6333
# Tùy chọn cấu hình mùa vụ nếu muốn ghi đè thủ công:
# FORCE_SEASON=MEGA_SALE
```

### Bước 3: Khởi động Server FastAPI
```powershell
uvicorn main:app --reload --port 8000
```
Sau khi server bật, truy cập Swagger UI trực quan tại:
👉 **[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## 📡 3. Danh sách API Endpoints

### 1. `POST /api/v1/match-item` *(Instant Image Tagging)*
* **Mô tả**: Nhận 1 ảnh crop đơn lẻ khi người dùng click vào vật thể trên ảnh hoặc frame video.
* **Hỗ trợ đa phương thức (Hybrid Input)**:
  - JSON Body với `image_base64` hoặc `image_url`.
  - Hoặc `multipart/form-data` upload file ảnh trực tiếp (`file`).
* **Luồng xử lý**: Kiểm tra Qdrant Cache $\rightarrow$ (Nếu miss) Gọi Gemini VLM + Serper + Rerank $\rightarrow$ Lưu Cache $\rightarrow$ Trả kết quả JSON danh sách sản phẩm xếp hạng.

### 2. `POST /api/v1/match-video-batch` *(Video Pre-processing & Async Task)*
* **Mô tả**: Nhận danh sách các detections của SAM 3 trong toàn bộ video và kích hoạt tìm kiếm.
* **Hỗ trợ 2 chế độ**:
  - `async_mode=True` (Mặc định): Trả về ngay lập tức HTTP `202 Accepted` cùng `task_id` để client không bị timeout khi xử lý video dài.
  - `async_mode=False`: Xử lý đồng bộ và trả về trực tiếp `TapAIMetadata`.
* **Tính năng Deduplication**: Tự động gom nhóm các bounding boxes theo `object_id`. Nếu 1 chiếc áo xuất hiện ở 300 frame, hệ thống sẽ tự động tính điểm đại diện $width \times height \times confidence$ và chỉ chọn đúng 1 frame rõ nhất để tìm kiếm 1 lần duy nhất.
* **Mở rộng 20 sản phẩm**: Tự động trả về tối đa 20 sản phẩm xếp hạng cao nhất cho mỗi vật thể để phục vụ danh sách scrollable trên Chrome Extension Side Panel.

### 3. `GET /api/v1/tasks/{task_id}` *(Task Progress Polling)*
* **Mô tả**: Kiểm tra trạng thái và tiến độ xử lý video ngầm (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`).
* **Phản hồi**: Bao gồm `progress` (0 - 100%), thông tin chi tiết và toàn bộ payload `TapAIMetadata` khi hoàn thành.

### 4. `GET /api/v1/tasks/{task_id}/download` *(Export metadata.json)*
* **Mô tả**: Tải trực tiếp file `metadata.json` đã chuẩn hóa (normalized coordinates 0.0 - 1.0, 20 sản phẩm kèm link affiliate).

### 5. `GET /api/v1/image-proxy` *(Image CORS & Anti-Hotlink Bypass)*
* **Mô tả**: Proxy chuyển tiếp hình ảnh từ Shopee / Lazada / TikTok Shop để vượt qua cơ chế chặn Hotlinking và CORS của các sàn, hỗ trợ Chrome Extension render ảnh mượt mà.
* **Tham số**: `?url=https://cf.shopee.vn/file/...`

### 6. `GET /api/v1/seasonality/status` *(Seasonality Status)*
* **Mô tả**: Xem thông tin mùa vụ hiện tại đang áp dụng (`DEFAULT`, `MEGA_SALE`, `TET_HOLIDAY`), trọng số $A$ (Similarity), $B$ (Commission), và ngưỡng lọc an toàn (Similarity Gate).
* **Tham số tùy chọn**: `?override=MEGA_SALE` để ép hệ thống chuyển chế độ theo ý muốn.

---

## 🎯 4. Thuật toán Xếp hạng (Optuna Pareto Multi-Objective Reranking)

Hệ thống tính điểm xếp hạng dựa trên sự cân bằng giữa độ chính xác thị giác và tối ưu doanh thu tiếp thị liên kết:

$$\text{Score} = A \times \text{similarity\_score} + B \times \text{commission\_rate}$$

* **Cơ chế an toàn (Similarity Gate)**: Nếu $\text{similarity\_score} < \text{Gate}$, sản phẩm bị phạt nặng để tránh trường hợp hoa hồng cao nhưng sản phẩm sai lệch với hình ảnh người dùng tap.
* **Tự động thích ứng mùa vụ**:
  - `DEFAULT`: $A=0.75, B=0.10, \text{Gate}=0.60$ (Ưu tiên độ chính xác visual).
  - `MEGA_SALE` (Ngày đôi, Black Friday): $A=0.65, B=0.30, \text{Gate}=0.55$ (Tối ưu hóa hoa hồng mùa sale).
  - `TET_HOLIDAY`: $A=0.70, B=0.20, \text{Gate}=0.58$ (Cân bằng giỏ hàng quà tết).

### Chạy tối ưu trọng số Pareto bằng Optuna:
```powershell
python scripts/tune_ranking_optuna.py
```

---

## 🧪 5. Chạy kiểm thử tự động
Bạn có thể chạy thử nghiệm toàn bộ luồng độc lập bằng lệnh:
```powershell
python scripts/test_search_pipeline.py
```
