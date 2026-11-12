import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.connection import init_db, SessionLocal
from database.models import (
    Merchant,
    MerchantShop,
    AffiliateProduct,
    ClickTracking,
    Conversion,
    SyncStatus,
    OrderStatus,
    PlatformType,
    MerchantRole,
    MerchantStatus,
)
from services.adapters import shopee_adapter, tiktok_adapter
from services.commission_sync_service import (
    import_product_by_url,
    sync_product_now,
    sync_all_active_products,
)
from services.link_wrapper_service import wrap_affiliate_link
from services.reconciliation_service import (
    process_webhook_conversion,
    get_merchant_orders,
    get_reconciliation_summary,
)

class TestAutoSyncPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 70)
        print("🚀 BẮT ĐẦU KIỂM THỬ: AUTO-SYNC COMMISSION & RECONCILIATION PIPELINE")
        print("=" * 70)
        init_db()
        cls.db = SessionLocal()

        # Dọn dẹp dữ liệu test cũ
        cls.db.query(Conversion).delete()
        cls.db.query(ClickTracking).delete()
        cls.db.query(AffiliateProduct).delete()
        cls.db.query(MerchantShop).delete()
        cls.db.query(Merchant).filter(Merchant.email.like("%@autosync-test.com")).delete()
        cls.db.commit()

        # 1. Tạo Merchant và MerchantShop phục vụ test
        cls.merchant = Merchant(
            email="coolmate_auto@autosync-test.com",
            password_hash="fakehash",
            business_name="Coolmate Vietnam",
            phone="0988776655",
            role=MerchantRole.MERCHANT,
            status=MerchantStatus.ACTIVE
        )
        cls.db.add(cls.merchant)
        cls.db.commit()
        cls.db.refresh(cls.merchant)

        cls.shop = MerchantShop(
            merchant_id=cls.merchant.id,
            platform=PlatformType.SHOPEE,
            platform_shop_id="987654321",
            shop_name="Coolmate Official Shopee",
            shop_url="https://shopee.vn/coolmate.vn",
            is_verified=True
        )
        cls.db.add(cls.shop)
        cls.db.commit()
        cls.db.refresh(cls.shop)

    @classmethod
    def tearDownClass(cls):
        cls.db.query(Conversion).delete()
        cls.db.query(ClickTracking).delete()
        cls.db.query(AffiliateProduct).delete()
        cls.db.query(MerchantShop).delete()
        cls.db.query(Merchant).filter(Merchant.email.like("%@autosync-test.com")).delete()
        cls.db.commit()
        cls.db.close()
        print("\n" + "=" * 70)
        print("🎉 TẤT CẢ UNIT TESTS AUTO-SYNC & RECONCILIATION HOÀN TẤT THÀNH CÔNG 100%!")
        print("=" * 70)

    def test_01_adapter_url_extraction(self):
        """Kiểm tra Adapter bóc tách chính xác item_id từ mọi biến thể URL sàn"""
        print("\n🔹 Test 1: Bóc tách item_id & shop_id từ URL Shopee và TikTok Shop")
        
        # 1.1 Shopee URL dạng slug + i.shop_id.item_id
        url_shopee_1 = "https://shopee.vn/Ao-Thun-Nam-Cotton-Compact-i.987654.12345678"
        s_id, i_id = shopee_adapter.extract_item_info(url_shopee_1)
        self.assertEqual(s_id, "987654")
        self.assertEqual(i_id, "12345678")
        print("   ✅ Shopee URL (-i.shop.item): shop_id=987654, item_id=12345678")

        # 1.2 Shopee URL dạng /product/shop_id/item_id
        url_shopee_2 = "https://shopee.vn/product/112233/44556677"
        s_id2, i_id2 = shopee_adapter.extract_item_info(url_shopee_2)
        self.assertEqual(s_id2, "112233")
        self.assertEqual(i_id2, "44556677")
        print("   ✅ Shopee URL (/product/shop/item): shop_id=112233, item_id=44556677")

        # 1.3 TikTok Shop URL
        url_tiktok = "https://shop.tiktok.com/view/product/172948291048"
        _, tt_item_id = tiktok_adapter.extract_item_info(url_tiktok)
        self.assertEqual(tt_item_id, "172948291048")
        print("   ✅ TikTok Shop URL: item_id=172948291048")

    def test_02_1click_import_auto_commission(self):
        """Kiểm tra 1-Click Import: Dán link tự quét hoa hồng sàn, không cần nhập thủ công"""
        print("\n🔹 Test 2: 1-Click Import tự động cào hoa hồng sàn (Zero Manual Rate)")

        url = "https://shopee.vn/Ao-Polo-Nam-Pro-Dry-Coolmate-i.987654321.88889999"
        prod = import_product_by_url(db=self.db, shop_id=self.shop.id, product_url=url)

        self.assertIsNotNone(prod.id)
        self.assertEqual(prod.platform, "SHOPEE")
        self.assertEqual(prod.platform_item_id, "88889999")
        # Shopee: 3.5% Standard + 6.5% Xtra = 10.0%
        self.assertEqual(float(prod.platform_base_rate), 3.5)
        self.assertEqual(float(prod.seller_extra_rate), 6.5)
        self.assertEqual(float(prod.total_commission_rate), 10.0)
        self.assertEqual(prod.sync_status, SyncStatus.ACTIVE)
        print(f"   ✅ Nhập tự động thành công: Tên = '{prod.title}', Tổng hoa hồng = {prod.total_commission_rate}%")
        print(f"   🎯 Trạng thái kích hoạt: {prod.sync_status} (Sẵn sàng phân phối)")

    def test_03_zero_commission_handling(self):
        """Kiểm tra trường hợp sản phẩm chưa bật hoa hồng trên sàn (NO_COMMISSION)"""
        print("\n🔹 Test 3: Phát hiện sản phẩm chưa bật hoa hồng trên Sàn (NO_COMMISSION)")

        url_no_comm = "https://shopee.vn/Ao-Khoac-Gio-Nam-no-commission-i.987654321.77778888"
        prod = import_product_by_url(db=self.db, shop_id=self.shop.id, product_url=url_no_comm)

        self.assertEqual(float(prod.total_commission_rate), 0.0)
        self.assertEqual(prod.sync_status, SyncStatus.NO_COMMISSION)
        print("   ✅ Tự động gắn nhãn NO_COMMISSION cho sản phẩm có hoa hồng = 0%")
        print("   💡 Web Portal sẽ hiển thị nút CTA dẫn sang Kênh Người Bán để Shop bật hoa hồng.")

    def test_04_sync_product_now(self):
        """Kiểm tra nút 'Làm mới mức hoa hồng' (Sync Now) khi Shop vừa chỉnh tăng trên Kênh Người Bán"""
        print("\n🔹 Test 4: Nút 'Làm mới mức hoa hồng' (Sync Now)")

        prod = self.db.query(AffiliateProduct).filter(
            AffiliateProduct.platform_item_id == "88889999"
        ).first()

        synced = sync_product_now(db=self.db, product_id=prod.id)
        self.assertEqual(synced.id, prod.id)
        self.assertGreater(float(synced.total_commission_rate), 0.0)
        print(f"   ✅ Đã quét lại hoa hồng từ sàn thành công: Mức hiện tại = {synced.total_commission_rate}%")

    def test_05_dynamic_link_wrapper_and_cache(self):
        """Kiểm tra Dynamic Link Wrapper sinh đủ 4 tham số sub_id1..4 và Caching Shortlink"""
        print("\n🔹 Test 5: Dynamic Link Wrapper gắn đủ 4 tham số sub_id & Cache Shortlink")

        prod = self.db.query(AffiliateProduct).filter(
            AffiliateProduct.platform_item_id == "88889999"
        ).first()

        res1 = wrap_affiliate_link(
            db=self.db,
            product_id=prod.id,
            ext_user_id="user_anon_123",
            source_platform="FB_REELS"
        )

        click_id1 = res1["click_id"]
        short_url1 = res1["generated_short_url"]

        self.assertTrue(click_id1)
        self.assertIn(f"sub_id1={click_id1}", short_url1)
        self.assertIn(f"sub_id2={self.merchant.id}", short_url1)
        self.assertIn("sub_id3=user_anon_123", short_url1)
        self.assertIn("sub_id4=FB_REELS", short_url1)
        print(f"   ✅ Sinh link chuyển hướng gắn 4 sub_id thành công:")
        print(f"      🔗 {short_url1}")

        # Kiểm tra bản ghi đã lưu vào click_trackings
        click_rec = self.db.query(ClickTracking).filter(ClickTracking.click_id == click_id1).first()
        self.assertIsNotNone(click_rec)
        self.assertEqual(click_rec.ext_user_id, "user_anon_123")
        print("   ✅ Bản ghi đã lưu vào bảng click_trackings thành công.")

        # Lần gọi thứ 2 trong vòng 1 giờ -> phải Cache Hit
        res2 = wrap_affiliate_link(
            db=self.db,
            product_id=prod.id,
            ext_user_id="user_anon_123",
            source_platform="FB_REELS"
        )
        self.assertTrue(res2["cached"])
        print("   ⚡ Cache Hit: Đã tái sử dụng shortlink đã sinh trong time_bucket_1h!")

    def test_06_reconciliation_order_state_machine(self):
        """Kiểm tra Reconciliation Engine: Khớp đơn hàng qua sub_id1 và chuyển đổi trạng thái PENDING -> COMPLETED"""
        print("\n🔹 Test 6: Nhận Webhook đối soát và Vòng đời trạng thái đơn hàng (Order State Machine)")

        prod = self.db.query(AffiliateProduct).filter(
            AffiliateProduct.platform_item_id == "88889999"
        ).first()

        # Tạo 1 lượt click trước
        wrap_res = wrap_affiliate_link(
            db=self.db,
            product_id=prod.id,
            ext_user_id="user_buyer_999",
            source_platform="TIKTOK_VIDEO"
        )
        test_click_id = wrap_res["click_id"]

        # 6.1 Giả lập Webhook Sàn báo đơn hàng mới phát sinh (PENDING)
        webhook_pending_payload = {
            "platform": "SHOPEE",
            "order_id": "SHOPEE_ORDER_1001",
            "item_id": "88889999",
            "sub_id1": test_click_id,
            "order_value": 300000.0,
            "status": "PENDING"
        }
        conv_pending = process_webhook_conversion(
            db=self.db,
            platform="SHOPEE",
            payload=webhook_pending_payload
        )
        self.assertEqual(conv_pending.order_status, OrderStatus.PENDING)
        self.assertEqual(float(conv_pending.order_gmv), 300000.0)
        # Hoa hồng 10%: 30.000đ (Base 3.5% = 10.500đ, Extra 6.5% = 19.500đ)
        self.assertEqual(float(conv_pending.base_commission_amount), 10500.0)
        self.assertEqual(float(conv_pending.extra_commission_amount), 19500.0)
        self.assertEqual(float(conv_pending.total_commission_amount), 30000.0)
        print("   ✅ Bước 1: Ghi nhận đơn PENDING (300.000₫) -> Hoa hồng chờ duyệt: 30.000₫")

        # 6.2 Khách nhận hàng và qua hạn đổi trả -> Sàn bắn webhook COMPLETED (Chốt chi trả)
        webhook_completed_payload = {
            "platform": "SHOPEE",
            "order_id": "SHOPEE_ORDER_1001",
            "item_id": "88889999",
            "sub_id1": test_click_id,
            "order_value": 300000.0,
            "status": "COMPLETED"
        }
        conv_completed = process_webhook_conversion(
            db=self.db,
            platform="SHOPEE",
            payload=webhook_completed_payload
        )
        self.assertEqual(conv_completed.order_status, OrderStatus.COMPLETED)
        self.assertIsNotNone(conv_completed.completed_at)
        print("   ✅ Bước 2: Chuyển trạng thái sang COMPLETED -> Sẵn sàng giải ngân về ví đối tác!")

        # 6.3 Thử nghiệm đơn hàng bị hủy (CANCELLED) -> Hoa hồng = 0đ
        webhook_cancelled_payload = {
            "platform": "SHOPEE",
            "order_id": "SHOPEE_ORDER_1002",
            "item_id": "88889999",
            "sub_id1": test_click_id,
            "order_value": 200000.0,
            "status": "CANCELLED"
        }
        conv_cancelled = process_webhook_conversion(
            db=self.db,
            platform="SHOPEE",
            payload=webhook_cancelled_payload
        )
        self.assertEqual(conv_cancelled.order_status, OrderStatus.CANCELLED)
        self.assertEqual(float(conv_cancelled.total_commission_amount), 0.0)
        print("   ✅ Bước 3: Đơn hàng bị hủy (CANCELLED) -> Hoa hồng tự động chuyển về 0₫")

    def test_07_reconciliation_api_and_summary(self):
        """Kiểm tra API tra cứu đối soát chi tiết và thống kê tài chính"""
        print("\n🔹 Test 7: API Bảng kê đối soát chi tiết và Thống kê tài chính nhận tiền")

        total_orders, orders = get_merchant_orders(
            db=self.db,
            shop_id=self.shop.id,
            page=1,
            limit=20
        )
        self.assertGreaterEqual(total_orders, 2)
        print(f"   ✅ Lấy danh sách đối soát: Tìm thấy {total_orders} đơn hàng")

        summary = get_reconciliation_summary(db=self.db, shop_id=self.shop.id)
        self.assertEqual(summary["total_orders"], total_orders)
        self.assertEqual(summary["completed_commission"], 30000.0)
        self.assertEqual(summary["cancelled_orders"], 1)
        print(f"   💰 Tổng hoa hồng đã duyệt (Thực nhận): {summary['completed_commission']:,.0f} ₫")
        print(f"   📊 Tổng đơn bị hủy: {summary['cancelled_orders']} đơn")

if __name__ == "__main__":
    unittest.main()

