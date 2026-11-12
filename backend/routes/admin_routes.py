from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import (
    Shop,
    Verification,
    Product,
    Click,
    Conversion,
    ShopStatus,
    VerificationStatus,
)
from models.auth_schemas import ShopInfo, MessageResponse
from models.shop_schemas import (
    VerificationResponse,
    AdminReviewRequest,
    AdminShopStatusUpdateRequest,
    ShopListItem,
    ShopListResponse,
    AdminStatsResponse,
)
from middleware.auth_middleware import get_current_admin
from services.verification_service import review_verification

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Management"])

@router.get(
    "/shops",
    response_model=ShopListResponse,
    summary="Xem danh sách tất cả các shop đối tác (có phân trang và bộ lọc)"
)
def list_shops(
    status_filter: Optional[str] = Query(None, alias="status", description="Lọc theo trạng thái shop"),
    platform_filter: Optional[str] = Query(None, alias="platform", description="Lọc theo sàn TMĐT"),
    page: int = Query(1, ge=1, description="Số trang (bắt đầu từ 1)"),
    limit: int = Query(20, ge=1, le=100, description="Số bản ghi mỗi trang"),
    admin_auth: bool = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Shop)

    if status_filter and isinstance(status_filter, str):
        query = query.filter(Shop.status == status_filter.lower())
    if platform_filter and isinstance(platform_filter, str):
        query = query.filter(Shop.platform == platform_filter.lower())

    p = page if isinstance(page, int) else 1
    l = limit if isinstance(limit, int) else 20

    total = query.count()
    shops = query.order_by(Shop.created_at.desc()).offset((p - 1) * l).limit(l).all()

    # Kiểm tra xem shop có hồ sơ pending hay không
    shop_items = []
    for s in shops:
        has_pending = db.query(Verification).filter(
            Verification.shop_id == s.id,
            Verification.status == VerificationStatus.PENDING
        ).first() is not None

        item = ShopListItem(
            id=s.id,
            email=s.email,
            phone=s.phone,
            shop_name=s.shop_name,
            platform=s.platform,
            shop_url=s.shop_url,
            status=s.status,
            email_verified=s.email_verified,
            phone_verified=s.phone_verified,
            created_at=s.created_at,
            has_pending_verification=has_pending
        )
        shop_items.append(item)

    return ShopListResponse(
        total=total,
        page=page,
        limit=limit,
        shops=shop_items
    )


@router.get(
    "/verifications/pending",
    response_model=List[VerificationResponse],
    summary="Danh sách các hồ sơ xác minh danh tính đang chờ duyệt"
)
def list_pending_verifications(
    admin_auth: bool = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    pending = db.query(Verification).filter(
        Verification.status == VerificationStatus.PENDING
    ).order_by(Verification.submitted_at.asc()).all()

    return [VerificationResponse.model_validate(v) for v in pending]


@router.post(
    "/verifications/{verification_id}/review",
    response_model=VerificationResponse,
    summary="Phê duyệt hoặc từ chối hồ sơ xác minh danh tính"
)
def review_shop_verification(
    verification_id: str,
    payload: AdminReviewRequest,
    admin_auth: bool = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    verification = review_verification(
        db=db,
        verification_id=verification_id,
        action=payload.action,
        admin_note=payload.admin_note,
        admin_id="admin_tapai"
    )
    return VerificationResponse.model_validate(verification)


@router.patch(
    "/shops/{shop_id}/status",
    response_model=ShopInfo,
    summary="Cập nhật trạng thái shop (ví dụ: tạm khóa suspended, mở khóa, v.v.)"
)
def update_shop_status(
    shop_id: str,
    payload: AdminShopStatusUpdateRequest,
    admin_auth: bool = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản shop")

    shop.status = payload.status
    db.commit()
    db.refresh(shop)
    return ShopInfo.model_validate(shop)


@router.get(
    "/stats",
    response_model=AdminStatsResponse,
    summary="Báo cáo thống kê tổng quan toàn hệ thống"
)
def get_system_stats(
    admin_auth: bool = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    total_shops = db.query(Shop).count()
    verified_shops = db.query(Shop).filter(Shop.status == ShopStatus.VERIFIED).count()
    pending_verifications = db.query(Verification).filter(Verification.status == VerificationStatus.PENDING).count()
    suspended_shops = db.query(Shop).filter(Shop.status == ShopStatus.SUSPENDED).count()
    rejected_shops = db.query(Shop).filter(Shop.status == ShopStatus.REJECTED).count()
    total_products = db.query(Product).count()
    total_clicks = db.query(Click).count()
    total_conversions = db.query(Conversion).count()

    return AdminStatsResponse(
        total_shops=total_shops,
        verified_shops=verified_shops,
        pending_verifications=pending_verifications,
        suspended_shops=suspended_shops,
        rejected_shops=rejected_shops,
        total_products=total_products,
        total_clicks=total_clicks,
        total_conversions=total_conversions
    )
