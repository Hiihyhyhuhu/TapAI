# TAP AI — Affiliate Merchant Portal Frontend

Giao diện Web Frontend hoàn chỉnh dành cho các Shop & Nhà bán hàng hợp tác với hệ thống AI TAP AI.

---

## 📁 Cấu Trúc Thư Mục `TapAI/portal/`

```text
TapAI/portal/
├── index.html                   # HTML gốc của ứng dụng Vite React
├── index.standalone.html        # Giao diện Standalone chạy trực tiếp trên mọi trình duyệt (Không cần Node.js)
├── package.json                 # Cấu hình React 19, Vite, Tailwind CSS, TypeScript
├── vite.config.ts               # Proxy cấu hình chuyển tiếp API về backend localhost:8000
├── tailwind.config.js           # Theme tối ưu Dark mode cho Affiliate Dashboard
├── tsconfig.json                # TypeScript config
├── src/
│   ├── main.tsx                 # Điểm mount React DOM gốc
│   ├── App.tsx                  # Điều phối trạng thái Shop, Auth, Tab Switcher & Demo Login
│   ├── index.css                # Tailwind directives & typography
│   ├── types/
│   │   └── index.ts             # TypeScript interfaces (Shop, Product, Reports, Verification)
│   ├── services/
│   │   └── api.ts               # API Client kết nối 29 endpoints của Backend FastAPI
│   └── components/
│       ├── Navbar.tsx           # Thanh điều hướng, brand logo, profile badge & quick demo button
│       ├── DashboardTab.tsx     # Báo cáo KPI, biểu đồ Clicks / Orders 7 ngày, Top sản phẩm
│       ├── ProductsTab.tsx      # Quản lý danh mục sản phẩm, modal thêm mới & chỉnh sửa Extra Rate %
│       ├── VerificationTab.tsx  # Nộp hồ sơ ĐKKD, chụp màn hình shop & trạng thái xét duyệt
│       └── AuthModal.tsx        # Modal Đăng ký, Đăng nhập và xác thực OTP email
```

---

## 🚀 Hướng Dẫn Khởi Chạy

### Cách 1: Sử dụng Nhanh Không Cần Cài Node.js (Khuyên Dùng)

Bạn có thể mở giao diện ngay lập tức bằng trình duyệt và Python:

1. **Khởi động Backend FastAPI:**
   ```powershell
   & "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn main:app --reload --port 8000
   ```
2. **Khởi chạy Cổng thông tin:**
   Chạy lệnh đơn giản từ thư mục gốc `TapAI/`:
   ```powershell
   & "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe" run_portal.py
   ```
   *Trình duyệt của bạn sẽ tự động mở trang web portal đã kết nối trực tiếp với backend `http://localhost:8000`.*

3. **Hoặc Mở Trực Tiếp Tệp HTML:**
   Nhấp đúp chuột vào tệp:
   `c:\Users\LENOVO\TapAI\portal\index.standalone.html`

---

### Cách 2: Phát Triển Bằng Node.js + Vite Dev Server

Nếu máy tính của bạn đã cài đặt Node.js:

```powershell
cd c:\Users\LENOVO\TapAI\portal
npm install
npm run dev
```

Mở trình duyệt tại: `http://localhost:5173`

---

## 🔑 Đăng Ký và Quản Lý Gian Hàng (Self-Service Onboarding)

Cổng thông tin hỗ trợ quy trình tự đăng ký hoàn chỉnh cho chủ shop và thương hiệu:
1. Bấm **"Đăng ký gian hàng mới"** trên giao diện chính.
2. Điền thông tin thương hiệu: Tên gian hàng, nền tảng (Shopee/TikTok Shop), link gian hàng, email và số điện thoại liên hệ.
3. Xác thực mã OTP xác nhận danh tính người đại diện.
4. Đăng nhập trực tiếp để liên kết danh mục sản phẩm, quản lý tỷ lệ Extra Commission % và theo dõi chuyển đổi đơn hàng từ video clip theo thời gian thực.

