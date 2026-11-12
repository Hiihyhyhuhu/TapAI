## 5. QUY TRÌNH HỆ THỐNG: CỔNG THÔNG TIN ĐỐI TÁC TRỰC TIẾP (DIRECT MERCHANT PORTAL - CPC & JSON FEED MODEL)

```text
================================================================================
         SYSTEM WORKFLOW: DIRECT MERCHANT PORTAL (CPC & JSON FEED MODEL)
================================================================================

[STAGE 1: MERCHANT ONBOARDING & E-CONTRACTING]
Merchant accesses Web Portal 
  ──► Registers account & submits Shop Profile (Shop URL, Business Info)
  ──► Completes Ownership Verification (Inserts token `VERIFY-XXXX` into Shop Bio / Meta Tag)
  ──► System generates a Digital CPC Agreement (PDF/HTML) defining Click Rates & Terms
  ──► Merchant signs via E-Signature (OTP Verification + SHA-256 Hash Logging)
  ──► Contract status transitions to `ACTIVE` (Unlocks Campaign & Product Creation).

[STAGE 2: PRODUCT REGISTRATION, CPC BIDDING & ESCROW FUNDING]
Merchant registers Products (Manual Form / CSV Upload / OpenGraph Auto-Scraper)
  │
  ├─► Sets Committed Affiliate Rate / CPC Bid (e.g., 2,000 VND per click or % equivalent)
  ├─► Sets Daily Budget Cap (Optional limit to prevent rapid budget depletion)
  ├─► Tops up the Prepaid Escrow Wallet (Mandatory balance required before activation)
  └─► Product status transitions to `ELIGIBLE` (Ready for JSON Export).

[STAGE 3: JSON DATA FEED EXPORT FOR CORE BACKEND]
Web Portal runs a Serializer Job (On-demand Webhook or Periodic Export)
  ──► Queries all Products where `Contract == ACTIVE`, `Wallet_Balance > Min_CPC`, and `Status == ELIGIBLE`
  ──► Packages Merchant, Contract, Product, and Committed Rate metadata into a standardized `.json` payload
  ──► Exports / Dispatches `merchant_products_feed.json` to the Core Ranking Backend
      (Core Backend ingests this JSON and runs its own proprietary Ranking Algorithm).

[STAGE 4: CLICK TRACKING, ANTI-FRAUD & REAL-TIME CPC BILLING]
End-User clicks a Product on Extension Sidebar 
  ──► Request hits Portal Redirect Gateway: `GET https://portal.domain.com/r/{product_id}?ext_uid={user_id}`
  ──► Anti-Fraud Filter validates the click (Checks IP Rate Limit, Bot User-Agent, Duplicate Click Window)
  │     ├─► [INVALID / DUPLICATE CLICK]: Redirects user to Product URL immediately (Cost = 0 VND).
  │     └─► [VALID UNIQUE CLICK]: 
  │           1. Logs click event with `committed_cpc_at_click` snapshot.
  │           2. Atomically deducts CPC fee from Merchant's Prepaid Wallet.
  │           3. If `Wallet_Balance <= 0`, triggers an event to update JSON Feed (`Status = PAUSED_NO_BUDGET`).
  └─► Responds with `HTTP 302 Found` ──► Redirects User directly to the Merchant's Product Page.
```
