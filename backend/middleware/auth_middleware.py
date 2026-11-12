import os
from typing import Optional
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database.connection import get_db
from database.models import Shop, ShopStatus
from services.auth_service import decode_token

load_dotenv()

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "admin-secret-change-this")

security = HTTPBearer(auto_error=False)
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

def get_current_shop(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db)
) -> Shop:
    """Dependency trích xuất Shop hiện tại từ Authorization Bearer Token."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu đăng nhập để truy cập tài nguyên này",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token, expected_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        )

    shop_id = payload.get("sub")
    if not shop_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không chứa định danh shop",
            headers={"WWW-Authenticate": "Bearer"},
        )

    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tài khoản shop không tồn tại hoặc đã bị xóa"
        )

    if shop.status == ShopStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản shop đã bị tạm khóa do vi phạm chính sách"
        )

    return shop

def get_current_verified_shop(
    shop: Shop = Depends(get_current_shop)
) -> Shop:
    """Dependency đảm bảo Shop đã ký Hợp đồng điện tử ACTIVE hoặc xác minh danh tính."""
    if shop.contract_status != "ACTIVE" and shop.status != ShopStatus.VERIFIED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Thao tác yêu cầu Hợp đồng điện tử ACTIVE hoặc Shop đã xác minh. Trạng thái hiện tại: Contract='{shop.contract_status}', Shop='{shop.status}'"
        )
    return shop

def get_current_admin(
    admin_key: Optional[str] = Security(admin_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> bool:
    """Dependency xác thực quyền Quản trị viên (Admin)."""
    # 1. Kiểm tra qua X-Admin-Key header
    if admin_key and admin_key == ADMIN_SECRET_KEY:
        return True

    # 2. Hoặc kiểm tra JWT payload có role == 'admin'
    if credentials and credentials.credentials:
        payload = decode_token(credentials.credentials, expected_type="access")
        if payload and payload.get("role") == "admin":
            return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Từ chối truy cập: Bạn không có quyền quản trị viên"
    )

