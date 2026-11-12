import sqlite3
import os

db_path = os.path.abspath("tapai_affiliate.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def add_column_if_missing(table, column, col_type):
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [c[1] for c in cursor.fetchall()]
    if column not in cols:
        print(f"Adding {column} to {table}...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    else:
        print(f"Column {column} already exists in {table}.")

# 1. Shops table
add_column_if_missing("shops", "ownership_token", "VARCHAR(32)")
add_column_if_missing("shops", "contract_status", "VARCHAR(32) DEFAULT 'PENDING'")
add_column_if_missing("shops", "contract_signed_at", "DATETIME")
add_column_if_missing("shops", "contract_hash", "VARCHAR(64)")
add_column_if_missing("shops", "wallet_balance", "NUMERIC(14, 2) DEFAULT 1000000.00")
add_column_if_missing("shops", "total_deposited", "NUMERIC(14, 2) DEFAULT 1000000.00")
add_column_if_missing("shops", "total_cpc_spent", "NUMERIC(14, 2) DEFAULT 0.00")

# Set defaults for existing shops
cursor.execute("UPDATE shops SET ownership_token = 'VERIFY-FCAJ' WHERE ownership_token IS NULL")
cursor.execute("UPDATE shops SET contract_status = 'ACTIVE' WHERE contract_status IS NULL OR contract_status = 'PENDING'")
cursor.execute("UPDATE shops SET contract_hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855' WHERE contract_hash IS NULL")
cursor.execute("UPDATE shops SET contract_signed_at = datetime('now') WHERE contract_signed_at IS NULL")
cursor.execute("UPDATE shops SET wallet_balance = 1000000.00 WHERE wallet_balance IS NULL")
cursor.execute("UPDATE shops SET total_deposited = 1000000.00 WHERE total_deposited IS NULL")
cursor.execute("UPDATE shops SET total_cpc_spent = 0.00 WHERE total_cpc_spent IS NULL")

# 2. Products table
add_column_if_missing("products", "cpc_bid", "NUMERIC(10, 2) DEFAULT 2000.00")
add_column_if_missing("products", "daily_budget", "NUMERIC(12, 2) DEFAULT 100000.00")
add_column_if_missing("products", "today_spent", "NUMERIC(12, 2) DEFAULT 0.00")

# 3. Affiliate Products table
add_column_if_missing("affiliate_products", "cpc_bid", "NUMERIC(10, 2) DEFAULT 2000.00")
add_column_if_missing("affiliate_products", "daily_budget", "NUMERIC(12, 2) DEFAULT 100000.00")
add_column_if_missing("affiliate_products", "today_spent", "NUMERIC(12, 2) DEFAULT 0.00")

# 4. Clicks table
add_column_if_missing("clicks", "committed_cpc_at_click", "NUMERIC(10, 2) DEFAULT 2000.00")
add_column_if_missing("clicks", "cpc_deducted", "NUMERIC(10, 2) DEFAULT 0.00")
add_column_if_missing("clicks", "is_valid_unique", "BOOLEAN DEFAULT 1")
add_column_if_missing("clicks", "fraud_reason", "VARCHAR(64)")
add_column_if_missing("clicks", "client_ip", "VARCHAR(64)")

# 5. Click Trackings table
add_column_if_missing("click_trackings", "committed_cpc_at_click", "NUMERIC(10, 2) DEFAULT 2000.00")
add_column_if_missing("click_trackings", "cpc_deducted", "NUMERIC(10, 2) DEFAULT 0.00")
add_column_if_missing("click_trackings", "is_valid_unique", "BOOLEAN DEFAULT 1")
add_column_if_missing("click_trackings", "fraud_reason", "VARCHAR(64)")
add_column_if_missing("click_trackings", "client_ip", "VARCHAR(64)")

conn.commit()
conn.close()
print("Migration completed successfully!")
