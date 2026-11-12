import os
import json
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc

from database.models import (
    Shop,
    Product,
    Commission,
    AffiliateProduct,
    SyncStatus,
    ShopStatus,
    ProductStatus,
    CommissionType,
    utc_now,
)
from models.product_schemas import (
    ProductCreateRequest,
    ProductUpdateRequest,
    CommissionUpdateRequest,
    CommissionResponse,
    ProductDetailResponse,
)
from services.verification_service import validate_platform_url

# Mức hoa hồng cố định sàn Shopee chi trả cho TAP AI (~3.5%)
SHOPEE_FIXED_PLATFORM_RATE = 3.5
# Mức hoa hồng tối thiểu các sàn khác phải cam kết
MIN_COMMISSION_PERCENTAGE_OTHER = 2.0
MIN_COMMISSION_FIXED_AMOUNT_OTHER = 5000.0

def validate_and_compute_commission(
    platform: str,
    comm_type: str,
    extra_rate: float,
    extra_fixed_amount: float
) -> Tuple[float, float, float, float]:
    """
    Tính toán và kiểm tra tính hợp lệ của hoa hồng theo chính sách:
    1. Shopee: Nhận cố định 3.5% từ Shopee Affiliate + Hoa hồng Xtra do Shop tự quyết định.
    2. Sàn khác (Lazada, Tiki, TikTok Shop...): Do Shop quyết định toàn bộ, tối thiểu >= 2.0% hoặc >= 5.000₫/đơn.
    Trả về: (platform_rate, extra_rate, extra_fixed_amount, min_rate)
    """
    norm_platform = platform.lower().strip()

    if norm_platform == "shopee":
        plat_rate = SHOPEE_FIXED_PLATFORM_RATE
        min_rate = 0.0
        # Shop có thể đặt 0% hoặc cao hơn cho Xtra
        return plat_rate, round(extra_rate, 2), round(extra_fixed_amount, 2), min_rate
    else:
        plat_rate = 0.0
        if comm_type == CommissionType.PERCENTAGE:
            min_rate = MIN_COMMISSION_PERCENTAGE_OTHER
            if extra_rate < min_rate:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Mức hoa hồng tối thiểu cho sàn '{platform}' là {min_rate}% (bạn đang đặt {extra_rate}%)"
                )
            return plat_rate, round(extra_rate, 2), 0.0, min_rate
        else:
            min_rate = 0.0
            if extra_fixed_amount < MIN_COMMISSION_FIXED_AMOUNT_OTHER:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Mức hoa hồng cố định tối thiểu cho mỗi đơn hàng là {int(MIN_COMMISSION_FIXED_AMOUNT_OTHER):,}₫"
                )
            return plat_rate, 0.0, round(extra_fixed_amount, 2), min_rate

def format_product_detail(product) -> ProductDetailResponse:
    """Chuyển đổi đối tượng ORM Product hoặc AffiliateProduct sang ProductDetailResponse schema."""
    image_list: List[str] = []
    if hasattr(product, "image_urls_list") and product.image_urls_list:
        image_list = product.image_urls_list
    else:
        raw_imgs = getattr(product, "image_urls", None)
        try:
            image_list = json.loads(raw_imgs) if raw_imgs else []
        except Exception:
            image_list = [raw_imgs] if raw_imgs else []

    thumbnail = image_list[0] if image_list else (getattr(product, "image_url", None) or "")

    comm_resp = None
    if getattr(product, "commissions", None):
        active_comm = product.commissions[0]
        total_rate = float(active_comm.platform_rate or 0.0) + float(active_comm.extra_rate or 0.0)
        comm_resp = CommissionResponse(
            id=active_comm.id,
            platform=active_comm.platform,
            commission_type=getattr(active_comm, "commission_type", "percentage"),
            platform_rate=float(active_comm.platform_rate or 0.0),
            extra_rate=float(active_comm.extra_rate or 0.0),
            extra_fixed_amount=float(getattr(active_comm, "extra_fixed_amount", 0.0) or 0.0),
            total_rate=round(total_rate, 2),
            min_rate=float(getattr(active_comm, "min_rate", 0.0) or 0.0)
        )

    filename = f"product_{product.id}.json"
    download_url = f"/api/v1/affiliate/products/{product.id}/export-json"

    p_base = float(getattr(product, "platform_base_rate", 0.0) or 0.0)
    p_extra = float(getattr(product, "seller_extra_rate", 0.0) or 0.0)
    p_total = float(getattr(product, "total_commission_rate", 0.0) or (comm_resp.total_rate if comm_resp else 0.0))
    p_sync = getattr(product, "sync_status", "ACTIVE")

    return ProductDetailResponse(
        id=product.id,
        shop_id=product.shop_id,
        shop_name=product.shop.shop_name if getattr(product, "shop", None) else "",
        name=getattr(product, "name", None) or getattr(product, "title", "Sản phẩm"),
        category=getattr(product, "category", "Thời trang"),
        product_url=getattr(product, "product_url", None) or getattr(product, "original_url", ""),
        platform=product.platform,
        image_urls=image_list,
        thumbnail_url=thumbnail,
        description=getattr(product, "description", None),
        price=float(getattr(product, "price", None) or getattr(product, "current_price", 0.0)),
        currency=getattr(product, "currency", "VND") or "VND",
        status=getattr(product, "status", "active"),
        commission=comm_resp,
        platform_base_rate=p_base,
        seller_extra_rate=p_extra,
        total_commission_rate=p_total,
        cpc_bid=float(getattr(product, "cpc_bid", 2000.0) or 2000.0),
        daily_budget=float(getattr(product, "daily_budget", 100000.0) or 100000.0),
        today_spent=float(getattr(product, "today_spent", 0.0) or 0.0),
        sync_status=p_sync,
        export_file_name=filename,
        export_download_url=download_url,
        created_at=product.created_at,
        updated_at=product.updated_at
    )

def build_product_export_data(product: Product) -> Dict[str, Any]:
    """
    Xây dựng cấu trúc dữ liệu JSON xuất khẩu tiêu chuẩn cho mỗi sản phẩm được đăng ký.
    Bao gồm tên đơn hàng, loại hàng, mức phí hoa hồng và các thông số cần thiết khác.
    """
    image_list: List[str] = []
    try:
        image_list = json.loads(product.image_urls) if product.image_urls else []
    except Exception:
        image_list = [product.image_urls] if product.image_urls else []
    thumbnail = image_list[0] if image_list else ""

    price_float = float(product.price)
    comm = product.commissions[0] if product.commissions else None

    plat_rate = float(comm.platform_rate or 0.0) if comm else 0.0
    extra_rate = float(comm.extra_rate or 0.0) if comm else 0.0
    total_rate = round(plat_rate + extra_rate, 2)
    comm_type = comm.commission_type if comm else "percentage"
    extra_fixed = float(comm.extra_fixed_amount or 0.0) if comm else 0.0

    # Ước tính hoa hồng nhận được trên mỗi đơn hàng thành công
    if comm_type == "fixed_amount" and extra_fixed > 0:
        est_commission = extra_fixed
    else:
        est_commission = round(price_float * (total_rate / 100.0), 2)

    export_now = utc_now().isoformat()
    created_time = product.created_at.isoformat() if product.created_at else export_now

    price_formatted = f"{int(price_float):,} ₫".replace(",", ".")
    est_comm_formatted = f"{int(est_commission):,} ₫".replace(",", ".")

    return {
        "order_item_name": product.name,           # Tên đơn hàng / Tên sản phẩm đăng ký
        "product_name": product.name,              # Tên sản phẩm
        "category": product.category,              # Loại hàng / Ngành hàng
        "platform": product.platform,              # Sàn TMĐT (Shopee, Lazada, TikTok...)
        "product_id": product.id,                  # Mã định danh sản phẩm
        "shop_id": product.shop_id,                # Mã định danh Shop
        "shop_name": product.shop.shop_name if product.shop else "",
        "pricing": {
            "price": price_float,
            "currency": product.currency or "VND",
            "price_formatted": price_formatted
        },
        "commission_rate": {
            "commission_type": comm_type,
            "total_rate_percent": total_rate,      # Tổng mức phí hoa hồng (%)
            "platform_rate_percent": plat_rate,    # Hoa hồng cố định từ sàn (%)
            "extra_rate_percent": extra_rate,      # Hoa hồng bổ sung Xtra của shop (%)
            "extra_fixed_amount": extra_fixed,     # Hoa hồng cố định VND nếu có
            "estimated_commission_per_order": est_commission,
            "estimated_commission_formatted": est_comm_formatted
        },
        "product_url": product.product_url,        # Link đặt hàng sản phẩm
        "thumbnail_url": thumbnail,                # Ảnh đại diện
        "image_urls": image_list,                  # Danh sách ảnh chi tiết
        "description": product.description or "",   # Mô tả sản phẩm
        "status": product.status,                  # Trạng thái hiển thị (active, paused...)
        "registered_at": created_time,             # Thời gian đăng ký vào hệ thống
        "export_metadata": {
            "exported_at": export_now,
            "generator": "TAP AI Partner Engine",
            "schema_version": "1.0.0",
            "export_filename": f"product_{product.id}.json"
        }
    }

def export_product_to_json_file(product: Product, export_dir: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Xuất thông tin sản phẩm vừa đăng ký ra 1 file JSON và lưu vào đĩa cứng.
    Trả về đường dẫn file tuyệt đối và đối tượng dữ liệu JSON.
    """
    if not export_dir:
        base_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        export_dir = os.path.join(base_backend, "exports", "products")

    os.makedirs(export_dir, exist_ok=True)
    export_data = build_product_export_data(product)

    filename = f"product_{product.id}.json"
    file_path = os.path.join(export_dir, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    return file_path, export_data

def create_product(db: Session, shop: Shop, payload: ProductCreateRequest) -> Product:
    """Tạo mới 1 sản phẩm affiliate kèm bản ghi hoa hồng."""
    product_platform = (payload.platform or shop.platform).lower().strip()

    # 1. Thẩm định URL sản phẩm
    if not validate_platform_url(product_platform, payload.product_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Đường dẫn sản phẩm không hợp lệ hoặc không thuộc sàn '{product_platform}'"
        )

    # 2. Thẩm định và tính toán hoa hồng
    plat_rate, ext_rate, ext_fixed, min_rate = validate_and_compute_commission(
        platform=product_platform,
        comm_type=payload.commission.commission_type,
        extra_rate=payload.commission.extra_rate,
        extra_fixed_amount=payload.commission.extra_fixed_amount
    )

    # 3. Tạo sản phẩm (Stage 2: CPC Bidding & Status Transition)
    cpc_bid_val = getattr(payload, "cpc_bid", 2000.0) or 2000.0
    daily_budget_val = getattr(payload, "daily_budget", 100000.0) or 100000.0
    is_eligible = (shop.contract_status == "ACTIVE" and float(shop.wallet_balance or 0.0) >= cpc_bid_val)
    prod_status = "ELIGIBLE" if is_eligible else ProductStatus.ACTIVE

    new_product = Product(
        shop_id=shop.id,
        name=payload.name.strip(),
        category=payload.category.strip(),
        product_url=payload.product_url.strip(),
        platform=product_platform,
        image_urls=json.dumps(payload.image_urls, ensure_ascii=False),
        description=payload.description.strip() if payload.description else None,
        price=payload.price,
        currency="VND",
        cpc_bid=cpc_bid_val,
        daily_budget=daily_budget_val,
        today_spent=0.0,
        status=prod_status,
        created_at=utc_now(),
        updated_at=utc_now()
    )
    db.add(new_product)
    db.flush()

    # 4. Tạo bản ghi hoa hồng
    commission = Commission(
        product_id=new_product.id,
        platform=product_platform,
        commission_type=payload.commission.commission_type,
        platform_rate=plat_rate,
        extra_rate=ext_rate,
        extra_fixed_amount=ext_fixed,
        min_rate=min_rate,
        effective_from=utc_now()
    )
    db.add(commission)
    db.commit()
    db.refresh(new_product)

    # 5. Tự động xuất 1 file JSON cho mỗi sản phẩm được đăng ký
    try:
        export_product_to_json_file(new_product)
    except Exception as e:
        print(f"⚠️ [Export JSON] Lỗi khi lưu file xuất JSON cho sản phẩm {new_product.id}: {e}")

    return new_product

def get_shop_products(
    db: Session,
    shop_id: str,
    status_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    search_query: Optional[str] = None,
    page: int = 1,
    limit: int = 20
) -> Tuple[int, List[Any]]:
    """Lấy danh sách sản phẩm của 1 shop (kết hợp cả affiliate_products và products legacy)."""
    # 1. Lấy sản phẩm từ bảng affiliate_products (Auto-sync)
    aff_query = db.query(AffiliateProduct).filter(AffiliateProduct.shop_id == shop_id)
    if status_filter:
        stat_up = status_filter.upper()
        if stat_up == "ACTIVE":
            aff_query = aff_query.filter(AffiliateProduct.sync_status == SyncStatus.ACTIVE)
        elif stat_up == "PAUSED":
            aff_query = aff_query.filter(AffiliateProduct.sync_status != SyncStatus.ACTIVE)
    if search_query:
        aff_query = aff_query.filter(AffiliateProduct.title.ilike(f"%{search_query.strip()}%"))
    aff_products = aff_query.order_by(desc(AffiliateProduct.created_at)).all()

    # 2. Lấy sản phẩm từ bảng products (Legacy)
    legacy_query = db.query(Product).filter(
        Product.shop_id == shop_id,
        Product.status != ProductStatus.DELETED
    )
    if status_filter:
        legacy_query = legacy_query.filter(Product.status == status_filter.lower().strip())
    if category_filter:
        legacy_query = legacy_query.filter(Product.category.ilike(f"%{category_filter.strip()}%"))
    if search_query:
        legacy_query = legacy_query.filter(
            or_(
                Product.name.ilike(f"%{search_query.strip()}%"),
                Product.description.ilike(f"%{search_query.strip()}%")
            )
        )
    legacy_products = legacy_query.order_by(desc(Product.created_at)).all()

    # Hợp nhất danh sách: ưu tiên sản phẩm auto-sync mới
    combined = aff_products + legacy_products
    total = len(combined)
    paginated = combined[(page - 1) * limit : page * limit]

    return total, paginated

def get_product_by_id(db: Session, product_id: str, shop_id: Optional[str] = None) -> Any:
    """Lấy chi tiết 1 sản phẩm từ affiliate_products hoặc bảng products cũ."""
    aff_query = db.query(AffiliateProduct).filter(AffiliateProduct.id == product_id)
    if shop_id:
        aff_query = aff_query.filter(AffiliateProduct.shop_id == shop_id)
    aff = aff_query.first()
    if aff:
        return aff

    query = db.query(Product).filter(
        Product.id == product_id,
        Product.status != ProductStatus.DELETED
    )
    if shop_id:
        query = query.filter(Product.shop_id == shop_id)

    product = query.first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sản phẩm")
    return product

def update_product(db: Session, product: Product, payload: ProductUpdateRequest) -> Product:
    """Cập nhật thông tin mô tả, giá bán, ảnh của sản phẩm."""
    if payload.name is not None:
        product.name = payload.name.strip()
    if payload.category is not None:
        product.category = payload.category.strip()
    if payload.price is not None:
        product.price = payload.price
    if payload.description is not None:
        product.description = payload.description.strip()
    if payload.image_urls is not None:
        product.image_urls = json.dumps(payload.image_urls, ensure_ascii=False)
    if payload.product_url is not None:
        if not validate_platform_url(product.platform, payload.product_url):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Link mới không thuộc sàn '{product.platform}'")
        product.product_url = payload.product_url.strip()

    product.updated_at = utc_now()
    db.commit()
    db.refresh(product)
    return product

def update_commission(db: Session, product: Product, payload: CommissionUpdateRequest) -> Commission:
    """Cập nhật tỷ lệ hoa hồng mới cho sản phẩm."""
    plat_rate, ext_rate, ext_fixed, min_rate = validate_and_compute_commission(
        platform=product.platform,
        comm_type=payload.commission_type,
        extra_rate=payload.extra_rate,
        extra_fixed_amount=payload.extra_fixed_amount
    )

    comm = None
    if product.commissions:
        comm = product.commissions[0]
        comm.commission_type = payload.commission_type
        comm.platform_rate = plat_rate
        comm.extra_rate = ext_rate
        comm.extra_fixed_amount = ext_fixed
        comm.min_rate = min_rate
    else:
        comm = Commission(
            product_id=product.id,
            platform=product.platform,
            commission_type=payload.commission_type,
            platform_rate=plat_rate,
            extra_rate=ext_rate,
            extra_fixed_amount=ext_fixed,
            min_rate=min_rate,
            effective_from=utc_now()
        )
        db.add(comm)

    product.updated_at = utc_now()
    db.commit()
    db.refresh(comm)
    return comm

def update_product_status(db: Session, product: Product, new_status: str) -> Product:
    """Tạm ẩn (paused) hoặc kích hoạt lại (active) sản phẩm."""
    if new_status not in [ProductStatus.ACTIVE, ProductStatus.PAUSED]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Trạng thái không hợp lệ: '{new_status}'")
    product.status = new_status
    product.updated_at = utc_now()
    db.commit()
    db.refresh(product)
    return product

def delete_product(db: Session, product: Product) -> bool:
    """Xóa mềm sản phẩm (đánh dấu DELETED)."""
    product.status = ProductStatus.DELETED
    product.updated_at = utc_now()
    db.commit()
    return True

def find_matching_affiliate_products(
    db: Session,
    query_text: str,
    category: Optional[str] = None,
    limit: int = 5
) -> List[Any]:
    """
    Thuật toán tìm kiếm và xếp hạng ưu tiên các sản phẩm của Shop đối tác:
    - Tìm kiếm trong affiliate_products (Auto-Sync) với sync_status == ACTIVE.
    - Tìm kiếm trong products cũ với ShopStatus.VERIFIED và ProductStatus.ACTIVE.
    - Ưu tiên hiển thị sản phẩm có hoa hồng cao hơn và điểm priority_score cao hơn (Top Verified Picks).
    """
    if not query_text:
        return []

    words = [w.lower().strip() for w in query_text.split() if len(w.strip()) > 1]
    if not words:
        words = [query_text.lower().strip()]

    scored_products: List[Tuple[float, Any]] = []

    # 1. Quét từ affiliate_products (Auto-Sync sản phẩm mới)
    aff_candidates = db.query(AffiliateProduct).filter(
        AffiliateProduct.sync_status == SyncStatus.ACTIVE
    ).all()
    for ap in aff_candidates:
        title_lower = ap.title.lower()
        match_count = sum(1 for w in words if w in title_lower)
        relevance = match_count / len(words) if words else 0.5
        comm_boost = float(ap.total_commission_rate or 0.0) / 100.0
        p_score = float(ap.priority_score or 0.0)
        final_score = (relevance * 0.6) + (comm_boost * 0.3) + (p_score * 0.1) + 0.1  # Partner Bonus Multiplier
        if relevance >= 0.25:
            scored_products.append((final_score, ap))

    # 2. Quét từ products cũ (Legacy)
    base_query = db.query(Product).join(Shop).filter(
        Shop.status == ShopStatus.VERIFIED,
        Product.status == ProductStatus.ACTIVE
    )
    filters = [Product.name.ilike(f"%{w}%") for w in words]
    if category:
        filters.append(Product.category.ilike(f"%{category.split('>')[-1].strip()}%"))
    legacy_candidates = base_query.filter(or_(*filters)).all()

    for p in legacy_candidates:
        name_lower = p.name.lower()
        match_count = sum(1 for w in words if w in name_lower)
        relevance = match_count / len(words) if words else 0.5
        comm_boost = 0.0
        if p.commissions:
            c = p.commissions[0]
            comm_boost = float(c.extra_rate or 0.0) / 100.0
        final_score = (relevance * 0.8) + (comm_boost * 0.2)
        if relevance >= 0.25:
            scored_products.append((final_score, p))

    scored_products.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored_products[:limit]]

