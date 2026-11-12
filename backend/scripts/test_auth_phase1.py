import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Đảm bảo import được các module từ thư mục backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.connection import init_db, SessionLocal
from database.models import Shop, Session as ShopSession, ShopStatus
from models.auth_schemas import (
    ShopRegisterRequest,
    VerifyEmailRequest,
    VerifyPhoneRequest,
    ResendOtpRequest,
    LoginRequest,
    RefreshTokenRequest,
)
from services.auth_service import (
    is_disposable_email,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from routes.auth_routes import (
    register_shop,
    verify_email,
    verify_phone,
    resend_otp,
    login,
    refresh_token,
    logout,
    get_my_profile,
)
from fastapi import HTTPException

class TestAuthPhase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 65)
        print("🚀 BẮT ĐẦU KIỂM THỬ PHASE 1: DATABASE & AUTHENTICATION (TAP AI)")
        print("=" * 65)
        init_db()
        cls.db = SessionLocal()

        # Dọn dẹp dữ liệu test cũ
        cls.db.query(ShopSession).delete()
        cls.db.query(Shop).filter(Shop.email.like("%@test-tapai.com")).delete()
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.query(ShopSession).delete()
        cls.db.query(Shop).filter(Shop.email.like("%@test-tapai.com")).delete()
        cls.db.commit()
        cls.db.close()
        print("\n" + "=" * 65)
        print("🎉 TẤT CẢ UNIT TESTS PHASE 1 HOÀN TẤT THÀNH CÔNG 100%!")
        print("=" * 65)

    def test_01_anti_spam_disposable_email(self):
        """Lớp chống spam 5: Chặn các domain email tạm thời / rác"""
        print("\n🔹 Test 1: Kiểm tra Lớp chống Spam (Disposable Email Filter)")
        self.assertTrue(is_disposable_email("user@yopmail.com"))
        self.assertTrue(is_disposable_email("test@tempmail.com"))
        self.assertTrue(is_disposable_email("bot@guerrillamail.com"))
        self.assertFalse(is_disposable_email("official@zara.vn"))
        self.assertFalse(is_disposable_email("shop@gmail.com"))

        req = ShopRegisterRequest(
            email="spammer@yopmail.com",
            phone="0912345678",
            password="Password123!",
            shop_name="Spam Store",
            platform="shopee",
            shop_url="https://shopee.vn/spam"
        )
        with self.assertRaises(HTTPException) as ctx:
            register_shop(req, self.db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("tạm thời", ctx.exception.detail.lower())
        print("   ✅ Đã chặn thành công domain email dùng 1 lần (yopmail.com) với mã 400")

    def test_02_register_valid_shop(self):
        """Đăng ký shop hợp lệ và tạo mã OTP"""
        print("\n🔹 Test 2: Đăng ký tài khoản Shop với thông tin hợp lệ")
        req = ShopRegisterRequest(
            email="zara_official@test-tapai.com",
            phone="0912345678",
            password="SecurePassword123@",
            shop_name="Zara Official Store",
            platform="shopee",
            shop_url="https://shopee.vn/zara_official"
        )
        res = register_shop(req, self.db)
        self.assertTrue(res.success)
        self.assertIn("shop_id", res.data)
        print(f"   ✅ Đăng ký thành công: Shop ID = {res.data['shop_id']}")

        # Kiểm tra trạng thái trong Database
        shop = self.db.query(Shop).filter(Shop.email == "zara_official@test-tapai.com").first()
        self.assertIsNotNone(shop)
        self.assertEqual(shop.status, ShopStatus.UNVERIFIED)
        self.assertFalse(shop.email_verified)
        self.assertFalse(shop.phone_verified)
        self.assertIsNotNone(shop.otp_email_code)
        self.assertIsNotNone(shop.otp_phone_code)
        print("   ✅ Trạng thái ban đầu: UNVERIFIED, email_verified=False, phone_verified=False")

    def test_03_reject_duplicate_registration(self):
        """Chặn đăng ký trùng Email hoặc Số điện thoại"""
        print("\n🔹 Test 3: Chặn đăng ký trùng Email hoặc Số điện thoại")
        req_dup_email = ShopRegisterRequest(
            email="zara_official@test-tapai.com",
            phone="0988888888",
            password="Password123!",
            shop_name="Duplicate Email",
            platform="shopee",
            shop_url="https://shopee.vn/dup"
        )
        with self.assertRaises(HTTPException) as ctx1:
            register_shop(req_dup_email, self.db)
        self.assertEqual(ctx1.exception.status_code, 409)
        print("   ✅ Chặn trùng Email thành công (mã 409 Conflict)")

        req_dup_phone = ShopRegisterRequest(
            email="another_shop@test-tapai.com",
            phone="0912345678",
            password="Password123!",
            shop_name="Duplicate Phone",
            platform="shopee",
            shop_url="https://shopee.vn/dup2"
        )
        with self.assertRaises(HTTPException) as ctx2:
            register_shop(req_dup_phone, self.db)
        self.assertEqual(ctx2.exception.status_code, 409)
        print("   ✅ Chặn trùng Số điện thoại thành công (mã 409 Conflict)")

    def test_04_verify_otp_flow(self):
        """Xác thực mã OTP cho Email và Số điện thoại"""
        print("\n🔹 Test 4: Xác thực mã OTP (Email & SĐT)")
        shop = self.db.query(Shop).filter(Shop.email == "zara_official@test-tapai.com").first()

        # 4.1 Thử OTP sai
        with self.assertRaises(HTTPException) as ctx:
            verify_email(VerifyEmailRequest(email=shop.email, otp_code="000000"), self.db)
        self.assertEqual(ctx.exception.status_code, 400)
        print("   ✅ Từ chối mã OTP sai thành công (mã 400)")

        # 4.2 Gửi OTP đúng cho Email
        res_email = verify_email(VerifyEmailRequest(email=shop.email, otp_code=shop.otp_email_code), self.db)
        self.assertTrue(res_email.success)
        print("   ✅ Xác thực mã OTP Email thành công")

        # 4.3 Gửi OTP đúng cho Số điện thoại
        res_phone = verify_phone(VerifyPhoneRequest(phone=shop.phone, otp_code=shop.otp_phone_code), self.db)
        self.assertTrue(res_phone.success)
        print("   ✅ Xác thực mã OTP Số điện thoại thành công")

        self.db.refresh(shop)
        self.assertTrue(shop.email_verified)
        self.assertTrue(shop.phone_verified)

    def test_05_login_and_jwt_session(self):
        """Đăng nhập, tạo JWT Access + Refresh Token và lưu Session"""
        print("\n🔹 Test 5: Đăng nhập & Quản lý JWT Session")

        # Mock request object for IP and User-Agent
        mock_req = MagicMock()
        mock_req.client.host = "127.0.0.1"
        mock_req.headers.get.return_value = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

        # 5.1 Đăng nhập sai mật khẩu
        with self.assertRaises(HTTPException) as ctx:
            login(LoginRequest(email_or_phone="zara_official@test-tapai.com", password="WrongPassword!"), mock_req, self.db)
        self.assertEqual(ctx.exception.status_code, 401)
        print("   ✅ Chặn đăng nhập khi sai mật khẩu (mã 401)")

        # 5.2 Đăng nhập đúng mật khẩu
        auth_resp = login(LoginRequest(email_or_phone="zara_official@test-tapai.com", password="SecurePassword123@"), mock_req, self.db)
        self.assertIsNotNone(auth_resp.access_token)
        self.assertIsNotNone(auth_resp.refresh_token)
        self.assertEqual(auth_resp.shop.shop_name, "Zara Official Store")
        print("   ✅ Đăng nhập thành công! Đã cấp phát Access Token và Refresh Token")

        # 5.3 Giải mã Access Token
        payload = decode_token(auth_resp.access_token, expected_type="access")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], auth_resp.shop.id)
        print("   ✅ Giải mã JWT Access Token hợp lệ")

        # 5.4 Lấy thông tin cá nhân qua /me
        shop = self.db.query(Shop).filter(Shop.id == auth_resp.shop.id).first()
        profile = get_my_profile(shop)
        self.assertEqual(profile.email, "zara_official@test-tapai.com")
        self.assertTrue(profile.email_verified)
        print("   ✅ Truy vấn thông tin tài khoản /api/v1/auth/me thành công")

        # 5.5 Làm mới token (Refresh Token)
        refresh_res = refresh_token(RefreshTokenRequest(refresh_token=auth_resp.refresh_token), self.db)
        self.assertIn("access_token", refresh_res)
        print("   ✅ Cấp phát Access Token mới qua /api/v1/auth/refresh thành công")

        # 5.6 Đăng xuất (Logout)
        logout_res = logout(shop, self.db)
        self.assertTrue(logout_res.success)
        active_sessions = self.db.query(ShopSession).filter(ShopSession.shop_id == shop.id).count()
        self.assertEqual(active_sessions, 0)
        print("   ✅ Đăng xuất và dọn dẹp các sessions thành công")

if __name__ == "__main__":
    unittest.main()
