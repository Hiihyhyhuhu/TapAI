from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Shop, Click, Conversion
from models.tracking_schemas import (
    ClickRecordRequest,
    ClickRecordResponse,
    ConversionRecordRequest,
    ConversionResponse,
)
from services.tracking_service import (
    record_click,
    record_conversion,
    get_click_detail,
    handle_cpc_redirect_gateway,
    get_cpc_click_ledger,
)
from services.link_wrapper_service import wrap_affiliate_link
from middleware.auth_middleware import get_current_shop

router = APIRouter(prefix="/api/v1/tracking", tags=["Tracking Engine (Clicks & Conversions)"])

@router.get(
    "/redirect/{product_id}",
    summary="STAGE 4: Redirect Gateway với bộ lọc Anti-Fraud và Khấu trừ ví CPC thời gian thực (Alias)"
)
def redirect_to_affiliate(
    product_id: str,
    request: Request,
    ext_user_id: Optional[str] = Query(None, alias="ext_uid", description="Mã người dùng Extension"),
    source: str = Query("EXTENSION_SIDEBAR", description="Nguồn ngữ cảnh"),
    test_fraud: Optional[str] = Query(None, description="bot | duplicate (dành cho thử nghiệm QA)"),
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")

    result = handle_cpc_redirect_gateway(
        db=db,
        product_id=product_id,
        ext_uid=ext_user_id,
        client_ip=client_ip,
        user_agent=user_agent,
        test_fraud=test_fraud
    )
    return RedirectResponse(url=result["redirect_url"], status_code=status.HTTP_302_FOUND)


@router.get(
    "/cpc-ledger",
    summary="STAGE 4: Bảng kê chi tiết lượt click đối soát thời gian thực (Click Ledger)"
)
def get_cpc_ledger_route(
    limit: int = Query(50, ge=1, le=100),
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    return get_cpc_click_ledger(db=db, shop_id=current_shop.id, limit=limit)



@router.post(
    "/wrap-link",
    summary="Dynamic Link Wrapper: Bọc shortlink Affiliate gắn đủ 4 tham số sub_id1..4 và ghi nhận click_trackings"
)
def wrap_link(
    product_id: str = Query(..., description="Mã ID của sản phẩm"),
    ext_user_id: Optional[str] = Query(None, description="Mã người dùng Extension (sub_id3)"),
    source_platform: str = Query("FB_REELS", description="Nguồn ngữ cảnh (sub_id4: FB_REELS, FB_FEED, TIKTOK_VIDEO...)"),
    db: Session = Depends(get_db)
):
    return wrap_affiliate_link(
        db=db,
        product_id=product_id,
        ext_user_id=ext_user_id,
        source_platform=source_platform
    )

@router.post(
    "/click",
    response_model=ClickRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ghi nhận lượt click 'Mua ngay' từ Extension và sinh link chuyển hướng gắn mã tracking"
)
def track_click(
    payload: ClickRecordRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    click = record_click(
        db=db,
        product_id=payload.product_id,
        user_session_id=payload.user_session_id,
        source_type=payload.source_type or "video",
        referral_url=payload.referral_url,
        client_ip=client_ip,
        user_agent=user_agent
    )

    return ClickRecordResponse(
        click_id=click.id,
        product_id=click.product_id,
        shop_id=click.shop_id,
        redirect_url=click.redirect_url,
        clicked_at=click.clicked_at
    )


@router.post(
    "/conversion",
    response_model=ConversionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Webhook ghi nhận đơn hàng thành công và tự động tính toán hoa hồng"
)
def track_conversion(
    payload: ConversionRecordRequest,
    db: Session = Depends(get_db)
):
    conversion = record_conversion(
        db=db,
        click_id=payload.click_id,
        order_id=payload.order_id,
        order_value=payload.order_value,
        status_str=payload.status or "confirmed"
    )

    return ConversionResponse(
        id=conversion.id,
        click_id=conversion.click_id,
        product_id=conversion.product_id,
        shop_id=conversion.shop_id,
        order_id=conversion.order_id,
        order_value=float(conversion.order_value),
        commission_earned=float(conversion.commission_earned),
        status=conversion.status,
        converted_at=conversion.converted_at,
        confirmed_at=conversion.confirmed_at
    )


@router.get(
    "/click/{click_id}",
    summary="Tra cứu thông tin chi tiết của 1 lượt click"
)
def get_click(
    click_id: str,
    current_shop: Shop = Depends(get_current_shop),
    db: Session = Depends(get_db)
):
    click = get_click_detail(db=db, click_id=click_id, shop_id=current_shop.id)
    return {
        "click_id": click.id,
        "product_id": click.product_id,
        "shop_id": click.shop_id,
        "source_type": click.source_type,
        "referral_url": click.referral_url,
        "clicked_at": click.clicked_at,
        "has_conversion": click.conversion is not None,
        "order_id": click.conversion.order_id if click.conversion else None
    }
