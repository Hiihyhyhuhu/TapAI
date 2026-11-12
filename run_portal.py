"""
One-click Launcher for TAP AI Partner Portal
Starts the backend (if not already running) and opens the Portal in your browser.
"""
import os
import sys
import time
import socket
import webbrowser
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def find_python_executable() -> str:
    candidates = [
        r"C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe",
        sys.executable,
        "python",
        "python3",
    ]
    for exe in candidates:
        if not exe:
            continue
        if "\\" in exe and not os.path.exists(exe):
            continue
        try:
            res = subprocess.run(
                [exe, "-c", "import fastapi, uvicorn; print('OK')"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if res.returncode == 0 and "OK" in res.stdout:
                return exe
        except Exception:
            continue
    return sys.executable

PYTHON_EXE = find_python_executable()

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def main():
    print("==================================================")
    print("   TAP AI — Affiliate Merchant Portal Launcher   ")
    print("==================================================")
    print(f" -> Sử dụng Python: {PYTHON_EXE}")

    # 1. Check Backend Server (port 8000)
    print("\n[1/2] Khởi động Backend FastAPI (http://localhost:8000)...")
    backend_proc = None
    if not is_port_in_use(8000):
        backend_dir = str(BASE_DIR / "backend")
        print(f" -> Khởi động uvicorn từ thư mục: {backend_dir}")
        backend_proc = subprocess.Popen(
            [
                PYTHON_EXE, "-m", "uvicorn", "main:app",
                "--app-dir", backend_dir,
                "--host", "127.0.0.1",
                "--port", "8000"
            ],
            cwd=str(BASE_DIR)
        )
        
        # Chờ tối đa 10 giây để backend sẵn sàng
        ready = False
        for i in range(20):
            time.sleep(0.5)
            if is_port_in_use(8000):
                ready = True
                break
        
        if ready:
            print(" -> Backend đã sẵn sàng tại http://localhost:8000 !")
        else:
            print(" ⚠️ Backend chưa phản hồi trên port 8000.")
            if backend_proc.poll() is not None:
                print(f" -> Lỗi: Tiến trình Backend đã dừng với mã {backend_proc.poll()}")
    else:
        print(" -> Backend đã đang chạy tại http://localhost:8000.")

    # 2. Open Portal in default browser
    portal_url = "http://localhost:8000/dashboard"
    print(f"\n[2/2] Đang mở giao diện Cổng thông tin Đối tác...")
    print(f" -> URL: {portal_url}")
    try:
        webbrowser.open(portal_url)
    except Exception as e:
        print(f" -> Không thể tự mở trình duyệt: {e}")

    print("\n==================================================")
    print(" 🎉 CỔNG THÔNG TIN ĐÃ SẴN SÀNG!")
    print(" - Trang chủ Portal : http://localhost:8000/dashboard")
    print(" - Swagger API Docs : http://localhost:8000/docs")
    print("--------------------------------------------------")
    print(" (Giữ cửa sổ này mở để duy trì Backend)")
    print(" (Nhấn Ctrl+C trong cửa sổ này khi muốn tắt)")
    print("==================================================")

    if backend_proc:
        try:
            backend_proc.wait()
        except KeyboardInterrupt:
            print("\nĐang dừng máy chủ Backend...")
            backend_proc.terminate()

if __name__ == "__main__":
    main()
