# TAP AI - Backend Engine

Hệ thống xử lý tương tác video và tìm kiếm sản phẩm thương mại điện tử (Shoppable Media Engine) xây dựng trên nền tảng **FastAPI**.

---

## 🛠️ 1. Cấu trúc thư mục Backend

```text
backend/
├── main.py                     # Entrypoint khởi tạo server FastAPI
├── requirements.txt            # Danh sách thư viện phụ thuộc
├── .env.example                # Mẫu biến môi trường (API Keys)
├── routes/
│   └── search_routes.py        # API Endpoints: /api/v1/match-item, /api/v1/match-video-batch
├── services/
│   ├── query_generator.py      # Module A: VLM Gemini trích xuất ngữ cảnh từ ảnh crop SAM 3
│   ├── shopee_searcher.py      # Module B: Quét và lọc link Shopee/Lazada thực tế qua Serper
│   ├── reranker.py             # Module C: Multimodal VLM Reranking thẩm định độ giống
│   ├── rag_cache.py            # Module D: Bộ nhớ đệm Vector DB (Qdrant + Meta DINOv2)
│   └── search_pipeline.py      # Pipeline tích hợp 4 module luồng Cache-First
├── models/
│   └── search_schemas.py       # Pydantic Schemas (Data Contracts)
├── types/
│   └── search_schemas.py       # Xuất khẩu Types hỗ trợ typing
├── scripts/
│   ├── test_search_pipeline.py # Script test độc lập kiểm thử pipeline
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

# Kích hoạt venv (nếu đã có venv chung của dự án)
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

### 1. `POST /api/v1/match-item` *(Instant Image Tagging)*
* **Mô tả**: Nhận 1 ảnh crop đơn lẻ khi người dùng click vào vật thể.
* **Luồng xử lý**: Kiểm tra Qdrant Cache $\rightarrow$ (Nếu miss) Gọi Gemini VLM + Serper + Rerank $\rightarrow$ Lưu Cache $\rightarrow$ Trả kết quả JSON.

### 2. `POST /api/v1/match-video-batch` *(Video Pre-processing)*
* **Mô tả**: Nhận danh sách các detections của SAM 3 trong toàn bộ video.
* **Tính năng Deduplication**: Tự động gom nhóm các bounding boxes theo `object_id`. Nếu 1 chiếc áo xuất hiện ở 300 frame, hệ thống sẽ **tự động tính diện tích $width \times height \times confidence$ và chỉ chọn đúng 1 frame rõ nhất** để tìm kiếm 1 lần duy nhất, tránh tìm lặp lại gây lãng phí.

---

## 🧪 4. Chạy kiểm thử tự động
Bạn có thể chạy thử nghiệm toàn bộ luồng độc lập bằng lệnh:
```powershell
python scripts/test_search_pipeline.py
```
