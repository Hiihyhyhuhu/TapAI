import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from database.models import Shop, Verification, ShopStatus, VerificationStatus, utc_now

UPLOAD_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "verifications")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

PLATFORM_DOMAINS = {
    "shopee": ["shopee.vn"],
    "lazada": ["lazada.vn"],
    "tiki": ["tiki.vn"],
    "tiktok_shop": ["tiktok.com"],
}

def validate_platform_url(platform: str, url: str) -> bool:
    """Kiểm tra đường dẫn shop có thuộc đúng sàn thương mại điện tử đã đăng ký."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        allowed_domains = PLATFORM_DOMAINS.get(platform.lower(), [])
        if not allowed_domains:
            return True  # 'other' platform allows any valid http/https URL
        return any(d in domain for d in allowed_domains)
    except Exception:
        return False

async def save_uploaded_file(shop_id: str, file: UploadFile, prefix: str = "doc") -> str:
    """Lưu file upload vào thư mục an toàn và trả về đường dẫn tương đối."""
    filename = file.filename or "file.bin"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Định dạng file '{ext}' không được hỗ trợ. Chỉ chấp nhận: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Đọc nội dung và kiểm tra kích thước
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Kích thước file vượt quá giới hạn 10MB ({len(content) / (1024 * 1024):.2f}MB)"
        )

    # Tạo thư mục cho shop
    shop_dir = os.path.join(UPLOAD_BASE_DIR, shop_id)
    os.makedirs(shop_dir, exist_ok=True)

    safe_name = f"{prefix}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(shop_dir, safe_name)

    with open(file_path, "wb") as f:
        f.write(content)

    # Trả về relative URL để lưu vào DB
    return f"/uploads/verifications/{shop_id}/{safe_name}"

def submit_shop_verification(
    db: Session,
    shop: Shop,
    business_license_url: str,
    shop_screenshot_url: str,
    shop_url_submitted: str
) -> Verification:
    """Tạo hồ sơ xác minh danh tính và cập nhật trạng thái shop sang PENDING_REVIEW."""
    # 1. Kiểm tra nếu shop đang có hồ sơ PENDING
    existing_pending = db.query(Verification).filter(
        Verification.shop_id == shop.id,
        Verification.status == VerificationStatus.PENDING
    ).first()
    if existing_pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shop đã có hồ sơ xác minh đang chờ xét duyệt. Vui lòng đợi quản trị viên phản hồi."
        )

    # 2. Kiểm tra tính hợp lệ của link shop
    if not validate_platform_url(shop.platform, shop_url_submitted):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Đường dẫn shop '{shop_url_submitted}' không thuộc miền chính thức của sàn '{shop.platform}'"
        )

    # 3. Tạo bản ghi hồ sơ xác minh
    verification = Verification(
        shop_id=shop.id,
        business_license_url=business_license_url,
        shop_screenshot_url=shop_screenshot_url,
        shop_url_submitted=shop_url_submitted,
        status=VerificationStatus.PENDING,
        submitted_at=utc_now()
    )
    db.add(verification)

    # 4. Chuyển trạng thái shop sang PENDING_REVIEW
    shop.status = ShopStatus.PENDING_REVIEW
    shop.shop_url = shop_url_submitted  # Cập nhật link mới nhất nếu có thay đổi
    db.commit()
    db.refresh(verification)

    return verification

def review_verification(
    db: Session,
    verification_id: str,
    action: str,
    admin_note: Optional[str] = None,
    admin_id: str = "admin"
) -> Verification:
    """Admin duyệt / từ chối / yêu cầu nộp lại hồ sơ xác minh."""
    verification = db.query(Verification).filter(Verification.id == verification_id).first()
    if not verification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy hồ sơ xác minh")

    if verification.status != VerificationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hồ sơ này đã được xử lý trước đó với trạng thái '{verification.status}'"
        )

    shop = db.query(Shop).filter(Shop.id == verification.shop_id).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thông tin shop liên kết")

    now = utc_now()
    verification.reviewed_by = admin_id
    verification.reviewed_at = now
    verification.admin_note = admin_note

    if action == "approve":
        verification.status = VerificationStatus.APPROVED
        shop.status = ShopStatus.VERIFIED
    elif action == "reject":
        if not admin_note:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vui lòng cung cấp lý do từ chối (admin_note)")
        verification.status = VerificationStatus.REJECTED
        shop.status = ShopStatus.REJECTED
    elif action == "resubmit_required":
        if not admin_note:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vui lòng cung cấp yêu cầu bổ sung hồ sơ (admin_note)")
        verification.status = VerificationStatus.RESUBMIT_REQUIRED
        shop.status = ShopStatus.UNVERIFIED
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Hành động không hợp lệ: '{action}'")

    db.commit()
    db.refresh(verification)
    return verification

