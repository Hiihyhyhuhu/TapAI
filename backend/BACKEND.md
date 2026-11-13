# TAP AI - Backend Engine

Hệ thống xử lý tương tác video và tìm kiếm sản phẩm thương mại điện tử (**Shoppable Media Engine**) xây dựng trên nền tảng **FastAPI**.

---

## 🛠️ 1. Cấu trúc thư mục Backend

```text
backend/
├── main.py                     # Entrypoint khởi tạo server FastAPI & CORS middleware
├── requirements.txt            # Danh sách thư viện phụ thuộc (FastAPI, Google GenAI, Torch, v.v.)
├── .env.example                # Mẫu biến môi trường (API Keys)
├── metadata_sample.json        # Chuẩn Data Contract 20 sản phẩm mẫu cho Frontend Side Panel
├── routes/
│   └── search_routes.py        # API Endpoints: match-item, match-video-batch, tasks, proxy, ranking-mode
├── services/
│   ├── query_generator.py      # Module A: VLM Gemini 3.5 Flash trích xuất ngữ cảnh từ ảnh crop SAM 3
│   ├── shopee_searcher.py      # Module B: Quét và lọc link Shopee/Lazada thực tế qua Serper (Top 20-25)
│   ├── reranker.py             # Module C: Multimodal VLM Reranking - Xếp hạng thuần túy độ tương đồng thị giác
│   ├── search_pipeline.py      # Pipeline cốt lõi tích hợp luồng: Crop -> VLM -> Serper -> Rerank
│   ├── task_manager.py         # Dual-Engine: In-process Async Background Task Worker & Polling
│   └── celery_worker.py        # Dual-Engine: Celery + Redis production worker (dành cho scale lớn)
├── models/
│   └── search_schemas.py       # Pydantic Schemas (TapAIMetadata, MatchItemRequest, VideoBatchRequest...)
├── types/
│   └── search_schemas.py       # Xuất khẩu Types hỗ trợ typing
├── scripts/
│   ├── test_search_pipeline.py # Script test độc lập kiểm thử pipeline
│   ├── test_reranker_ranking.py# Script kiểm thử xếp hạng theo độ khớp sản phẩm cao nhất
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
```

### Bước 3: Khởi động Server FastAPI
```powershell
uvicorn main:app --reload --port 8000
```
Sau khi server bật, truy cập Swagger UI trực quan tại:
👉 **[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## 📡 3. Danh sách API Endpoints

### 1. `POST /api/v1/match-item/upload` *(Test trực tiếp với nút Chọn tệp)*
* **Mô tả**: Tải trực tiếp file ảnh từ máy tính (`.webp`, `.png`, `.jpg`) trên giao diện Swagger UI để kiểm tra kết quả ngay lập tức.

### 2. `POST /api/v1/match-item` *(Instant Image Tagging cho Extension)*
* **Mô tả**: Nhận 1 ảnh crop đơn lẻ khi người dùng click vào vật thể trên ảnh hoặc frame video.
* **Hỗ trợ JSON Body**: `image_base64` hoặc `image_url`.
* **Luồng xử lý**: Nhận ảnh $\rightarrow$ Gemini VLM phân tích từ khóa $\rightarrow$ Serper Search Shopee $\rightarrow$ Gemini Rerank theo hoa hồng $\rightarrow$ Trả kết quả JSON danh sách sản phẩm xếp hạng.

### 3. `POST /api/v1/match-video-batch` *(Video Pre-processing & Async Task)*
* **Mô tả**: Nhận danh sách các detections của SAM 3 trong toàn bộ video và kích hoạt tìm kiếm.
* **Hỗ trợ 2 chế độ**:
  - `async_mode=True` (Mặc định): Trả về ngay lập tức HTTP `202 Accepted` cùng `task_id` để client không bị timeout khi xử lý video dài.
  - `async_mode=False`: Xử lý đồng bộ và trả về trực tiếp `TapAIMetadata`.
* **Tính năng Deduplication**: Tự động gom nhóm các bounding boxes theo `object_id`. Nếu 1 chiếc áo xuất hiện ở 300 frame, hệ thống sẽ tự động tính điểm đại diện $width \times height \times confidence$ và chỉ chọn đúng 1 frame rõ nhất để tìm kiếm 1 lần duy nhất.
* **Mở rộng 20 sản phẩm**: Tự động trả về tối đa 20 sản phẩm xếp hạng cao nhất cho mỗi vật thể để phục vụ danh sách scrollable trên Chrome Extension Side Panel.

### 4. `GET /api/v1/tasks/{task_id}` *(Task Progress Polling)*
* **Mô tả**: Kiểm tra trạng thái và tiến độ xử lý video ngầm (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`).
* **Phản hồi**: Bao gồm `progress` (0 - 100%), thông tin chi tiết và toàn bộ payload `TapAIMetadata` khi hoàn thành.

### 5. `GET /api/v1/tasks/{task_id}/download` *(Export metadata.json)*
* **Mô tả**: Tải trực tiếp file `metadata.json` đã chuẩn hóa (normalized coordinates 0.0 - 1.0, 20 sản phẩm kèm link affiliate).

### 6. `GET /api/v1/image-proxy` *(Image CORS & Anti-Hotlink Bypass)*
* **Mô tả**: Proxy chuyển tiếp hình ảnh từ Shopee / Lazada / TikTok Shop để vượt qua cơ chế chặn Hotlinking và CORS của các sàn, hỗ trợ Chrome Extension render ảnh mượt mà.

### 7. `GET /api/v1/ranking-mode` *(Ranking Mode Status)*
* **Mô tả**: Xem thông tin chế độ xếp hạng hiện tại (`pure_similarity`: Tối ưu hóa 100% trả về các sản phẩm khớp thị giác nhất với ảnh mục tiêu).

---

## 🎯 4. Thuật toán Xếp hạng (Deterministic Rubric Scoring & Anti-Index Shifting)

Hệ thống tối ưu hóa 100% trải nghiệm tìm kiếm của người dùng bằng cách xếp hạng theo **độ tương đồng thị giác tất định**, khắc phục triệt để hiện tượng suy giảm Attention, lệch chỉ mục (Index Shifting) và sai số thả nổi (Float Hallucination):

### a. Cơ chế Micro-batching bảo toàn Attention
* Giới hạn tối đa **4 ứng viên/lượt** gửi cho Gemini VLM (tổng cộng 5 ảnh: 1 ảnh mục tiêu + 4 ảnh ứng viên sàn).
* Giữ toàn bộ ảnh trong cửa sổ tập trung (Attention Window) tối ưu của Vision-LLM, tránh hiện tượng quá tải và lẫn lộn giữa các ảnh.

### b. Chống lệch chỉ mục (Anti-Index Shifting)
* Mỗi ảnh ứng viên được đóng khung định danh rõ ràng kèm `ITEM_ID: "sp_..."` ngay trên ảnh.
* Đặt `temperature=0.0` để loại bỏ tính ngẫu nhiên.
* Thuật toán tự động đối chiếu theo `item_id`, kèm cơ chế fallback theo chỉ mục thứ tự (`positional index`).

### c. Chuẩn hóa bằng Rubric rời rạc (Deterministic Scoring Formula)
VLM **không tự chấm điểm số thực thả nổi** từ 0.0 đến 1.0 (vốn rất dễ dao động thất thường). Thay vào đó, VLM chỉ phân loại các trường Enum rời rạc (`EXACT`, `CLOSE`, `DIFFERENT`), sau đó hàm Python tự động tính điểm tổng:

$$\text{match\_score} = 0.30 \times S_{\text{silhouette}} + 0.25 \times S_{\text{collar}} + 0.25 \times S_{\text{pattern}} + 0.10 \times S_{\text{color}} + 0.10 \times S_{\text{details}}$$

* **Phom dáng (Silhouette - 30%)**: Khớp phom rộng, tay dài, kiểu dáng áo. Nếu sai phom (ví dụ áo thun cộc tay thay vì polo dài tay) sẽ bị phạt nặng.
* **Cổ áo & Khóa (Collar/Neckline - 25%)**: Cổ polo zip có khóa kéo vs cổ tròn vs cổ bẻ cài cúc.
* **Hoa văn (Pattern - 25%)**: Kẻ sọc ngang vs kẻ sọc dọc vs caro vs trơn.
* **Tông màu (Color Palette - 10%)**: Phối màu đen/trắng/đỏ vs đơn sắc.
* **Chi tiết điểm nhấn (Key Details - 10%)**: Khóa kéo kim loại, bo gấu tay, túi áo.

Mỗi sản phẩm trả về đều đính kèm trường `rubric_breakdown` minh bạch để client/frontend kiểm tra chi tiết.

---

## 🧪 5. Chạy kiểm thử tự động
Bạn có thể chạy thử nghiệm toàn bộ luồng độc lập bằng lệnh:
```powershell
python scripts/test_reranker_ranking.py
python scripts/test_schema_and_cors.py
python scripts/test_search_pipeline.py
```
