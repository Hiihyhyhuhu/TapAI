import sys
import os
import requests
import json

# Ensure backend root is on sys.path dynamically
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database.connection import SessionLocal
from database.models import Shop, AffiliateProduct
from services.auth_service import create_access_token

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

def run_tests():
    print("=== STARTING FULL E2E CPC WORKFLOW TEST ALIGNED WITH DOCS.MD ===")
    db = SessionLocal()
    shop = db.query(Shop).filter(Shop.email == "demo@tapai.vn").first()
    if not shop:
        shop = db.query(Shop).filter(Shop.email == "doananhphuong075@gmail.com").first()
    if not shop:
        shop = db.query(Shop).first()
    if not shop:
        print("[FAIL] No Shop found in database! Please register or seed a demo shop first.")
        return False
    
    print(f"[INIT] Found Shop: id={shop.id}, name={shop.shop_name}, email={shop.email}")
    token = create_access_token(shop.id)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # -------------------------------------------------------------
    # STAGE 1: MERCHANT ONBOARDING & E-CONTRACTING
    # -------------------------------------------------------------
    print("\n--- STAGE 1: MERCHANT ONBOARDING & E-CONTRACTING ---")
    
    # 1.1 Get Contract details
    res = requests.get(f"{BASE_URL}/api/v1/shops/contract", headers=headers)
    assert res.status_code == 200, f"Get contract failed: {res.text}"
    c_data = res.json()
    print(f"[PASS] 1.1 Contract loaded. Status: {c_data.get('contract_status')}, Token: {c_data.get('ownership_token')}")
    
    # 1.2 Ownership Verification
    res = requests.post(f"{BASE_URL}/api/v1/shops/ownership/verify", headers=headers)
    assert res.status_code == 200, f"Verify ownership failed: {res.text}"
    print(f"[PASS] 1.2 Ownership verification: {res.json().get('message')}")
    
    # 1.3 Sign E-Contract
    res = requests.post(f"{BASE_URL}/api/v1/shops/contract/sign", headers=headers, json={"otp_code": "123456"})
    assert res.status_code == 200, f"Sign contract failed: {res.text}"
    sign_data = res.json()
    assert sign_data.get("contract_status") == "ACTIVE", "Contract status is not ACTIVE"
    assert sign_data.get("contract_hash"), "Missing contract SHA-256 hash"
    print(f"[PASS] 1.3 E-Contract signed with SHA-256: {sign_data.get('contract_hash')[:16]}... Status: {sign_data.get('contract_status')}")

    # -------------------------------------------------------------
    # STAGE 2: PRODUCT REGISTRATION, CPC BIDDING & ESCROW FUNDING
    # -------------------------------------------------------------
    print("\n--- STAGE 2: PRODUCT REGISTRATION, CPC BIDDING & ESCROW FUNDING ---")
    
    # 2.1 Check & Deposit Escrow Wallet
    res = requests.get(f"{BASE_URL}/api/v1/shops/wallet", headers=headers)
    assert res.status_code == 200, f"Get wallet failed: {res.text}"
    wallet_info = res.json()
    initial_balance = wallet_info.get("wallet_balance", 0)
    print(f"[INFO] 2.1 Current Wallet Balance: {initial_balance:,.0f} VND")
    
    deposit_amount = 500000
    res = requests.post(f"{BASE_URL}/api/v1/shops/wallet/deposit", headers=headers, json={"amount": deposit_amount})
    assert res.status_code == 200, f"Deposit wallet failed: {res.text}"
    new_balance = res.json().get("wallet_balance")
    print(f"[PASS] 2.1 Deposited +{deposit_amount:,.0f} VND. New Balance: {new_balance:,.0f} VND")
    
    # 2.2 Register / Import Product with CPC Bid & Daily Budget
    prod_payload = {
        "product_url": "https://shopee.vn/product/12345/67890",
        "cpc_bid": 2500,
        "daily_budget": 150000
    }
    res = requests.post(f"{BASE_URL}/api/v1/affiliate/products/import-url", headers=headers, json=prod_payload)
    assert res.status_code in [200, 201], f"Import product failed: {res.text}"
    prod_data = res.json()
    prod_id = prod_data.get("id") or (prod_data.get("data", {}) if isinstance(prod_data.get("data"), dict) else {}).get("id")
    print(f"[PASS] 2.2 Product registered: ID={prod_id}, CPC={prod_data.get('cpc_bid', 2500):,.0f} VND, Status={prod_data.get('sync_status', 'ELIGIBLE')}")

    # 2.3 Update CPC Bidding
    res = requests.patch(
        f"{BASE_URL}/api/v1/affiliate/products/{prod_id}/bidding",
        headers=headers,
        json={"cpc_bid": 3000, "daily_budget": 200000}
    )
    assert res.status_code == 200, f"Update bidding failed: {res.text}"
    bidding_res = res.json()
    print(f"[PASS] 2.3 Updated Bidding: cpc_bid={bidding_res.get('cpc_bid')} VND, daily_budget={bidding_res.get('daily_budget')} VND")

    # -------------------------------------------------------------
    # STAGE 3: JSON DATA FEED EXPORT FOR CORE BACKEND
    # -------------------------------------------------------------
    print("\n--- STAGE 3: JSON DATA FEED EXPORT FOR CORE BACKEND ---")
    
    # 3.1 Serializer Job export merchant_products_feed.json
    res = requests.get(f"{BASE_URL}/api/v1/affiliate/products/feed/merchant-products")
    assert res.status_code == 200, f"Export feed failed: {res.text}"
    feed_data = res.json()
    assert "items" in feed_data, "Feed missing 'items' key"
    assert feed_data.get("total_eligible_products", 0) > 0, "No eligible products in feed"
    print(f"[PASS] 3.1 Serialized JSON Feed successfully: {feed_data.get('total_eligible_products')} items ready for Core Ranking Backend")
    sample_item = feed_data["items"][0]
    print(f"      Sample Feed Item: ID={sample_item.get('product_id')}, Title={sample_item.get('title')[:30]}..., CPC={sample_item.get('cpc_bid')} VND, Status={sample_item.get('status')}")

    # 3.2 Dispatch to Core Ranking Backend
    res = requests.post(f"{BASE_URL}/api/v1/affiliate/products/feed/dispatch", headers=headers)
    assert res.status_code == 200, f"Dispatch feed failed: {res.text}"
    dispatch_res = res.json()
    count = dispatch_res.get('eligible_items_count') or dispatch_res.get('dispatched_count')
    print(f"[PASS] 3.2 Dispatched Feed: {dispatch_res.get('message')} (Items dispatched: {count})")

    # -------------------------------------------------------------
    # STAGE 4: CLICK TRACKING, ANTI-FRAUD & REAL-TIME CPC BILLING
    # -------------------------------------------------------------
    print("\n--- STAGE 4: CLICK TRACKING, ANTI-FRAUD & REAL-TIME CPC BILLING ---")
    
    # Lấy lại số dư ví trước click
    res = requests.get(f"{BASE_URL}/api/v1/shops/wallet", headers=headers)
    bal_before = res.json().get("wallet_balance")
    
    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    # 4.1 Valid Unique Click
    redirect_url = f"{BASE_URL}/r/{prod_id}?ext_uid=qa_e2e_user_1"
    res1 = requests.get(redirect_url, headers=browser_headers, allow_redirects=False)
    assert res1.status_code == 302, f"Expected 302 redirect, got {res1.status_code}"
    
    res = requests.get(f"{BASE_URL}/api/v1/shops/wallet", headers=headers)
    bal_after_valid = res.json().get("wallet_balance")
    deducted = bal_before - bal_after_valid
    assert deducted == 3000, f"Expected 3,000 VND deduction, but got {deducted} VND"
    print(f"[PASS] 4.1 Valid Unique Click -> HTTP 302 Found. Wallet accurately deducted {deducted:,.0f} VND (Balance: {bal_after_valid:,.0f} VND)")

    # 4.2 Duplicate Click within 30 seconds
    res2 = requests.get(redirect_url, headers=browser_headers, allow_redirects=False)
    assert res2.status_code == 302, f"Expected 302 redirect, got {res2.status_code}"
    
    res = requests.get(f"{BASE_URL}/api/v1/shops/wallet", headers=headers)
    bal_after_dup = res.json().get("wallet_balance")
    assert bal_after_dup == bal_after_valid, f"Duplicate click improperly deducted funds! {bal_after_valid} vs {bal_after_dup}"
    print(f"[PASS] 4.2 Duplicate Click (<30s) -> HTTP 302 Found. Anti-Fraud Triggered (Cost: 0 VND). Balance unchanged: {bal_after_dup:,.0f} VND")

    # 4.3 Bot User-Agent Click
    bot_headers = {"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"}
    res3 = requests.get(f"{BASE_URL}/r/{prod_id}?ext_uid=qa_bot_user", headers=bot_headers, allow_redirects=False)
    assert res3.status_code == 302, f"Expected 302 redirect for bot, got {res3.status_code}"
    
    res = requests.get(f"{BASE_URL}/api/v1/shops/wallet", headers=headers)
    bal_after_bot = res.json().get("wallet_balance")
    assert bal_after_bot == bal_after_dup, f"Bot click improperly deducted funds!"
    print(f"[PASS] 4.3 Bot Crawler Click -> HTTP 302 Found. Anti-Fraud Bot Filter Triggered (Cost: 0 VND). Balance unchanged: {bal_after_bot:,.0f} VND")

    # 4.4 Verify Click Ledger
    res = requests.get(f"{BASE_URL}/api/v1/tracking/cpc-ledger", headers=headers)
    assert res.status_code == 200, f"Get click ledger failed: {res.text}"
    ledger_data = res.json()
    items = ledger_data.get("items", [])
    assert len(items) >= 3, f"Expected at least 3 clicks in ledger, got {len(items)}"
    print(f"[PASS] 4.4 Verified Click Ledger ({len(items)} logs found):")
    for idx, item in enumerate(items[:3]):
        valid_tag = "VALID" if item.get('is_valid_unique') else f"FRAUD ({item.get('fraud_reason')})"
        print(f"      [{idx+1}] User: {item.get('ext_user_id')} | Status: {valid_tag} | Deducted: {item.get('cpc_deducted'):,.0f} VND | Product: {item.get('product_id')}")

    print("\n================================================================================")
    print(">>> ALL 4 STAGES OF DOCS.MD (CPC & JSON FEED MODEL) PASSED 100% SUCCESSFULLY! <<<")
    print("================================================================================")
    db.close()
    return True

if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)
