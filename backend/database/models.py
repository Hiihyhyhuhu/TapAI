import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Numeric,
    Text,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship, synonym, foreign
from .connection import Base

def generate_uuid() -> str:
    return uuid.uuid4().hex

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

# ==============================================================================
# HẰNG SỐ TRẠNG THÁI VÀ PHÂN QUYỀN (THEO DOCS.MD)
# ==============================================================================
class MerchantRole:
    MERCHANT = "MERCHANT"
    ADMIN = "ADMIN"

class MerchantStatus:
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"

class PlatformType:
    SHOPEE = "SHOPEE"
    TIKTOK_SHOP = "TIKTOK_SHOP"

class SyncStatus:
    ACTIVE = "ACTIVE"                 # Có hoa hồng > 0, sẵn sàng phân phối
    NO_COMMISSION = "NO_COMMISSION"   # Hoa hồng = 0 (Shop cần bật trên sàn)
    OUT_OF_STOCK = "OUT_OF_STOCK"     # Hết hàng

class OrderStatus:
    CLICKED = "CLICKED"               # Vừa click link
    PENDING = "PENDING"               # Đơn hàng mới phát sinh trên sàn
    COMPLETED = "COMPLETED"           # Đã đối soát và duyệt chi trả hoa hồng
    CANCELLED = "CANCELLED"           # Hủy đơn / Bom hàng / Trả hàng hoàn tiền

# ==============================================================================
# 1. BẢNG TÀI KHOẢN CHỦ SHOP (MERCHANTS)
# ==============================================================================
class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    business_name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    role = Column(String(20), default=MerchantRole.MERCHANT, nullable=False)
    status = Column(String(20), default=MerchantStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    shops = relationship("MerchantShop", back_populates="merchant", cascade="all, delete-orphan")


# ==============================================================================
# 2. BẢNG GIAN HÀNG LIÊN KẾT TRÊN SÀN (MERCHANT_SHOPS)
# ==============================================================================
class MerchantShop(Base):
    __tablename__ = "merchant_shops"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(36), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(20), nullable=False)  # 'SHOPEE' | 'TIKTOK_SHOP'
    platform_shop_id = Column(String(100), nullable=False)
    shop_name = Column(String(255), nullable=True)
    shop_url = Column(Text, nullable=False)
    verification_code = Column(String(50), nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False)
    oauth_access_token = Column(Text, nullable=True)
    oauth_refresh_token = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("platform", "platform_shop_id", name="uq_merchant_shop_platform_id"),
    )

    # Relationships
    merchant = relationship("Merchant", back_populates="shops")
    products = relationship("AffiliateProduct", back_populates="shop", cascade="all, delete-orphan")
    clicks = relationship("ClickTracking", back_populates="shop")
    conversions = relationship("Conversion", back_populates="shop")


# ==============================================================================
# 3. BẢNG SẢN PHẨM & HOA HỒNG TỰ ĐỘNG ĐỒNG BỘ (AFFILIATE_PRODUCTS)
# ==============================================================================
class AffiliateProduct(Base):
    __tablename__ = "affiliate_products"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shop_id = Column(String(36), ForeignKey("merchant_shops.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(20), nullable=False)  # 'SHOPEE' | 'TIKTOK_SHOP'
    platform_item_id = Column(String(100), nullable=False)
    original_url = Column(Text, nullable=False)
    title = Column(String(255), nullable=False)
    image_url = Column(Text, nullable=True)
    current_price = Column(Numeric(12, 2), nullable=False)

    # Hoa hồng tự động đọc từ Sàn (%)
    platform_base_rate = Column(Numeric(5, 2), default=0.00, nullable=False)   # Shopee Standard (~3.5%)
    seller_extra_rate = Column(Numeric(5, 2), default=0.00, nullable=False)    # Shopee Xtra / TikTok Plan
    total_commission_rate = Column(Numeric(5, 2), default=0.00, nullable=False) # Tổng % thực tế = base + extra

    # Trạng thái đồng bộ & Điểm xếp hạng
    sync_status = Column(String(30), default=SyncStatus.ACTIVE, nullable=False)
    priority_score = Column(Numeric(8, 4), default=0.0000, nullable=False)
    cpc_bid = Column(Numeric(10, 2), default=2000.00, nullable=False)
    daily_budget = Column(Numeric(12, 2), default=100000.00, nullable=False)
    today_spent = Column(Numeric(12, 2), default=0.00, nullable=False)
    last_synced_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("platform", "platform_item_id", name="uq_affiliate_product_platform_item"),
        Index("idx_products_active_score", "sync_status", "priority_score"),
    )

    # Relationships
    shop = relationship("MerchantShop", back_populates="products")
    clicks = relationship("ClickTracking", back_populates="product")
    conversions = relationship("Conversion", back_populates="product")

    # Compatibility Aliases với hệ thống cũ
    name = synonym("title")
    price = synonym("current_price")
    product_url = synonym("original_url")

    @property
    def category(self):
        return "Thời trang"

    @property
    def status(self):
        return "active" if self.sync_status == SyncStatus.ACTIVE else "paused"

    @property
    def image_urls_list(self):
        return [self.image_url] if self.image_url else []

    @property
    def commissions(self):
        class MockComm:
            def __init__(self, p_rate, e_rate, t_rate, platform):
                self.id = "comm_auto"
                self.platform = platform
                self.commission_type = "percentage"
                self.platform_rate = p_rate
                self.extra_rate = e_rate
                self.extra_fixed_amount = 0.0
                self.total_rate = t_rate
                self.min_rate = 0.0
        return [MockComm(float(self.platform_base_rate or 0), float(self.seller_extra_rate or 0), float(self.total_commission_rate or 0), self.platform)]


# ==============================================================================
# 4. BẢNG GHI NHẬN LƯỢT CLICK & SUB_ID (CLICK_TRACKINGS)
# ==============================================================================
class ClickTracking(Base):
    __tablename__ = "click_trackings"

    click_id = Column(String(64), primary_key=True)  # sub_id1 của sàn
    product_id = Column(String(36), ForeignKey("affiliate_products.id", ondelete="CASCADE"), nullable=False, index=True)
    shop_id = Column(String(36), ForeignKey("merchant_shops.id", ondelete="CASCADE"), nullable=False, index=True)
    ext_user_id = Column(String(100), nullable=True)      # sub_id3: ID ẩn danh Extension User
    source_context = Column(String(50), nullable=True)   # sub_id4: FB_REELS, FB_FEED, TIKTOK_VIDEO
    generated_short_url = Column(Text, nullable=False)
    committed_cpc_at_click = Column(Numeric(10, 2), default=2000.00, nullable=False)
    cpc_deducted = Column(Numeric(10, 2), default=0.00, nullable=False)
    is_valid_unique = Column(Boolean, default=True, nullable=False)
    fraud_reason = Column(String(64), nullable=True)
    client_ip = Column(String(64), nullable=True)
    clicked_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_clicks_shop_date", "shop_id", "clicked_at"),
    )

    # Relationships
    product = relationship("AffiliateProduct", back_populates="clicks")
    shop = relationship("MerchantShop", back_populates="clicks")
    conversions = relationship("Conversion", back_populates="click_log")


# ==============================================================================
# 5. BẢNG ĐỐI SOÁT ĐƠN HÀNG & HOA HỒNG (CONVERSIONS)
# ==============================================================================
class Conversion(Base):
    __tablename__ = "conversions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    platform = Column(String(20), nullable=False)  # 'SHOPEE' | 'TIKTOK_SHOP'
    platform_order_id = Column(String(100), nullable=False)
    platform_item_id = Column(String(100), nullable=False)
    click_id = Column(String(64), ForeignKey("click_trackings.click_id", ondelete="SET NULL"), nullable=True, index=True)
    shop_id = Column(String(36), ForeignKey("merchant_shops.id", ondelete="SET NULL"), nullable=True, index=True)
    product_id = Column(String(36), ForeignKey("affiliate_products.id", ondelete="SET NULL"), nullable=True, index=True)

    # Số liệu tài chính (VNĐ)
    order_gmv = Column(Numeric(14, 2), nullable=False)
    base_commission_amount = Column(Numeric(12, 2), default=0.00, nullable=False)
    extra_commission_amount = Column(Numeric(12, 2), default=0.00, nullable=False)
    total_commission_amount = Column(Numeric(12, 2), nullable=False)

    # Trạng thái đối soát
    order_status = Column(String(30), default=OrderStatus.PENDING, nullable=False)  # PENDING | COMPLETED | CANCELLED
    ordered_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    raw_payload = Column(Text, nullable=True)  # JSON text lưu nguyên bản payload từ sàn
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("platform", "platform_order_id", "platform_item_id", name="uq_conversion_platform_order_item"),
        Index("idx_conversions_shop_status", "shop_id", "order_status", "ordered_at"),
    )

    # Relationships
    shop = relationship("MerchantShop", back_populates="conversions")
    product = relationship("AffiliateProduct", back_populates="conversions")
    click_log = relationship("ClickTracking", back_populates="conversions")

    # Synonyms / Aliases cho backward compatibility với code cũ
    order_id = synonym("platform_order_id")
    order_value = synonym("order_gmv")
    commission_earned = synonym("total_commission_amount")
    status = synonym("order_status")
    converted_at = synonym("ordered_at")
    confirmed_at = synonym("completed_at")

    def __init__(self, **kwargs):
        # Tự động map tham số cũ sang schema DOCS.md mới
        if "platform_order_id" not in kwargs and "order_id" in kwargs:
            kwargs["platform_order_id"] = kwargs.pop("order_id")
        if "platform" not in kwargs:
            kwargs["platform"] = "SHOPEE"
        if "platform_item_id" not in kwargs:
            kwargs["platform_item_id"] = kwargs.get("product_id") or "legacy_item"
        if "order_gmv" not in kwargs and "order_value" in kwargs:
            kwargs["order_gmv"] = kwargs.pop("order_value")
        if "total_commission_amount" not in kwargs and "commission_earned" in kwargs:
            kwargs["total_commission_amount"] = kwargs.pop("commission_earned")
        if "order_status" not in kwargs and "status" in kwargs:
            kwargs["order_status"] = kwargs.pop("status")
        if "ordered_at" not in kwargs:
            kwargs["ordered_at"] = kwargs.pop("converted_at", utc_now())
        if "completed_at" not in kwargs and "confirmed_at" in kwargs:
            kwargs["completed_at"] = kwargs.pop("confirmed_at")
        super().__init__(**kwargs)


# ==============================================================================
# CÁC MODEL BẢN CŨ ĐỂ HỖ TRỢ CHUYỂN TIẾP VÀ MIGRATION (LEGACY COMPATIBILITY)
# ==============================================================================
class ShopStatus:
    UNVERIFIED = "unverified"
    PENDING_REVIEW = "pending_review"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    REJECTED = "rejected"

class VerificationStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESUBMIT_REQUIRED = "resubmit_required"

class ProductStatus:
    ACTIVE = "active"
    PAUSED = "paused"
    REJECTED = "rejected"
    DELETED = "deleted"

class CommissionType:
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"

class ConversionStatus:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

class Shop(Base):
    __tablename__ = "shops"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(32), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    shop_name = Column(String(255), nullable=False)
    platform = Column(String(64), nullable=False, default="shopee")
    shop_url = Column(Text, nullable=False)
    shop_external_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default=ShopStatus.UNVERIFIED)

    # Stage 1: Merchant Onboarding & E-Contracting
    ownership_token = Column(String(32), default=lambda: f"VERIFY-{uuid.uuid4().hex[:4].upper()}", nullable=True)
    contract_status = Column(String(32), default="PENDING", nullable=False) # PENDING | ACTIVE | SUSPENDED
    contract_signed_at = Column(DateTime(timezone=True), nullable=True)
    contract_hash = Column(String(64), nullable=True)

    # Stage 2: Prepaid Escrow Wallet
    wallet_balance = Column(Numeric(14, 2), default=1000000.00, nullable=False)
    total_deposited = Column(Numeric(14, 2), default=1000000.00, nullable=False)
    total_cpc_spent = Column(Numeric(14, 2), default=0.00, nullable=False)

    email_verified = Column(Boolean, default=False, nullable=False)
    phone_verified = Column(Boolean, default=False, nullable=False)

    otp_email_code = Column(String(16), nullable=True)
    otp_email_expires_at = Column(DateTime(timezone=True), nullable=True)
    otp_phone_code = Column(String(16), nullable=True)
    otp_phone_expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    verifications = relationship("Verification", back_populates="shop", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="shop", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="shop")
    sessions = relationship("Session", back_populates="shop", cascade="all, delete-orphan")

class Verification(Base):
    __tablename__ = "verifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shop_id = Column(String(36), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    business_license_url = Column(Text, nullable=False)
    shop_screenshot_url = Column(Text, nullable=False)
    shop_url_submitted = Column(Text, nullable=False)
    status = Column(String(32), default=VerificationStatus.PENDING, nullable=False)
    admin_note = Column(Text, nullable=True)
    reviewed_by = Column(String(128), nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    shop = relationship("Shop", back_populates="verifications")

class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shop_id = Column(String(36), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(128), nullable=False)
    product_url = Column(Text, nullable=False)
    platform = Column(String(64), nullable=False, default="shopee")
    image_urls = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(16), default="VND", nullable=False)
    status = Column(String(32), default=ProductStatus.ACTIVE, nullable=False)
    cpc_bid = Column(Numeric(10, 2), default=2000.00, nullable=False)
    daily_budget = Column(Numeric(12, 2), default=100000.00, nullable=False)
    today_spent = Column(Numeric(12, 2), default=0.00, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    shop = relationship("Shop", back_populates="products")
    commissions = relationship("Commission", back_populates="product", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="product")

class Commission(Base):
    __tablename__ = "commissions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    product_id = Column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(64), nullable=False, default="shopee")
    commission_type = Column(String(32), default=CommissionType.PERCENTAGE, nullable=False)
    platform_rate = Column(Numeric(5, 2), default=0.0, nullable=False)
    extra_rate = Column(Numeric(5, 2), default=0.0, nullable=False)
    extra_fixed_amount = Column(Numeric(12, 2), default=0.0, nullable=False)
    min_rate = Column(Numeric(5, 2), default=2.0, nullable=False)
    effective_from = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    effective_to = Column(DateTime(timezone=True), nullable=True)

    product = relationship("Product", back_populates="commissions")

class Click(Base):
    __tablename__ = "clicks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    product_id = Column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    shop_id = Column(String(36), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    user_session_id = Column(String(128), nullable=True)
    source_type = Column(String(32), default="video", nullable=False)
    referral_url = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)
    ip_hash = Column(String(64), nullable=True)
    client_ip = Column(String(64), nullable=True)
    redirect_url = Column(Text, nullable=False)
    committed_cpc_at_click = Column(Numeric(10, 2), default=2000.00, nullable=False)
    cpc_deducted = Column(Numeric(10, 2), default=0.00, nullable=False)
    is_valid_unique = Column(Boolean, default=True, nullable=False)
    fraud_reason = Column(String(64), nullable=True)
    clicked_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    shop = relationship("Shop", back_populates="clicks")
    product = relationship("Product", back_populates="clicks")
    conversions = relationship("Conversion", primaryjoin="Click.id == foreign(Conversion.click_id)", viewonly=True)

    @property
    def conversion(self):
        return self.conversions[0] if self.conversions else None

class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shop_id = Column(String(36), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, index=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    shop = relationship("Shop", back_populates="sessions")


