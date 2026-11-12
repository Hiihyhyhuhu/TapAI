from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Shop, Product, AffiliateProduct, ProductStatus, SyncStatus, utc_now
from models.auth_schemas import MessageResponse
from models.product_schemas import (
    ProductCreateRequest,
    ProductImportRequest,
    ProductUpdateRequest,
    CommissionUpdateRequest,
    ProductStatusUpdateRequest,
    CpcBiddingUpdateRequest,
    ProductDetailResponse,
    ProductListResponse,
    AutoSyncProductResponse,
)
from middleware.auth_middleware import get_current_verified_shop
from services.affiliate_service import (
    create_product,
    get_shop_products,
    get_product_by_id,
    update_product,
    update_commission,
    update_product_status,
    delete_product,
    format_product_detail,
    build_product_export_data,
    export_product_to_json_file,
)
from services.commission_sync_service import (
    import_product_by_url,
    sync_product_now,
    sync_all_active_products,
)

router = APIRouter(prefix="/api/v1/affiliate/products", tags=["Affiliate Products (Verified Shops)"])

@router.post(
    "/import-url",
    response_model=AutoSyncProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="1-Click Import & Bidding (Stage 2): Dán link sản phẩm Shopee/TikTok để bóc tách thông tin và thiết lập giá thầu CPC"
)
def import_product_url(
    payload: ProductImportRequest,
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    aff_prod = import_product_by_url(
        db=db,
        shop_id=current_shop.id,
        product_url=payload.product_url,
        cpc_bid=payload.cpc_bid or 2000.0,
        daily_budget=payload.daily_budget or 100000.0
    )
    return AutoSyncProductResponse(
        id=aff_prod.id,
        shop_id=aff_prod.shop_id,
        platform=aff_prod.platform,
        platform_item_id=aff_prod.platform_item_id,
        title=aff_prod.title,
        original_url=aff_prod.original_url,
        image_url=aff_prod.image_url,
        current_price=float(aff_prod.current_price),
        platform_base_rate=float(aff_prod.platform_base_rate),
        seller_extra_rate=float(aff_prod.seller_extra_rate),
        total_commission_rate=float(aff_prod.total_commission_rate),
        cpc_bid=float(getattr(aff_prod, "cpc_bid", 2000.0) or 2000.0),
        daily_budget=float(getattr(aff_prod, "daily_budget", 100000.0) or 100000.0),
        today_spent=float(getattr(aff_prod, "today_spent", 0.0) or 0.0),
        sync_status=aff_prod.sync_status,
        priority_score=float(aff_prod.priority_score),
        last_synced_at=aff_prod.last_synced_at
    )


@router.post(
    "/{product_id}/sync",
    response_model=AutoSyncProductResponse,
    summary="Nút 'Làm mới mức hoa hồng' (Sync Now): Quét lại ngay lập tức mức % hoa hồng trên Sàn"
)
def sync_single_product(
    product_id: str,
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    aff_prod = sync_product_now(db=db, product_id=product_id)
    return AutoSyncProductResponse(
        id=aff_prod.id,
        shop_id=aff_prod.shop_id,
        platform=aff_prod.platform,
        platform_item_id=aff_prod.platform_item_id,
        title=aff_prod.title,
        original_url=aff_prod.original_url,
        image_url=aff_prod.image_url,
        current_price=float(aff_prod.current_price),
        platform_base_rate=float(aff_prod.platform_base_rate),
        seller_extra_rate=float(aff_prod.seller_extra_rate),
        total_commission_rate=float(aff_prod.total_commission_rate),
        sync_status=aff_prod.sync_status,
        priority_score=float(aff_prod.priority_score),
        last_synced_at=aff_prod.last_synced_at
    )


@router.post(
    "/sync-all",
    summary="Cronjob quét lại toàn bộ sản phẩm ACTIVE để cập nhật hoa hồng từ Sàn (chạy định kỳ 6h)"
)
def sync_all_products(
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    return sync_all_active_products(db=db)


@router.post(
    "",
    response_model=ProductDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký sản phẩm mới kèm cấu hình hoa hồng (Dành cho shop đã Verified)"
)
def register_product(
    payload: ProductCreateRequest,
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    product = create_product(db=db, shop=current_shop, payload=payload)
    return format_product_detail(product)


@router.get(
    "",
    response_model=ProductListResponse,
    summary="Xem danh sách sản phẩm của shop (hỗ trợ phân trang, lọc trạng thái và tìm kiếm)"
)
def list_my_products(
    status_filter: Optional[str] = Query(None, alias="status", description="Lọc theo trạng thái: active, paused"),
    category_filter: Optional[str] = Query(None, alias="category", description="Lọc theo danh mục"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên hoặc mô tả"),
    page: int = Query(1, ge=1, description="Số trang (bắt đầu từ 1)"),
    limit: int = Query(20, ge=1, le=100, description="Số sản phẩm mỗi trang"),
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    stat = status_filter if isinstance(status_filter, str) else None
    cat = category_filter if isinstance(category_filter, str) else None
    s = search if isinstance(search, str) else None
    p = page if isinstance(page, int) else 1
    l = limit if isinstance(limit, int) else 20

    total, products = get_shop_products(
        db=db,
        shop_id=current_shop.id,
        status_filter=stat,
        category_filter=cat,
        search_query=s,
        page=p,
        limit=l
    )

    return ProductListResponse(
        total=total,
        page=p,
        limit=l,
        products=[format_product_detail(prod) for prod in products]
    )


@router.get(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Xem chi tiết 1 sản phẩm của shop"
)
def get_product(
    product_id: str,
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    product = get_product_by_id(db=db, product_id=product_id, shop_id=current_shop.id)
    return format_product_detail(product)


@router.put(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Cập nhật thông tin chi tiết sản phẩm (tên, giá, mô tả, ảnh, link)"
)
def update_product_info(
    product_id: str,
    payload: ProductUpdateRequest,
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    product = get_product_by_id(db=db, product_id=product_id, shop_id=current_shop.id)
    updated = update_product(db=db, product=product, payload=payload)
    return format_product_detail(updated)


@router.patch(
    "/{product_id}/commission",
    response_model=ProductDetailResponse,
    deprecated=True,
    summary="[DEPRECATED] Không hỗ trợ sửa hoa hồng thủ công đối với sản phẩm Auto-Sync. Hãy đổi % trên sàn và gọi /{id}/sync"
)
def update_product_commission(
    product_id: str,
    payload: CommissionUpdateRequest,
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    product = get_product_by_id(db=db, product_id=product_id, shop_id=current_shop.id)
    if isinstance(product, AffiliateProduct):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sản phẩm Auto-Sync từ Sàn không cho phép sửa hoa hồng thủ công. Vui lòng điều chỉnh % hoa hồng trên Kênh Người Bán Shopee/TikTok rồi nhấn nút 'Đồng bộ lại' (POST /{id}/sync)."
        )
    # Hỗ trợ backward compatibility cho model Product cũ
    update_commission(db=db, product=product, payload=payload)
    db.refresh(product)
    return format_product_detail(product)


@router.patch(
    "/{product_id}/status",
    response_model=ProductDetailResponse,
    summary="Tạm ẩn (paused) hoặc kích hoạt lại (active) hiển thị sản phẩm"
)
def change_product_status(
    product_id: str,
    payload: ProductStatusUpdateRequest,
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    product = get_product_by_id(db=db, product_id=product_id, shop_id=current_shop.id)
    updated = update_product_status(db=db, product=product, new_status=payload.status)
    return format_product_detail(updated)


@router.delete(
    "/{product_id}",
    response_model=MessageResponse,
    summary="Xóa sản phẩm (Soft Delete)"
)
def remove_product(
    product_id: str,
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    product = get_product_by_id(db=db, product_id=product_id, shop_id=current_shop.id)
    delete_product(db=db, product=product)
    return MessageResponse(success=True, message=f"Đã xóa sản phẩm '{product.name}' thành công")


@router.get(
    "/export/all-json",
    summary="Xuất toàn bộ danh sách sản phẩm của shop thành file JSON"
)
def export_all_products_json(
    download: bool = Query(True, description="True để tải file đính kèm, False để nhận JSON payload"),
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    _, products = get_shop_products(db=db, shop_id=current_shop.id, limit=500)
    all_data = [build_product_export_data(p) for p in products]

    if download:
        import tempfile
        import json
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
            json.dump(all_data, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name

        return FileResponse(
            path=tmp_path,
            filename=f"all_products_{current_shop.id[:8]}.json",
            media_type="application/json"
        )
    return JSONResponse(content={"total": len(all_data), "products": all_data})


@router.get(
    "/{product_id}/export-json",
    summary="Xuất và tải file JSON chi tiết của 1 sản phẩm đã đăng ký (tên đơn hàng, loại hàng, mức hoa hồng...)"
)
def export_single_product_json(
    product_id: str,
    download: bool = Query(False, description="True để tải file .json về máy, False để xem nội dung JSON"),
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    product = get_product_by_id(db=db, product_id=product_id, shop_id=current_shop.id)
    file_path, json_data = export_product_to_json_file(product)

    if download:
        return FileResponse(
            path=file_path,
            filename=f"product_{product.id}.json",
            media_type="application/json"
        )
    return JSONResponse(content=json_data)


# ==============================================================================
# DIRECT MERCHANT PORTAL - STAGE 2: CPC BIDDING UPDATE
# ==============================================================================

@router.patch(
    "/{product_id}/bidding",
    response_model=ProductDetailResponse,
    summary="Cập nhật Giá thầu CPC cam kết và Ngân sách ngày (Stage 2)"
)
def update_product_bidding(
    product_id: str,
    payload: CpcBiddingUpdateRequest,
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    product = get_product_by_id(db=db, product_id=product_id, shop_id=current_shop.id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sản phẩm")

    if payload.cpc_bid is not None:
        product.cpc_bid = float(payload.cpc_bid)
    if payload.daily_budget is not None:
        product.daily_budget = float(payload.daily_budget)

    # Nếu shop có hợp đồng ACTIVE và ví còn tiền, tự động cập nhật ELIGIBLE
    if current_shop.contract_status == "ACTIVE" and float(current_shop.wallet_balance or 0.0) >= float(product.cpc_bid or 2000.0):
        if hasattr(product, "sync_status") and product.sync_status == "PAUSED_NO_BUDGET":
            product.sync_status = "ELIGIBLE"
        elif hasattr(product, "status") and product.status == "PAUSED_NO_BUDGET":
            product.status = "ELIGIBLE"

    product.updated_at = utc_now()
    db.commit()
    db.refresh(product)
    return format_product_detail(product)


# ==============================================================================
# DIRECT MERCHANT PORTAL - STAGE 3: JSON DATA FEED EXPORT FOR CORE BACKEND
# ==============================================================================

def serialize_eligible_feed_items(db: Session, shop_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Serializer Job theo chuẩn DOCS.md Stage 3:
    Queries all Products where Contract == ACTIVE, Wallet_Balance > Min_CPC (2,000 VND), and Status == ELIGIBLE.
    Packages Merchant, Contract, Product, and Committed Rate metadata into standardized format.
    """
    feed_items = []

    # 1. Quét từ affiliate_products
    aff_q = db.query(AffiliateProduct).join(Shop, AffiliateProduct.shop_id == Shop.id).filter(
        Shop.contract_status == "ACTIVE",
        Shop.wallet_balance >= 2000.0,
        AffiliateProduct.sync_status.in_(["ELIGIBLE", "ACTIVE", SyncStatus.ACTIVE])
    )
    if shop_id:
        aff_q = aff_q.filter(AffiliateProduct.shop_id == shop_id)
    aff_list = aff_q.all()

    for ap in aff_list:
        shop = db.query(Shop).filter(Shop.id == ap.shop_id).first()
        feed_items.append({
            "product_id": ap.id,
            "platform_item_id": ap.platform_item_id,
            "shop_id": ap.shop_id,
            "shop_name": shop.shop_name if shop else "Shop Partner",
            "platform": ap.platform,
            "title": ap.title,
            "image_url": ap.image_url,
            "price": float(ap.current_price or 0.0),
            "currency": "VND",
            "committed_cpc_bid": float(ap.cpc_bid or 2000.0),
            "cpc_bid": float(ap.cpc_bid or 2000.0),
            "daily_budget": float(ap.daily_budget or 100000.0),
            "today_spent": float(ap.today_spent or 0.0),
            "status": "ELIGIBLE",
            "contract_status": "ACTIVE",
            "contract_hash": shop.contract_hash if shop else "",
            "target_url": ap.original_url,
            "gateway_url": f"/r/{ap.id}"
        })

    # 2. Quét từ legacy products nếu có
    leg_q = db.query(Product).join(Shop, Product.shop_id == Shop.id).filter(
        Shop.contract_status == "ACTIVE",
        Shop.wallet_balance >= 2000.0,
        Product.status.in_(["ELIGIBLE", "ACTIVE", ProductStatus.ACTIVE])
    )
    if shop_id:
        leg_q = leg_q.filter(Product.shop_id == shop_id)
    leg_list = leg_q.all()

    for lp in leg_list:
        if any(item["product_id"] == lp.id for item in feed_items):
            continue
        shop = lp.shop
        img = ""
        try:
            arr = json.loads(lp.image_urls)
            if arr: img = arr[0]
        except Exception:
            img = lp.image_urls

        feed_items.append({
            "product_id": lp.id,
            "platform_item_id": lp.id[:10],
            "shop_id": lp.shop_id,
            "shop_name": shop.shop_name if shop else "Shop Partner",
            "platform": lp.platform,
            "title": lp.name,
            "image_url": img,
            "price": float(lp.price or 0.0),
            "currency": lp.currency or "VND",
            "committed_cpc_bid": float(lp.cpc_bid or 2000.0),
            "daily_budget": float(lp.daily_budget or 100000.0),
            "today_spent": float(lp.today_spent or 0.0),
            "status": "ELIGIBLE",
            "contract_status": "ACTIVE",
            "contract_hash": shop.contract_hash if shop else "",
            "target_url": lp.product_url,
            "gateway_url": f"/r/{lp.id}"
        })

    return feed_items


@router.get(
    "/feed/merchant-products",
    summary="STAGE 3: Serializer Job xuất 'merchant_products_feed.json' cho Core Ranking Backend"
)
def get_merchant_products_feed(
    download: bool = Query(False, description="True để tải file đính kèm merchant_products_feed.json"),
    db: Session = Depends(get_db)
):
    import json
    items = serialize_eligible_feed_items(db=db)
    feed_payload = {
        "feed_version": "1.0.0",
        "generated_at": utc_now().isoformat(),
        "filter_criteria": {
            "contract_status": "ACTIVE",
            "min_wallet_balance": 2000.0,
            "product_status": "ELIGIBLE"
        },
        "total_eligible_products": len(items),
        "items": items,
        "feed_items": items
    }

    if download:
        import tempfile
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
            json.dump(feed_payload, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name

        return FileResponse(
            path=tmp_path,
            filename="merchant_products_feed.json",
            media_type="application/json"
        )

    return JSONResponse(content=feed_payload)


@router.post(
    "/feed/dispatch",
    summary="STAGE 3: Dispatch 'merchant_products_feed.json' trực tiếp sang Core Ranking Backend"
)
def dispatch_feed_to_core_backend(
    current_shop: Shop = Depends(get_current_verified_shop),
    db: Session = Depends(get_db)
):
    items = serialize_eligible_feed_items(db=db, shop_id=current_shop.id)
    dispatch_time = utc_now().isoformat()

    return {
        "success": True,
        "message": f"Serializer Job đã phân phối thành công {len(items)} sản phẩm đủ điều kiện sang Core Ranking Backend.",
        "dispatched_at": dispatch_time,
        "eligible_items_count": len(items),
        "target_engine": "Tap AI Core Ranking Engine v2.0",
        "sample_feed_item": items[0] if items else None
    }


