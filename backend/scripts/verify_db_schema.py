import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.connection import init_db, engine
from sqlalchemy import inspect

init_db()
inspector = inspect(engine)
tables = inspector.get_table_names()
print("Tables in DB:", tables)

required_tables = ["merchants", "merchant_shops", "affiliate_products", "click_trackings", "conversions"]
for t in required_tables:
    assert t in tables, f"Missing table: {t}"
    print(f"  ✓ Found table: {t}")

print("🎉 ALL 5 REQUIRED TABLES CREATED SUCCESSFULLY!")

