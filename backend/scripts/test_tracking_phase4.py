import os
import sys
import unittest
import json
from unittest.mock import MagicMock
from fastapi import HTTPException

# Đảm bảo import được các module từ thư mục backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.connection import init_db, SessionLocal
from database.models import (
    Shop,
    Product,
    Commission,
    Click,
    Conversion,
    ShopStatus,
    ProductStatus,
    ConversionStatus,
    utc_now,
)
from models.tracking_schemas import (
    ClickRecordRequest,
    ConversionRecordRequest,
)
from services.tracking_service import (
    record_click,
    record_conversion,
    get_click_detail,
)
from services.report_service import (
    get_shop_overview,
    get_shop_daily_metrics,
    get_shop_product_performance,
)
from routes.tracking_routes import (
    track_click,
    track_conversion,
    get_click,
)
from routes.report_routes import (
    get_overview_report,
    get_daily_report,
    get_products_report,
)

class TestTrackingPhase4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 65)
        print("🚀 BẮT ĐẦU KIỂM THỬ PHASE 4: TRACKING & ANALYTICS REPORT (TAP AI)")
        print("=" * 65)
        init_db()
        cls.db = SessionLocal()

        # Dọn dẹp dữ liệu test cũ
        cls.db.query(Conversion).delete()
        cls.db.query(Click).delete()
        cls.db.query(Commission).delete()
        cls.db.query(Product).delete()
        cls.db.query(Shop).filter(Shop.email.like("%@phase4-test.com")).delete()
        cls.db.commit()

        # 1. Tạo Shop test
        cls.shop = Shop(
            email="routine_vietnam@phase4-test.com",
            phone="0988776655",
            password_hash="fakehash",
            shop_name="Routine Vietnam",
            platform="shopee",
            shop_url="https://shopee.vn/routine_official",
            status=ShopStatus.VERIFIED,
            email_verified=True,
            phone_verified=True,
        )
        cls.db.add(cls.shop)
        cls.db.commit()
        cls.db.refresh(cls.shop)

        # 2. Tạo 2 Sản phẩm test của Shop
        cls.prod1 = Product(
            shop_id=cls.shop.id,
            name="Áo sơ mi nam Oxford tay dài Routine form Regular",
            category="Thời trang nam > Áo sơ mi",
            product_url="https://shopee.vn/routine/ao-so-mi-oxford",
            platform="shopee",
            image_urls=json.dumps(["https://routine.vn/images/oxford.jpg"]),
            price=450000.0,
            status=ProductStatus.ACTIVE,
        )
        cls.prod2 = Product(
            shop_id=cls.shop.id,
            name="Quần Jeans nam Slimfit co giãn Routine",
            category="Thời trang nam > Quần Jeans",
            product_url="https://shopee.vn/routine/quan-jeans-slimfit",
            platform="shopee",
            image_urls=json.dumps(["https://routine.vn/images/jeans.jpg"]),
            price=620000.0,
            status=ProductStatus.ACTIVE,
        )
        cls.db.add_all([cls.prod1, cls.prod2])
        cls.db.flush()

        # 3. Gắn cấu hình hoa hồng:
        # Prod 1: Shopee 3.5% + Extra 6.5% = Tổng 10.0%
        cls.comm1 = Commission(
            product_id=cls.prod1.id,
            platform="shopee",
            commission_type="percentage",
            platform_rate=3.5,
            extra_rate=6.5,
            min_rate=0.0
        )
        # Prod 2: Shopee 3.5% + Extra 5.0% = Tổng 8.5%
        cls.comm2 = Commission(
            product_id=cls.prod2.id,
            platform="shopee",
            commission_type="percentage",
            platform_rate=3.5,
            extra_rate=5.0,
            min_rate=0.0
        )
        cls.db.add_all([cls.comm1, cls.comm2])
        cls.db.commit()
        cls.db.refresh(cls.prod1)
        cls.db.refresh(cls.prod2)

    @classmethod
    def tearDownClass(cls):
        cls.db.query(Conversion).delete()
        cls.db.query(Click).delete()
        cls.db.query(Commission).delete()
        cls.db.query(Product).delete()
        cls.db.query(Shop).filter(Shop.email.like("%@phase4-test.com")).delete()
        cls.db.commit()
        cls.db.close()
        print("\n" + "=" * 65)
        print("🎉 TẤT CẢ UNIT TESTS PHASE 4 HOÀN TẤT THÀNH CÔNG 100%!")
        print("=" * 65)

    def test_01_record_click_and_redirect_url(self):
        """Ghi nhận lượt Click 'Mua ngay' từ Extension và sinh affiliate redirect URL"""
        print("\n🔹 Test 1: Ghi nhận Click & Tạo Affiliate Redirect Link")
        mock_req = MagicMock()
        mock_req.client.host = "113.161.45.88"
        mock_req.headers.get.return_value = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"

        click_req = ClickRecordRequest(
            product_id=self.prod1.id,
            user_session_id="user_session_abc123",
            source_type="video",
            referral_url="https://www.tiktok.com/@fashion_review/video/12345"
        )
        click_resp = track_click(payload=click_req, request=mock_req, db=self.db)

        self.assertIsNotNone(click_resp.click_id)
        self.assertEqual(click_resp.shop_id, self.shop.id)
        self.assertIn("tap_ref=" + click_resp.click_id, click_resp.redirect_url)
        self.assertIn("sub_id=" + click_resp.click_id, click_resp.redirect_url)

        # Lưu lại click_id để dùng cho test conversion
        self.__class__.saved_click_id = click_resp.click_id
        print(f"   ✅ Click ghi nhận thành công: Click ID = {click_resp.click_id}")
        print(f"   🔗 Redirect URL: {click_resp.redirect_url}")

    def test_02_conversion_webhook_commission_calc(self):
        """Webhook ghi nhận đơn hàng thành công và tự động tính hoa hồng chính xác"""
        print("\n🔹 Test 2: Webhook Ghi nhận Conversion & Tính toán Hoa hồng")

        # 2.1 Thử click_id không tồn tại -> 404
        with self.assertRaises(HTTPException) as ctx:
            track_conversion(
                ConversionRecordRequest(click_id="invalid_click_id", order_id="ORDER_999", order_value=100000.0),
                db=self.db
            )
        self.assertEqual(ctx.exception.status_code, 404)
        print("   ✅ Từ chối click_id không tồn tại thành công (mã 404)")

        # 2.2 Ghi nhận đơn hàng thật: Giá trị đơn hàng 500.000₫, hoa hồng 10% -> 50.000₫
        conv_req = ConversionRecordRequest(
            click_id=self.saved_click_id,
            order_id="SHOPEE_ORDER_888999",
            order_value=500000.0,
            status="confirmed"
        )
        conv_resp = track_conversion(payload=conv_req, db=self.db)

        self.assertEqual(conv_resp.order_id, "SHOPEE_ORDER_888999")
        self.assertEqual(conv_resp.order_value, 500000.0)
        # Hoa hồng Prod 1 = 10.0% * 500.000 = 50.000₫
        self.assertEqual(conv_resp.commission_earned, 50000.0)
        self.assertEqual(conv_resp.status, "confirmed")
        print(f"   ✅ Đơn hàng ghi nhận: Mã đơn = {conv_resp.order_id}, Giá trị = 500.000₫")
        print(f"   💰 Hoa hồng tự động tính: 50.000₫ (10.0% = 3.5% Shopee + 6.5% Xtra)")

    def test_03_reject_duplicate_conversion(self):
        """Chặn ghi nhận đơn hàng trùng lặp cho cùng 1 click_id"""
        print("\n🔹 Test 3: Chặn đơn hàng trùng lặp trên cùng 1 Click")
        dup_req = ConversionRecordRequest(
            click_id=self.saved_click_id,
            order_id="SHOPEE_ORDER_DUPLICATE",
            order_value=300000.0
        )
        with self.assertRaises(HTTPException) as ctx:
            track_conversion(payload=dup_req, db=self.db)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("đã được ghi nhận", ctx.exception.detail)
        print("   ✅ Đã chặn đơn hàng trùng lặp thành công (mã 409 Conflict)")

    def test_04_query_click_detail(self):
        """Shop kiểm tra trạng thái lượt click và đơn hàng liên kết"""
        print("\n🔹 Test 4: Shop kiểm tra chi tiết Click")
        detail = get_click(click_id=self.saved_click_id, current_shop=self.shop, db=self.db)
        self.assertEqual(detail["click_id"], self.saved_click_id)
        self.assertTrue(detail["has_conversion"])
        self.assertEqual(detail["order_id"], "SHOPEE_ORDER_888999")
        print(f"   ✅ Tra cứu Click thành công: has_conversion = True, order_id = {detail['order_id']}")

    def test_05_shop_overview_report(self):
        """Báo cáo tổng quan số liệu kinh doanh trên Dashboard của Shop"""
        print("\n🔹 Test 5: Báo cáo Tổng quan Dashboard (Overview Report)")
        overview = get_overview_report(current_shop=self.shop, db=self.db)

        self.assertEqual(overview.shop_name, "Routine Vietnam")
        self.assertEqual(overview.total_products, 2)
        self.assertGreaterEqual(overview.total_clicks, 1)
        self.assertGreaterEqual(overview.total_conversions, 1)
        self.assertEqual(overview.total_order_value, 500000.0)
        self.assertEqual(overview.total_commission_earned, 50000.0)
        self.assertEqual(overview.confirmed_commission, 50000.0)
        self.assertGreater(overview.conversion_rate_percent, 0.0)

        print(f"   ✅ Tổng sản phẩm : {overview.total_products}")
        print(f"   ✅ Tổng Clicks   : {overview.total_clicks}")
        print(f"   ✅ Tổng Đơn hàng : {overview.total_conversions} đơn (CVR: {overview.conversion_rate_percent}%)")
        print(f"   ✅ Doanh số (GMV): {overview.total_order_value:,.0f} ₫")
        print(f"   ✅ Hoa hồng nhận : {overview.total_commission_earned:,.0f} ₫")

    def test_06_shop_daily_metrics_chart(self):
        """Báo cáo chuỗi thời gian 7 ngày phục vụ vẽ biểu đồ trên Dashboard"""
        print("\n🔹 Test 6: Báo cáo Theo ngày (Daily Metrics Chart Series)")
        daily_resp = get_daily_report(days=7, current_shop=self.shop, db=self.db)

        self.assertEqual(len(daily_resp.daily_metrics), 7)
        # Ngày hôm nay phải ghi nhận ít nhất 1 click và 1 conversion
        today_metric = daily_resp.daily_metrics[-1]
        self.assertGreaterEqual(today_metric.clicks, 1)
        self.assertGreaterEqual(today_metric.conversions, 1)
        self.assertEqual(today_metric.commission_earned, 50000.0)
        print(f"   ✅ Chuỗi dữ liệu biểu đồ: {len(daily_resp.daily_metrics)} ngày từ {daily_resp.start_date} đến {daily_resp.end_date}")
        print(f"   ✅ Số liệu hôm nay ({today_metric.date}): {today_metric.clicks} clicks, {today_metric.conversions} đơn, {today_metric.commission_earned:,.0f}₫ hoa hồng")

    def test_07_product_performance_report(self):
        """Báo cáo hiệu quả kinh doanh chi tiết theo từng sản phẩm"""
        print("\n🔹 Test 7: Báo cáo Hiệu quả theo từng Sản phẩm (Product Breakdown)")
        prod_report = get_products_report(current_shop=self.shop, db=self.db)

        self.assertEqual(prod_report.total_products, 2)
        top_prod = prod_report.products[0]
        self.assertEqual(top_prod.product_id, self.prod1.id)
        self.assertEqual(top_prod.conversions, 1)
        self.assertEqual(top_prod.order_value, 500000.0)
        self.assertEqual(top_prod.commission_earned, 50000.0)
        print(f"   ✅ Top 1 sản phẩm bán chạy: '{top_prod.product_name}'")
        print(f"   ✅ Doanh số: {top_prod.order_value:,.0f}₫ | Hoa hồng: {top_prod.commission_earned:,.0f}₫")

if __name__ == "__main__":
    unittest.main()

