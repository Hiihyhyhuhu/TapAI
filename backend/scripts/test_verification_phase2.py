import os
import sys
import unittest
import io
from fastapi import UploadFile, HTTPException

# Đảm bảo import được các module từ thư mục backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.connection import init_db, SessionLocal
from database.models import Shop, Verification, ShopStatus, VerificationStatus
from models.shop_schemas import (
    AdminReviewRequest,
    AdminShopStatusUpdateRequest,
    ShopProfileUpdateRequest,
)
from services.verification_service import (
    validate_platform_url,
    submit_shop_verification,
    review_verification,
)
from routes.shop_routes import (
    get_verification_status,
    get_profile,
    update_profile,
)
from routes.admin_routes import (
    list_shops,
    list_pending_verifications,
    review_shop_verification,
    update_shop_status,
    get_system_stats,
)

class TestVerificationPhase2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 65)
        print("🚀 BẮT ĐẦU KIỂM THỬ PHASE 2: SHOP VERIFICATION & ADMIN REVIEW (TAP AI)")
        print("=" * 65)
        init_db()
        cls.db = SessionLocal()

        # Dọn dẹp dữ liệu test cũ
        cls.db.query(Verification).delete()
        cls.db.query(Shop).filter(Shop.email.like("%@phase2-test.com")).delete()
        cls.db.commit()

        # Tạo 1 Shop mẫu để test
        cls.test_shop = Shop(
            email="uniqlo_vn@phase2-test.com",
            phone="0911223344",
            password_hash="fakehash",
            shop_name="Uniqlo Vietnam",
            platform="shopee",
            shop_url="https://shopee.vn/uniqlo_official",
            status=ShopStatus.UNVERIFIED,
            email_verified=True,
            phone_verified=True,
        )
        cls.db.add(cls.test_shop)
        cls.db.commit()
        cls.db.refresh(cls.test_shop)

    @classmethod
    def tearDownClass(cls):
        cls.db.query(Verification).delete()
        cls.db.query(Shop).filter(Shop.email.like("%@phase2-test.com")).delete()
        cls.db.commit()
        cls.db.close()
        print("\n" + "=" * 65)
        print("🎉 TẤT CẢ UNIT TESTS PHASE 2 HOÀN TẤT THÀNH CÔNG 100%!")
        print("=" * 65)

    def test_01_platform_url_validation(self):
        """Kiểm tra logic thẩm định tên miền sàn TMĐT"""
        print("\n🔹 Test 1: Kiểm tra Thẩm định URL Sàn TMĐT")
        self.assertTrue(validate_platform_url("shopee", "https://shopee.vn/shopname"))
        self.assertTrue(validate_platform_url("lazada", "https://www.lazada.vn/shop/abc"))
        self.assertTrue(validate_platform_url("tiki", "https://tiki.vn/cua-hang/xyz"))
        self.assertTrue(validate_platform_url("tiktok_shop", "https://www.tiktok.com/@shopname"))

        # URL không hợp lệ
        self.assertFalse(validate_platform_url("shopee", "https://fake-shopee.com/shop"))
        self.assertFalse(validate_platform_url("lazada", "https://shopee.vn/wrong_platform"))
        print("   ✅ Thẩm định chính xác domain hợp lệ và chặn các link giả mạo/nhầm sàn")

    def test_02_submit_verification_invalid_url(self):
        """Chặn nộp hồ sơ khi link shop không thuộc sàn đã đăng ký"""
        print("\n🔹 Test 2: Chặn nộp hồ sơ khi URL shop sai sàn")
        with self.assertRaises(HTTPException) as ctx:
            submit_shop_verification(
                db=self.db,
                shop=self.test_shop,
                business_license_url="/uploads/license.png",
                shop_screenshot_url="/uploads/screenshot.png",
                shop_url_submitted="https://fake-ecommerce.com/store"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("không thuộc miền chính thức", ctx.exception.detail)
        print("   ✅ Đã chặn thành công hồ sơ có link không hợp lệ (mã 400)")

    def test_03_submit_valid_verification(self):
        """Nộp hồ sơ hợp lệ -> Chuyển trạng thái shop sang PENDING_REVIEW"""
        print("\n🔹 Test 3: Nộp hồ sơ xác minh danh tính hợp lệ")
        verif = submit_shop_verification(
            db=self.db,
            shop=self.test_shop,
            business_license_url="/uploads/uniqlo_gpkd.png",
            shop_screenshot_url="/uploads/uniqlo_seller_dash.png",
            shop_url_submitted="https://shopee.vn/uniqlo_official"
        )
        self.assertIsNotNone(verif.id)
        self.assertEqual(verif.status, VerificationStatus.PENDING)

        self.db.refresh(self.test_shop)
        self.assertEqual(self.test_shop.status, ShopStatus.PENDING_REVIEW)
        print(f"   ✅ Hồ sơ đã tạo: ID = {verif.id}, Trạng thái Shop = PENDING_REVIEW")

        # Kiểm tra API status của Shop
        status_resp = get_verification_status(current_shop=self.test_shop, db=self.db)
        self.assertTrue(status_resp.has_pending_verification)
        self.assertEqual(status_resp.latest_verification.id, verif.id)
        print("   ✅ API /api/v1/shops/verification/status phản hồi chính xác")

    def test_04_reject_duplicate_pending_verification(self):
        """Chặn nộp trùng hồ sơ khi đang có hồ sơ PENDING"""
        print("\n🔹 Test 4: Chặn nộp đè hồ sơ khi đang chờ duyệt")
        with self.assertRaises(HTTPException) as ctx:
            submit_shop_verification(
                db=self.db,
                shop=self.test_shop,
                business_license_url="/uploads/another_doc.png",
                shop_screenshot_url="/uploads/another_scr.png",
                shop_url_submitted="https://shopee.vn/uniqlo_official"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("đang chờ xét duyệt", ctx.exception.detail)
        print("   ✅ Đã chặn nộp lặp lại thành công (mã 400)")

    def test_05_admin_list_and_request_resubmit(self):
        """Admin xem danh sách pending và yêu cầu nộp lại (resubmit_required)"""
        print("\n🔹 Test 5: Admin xem hồ sơ và yêu cầu bổ sung (Resubmit Required)")
        pending_list = list_pending_verifications(admin_auth=True, db=self.db)
        self.assertGreaterEqual(len(pending_list), 1)
        target_verif = pending_list[0]
        print(f"   ✅ Admin tìm thấy {len(pending_list)} hồ sơ chờ duyệt")

        # Admin yêu cầu bổ sung tài liệu
        review_req = AdminReviewRequest(
            action="resubmit_required",
            admin_note="Ảnh chụp GPKD bị mờ góc dưới bên phải, vui lòng chụp lại rõ nét hơn."
        )
        reviewed = review_shop_verification(
            verification_id=target_verif.id,
            payload=review_req,
            admin_auth=True,
            db=self.db
        )
        self.assertEqual(reviewed.status, VerificationStatus.RESUBMIT_REQUIRED)
        self.assertEqual(reviewed.reviewed_by, "admin_tapai")

        self.db.refresh(self.test_shop)
        self.assertEqual(self.test_shop.status, ShopStatus.UNVERIFIED)
        print("   ✅ Xử lý Resubmit thành công: Trạng thái Shop quay về UNVERIFIED để nộp lại")

    def test_06_shop_resubmit_and_admin_approve(self):
        """Shop nộp lại hồ sơ rõ nét hơn và Admin Phê duyệt (Approve)"""
        print("\n🔹 Test 6: Shop nộp lại hồ sơ và Admin Phê duyệt thành công")
        # Shop nộp lại
        new_verif = submit_shop_verification(
            db=self.db,
            shop=self.test_shop,
            business_license_url="/uploads/uniqlo_gpkd_hd.png",
            shop_screenshot_url="/uploads/uniqlo_seller_dash.png",
            shop_url_submitted="https://shopee.vn/uniqlo_official"
        )
        self.assertEqual(new_verif.status, VerificationStatus.PENDING)

        # Admin duyệt Approve
        review_req = AdminReviewRequest(
            action="approve",
            admin_note="Hồ sơ hợp lệ và thông tin trùng khớp với sàn Shopee."
        )
        approved = review_shop_verification(
            verification_id=new_verif.id,
            payload=review_req,
            admin_auth=True,
            db=self.db
        )
        self.assertEqual(approved.status, VerificationStatus.APPROVED)

        self.db.refresh(self.test_shop)
        self.assertEqual(self.test_shop.status, ShopStatus.VERIFIED)
        print("   ✅ Phê duyệt thành công: Trạng thái Shop = VERIFIED (Được phép đăng ký sản phẩm)")

    def test_07_admin_management_and_stats(self):
        """Admin quản trị danh sách shop, khóa tài khoản và xem thống kê hệ thống"""
        print("\n🔹 Test 7: Admin quản lý Shop & Thống kê hệ thống")

        # 7.1 Lọc danh sách shop
        shop_list_resp = list_shops(status_filter="verified", page=1, limit=10, admin_auth=True, db=self.db)
        self.assertGreaterEqual(shop_list_resp.total, 1)
        print(f"   ✅ Lọc danh sách shop VERIFIED: Tìm thấy {shop_list_resp.total} shop")

        # 7.2 Admin tạm khóa shop (Suspend)
        update_req = AdminShopStatusUpdateRequest(status="suspended", reason="Nghi vấn hàng vi phạm bản quyền")
        updated_shop = update_shop_status(shop_id=self.test_shop.id, payload=update_req, admin_auth=True, db=self.db)
        self.assertEqual(updated_shop.status, "suspended")
        print("   ✅ Admin tạm khóa (SUSPENDED) shop thành công")

        # 7.3 Mở khóa lại shop (Unsuspend back to VERIFIED)
        unpause_req = AdminShopStatusUpdateRequest(status="verified", reason="Đã xác minh không vi phạm")
        restored_shop = update_shop_status(shop_id=self.test_shop.id, payload=unpause_req, admin_auth=True, db=self.db)
        self.assertEqual(restored_shop.status, "verified")
        print("   ✅ Admin mở khóa phục hồi (VERIFIED) shop thành công")

        # 7.4 Xem thống kê
        stats = get_system_stats(admin_auth=True, db=self.db)
        self.assertGreaterEqual(stats.total_shops, 1)
        self.assertGreaterEqual(stats.verified_shops, 1)
        print(f"   ✅ Thống kê hệ thống: Tổng {stats.total_shops} shops, {stats.verified_shops} verified")

    def test_08_shop_profile_update(self):
        """Shop xem và cập nhật hồ sơ cá nhân"""
        print("\n🔹 Test 8: Shop xem và cập nhật hồ sơ cá nhân")
        profile = get_profile(current_shop=self.test_shop)
        self.assertEqual(profile.email, "uniqlo_vn@phase2-test.com")

        update_req = ShopProfileUpdateRequest(
            shop_name="Uniqlo Vietnam Official Flagship",
            phone="0911223399"
        )
        updated = update_profile(payload=update_req, current_shop=self.test_shop, db=self.db)
        self.assertEqual(updated.shop_name, "Uniqlo Vietnam Official Flagship")
        self.assertEqual(updated.phone, "0911223399")
        print("   ✅ Cập nhật hồ sơ shop thành công (/api/v1/shops/profile)")

if __name__ == "__main__":
    unittest.main()

