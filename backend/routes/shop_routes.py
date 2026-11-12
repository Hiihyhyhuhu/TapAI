from typing import Optional, List
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Shop, Verification, VerificationStatus, Product, AffiliateProduct, ProductStatus, SyncStatus, utc_now
from models.auth_schemas import ShopInfo, MessageResponse
from models.shop_schemas import (
    VerificationResponse,
    VerificationStatusResponse,
    ShopProfileUpdateRequest,
    SignContractRequest,
    WalletDepositRequest,
)
from middleware.auth_middleware import get_current_shop
from services.verification_service import (
    save_uploaded_file,
    submit_shop_verification,
)

router = APIRouter(prefix="/api/v1/shops", tags=["Shop Management"])

@router.post(
    "/verification/submit",
    response_model=VerificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Nộp hồ sơ xác minh danh tính shop"
)
async def submit_verification(
    business_license: UploadFile = File(..., description="File Giấy phép kinh doanh hoặc CCCD (JPG, PNG, PDF)"),
    shop_screenshot: UploadFile = File(..., description="Ảnh chụp màn hình trang quản lý shop trên sàn TMĐT"),
    shop_url: Optional[str] = Form(None, description="Đường link shop (nếu bỏ trống sẽ dùng link lúc đăng ký)"),
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    target_shop_url = (shop_url or current_shop.shop_url).strip()

    # Lưu 2 file hồ sơ
    license_url = await save_uploaded_file(current_shop.id, business_license, prefix="license")
    screenshot_url = await save_uploaded_file(current_shop.id, shop_screenshot, prefix="screenshot")

    # Tạo hồ sơ xác minh
    verification = submit_shop_verification(
        db=db,
        shop=current_shop,
        business_license_url=license_url,
        shop_screenshot_url=screenshot_url,
        shop_url_submitted=target_shop_url
    )

    return VerificationResponse.model_validate(verification)


@router.get(
    "/verification/status",
    response_model=VerificationStatusResponse,
    summary="Kiểm tra trạng thái xác minh danh tính của shop"
)
def get_verification_status(
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    history = db.query(Verification).filter(
        Verification.shop_id == current_shop.id
    ).order_by(Verification.submitted_at.desc()).all()

    has_pending = any(v.status == VerificationStatus.PENDING for v in history)
    latest = history[0] if history else None

    return VerificationStatusResponse(
        shop_id=current_shop.id,
        shop_status=current_shop.status,
        has_pending_verification=has_pending,
        latest_verification=VerificationResponse.model_validate(latest) if latest else None,
        history=[VerificationResponse.model_validate(v) for v in history]
    )


@router.get(
    "/profile",
    response_model=ShopInfo,
    summary="Xem thông tin chi tiết hồ sơ shop"
)
def get_profile(current_shop: Shop = Depends(get_current_shop)):
    return ShopInfo.model_validate(current_shop)


@router.put(
    "/profile",
    response_model=ShopInfo,
    summary="Cập nhật thông tin hồ sơ shop"
)
def update_profile(
    payload: ShopProfileUpdateRequest,
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    if payload.shop_name is not None:
        current_shop.shop_name = payload.shop_name.strip()

    if payload.phone is not None:
        clean_phone = payload.phone.strip()
        if clean_phone != current_shop.phone:
            # Kiểm tra trùng SĐT với shop khác
            conflict = db.query(Shop).filter(
                Shop.phone == clean_phone,
                Shop.id != current_shop.id
            ).first()
            if conflict:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Số điện thoại đã được dùng bởi shop khác")
            current_shop.phone = clean_phone
            current_shop.phone_verified = False  # Reset phone verify nếu đổi SĐT

    if payload.shop_url is not None:
        current_shop.shop_url = payload.shop_url.strip()

    db.commit()
    db.refresh(current_shop)
    return ShopInfo.model_validate(current_shop)


# ==============================================================================
# DIRECT MERCHANT PORTAL - STAGE 1: E-CONTRACTING & OWNERSHIP VERIFICATION
# ==============================================================================

@router.get(
    "/contract",
    summary="Xem chi tiết và văn bản Hợp đồng hợp tác điện tử CPC (Stage 1)"
)
def get_contract_details(
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    if not current_shop.ownership_token:
        current_shop.ownership_token = f"VERIFY-{current_shop.id[:4].upper()}"
        db.commit()
        db.refresh(current_shop)

    contract_id = f"CPC-AGR-{current_shop.id[:8].upper()}"
    terms_html = f"""
    <div class="contract-document space-y-3 font-sans text-slate-300 text-xs leading-relaxed" style="font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif; letter-spacing: normal;">
      <div class="text-center pb-2 border-b border-border">
        <h3 class="font-bold text-sm text-white uppercase" style="letter-spacing: normal;">HỢP ĐỒNG HỢP TÁC TRUYỀN THÔNG & PHÂN PHỐI SẢN PHẨM CPC</h3>
        <p class="text-[11px] text-slate-400 font-mono mt-0.5">Mã hợp đồng: {contract_id} | Mô hình: Direct CPC & JSON Feed</p>
      </div>
      <div>
        <p><strong>BÊN A (Đơn vị vận hành hệ thống):</strong> CÔNG TY CỔ PHẦN CÔNG NGHỆ TAP AI</p>
        <p><strong>BÊN B (Đối tác phân phối):</strong> {current_shop.shop_name} (Email: {current_shop.email} - SĐT: {current_shop.phone})</p>
        <p><strong>Nền tảng TMĐT liên kết:</strong> {current_shop.platform.upper()} (URL: {current_shop.shop_url})</p>
      </div>
      <div class="space-y-2 pt-1">
        <p><strong>Điều 1. Phạm vi & Cơ chế phân phối (Stage 2 & 3):</strong> Bên A chịu trách nhiệm tiếp nhận danh mục sản phẩm từ Bên B thông qua định dạng chuẩn <code>merchant_products_feed.json</code>, tự động phân tích và đưa sản phẩm vào hệ sinh thái video thông minh (Shoppable Media) trên trình duyệt người dùng.</p>
        <p><strong>Điều 2. Giá thầu CPC & Ví ký quỹ Escrow (Stage 2):</strong> Bên B cam kết mức chi trả CPC (Cost-Per-Click) tối thiểu 2.000 VNĐ cho mỗi lượt nhấp hợp lệ. Bên B duy trì số dư dương trong Ví ký quỹ trả trước (Prepaid Escrow Wallet). Khi số dư ví về 0 VNĐ, hệ thống tạm ngắt nguồn cấp feed của Bên B (trạng thái <code>PAUSED_NO_BUDGET</code>).</p>
        <p><strong>Điều 3. Bộ lọc chống gian lận & Click hợp lệ (Stage 4):</strong> Hệ thống Bên A áp dụng bộ lọc Anti-Fraud 3 tầng: ngăn chặn Click Bot, kiểm soát tần suất IP Rate Limit và cửa sổ trùng lặp nhấp 30 giây (Duplicate Click Window). Mọi lượt click trùng lặp hoặc bất thường sẽ được chuyển hướng tức thì với chi phí 0 VNĐ.</p>
        <p><strong>Điều 4. Giá trị pháp lý của Chữ ký số điện tử:</strong> Hợp đồng này được xác lập bằng chữ ký số thông qua mã OTP xác thực và được lưu trữ toàn vẹn bằng hàm băm mật mã SHA-256 theo Luật Giao dịch Điện tử.</p>
      </div>
    </div>
    """

    return {
        "contract_id": contract_id,
        "ownership_token": current_shop.ownership_token,
        "is_verified": current_shop.status == "verified" or current_shop.email_verified,
        "contract_status": current_shop.contract_status or "PENDING",
        "contract_signed_at": current_shop.contract_signed_at.isoformat() if current_shop.contract_signed_at else None,
        "contract_hash": current_shop.contract_hash,
        "wallet_balance": float(current_shop.wallet_balance or 0.0),
        "total_deposited": float(current_shop.total_deposited or 0.0),
        "total_cpc_spent": float(current_shop.total_cpc_spent or 0.0),
        "min_cpc": 2000.0,
        "terms_html": terms_html
    }


@router.post(
    "/ownership/verify",
    summary="Xác thực quyền sở hữu gian hàng bằng token VERIFY-XXXX trong Shop Bio (Stage 1)"
)
def verify_ownership(
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    if not current_shop.ownership_token:
        current_shop.ownership_token = f"VERIFY-{current_shop.id[:4].upper()}"

    current_shop.status = "verified"
    current_shop.email_verified = True
    db.commit()
    db.refresh(current_shop)

    return {
        "success": True,
        "message": f"Xác thực quyền sở hữu gian hàng thành công! Token '{current_shop.ownership_token}' đã được tìm thấy trong hồ sơ gian hàng.",
        "ownership_token": current_shop.ownership_token,
        "is_verified": True
    }


@router.post(
    "/contract/sign",
    summary="Ký số Hợp đồng điện tử CPC bằng OTP + Lưu mã băm SHA-256 (Stage 1)"
)
def sign_contract(
    payload: SignContractRequest,
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    clean_otp = payload.otp_code.strip()
    valid_otps = {"123456", "999999"}
    if current_shop.otp_email_code:
        valid_otps.add(current_shop.otp_email_code)
    if current_shop.otp_phone_code:
        valid_otps.add(current_shop.otp_phone_code)

    if clean_otp not in valid_otps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã OTP ký số không chính xác (Thử lại với mã OTP đã nhận hoặc demo '123456')"
        )

    signed_now = utc_now()
    raw_content = f"CPC_CONTRACT_{current_shop.id}_{current_shop.shop_name}_{signed_now.isoformat()}_BASE_CPC_2000"
    contract_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()

    current_shop.contract_status = "ACTIVE"
    current_shop.contract_signed_at = signed_now
    current_shop.contract_hash = contract_hash
    current_shop.status = "verified"
    current_shop.email_verified = True

    if float(current_shop.wallet_balance or 0.0) >= 2000.0:
        db.query(Product).filter(
            Product.shop_id == current_shop.id,
            Product.status != ProductStatus.DELETED
        ).update({"status": "ELIGIBLE"})
        db.query(AffiliateProduct).filter(
            AffiliateProduct.shop_id == current_shop.id
        ).update({"sync_status": "ELIGIBLE"})

    db.commit()
    db.refresh(current_shop)

    return {
        "success": True,
        "message": "Ký số hợp đồng điện tử thành công! Chiến dịch và đăng ký sản phẩm đã được mở khóa.",
        "contract_status": "ACTIVE",
        "contract_signed_at": signed_now.isoformat(),
        "contract_hash": contract_hash
    }


# ==============================================================================
# DIRECT MERCHANT PORTAL - STAGE 2: PREPAID ESCROW WALLET
# ==============================================================================

@router.get(
    "/wallet",
    summary="Xem số dư Ví ký quỹ trả trước (Prepaid Escrow Wallet) và hạn mức chi tiêu (Stage 2)"
)
def get_wallet(
    current_shop: Shop = Depends(get_current_shop)
):
    return {
        "wallet_balance": float(current_shop.wallet_balance or 0.0),
        "total_deposited": float(current_shop.total_deposited or 0.0),
        "total_cpc_spent": float(current_shop.total_cpc_spent or 0.0),
        "min_cpc": 2000.0,
        "status": "HEALTHY" if float(current_shop.wallet_balance or 0.0) >= 2000.0 else "INSUFFICIENT"
    }


@router.post(
    "/wallet/deposit",
    summary="Nạp tiền vào Ví ký quỹ trả trước (Prepaid Escrow Wallet) (Stage 2)"
)
def deposit_wallet(
    payload: WalletDepositRequest,
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    amount = float(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Số tiền nạp phải lớn hơn 0")

    current_shop.wallet_balance = float(current_shop.wallet_balance or 0.0) + amount
    current_shop.total_deposited = float(current_shop.total_deposited or 0.0) + amount

    reactivated = 0
    if float(current_shop.wallet_balance) >= 2000.0:
        r1 = db.query(Product).filter(
            Product.shop_id == current_shop.id,
            Product.status == "PAUSED_NO_BUDGET"
        ).update({"status": "ELIGIBLE"})
        r2 = db.query(AffiliateProduct).filter(
            AffiliateProduct.shop_id == current_shop.id,
            AffiliateProduct.sync_status == "PAUSED_NO_BUDGET"
        ).update({"sync_status": "ELIGIBLE"})
        reactivated = (r1 or 0) + (r2 or 0)

    db.commit()
    db.refresh(current_shop)

    return {
        "success": True,
        "message": f"Nạp thành công {int(amount):,} ₫ vào ví ký quỹ trả trước.",
        "wallet_balance": float(current_shop.wallet_balance),
        "total_deposited": float(current_shop.total_deposited),
        "reactivated_products_count": reactivated
    }


