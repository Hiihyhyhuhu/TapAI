"""
Seed script to create a fully functioning Demo Shop for TAP AI Partner Portal.
Shop Credentials:
  - Email: demo@tapai.vn
  - Password: Password@123
  - Phone: 0988776655
  - Shop Name: Coolmate Official Store
"""
import os
import sys
import json
import uuid
from datetime import datetime, timezone, timedelta

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.database.connection import SessionLocal, init_db
from backend.database.models import (
    Shop, Verification, Product, Commission, Click, Conversion,
    ShopStatus, VerificationStatus, ProductStatus, CommissionType, ConversionStatus
)
from backend.services.auth_service import hash_password

def seed_demo_data():
    init_db()
    db = SessionLocal()

    try:
        demo_email = "demo@tapai.vn"
        existing_shop = db.query(Shop).filter(Shop.email == demo_email).first()

        if existing_shop:
            print(f"Shop {demo_email} already exists. Cleaning up existing demo data for clean refresh...")
            db.delete(existing_shop)
            db.commit()

        # 1. Create Verified Demo Shop
        now = datetime.now(timezone.utc)
        pwd_hash = hash_password("Password@123")

        demo_shop = Shop(
            id=uuid.uuid4().hex,
            email=demo_email,
            phone="0988000111",
            password_hash=pwd_hash,
            shop_name="Coolmate Official Store",
            platform="shopee",
            shop_url="https://shopee.vn/coolmate.vn",
            shop_external_id="coolmate_shopee_88",
            status=ShopStatus.VERIFIED,
            email_verified=True,
            phone_verified=True,
            created_at=now - timedelta(days=30),
            updated_at=now
        )
        db.add(demo_shop)
        db.flush()

        # 2. Add Approved Verification Record
        verification = Verification(
            id=uuid.uuid4().hex,
            shop_id=demo_shop.id,
            business_license_url="http://localhost:8000/uploads/verifications/demo_license.pdf",
            shop_screenshot_url="http://localhost:8000/uploads/verifications/demo_shop_screen.png",
            shop_url_submitted="https://shopee.vn/coolmate.vn",
            status=VerificationStatus.APPROVED,
            admin_note="Hồ sơ doanh nghiệp hợp lệ. Đã đối soát MST và gian hàng Shopee Mall chính hãng.",
            reviewed_by="admin_system",
            submitted_at=now - timedelta(days=29),
            reviewed_at=now - timedelta(days=28)
        )
        db.add(verification)

        # 3. Add Sample Products with Extra Commissions
        products_data = [
            {
                "name": "Áo Thun Nam Thể Thao ProMax Thoáng Khí Coolmate",
                "category": "Thời trang nam > Áo thun",
                "product_url": "https://shopee.vn/product/12345/67890",
                "image_urls": json.dumps([
                    "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=600&q=80"
                ]),
                "description": "Chất liệu sợi Quick-dry thấm hút mồ hôi tối ưu, thiết kế dáng suông thoải mái khi vận động thể thao.",
                "price": 189000.0,
                "extra_rate": 8.5
            },
            {
                "name": "Quần Short Thể Thao Nam Chạy Bộ 5 Inch New Basics",
                "category": "Thời trang nam > Quần short",
                "product_url": "https://shopee.vn/product/12345/67891",
                "image_urls": json.dumps([
                    "https://images.unsplash.com/photo-1591195853828-11db59a44f6b?auto=format&fit=crop&w=600&q=80"
                ]),
                "description": "Quần short nam 2 lớp co giãn 4 chiều, có ngăn để điện thoại chống rung lắc tiện lợi khi tập gym và chạy bộ.",
                "price": 249000.0,
                "extra_rate": 6.5
            },
            {
                "name": "Combo 3 Quần Lót Nam Cotton Compact Kháng Khuẩn",
                "category": "Thời trang nam > Đồ lót",
                "product_url": "https://shopee.vn/product/12345/67892",
                "image_urls": json.dumps([
                    "https://images.unsplash.com/photo-1582533561751-ef6f6ab93a2e?auto=format&fit=crop&w=600&q=80"
                ]),
                "description": "Sợi bông chải kỹ Cotton Compact siêu mềm mịn, công nghệ Nano bạc kháng khuẩn đạt chuẩn 99%.",
                "price": 199000.0,
                "extra_rate": 10.0
            },
            {
                "name": "Combo 4 Đôi Tất Cổ Trung Bamboo Khử Mùi Thoáng Khí",
                "category": "Phụ kiện thời trang > Vớ tất",
                "product_url": "https://shopee.vn/product/12345/67893",
                "image_urls": json.dumps([
                    "https://images.unsplash.com/photo-1586350977771-b3b0abd50c82?auto=format&fit=crop&w=600&q=80"
                ]),
                "description": "Sợi sợi tre tự nhiên Bamboo êm ái, chống mùi hôi chân hiệu quả cả ngày dài làm việc.",
                "price": 99000.0,
                "extra_rate": 12.0
            }
        ]

        created_products = []
        for p_data in products_data:
            p = Product(
                id=uuid.uuid4().hex,
                shop_id=demo_shop.id,
                name=p_data["name"],
                category=p_data["category"],
                product_url=p_data["product_url"],
                platform="shopee",
                image_urls=p_data["image_urls"],
                description=p_data["description"],
                price=p_data["price"],
                currency="VND",
                status=ProductStatus.ACTIVE,
                created_at=now - timedelta(days=20),
                updated_at=now
            )
            db.add(p)
            db.flush()

            # Commission
            comm = Commission(
                id=uuid.uuid4().hex,
                product_id=p.id,
                platform="shopee",
                commission_type=CommissionType.PERCENTAGE,
                platform_rate=3.0,
                extra_rate=p_data["extra_rate"],
                extra_fixed_amount=0.0,
                min_rate=2.0,
                effective_from=now - timedelta(days=20)
            )
            db.add(comm)
            created_products.append((p, p_data["extra_rate"]))

        db.flush()

        # 4. Generate Realistic Click & Conversion Analytics across past 7 days
        # Daily distribution of clicks & orders
        daily_stats = [
            {"days_ago": 6, "clicks": 142, "orders": 7},
            {"days_ago": 5, "clicks": 185, "orders": 11},
            {"days_ago": 4, "clicks": 160, "orders": 9},
            {"days_ago": 3, "clicks": 210, "orders": 14},
            {"days_ago": 2, "clicks": 245, "orders": 15},
            {"days_ago": 1, "clicks": 280, "orders": 18},
            {"days_ago": 0, "clicks": 195, "orders": 12},
        ]

        total_clicks_count = 0
        total_conv_count = 0

        for stat in daily_stats:
            d_time = now - timedelta(days=stat["days_ago"], hours=4)
            for i in range(stat["clicks"]):
                prod, extra_r = created_products[i % len(created_products)]
                click = Click(
                    id=uuid.uuid4().hex,
                    product_id=prod.id,
                    shop_id=demo_shop.id,
                    user_session_id=f"sess_{stat['days_ago']}_{i}",
                    source_type="video",
                    referral_url="https://youtube.com/watch?v=coolmate_review",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    ip_hash=f"hash_{stat['days_ago']}_{i%20}",
                    redirect_url=prod.product_url,
                    clicked_at=d_time + timedelta(minutes=i * 3)
                )
                db.add(click)
                total_clicks_count += 1

                # If this click generated a conversion
                if i < stat["orders"]:
                    order_val = float(prod.price)
                    comm_earned = order_val * ((3.0 + extra_r) / 100.0)
                    conv = Conversion(
                        id=uuid.uuid4().hex,
                        click_id=click.id,
                        product_id=prod.id,
                        shop_id=demo_shop.id,
                        order_id=f"SP_ORD_{stat['days_ago']}{i:03d}",
                        order_value=order_val,
                        commission_earned=comm_earned,
                        status=ConversionStatus.CONFIRMED,
                        converted_at=d_time + timedelta(minutes=i * 3 + 12),
                        confirmed_at=d_time + timedelta(minutes=i * 3 + 30)
                    )
                    db.add(conv)
                    total_conv_count += 1

        db.commit()
        print(" Successfully seeded demo shop!")
        print(f" - Shop: {demo_shop.shop_name} ({demo_shop.email})")
        print(f" - Password: Password@123")
        print(f" - Products created: {len(created_products)}")
        print(f" - Clicks created: {total_clicks_count}")
        print(f" - Conversions created: {total_conv_count}")

    except Exception as e:
        db.rollback()
        print(f"Error seeding demo data: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_demo_data()
