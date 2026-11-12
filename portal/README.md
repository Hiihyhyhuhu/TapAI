# TAP AI — Direct Merchant Portal (CPC & JSON Feed Model)

> **Cổng thông tin tự phục vụ (Self-Service Partner Portal) dành cho Nhà bán lẻ & Thương hiệu TMĐT hợp tác cùng hệ sinh thái Video Mua sắm Thông minh TAP AI.**

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/Frontend-React_19_%7C_Tailwind_CSS-blue.svg)](https://react.dev/)
[![Model](https://img.shields.io/badge/Monetization-Direct_CPC_%26_Escrow_Wallet-emerald.svg)](#quy-trình-hệ-thống-4-giai-đoạn-portal-system-workflow)
[![Specification](https://img.shields.io/badge/Standards-DOCS.md_Compliant-green.svg)](../DOCS.md)

---

## 📑 Mục Lục
1. [Giới Thiệu Tổng Quan](#-giới-thiệu-tổng-quan)
2. [Sơ Đồ Luồng Hoạt Động (Architecture Flow)](#-sơ-đồ-luồng-hoạt-động-architecture-flow)
3. [Quy Trình Hệ Thống 4 Giai Đoạn (Portal System Workflow)](#-quy-trình-hệ-thống-4-giai-đoạn-portal-system-workflow)
   - [Giai đoạn 1: Onboarding, Xác minh Quyền sở hữu & Ký số Hợp đồng](#giai-đoạn-1-merchant-onboarding--e-contracting)
   - [Giai đoạn 2: Đăng ký Sản phẩm, Đấu thầu CPC & Ví ký quỹ Escrow](#giai-đoạn-2-product-registration-cpc-bidding--escrow-funding)
   - [Giai đoạn 3: Chuẩn hóa & Phân phối JSON Data Feed](#giai-đoạn-3-json-data-feed-export-for-core-backend)
   - [Giai đoạn 4: Redirect Gateway, Bộ lọc Anti-Fraud & Khấu trừ Ví thời gian thực](#giai-đoạn-4-click-tracking-anti-fraud--real-time-cpc-billing)
4. [Cấu Trúc Thư Mục `portal/`](#-cấu-trúc-thư-mục-portal)
5. [Danh Sách API Endpoints Chính](#-danh-sách-api-endpoints-chính)
6. [Hướng Dẫn Cài Đặt & Khởi Chạy](#-hướng-dẫn-cài-đặt--khởi-chạy)
7. [Kiểm Thử Tự Động (E2E Automated Testing)](#-kiểm-thử-tự-động-e2e-automated-testing)

---

## 🌟 Giới Thiệu Tổng Quan

Hệ thống **TAP AI Merchant Portal** giải quyết bài toán cốt lõi: Kết nối trực tiếp giữa **Nhà bán lẻ (Merchants / Brands)** và **Hệ sinh thái Video tương tác (Interactive Shoppable Media)** của TAP AI. 

Thay vì chỉ dựa vào mạng lưới tiếp thị liên kết (Affiliate Network) trung gian với độ trễ cao và tỷ lệ hoa hồng cố định, TAP AI triển khai mô hình **Direct CPC Bidding & Prepaid Escrow Wallet**:
- Nhà bán hàng chủ động đấu giá CPC cho từng sản phẩm.
- Tự động tích hợp vào các vật thể xuất hiện trong video/ảnh của người dùng.
- Khấu trừ ngân sách minh bạch theo từng lượt nhấp hợp lệ với bộ lọc chống gian lận (Anti-Fraud) 3 tầng nghiêm ngặt.

---

## 🔄 Sơ Đồ Luồng Hoạt Động (Architecture Flow)

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                             TAP AI MERCHANT PORTAL ECOSYSTEM                                │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

 [MERCHANT / SHOP]
        │
        ├── 1. Đăng ký & Nhận mã Bio Token (VD: VERIFY-FCAJ)
        ├── 2. Ký Hợp đồng điện tử CPC (Xác thực OTP + Băm bảo chứng SHA-256)
        ├── 3. Nạp tiền Ví ký quỹ trả trước (Prepaid Escrow Wallet)
        └── 4. Đăng ký sản phẩm & Thiết lập giá thầu CPC Bid (≥ 2.000 VNĐ)
                    │
                    ▼
 [FASTAPI BACKEND & DATABASE]
        │
        ├── Quản lý trạng thái Hợp đồng (`ACTIVE`)
        ├── Kiểm soát số dư ví Escrow an toàn
        └── Tự động kích hoạt trạng thái sản phẩm (`ELIGIBLE`)
                    │
                    ▼
 [SERIALIZER JOB (FEED EXPORT)] ────────► [merchant_products_feed.json]
                                                        │
                                                        ▼
                                         [CORE AI & RANKING BACKEND]
                                         (Đưa sản phẩm ưu tiên vào
                                          Shoppable Media & Search)
                                                        │
                                                        ▼
 [END-USER / EXTENSION] ◄────────────── [CHROME EXTENSION SIDEBAR]
 (Xem video mua sắm)                     (Hiển thị thẻ sản phẩm ghim)
        │
        ▼ (Click "Mua ngay")
 [PORTAL REDIRECT GATEWAY: GET /r/{product_id}?ext_uid={user_id}]
        │
        ├──► BỘ LỌC CHỐNG GIAN LẬN ANTI-FRAUD 3 TẦNG:
        │     • Tầng 1: Bot / Web Crawler Detection (User-Agent)
        │     • Tầng 2: Cửa sổ trùng lặp 30s (Duplicate Click Window)
        │     • Tầng 3: Tần suất IP (IP Rate Limit)
        │
        ├──► [Click Gian lận/Trùng]: Phí 0 VNĐ ──► Redirect ngay lập tức
        └──► [Click Hợp lệ]: Trừ ví nguyên tử (Atomic Deduct CPC) ──► Ghi sổ cái Click Ledger
                    │
                    ▼ (HTTP 302 Found)
 [TRANG ĐÍCH SẢN PHẨM TRÊN SÀN TMĐT (SHOPEE / TIKTOK SHOP / LAZADA)]
```

---

## 🚀 Quy Trình Hệ Thống 4 Giai Đoạn (Portal System Workflow)

Toàn bộ quy trình vận hành tuân thủ nghiêm ngặt theo đặc tả chuẩn tại [DOCS.md](../DOCS.md):

### Giai đoạn 1: Merchant Onboarding & E-Contracting
1. **Đăng ký tài khoản:** Merchant truy cập Web Portal, đăng ký bằng Email, Mật khẩu, Tên gian hàng và URL Shop (Shopee, TikTok Shop, Lazada).
2. **Xác thực quyền sở hữu gian hàng (Ownership Verification):**
   - Hệ thống tự động cấp phát một mã định danh duy nhất: `VERIFY-XXXX` (ví dụ: `VERIFY-FCAJ`).
   - Merchant gắn token này vào phần mô tả gian hàng (Shop Bio) hoặc Meta Tag.
   - Hệ thống thực hiện xác thực để chứng minh quyền sở hữu hợp pháp trước khi cấp phép phân phối.
3. **Sinh thỏa thuận hợp tác điện tử (Digital CPC Agreement):**
   - Tạo văn bản hợp đồng pháp lý trực quan quy định rõ mức giá thầu CPC tối thiểu (2.000 VNĐ), nguyên tắc duy trì số dư ví ký quỹ và quy chế xử lý gian lận click.
4. **Ký số bảo chứng toàn vẹn (E-Signature):**
   - Merchant nhập mã xác thực OTP gửi qua email/SMS để ký số.
   - Hệ thống tạo hàm băm mật mã SHA-256 từ nội dung hợp đồng, mốc thời gian và danh tính để chống chối bỏ theo Luật Giao dịch Điện tử.
   - Trạng thái hợp đồng chuyển thành **`ACTIVE`**, mở khóa quyền đăng ký sản phẩm và tạo chiến dịch.

---

### Giai đoạn 2: Product Registration, CPC Bidding & Escrow Funding
1. **Đăng ký sản phẩm:** Hỗ trợ nhập thủ công, tải lên hàng loạt (CSV/JSON), hoặc phân tích tự động dữ liệu qua OpenGraph từ đường dẫn sản phẩm.
2. **Thiết lập giá thầu CPC Bidding:**
   - Merchant đặt mức chi trả cam kết cho mỗi lượt nhấp: `cpc_bid` (Tối thiểu 2.000 VNĐ/click).
   - Thiết lập hạn mức chi tiêu mỗi ngày (`daily_budget`) nhằm tránh cạn kiệt ngân sách đột ngột trong các đợt bùng nổ lưu lượng.
3. **Nạp tiền vào Ví ký quỹ trả trước (Prepaid Escrow Wallet):**
   - Merchant nạp ngân sách vào ví trả trước thông qua cổng chuyển khoản / đối soát tự động.
4. **Kích hoạt tự động (Auto-Activation):**
   - Khi hợp đồng ở trạng thái `ACTIVE` và số dư ví $\ge$ mức CPC tối thiểu, sản phẩm tự động chuyển sang trạng thái **`ELIGIBLE`** (Sẵn sàng xuất Feed dữ liệu).
   - Khi số dư ví về 0 VNĐ, sản phẩm sẽ tự động chuyển sang trạng thái an toàn **`PAUSED_NO_BUDGET`** để bảo vệ tài khoản của Merchant.

---

### Giai đoạn 3: JSON Data Feed Export for Core Backend
1. **Serializer Job định kỳ / theo yêu cầu:**
   - Backend lọc toàn bộ sản phẩm thỏa mãn điều kiện nghiêm ngặt:
     $$\text{Contract} = \text{ACTIVE} \quad\land\quad \text{Wallet\_Balance} \ge \text{Min\_CPC} \quad\land\quad \text{Product\_Status} = \text{ELIGIBLE}$$
2. **Đóng gói chuẩn hóa `merchant_products_feed.json`:**
   - Cấu trúc bản ghi JSON bao gồm: `product_id`, `shop_id`, `shop_name`, `title`, `price`, `affiliate_url`, `cpc_bid`, `status`, `contract_status`, `updated_at`.
3. **Phân phối sang Core AI Pipeline:**
   - Feed dữ liệu được nạp vào thuật toán chấm điểm và xếp hạng (Ranking Engine) của TAP AI, giúp sản phẩm của Merchant được ưu tiên hiển thị hàng đầu trong danh mục nhận diện đồ họa của video.

---

### Giai đoạn 4: Click Tracking, Anti-Fraud & Real-Time CPC Billing
1. **Lưu lượng nhấp từ người dùng:**
   - Khi người xem video click vào thẻ sản phẩm hiển thị trên Extension Sidebar, yêu cầu được điều hướng qua cổng Gateway:
     ```http
     GET https://portal.domain.com/r/{product_id}?ext_uid={user_id}
     ```
2. **Bộ lọc chống gian lận Anti-Fraud 3 tầng độc quyền:**
   - **Tầng 1 (Bot Detection):** Phân tích chuỗi `User-Agent` nhằm chặn đứng các crawler, spider, script bot tự động (chỉ chấp nhận lưu lượng từ trình duyệt thật).
   - **Tầng 2 (Duplicate Click Window):** Khóa cửa sổ trùng lặp 30 giây đối với cùng một người dùng (`ext_uid`) hoặc cùng IP trên cùng một sản phẩm.
   - **Tầng 3 (IP Rate Limit):** Ngăn chặn hành vi dồn dập nhấp phá hoại từ một địa chỉ mạng.
3. **Cơ chế tính cước minh bạch (Real-time Billing):**
   - **Click gian lận / Trùng lặp:** Ghi log cảnh báo `FRAUD`, tính phí **0 VNĐ**, lập tức điều hướng khách đến link sản phẩm để không gián đoạn trải nghiệm mua hàng.
   - **Click hợp lệ (Valid Unique Click):** 
     - Ghi nhận `VALID` vào Sổ cái Click Ledger cùng ảnh chụp giá thầu `committed_cpc_at_click`.
     - Thực hiện trừ tiền nguyên tử (Atomic Deduction) khỏi số dư ví ký quỹ của Shop.
4. **Điều hướng khách hàng:** Hệ thống phản hồi mã `HTTP 302 Found`, chuyển hướng người dùng an toàn đến trang sản phẩm gốc trên Shopee/TikTok Shop.

---

## 📁 Cấu Trúc Thư Mục `TapAI/portal/`

```text
TapAI/portal/
├── index.html                   # Entrypoint HTML cho Vite React App
├── index.standalone.html        # Giao diện Portal hoàn chỉnh (Single File, chạy trực tiếp mọi nơi)
├── package.json                 # Cấu hình dự án (React 19, Vite, Tailwind CSS, TypeScript)
├── vite.config.ts               # Proxy chuyển tiếp API `/api/v1` về backend localhost:8000
├── tailwind.config.js           # Bảng màu sắc & kiểu chữ tối ưu cho Dark Theme E-Commerce
├── tsconfig.json                # Cấu hình TypeScript compiler
├── src/
│   ├── main.tsx                 # Điểm mount React DOM gốc
│   ├── App.tsx                  # Bộ điều phối trạng thái Shop, Auth, Tab Switcher & Demo Login
│   ├── index.css                # CSS styles & Typography font chữ
│   ├── types/
│   │   └── index.ts             # TypeScript interfaces (Shop, Product, Feed, ClickLedger, Verification)
│   ├── services/
│   │   └── api.ts               # API Client tương tác với toàn bộ 29 endpoints của Backend FastAPI
│   └── components/
│       ├── Navbar.tsx           # Thanh điều hướng, Trạng thái Hợp đồng, Số dư ví & Nút Đăng nhập/Đăng xuất
│       ├── DashboardTab.tsx     # Báo cáo biểu đồ Clicks, Doanh thu CPC, Số dư ví ký quỹ & Lịch sử
│       ├── ProductsTab.tsx      # Quản lý danh mục, thiết lập CPC Bid, nạp Feed JSON & lọc trạng thái
│       ├── VerificationTab.tsx  # Xác thực quyền sở hữu Bio Token & Ký số Hợp đồng điện tử bằng OTP
│       ├── ReconciliationTab.tsx# Chi tiết Sổ cái Click Ledger & Quản lý nạp/rút Ví ký quỹ Escrow
│       └── AuthModal.tsx        # Cửa sổ Đăng ký, Đăng nhập và Khôi phục mật khẩu gian hàng
```

---

## 🌐 Danh Sách API Endpoints Chính

Tất cả các API được bảo mật bằng tiêu chuẩn Bearer JWT Authentication:

| Giai đoạn | Phương thức | Endpoint | Mô tả |
| :--- | :--- | :--- | :--- |
| **Auth** | `POST` | `/api/v1/auth/register` | Đăng ký tài khoản gian hàng mới |
| **Auth** | `POST` | `/api/v1/auth/login` | Đăng nhập nhận JWT Access & Refresh Token |
| **Stage 1** | `GET` | `/api/v1/shops/contract` | Xem văn bản thỏa thuận hợp tác CPC |
| **Stage 1** | `POST` | `/api/v1/shops/ownership/verify` | Xác thực quyền sở hữu qua Bio Token `VERIFY-XXXX` |
| **Stage 1** | `POST` | `/api/v1/shops/contract/sign` | Ký số hợp đồng bằng OTP & lưu hash SHA-256 |
| **Stage 2** | `GET` | `/api/v1/shops/wallet` | Xem số dư Ví ký quỹ trả trước Escrow |
| **Stage 2** | `POST` | `/api/v1/shops/wallet/deposit` | Nạp tiền vào ví ký quỹ Escrow |
| **Stage 2** | `POST` | `/api/v1/products` | Đăng ký sản phẩm mới & đặt giá thầu CPC |
| **Stage 2** | `PUT` | `/api/v1/products/{id}/bidding` | Cập nhật giá thầu CPC Bid & Daily Budget Cap |
| **Stage 3** | `GET` | `/api/v1/products/feed/export` | Tải về tệp `merchant_products_feed.json` chuẩn hóa |
| **Stage 3** | `POST` | `/api/v1/products/feed/dispatch` | Kích hoạt Serializer Job đẩy feed sang Core Backend |
| **Stage 4** | `GET` | `/r/{product_id}` | Redirect Gateway xử lý nhấp chuột & Anti-Fraud |
| **Stage 4** | `GET` | `/api/v1/tracking/ledger` | Truy xuất Sổ cái đối soát Click Ledger thời gian thực |
| **Report** | `GET` | `/api/v1/reports/daily` | Báo cáo chuỗi thời gian phân tích Clicks & Doanh thu CPC |

---

## 💻 Hướng Dẫn Cài Đặt & Khởi Chạy

### Cách 1: Sử dụng Bản Standalone Trực Tiếp (Khuyên dùng)
Giao diện `index.standalone.html` tích hợp sẵn toàn bộ CSS, biểu đồ Chart.js và logic kết nối API mà không yêu cầu cài đặt môi trường Node.js.

1. **Khởi động Backend FastAPI:**
   ```powershell
   cd c:\Users\LENOVO\TapAI\backend
   & "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn main:app --reload --port 8000
   ```
2. **Khởi chạy Web Portal:**
   Từ thư mục gốc `TapAI/`:
   ```powershell
   & "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe" run_portal.py
   ```
   *Trình duyệt sẽ tự động mở trang:* `http://localhost:8000/portal/index.standalone.html`

3. **Tài khoản dùng thử (Demo Account):**
   - **Email:** `demo@tapai.vn`
   - **Mật khẩu:** `123456`
   - **Mã OTP ký hợp đồng:** `123456`
   - *Tài khoản đã có sẵn 2.000.000 ₫ trong ví Escrow để kiểm thử ngay lập tức.*

---

### Cách 2: Phát Triển Với Node.js & Vite Dev Server
Dành cho lập trình viên muốn mở rộng các thành phần React Component:

```powershell
cd c:\Users\LENOVO\TapAI\portal
npm install
npm run dev
```
Truy cập giao diện lập trình tại: `http://localhost:5173`

---

## 🧪 Kiểm Thử Tự Động (E2E Automated Testing)

Dự án cung cấp bộ kịch bản kiểm thử tích hợp toàn diện [test_portal_cpc_workflow.py](../test_portal_cpc_workflow.py) để xác thực tính toàn vẹn của cả 4 giai đoạn:

```powershell
& "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe" test_portal_cpc_workflow.py
```

**Kết quả kiểm thử tiêu chuẩn:**
- ✅ **Stage 1:** Ký số hợp đồng điện tử & tạo mã băm SHA-256 thành công.
- ✅ **Stage 2:** Nạp ví ký quỹ Escrow, đăng ký sản phẩm, thiết lập giá thầu CPC và kiểm tra trạng thái kích hoạt tự động.
- ✅ **Stage 3:** Xuất bản và xác thực định dạng dữ liệu `merchant_products_feed.json`.
- ✅ **Stage 4:** Kiểm tra Redirect Gateway, bộ lọc Bot/Crawler, bộ lọc Duplicate Click Window và khấu trừ chính xác ngân sách vào Sổ cái Click Ledger.
