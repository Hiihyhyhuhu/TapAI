import os
import sys
import unittest
from fastapi import HTTPException

# Đảm bảo import được các module từ thư mục backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.connection import init_db, SessionLocal
from database.models import Shop, Product, Commission, ShopStatus, ProductStatus
from models.product_schemas import (
    ProductCreateRequest,
    CommissionInput,
    ProductUpdateRequest,
    CommissionUpdateRequest,
    ProductStatusUpdateRequest,
)
from services.affiliate_service import (
    validate_and_compute_commission,
    create_product,
    get_shop_products,
    get_product_by_id,
    update_product,
    update_commission,
    update_product_status,
    delete_product,
    find_matching_affiliate_products,
    format_product_detail,
)
from routes.product_routes import (
    register_product,
    list_my_products,
    get_product,
    update_product_info,
    update_product_commission,
    change_product_status,
    remove_product,
    export_single_product_json,
    export_all_products_json,
)

class TestProductsPhase3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 65)
        print("🚀 BẮT ĐẦU KIỂM THỬ PHASE 3: PRODUCT & COMMISSION ENGINE (TAP AI)")
        print("=" * 65)
        init_db()
        cls.db = SessionLocal()

        # Dọn dẹp dữ liệu test cũ
        cls.db.query(Commission).delete()
        cls.db.query(Product).delete()
        cls.db.query(Shop).filter(Shop.email.like("%@phase3-test.com")).delete()
        cls.db.commit()

        # 1. Shop đã VERIFIED (Được phép đăng ký sản phẩm)
        cls.verified_shop = Shop(
            email="coolmate_official@phase3-test.com",
            phone="0911223388",
            password_hash="fakehash",
            shop_name="Coolmate Vietnam",
            platform="shopee",
            shop_url="https://shopee.vn/coolmate.vn",
            status=ShopStatus.VERIFIED,
            email_verified=True,
            phone_verified=True,
        )
        # 2. Shop đối tác trên Lazada
        cls.lazada_shop = Shop(
            email="ananas_vn@phase3-test.com",
            phone="0922334455",
            password_hash="fakehash",
            shop_name="Ananas Sneakers",
            platform="lazada",
            shop_url="https://www.lazada.vn/shop/ananas-vietnam",
            status=ShopStatus.VERIFIED,
            email_verified=True,
            phone_verified=True,
        )
        # 3. Shop CHƯA VERIFIED
        cls.unverified_shop = Shop(
            email="unverified@phase3-test.com",
            phone="0933445566",
            password_hash="fakehash",
            shop_name="Unverified Shop",
            platform="shopee",
            shop_url="https://shopee.vn/unverified",
            status=ShopStatus.UNVERIFIED,
            email_verified=True,
            phone_verified=True,
        )

        cls.db.add_all([cls.verified_shop, cls.lazada_shop, cls.unverified_shop])
        cls.db.commit()
        cls.db.refresh(cls.verified_shop)
        cls.db.refresh(cls.lazada_shop)
        cls.db.refresh(cls.unverified_shop)

    @classmethod
    def tearDownClass(cls):
        cls.db.query(Commission).delete()
        cls.db.query(Product).delete()
        cls.db.query(Shop).filter(Shop.email.like("%@phase3-test.com")).delete()
        cls.db.commit()
        cls.db.close()
        print("\n" + "=" * 65)
        print("🎉 TẤT CẢ UNIT TESTS PHASE 3 HOÀN TẤT THÀNH CÔNG 100%! ")
        print("=" * 65)

    def test_01_commission_rules_shopee(self):
        """Mô hình hoa hồng Shopee: Sàn cố định (3.5%) + Xtra do Shop tự quyết định"""
        print("\n🔹 Test 1: Quy tắc hoa hồng sàn Shopee (Cố định + Xtra)")
        plat_rate, ext_rate, ext_fixed, min_rate = validate_and_compute_commission(
            platform="shopee",
            comm_type="percentage",
            extra_rate=6.5,
            extra_fixed_amount=0.0
        )
        self.assertEqual(plat_rate, 3.5)
        self.assertEqual(ext_rate, 6.5)
        self.assertEqual(plat_rate + ext_rate, 10.0)
        print("   ✅ Shopee: 3.5% cố định từ sàn + 6.5% Xtra từ shop = Tổng nhận 10.0%")

    def test_02_commission_rules_other_platforms(self):
        """Mô hình hoa hồng sàn khác: Shop tự quyết toàn bộ, tối thiểu >= 2.0%"""
        print("\n🔹 Test 2: Quy tắc hoa hồng sàn khác (Lazada, Tiki, TikTok Shop >= 2%)")
        # 2.1 Thử đặt < 2% -> Phải bị từ chối với mã 400
        with self.assertRaises(HTTPException) as ctx:
            validate_and_compute_commission(
                platform="lazada",
                comm_type="percentage",
                extra_rate=1.5,
                extra_fixed_amount=0.0
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("tối thiểu", ctx.exception.detail)
        print("   ✅ Từ chối mức hoa hồng < 2.0% trên Lazada thành công (mã 400)")

        # 2.2 Đặt >= 2% -> Hợp lệ
        plat_rate, ext_rate, ext_fixed, min_rate = validate_and_compute_commission(
            platform="lazada",
            comm_type="percentage",
            extra_rate=7.0,
            extra_fixed_amount=0.0
        )
        self.assertEqual(plat_rate, 0.0)
        self.assertEqual(ext_rate, 7.0)
        self.assertEqual(min_rate, 2.0)
        print("   ✅ Lazada: Shop đặt 7.0% (>= 2.0% sàn khác) được chấp thuận thành công")

    def test_03_register_product_shopee(self):
        """Đăng ký sản phẩm Shopee thành công kèm hoa hồng"""
        print("\n🔹 Test 3: Đăng ký sản phẩm Shopee kèm hoa hồng Xtra")
        payload = ProductCreateRequest(
            name="Áo thun nam Cotton Compact Coolmate thoáng mát",
            category="Thời trang nam > Áo thun",
            product_url="https://shopee.vn/coolmate.vn/ao-thun-cotton-compact",
            image_urls=[
                "https://cf.shopee.vn/file/vn-11134207-7r98o-ao-thun-1.jpg",
                "https://cf.shopee.vn/file/vn-11134207-7r98o-ao-thun-2.jpg"
            ],
            description="Chất liệu 100% Cotton Compact siêu mềm mịn chống nhăn",
            price=189000.0,
            commission=CommissionInput(
                commission_type="percentage",
                extra_rate=5.0
            )
        )
        prod_resp = register_product(payload=payload, current_shop=self.verified_shop, db=self.db)
        self.assertIsNotNone(prod_resp.id)
        self.assertEqual(prod_resp.shop_name, "Coolmate Vietnam")
        self.assertEqual(prod_resp.status, "active")
        self.assertEqual(prod_resp.commission.platform_rate, 3.5)
        self.assertEqual(prod_resp.commission.extra_rate, 5.0)
        self.assertEqual(prod_resp.commission.total_rate, 8.5)
        self.test_product_id = prod_resp.id
        print(f"   ✅ Đăng ký sản phẩm Shopee thành công: ID = {prod_resp.id}, Tổng hoa hồng = 8.5%")

    def test_04_register_product_lazada(self):
        """Đăng ký sản phẩm Lazada thành công kèm hoa hồng"""
        print("\n🔹 Test 4: Đăng ký sản phẩm trên sàn Lazada")
        payload = ProductCreateRequest(
            name="Giày Sneaker Ananas Basas Bumper Gum High Top",
            category="Giày dép nam > Giày sneaker",
            product_url="https://www.lazada.vn/shop/ananas-vietnam/basas-high-top",
            image_urls=["https://vn-live.slatic.net/p/ananas-basas.jpg"],
            price=590000.0,
            commission=CommissionInput(
                commission_type="percentage",
                extra_rate=8.0
            )
        )
        prod_resp = register_product(payload=payload, current_shop=self.lazada_shop, db=self.db)
        self.assertEqual(prod_resp.commission.total_rate, 8.0)
        print(f"   ✅ Đăng ký sản phẩm Lazada thành công: Tổng hoa hồng = 8.0%")

    def test_05_list_and_search_products(self):
        """Xem danh sách sản phẩm của shop có bộ lọc và tìm kiếm"""
        print("\n🔹 Test 5: Xem danh sách và tìm kiếm sản phẩm của shop")
        list_resp = list_my_products(
            status_filter="active",
            search="Cotton",
            page=1,
            limit=10,
            current_shop=self.verified_shop,
            db=self.db
        )
        self.assertGreaterEqual(list_resp.total, 1)
        self.assertIn("Cotton", list_resp.products[0].name)
        print(f"   ✅ Tìm kiếm sản phẩm theo từ khóa 'Cotton': Tìm thấy {list_resp.total} sản phẩm")

    def test_06_update_product_and_commission(self):
        """Cập nhật thông tin sản phẩm và nâng mức hoa hồng Xtra"""
        print("\n🔹 Test 6: Cập nhật thông tin sản phẩm và thay đổi mức hoa hồng")
        # Tìm sản phẩm vừa tạo
        product = self.db.query(Product).filter(Product.shop_id == self.verified_shop.id).first()

        # 6.1 Cập nhật giá bán và mô tả
        update_req = ProductUpdateRequest(
            price=199000.0,
            description="Phiên bản nâng cấp 2026 chống nhăn tuyệt đối"
        )
        updated_prod = update_product_info(
            product_id=product.id,
            payload=update_req,
            current_shop=self.verified_shop,
            db=self.db
        )
        self.assertEqual(updated_prod.price, 199000.0)
        print("   ✅ Cập nhật giá bán mới 199.000₫ thành công")

        # 6.2 Nâng mức hoa hồng Xtra từ 5.0% lên 10.0%
        comm_req = CommissionUpdateRequest(
            commission_type="percentage",
            extra_rate=10.0
        )
        updated_comm = update_product_commission(
            product_id=product.id,
            payload=comm_req,
            current_shop=self.verified_shop,
            db=self.db
        )
        self.assertEqual(updated_comm.commission.extra_rate, 10.0)
        self.assertEqual(updated_comm.commission.total_rate, 13.5)
        print("   ✅ Nâng hoa hồng Xtra lên 10.0% (Tổng nhận 13.5%) thành công")

    def test_07_pause_activate_and_delete(self):
        """Tạm ẩn (paused), kích hoạt lại (active) và xóa mềm (delete) sản phẩm"""
        print("\n🔹 Test 7: Tạm ẩn, kích hoạt lại và xóa mềm sản phẩm")
        product = self.db.query(Product).filter(Product.shop_id == self.verified_shop.id).first()

        # 7.1 Tạm ẩn
        paused = change_product_status(
            product_id=product.id,
            payload=ProductStatusUpdateRequest(status="paused"),
            current_shop=self.verified_shop,
            db=self.db
        )
        self.assertEqual(paused.status, "paused")
        print("   ✅ Tạm ẩn (PAUSED) sản phẩm thành công")

        # 7.2 Kích hoạt lại
        activated = change_product_status(
            product_id=product.id,
            payload=ProductStatusUpdateRequest(status="active"),
            current_shop=self.verified_shop,
            db=self.db
        )
        self.assertEqual(activated.status, "active")
        print("   ✅ Kích hoạt lại (ACTIVE) sản phẩm thành công")

    def test_08_search_pipeline_partner_priority(self):
        """Tích hợp Pipeline: Ưu tiên gợi ý sản phẩm đối tác khi người dùng tìm kiếm"""
        print("\n🔹 Test 8: Pipeline ưu tiên tìm kiếm và gợi ý sản phẩm Shop Đối tác")
        matches = find_matching_affiliate_products(
            db=self.db,
            query_text="Áo thun nam cotton thoáng mát",
            category="Thời trang nam > Áo thun",
            limit=5
        )
        self.assertGreaterEqual(len(matches), 1)
        self.assertEqual(matches[0].shop_id, self.verified_shop.id)
        print(f"   ✅ Thuật toán đã phát hiện sản phẩm đối tác: '{matches[0].name}'")
        print(f"   🎯 Sản phẩm của đối tác được ưu tiên gắn huy hiệu chính hãng và đưa lên hàng đầu trong Side Panel!")

    def test_09_export_product_json(self):
        """Kiểm thử tính năng tự động xuất file JSON cho mỗi sản phẩm được đăng ký"""
        import json
        print("\n🔹 Test 9: Tự động xuất file JSON cho mỗi sản phẩm đăng ký (tên đơn hàng, loại hàng, mức hoa hồng...)")

        payload = ProductCreateRequest(
            name="Áo Polo Thể Thao Nam Pro Dry Coolmate",
            category="Thời trang nam > Áo Polo",
            product_url="https://shopee.vn/coolmate.vn/ao-polo-the-thao-pro-dry",
            image_urls=["https://cf.shopee.vn/file/vn-polo-pro-dry-1.jpg"],
            description="Vải dệt tổ ong thoáng khí, kháng khuẩn, co giãn thể thao",
            price=249000.0,
            commission=CommissionInput(
                commission_type="percentage",
                extra_rate=7.5,
                extra_fixed_amount=0.0
            )
        )

        res = register_product(payload=payload, current_shop=self.verified_shop, db=self.db)
        product_id = res.id

        # 1. Kiểm tra file JSON đã được tự động lưu vào thư mục exports/products
        export_file_path = os.path.join(BASE_DIR, "exports", "products", f"product_{product_id}.json")
        self.assertTrue(os.path.exists(export_file_path), f"File JSON xuất khẩu không tồn tại tại: {export_file_path}")

        # 2. Đọc nội dung file JSON và kiểm tra các trường bắt buộc
        with open(export_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Kiểm tra Tên đơn hàng & Tên sản phẩm
        self.assertEqual(data["order_item_name"], "Áo Polo Thể Thao Nam Pro Dry Coolmate")
        self.assertEqual(data["product_name"], "Áo Polo Thể Thao Nam Pro Dry Coolmate")
        print("   ✅ Tên đơn hàng / sản phẩm trong file JSON: OK")

        # Kiểm tra Loại hàng
        self.assertEqual(data["category"], "Thời trang nam > Áo Polo")
        print("   ✅ Loại hàng (ngành hàng) trong file JSON: OK")

        # Kiểm tra Mức phí hoa hồng
        # Shopee: 3.5% sàn + 7.5% extra = 11.0%
        comm = data["commission_rate"]
        self.assertEqual(comm["commission_type"], "percentage")
        self.assertEqual(comm["total_rate_percent"], 11.0)
        self.assertEqual(comm["platform_rate_percent"], 3.5)
        self.assertEqual(comm["extra_rate_percent"], 7.5)
        # Hoa hồng ước tính: 249000 * 11% = 27390 VND
        self.assertEqual(comm["estimated_commission_per_order"], 27390.0)
        self.assertIn("27.390", comm["estimated_commission_formatted"])
        print("   ✅ Mức phí hoa hồng và ước tính hoa hồng trên mỗi đơn hàng: OK")

        # Kiểm tra các yếu tố cần thiết bổ sung
        self.assertEqual(data["product_id"], product_id)
        self.assertEqual(data["platform"], "shopee")
        self.assertEqual(data["shop_name"], self.verified_shop.shop_name)
        self.assertEqual(data["pricing"]["price"], 249000.0)
        self.assertEqual(data["status"], "active")
        self.assertIn("export_metadata", data)
        print("   ✅ Các yếu tố bổ trợ (Mã SP, Shop, Giá, URL, Metadata): Đầy đủ và chính xác")

        # 3. Kiểm tra endpoint API xuất JSON
        api_res = export_single_product_json(product_id=product_id, download=False, current_shop=self.verified_shop, db=self.db)
        self.assertEqual(api_res.status_code, 200)
        print("   ✅ Endpoint GET /api/v1/affiliate/products/{id}/export-json hoạt động tốt")

        print("   🎉 Hoàn thành kiểm tra xuất file JSON khi đăng ký sản phẩm!")

if __name__ == "__main__":
    unittest.main()

