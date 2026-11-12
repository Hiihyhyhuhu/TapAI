from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Đảm bảo datetime luôn có timezone UTC (hỗ trợ tương thích SQLite & PostgreSQL)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

from database.connection import get_db
from database.models import Shop, Session as ShopSession, ShopStatus, utc_now
from models.auth_schemas import (
    ShopRegisterRequest,
    VerifyEmailRequest,
    VerifyPhoneRequest,
    ResendOtpRequest,
    LoginRequest,
    RefreshTokenRequest,
    AuthResponse,
    ShopInfo,
    MessageResponse,
)
from services.auth_service import (
    is_disposable_email,
    hash_password,
    verify_password,
    generate_otp,
    get_otp_expiry,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
    send_mock_otp,
)
from middleware.auth_middleware import get_current_shop

router = APIRouter(prefix="/api/v1/auth", tags=["Shop Authentication"])

@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED, summary="Đăng ký tài khoản shop mới")
def register_shop(payload: ShopRegisterRequest, db: Session = Depends(get_db)):
    # 1. Anti-spam: Kiểm tra domain email rác (Layer 5)
    if is_disposable_email(payload.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tên miền email tạm thời/dùng 1 lần bị từ chối. Vui lòng sử dụng email doanh nghiệp hoặc cá nhân chính thức."
        )

    # 2. Kiểm tra trùng lặp email
    existing_email = db.query(Shop).filter(Shop.email == payload.email.lower()).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email này đã được sử dụng để đăng ký shop khác."
        )

    # 3. Kiểm tra trùng lặp số điện thoại
    existing_phone = db.query(Shop).filter(Shop.phone == payload.phone).first()
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Số điện thoại này đã được liên kết với một tài khoản khác."
        )

    # 4. Tạo mã OTP cho Email và SĐT
    email_otp = generate_otp(6)
    phone_otp = generate_otp(6)
    expiry = get_otp_expiry(5)

    # 5. Lưu vào Database
    new_shop = Shop(
        email=payload.email.lower(),
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        shop_name=payload.shop_name,
        platform=payload.platform,
        shop_url=payload.shop_url,
        status=ShopStatus.UNVERIFIED,
        email_verified=False,
        phone_verified=False,
        otp_email_code=email_otp,
        otp_email_expires_at=expiry,
        otp_phone_code=phone_otp,
        otp_phone_expires_at=expiry,
    )
    db.add(new_shop)
    db.commit()
    db.refresh(new_shop)

    # 6. Gửi OTP (Console MVP)
    send_mock_otp(new_shop.email, email_otp, "Email")
    send_mock_otp(new_shop.phone, phone_otp, "SMS/Phone")

    return MessageResponse(
        success=True,
        message=f"Đăng ký thành công! Mã OTP xác thực: {email_otp}",
        data={"shop_id": new_shop.id, "email": new_shop.email, "phone": new_shop.phone, "dev_otp": email_otp}
    )


@router.post("/verify-email", response_model=MessageResponse, summary="Xác thực mã OTP gửi qua Email")
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.email == payload.email.lower()).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản với email này")

    if shop.email_verified:
        return MessageResponse(success=True, message="Email này đã được xác thực trước đó")

    now = datetime.now(timezone.utc)
    if not shop.otp_email_code or shop.otp_email_code != payload.otp_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã OTP email không chính xác")

    exp = ensure_utc(shop.otp_email_expires_at)
    if exp and exp < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã OTP email đã hết hạn. Vui lòng yêu cầu gửi lại")

    shop.email_verified = True
    shop.otp_email_code = None
    shop.otp_email_expires_at = None
    db.commit()

    return MessageResponse(success=True, message="Xác thực Email thành công!")


@router.post("/verify-phone", response_model=MessageResponse, summary="Xác thực mã OTP gửi qua SMS")
def verify_phone(payload: VerifyPhoneRequest, db: Session = Depends(get_db)):
    clean_phone = payload.phone.strip()
    shop = db.query(Shop).filter(Shop.phone == clean_phone).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản với số điện thoại này")

    if shop.phone_verified:
        return MessageResponse(success=True, message="Số điện thoại này đã được xác thực trước đó")

    now = datetime.now(timezone.utc)
    if not shop.otp_phone_code or shop.otp_phone_code != payload.otp_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã OTP số điện thoại không chính xác")

    exp = ensure_utc(shop.otp_phone_expires_at)
    if exp and exp < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã OTP số điện thoại đã hết hạn")

    shop.phone_verified = True
    shop.otp_phone_code = None
    shop.otp_phone_expires_at = None
    db.commit()

    return MessageResponse(success=True, message="Xác thực số điện thoại thành công!")


@router.post("/resend-otp", response_model=MessageResponse, summary="Yêu cầu gửi lại mã OTP")
def resend_otp(payload: ResendOtpRequest, db: Session = Depends(get_db)):
    target = payload.target.strip()
    otp_type = payload.type.lower()

    if otp_type == "email":
        shop = db.query(Shop).filter(Shop.email == target.lower()).first()
    else:
        shop = db.query(Shop).filter(Shop.phone == target).first()

    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy tài khoản với {otp_type} '{target}'")

    new_otp = generate_otp(6)
    expiry = get_otp_expiry(5)

    if otp_type == "email":
        shop.otp_email_code = new_otp
        shop.otp_email_expires_at = expiry
        send_mock_otp(shop.email, new_otp, "Email")
    else:
        shop.otp_phone_code = new_otp
        shop.otp_phone_expires_at = expiry
        send_mock_otp(shop.phone, new_otp, "SMS/Phone")

    db.commit()
    return MessageResponse(
        success=True,
        message=f"Đã tạo và gửi lại mã OTP mới: {new_otp}",
        data={"dev_otp": new_otp}
    )


@router.post("/login", response_model=AuthResponse, summary="Đăng nhập tài khoản shop")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ident = payload.email_or_phone.strip()

    shop = db.query(Shop).filter(
        (Shop.email == ident.lower()) | (Shop.phone == ident)
    ).first()

    if not shop or not verify_password(payload.password, shop.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/Số điện thoại hoặc mật khẩu không chính xác",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if shop.status == ShopStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản shop đã bị tạm ngưng do vi phạm chính sách"
        )

    # Tạo JWT access & refresh token
    access_token = create_access_token(shop.id)
    refresh_token = create_refresh_token(shop.id)

    # Lưu session vào Database
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    session_record = ShopSession(
        shop_id=shop.id,
        token_hash=hash_token(refresh_token),
        ip_address=client_ip,
        user_agent=user_agent,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )

    db.add(session_record)
    db.commit()

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        shop=ShopInfo.model_validate(shop)
    )


@router.post("/refresh", summary="Làm mới Access Token bằng Refresh Token")
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    token_data = decode_token(payload.refresh_token, expected_type="refresh")
    if not token_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token không hợp lệ hoặc đã hết hạn")

    shop_id = token_data.get("sub")
    t_hash = hash_token(payload.refresh_token)

    session_record = db.query(ShopSession).filter(
        ShopSession.shop_id == shop_id,
        ShopSession.token_hash == t_hash
    ).first()

    if not session_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không tồn tại hoặc đã bị đăng xuất")

    now = datetime.now(timezone.utc)
    sess_exp = ensure_utc(session_record.expires_at)
    if sess_exp and sess_exp < now:
        db.delete(session_record)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại")

    new_access_token = create_access_token(shop_id)
    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }


@router.post("/logout", response_model=MessageResponse, summary="Đăng xuất tài khoản")
def logout(
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    # Xóa các sessions của shop
    db.query(ShopSession).filter(ShopSession.shop_id == current_shop.id).delete()
    db.commit()
    return MessageResponse(success=True, message="Đăng xuất thành công!")


@router.get("/me", response_model=ShopInfo, summary="Lấy thông tin tài khoản shop hiện tại")
def get_my_profile(current_shop: Shop = Depends(get_current_shop)):
    return ShopInfo.model_validate(current_shop)
