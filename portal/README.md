# TAP AI — Direct Merchant Portal (CPC & JSON Feed Model)

> **Self-Service Partner Portal for E-Commerce Merchants & Brands in the TAP AI Interactive Shoppable Media Ecosystem.**

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/Frontend-React_19_%7C_Tailwind_CSS-blue.svg)](https://react.dev/)
[![Monetization](https://img.shields.io/badge/Monetization-Direct_CPC_%26_Escrow_Wallet-emerald.svg)](#-the-4-stage-merchant-system-workflow)
[![Specification](https://img.shields.io/badge/Standards-DOCS.md_Compliant-green.svg)](../DOCS.md)

---

## 📑 Table of Contents
1. [Overview](#-overview)
2. [System Architecture Flow](#-system-architecture-flow)
3. [The 4-Stage Merchant System Workflow](#-the-4-stage-merchant-system-workflow)
   - [Stage 1: Merchant Onboarding, Ownership Verification & E-Contracting](#stage-1-merchant-onboarding-ownership-verification--e-contracting)
   - [Stage 2: Product Registration, CPC Bidding & Prepaid Escrow Wallet](#stage-2-product-registration-cpc-bidding--prepaid-escrow-wallet)
   - [Stage 3: Standardized JSON Data Feed Export for Core Backend](#stage-3-standardized-json-data-feed-export-for-core-backend)
   - [Stage 4: Redirect Gateway, 3-Tier Anti-Fraud Filter & Real-Time Billing](#stage-4-redirect-gateway-3-tier-anti-fraud-filter--real-time-billing)
4. [Directory Structure (`portal/`)](#-directory-structure-portal)
5. [Key API Endpoints](#-key-api-endpoints)
6. [Setup & Execution Guide](#-setup--execution-guide)
7. [Automated E2E Testing](#-automated-e2e-testing)

---

## 🌟 Overview

The **TAP AI Merchant Portal** establishes a direct bridge between **E-Commerce Merchants / Brands** and TAP AI's **Interactive Shoppable Media Engine**.

Rather than relying solely on third-party affiliate networks with high latency and fixed low commission rates, TAP AI introduces a high-performance **Direct CPC Bidding & Prepaid Escrow Wallet** infrastructure:
- **Direct Merchant Control:** Brands set customized Cost-Per-Click (CPC) bids for each inventory item.
- **Automated Media Injection:** Verified products are dynamically mapped to segmented visual objects in user videos and images.
- **Transparent Prepaid Escrow:** Real-time atomic balance deductions only for valid high-intent clicks.
- **Enterprise Anti-Fraud Protection:** Proprietary 3-tier click filtering safeguards merchant advertising budgets against web crawlers, duplicate spam, and bot traffic.

---

## 🔄 System Architecture Flow

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                             TAP AI MERCHANT PORTAL ECOSYSTEM                                │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

 [MERCHANT / SELLER]
        │
        ├── 1. Sign up & receive Bio Verification Token (e.g., VERIFY-FCAJ)
        ├── 2. E-Sign Digital CPC Agreement (OTP verification + SHA-256 hash logging)
        ├── 3. Deposit funds into Prepaid Escrow Wallet
        └── 4. Register products & configure CPC Bids (≥ 2,000 VND / click)
                    │
                    ▼
 [FASTAPI BACKEND & DATABASE]
        │
        ├── Manages contract lifecycle (`ACTIVE`)
        ├── Guarantees escrow balance safety & atomic updates
        └── Automatically triggers product eligibility (`ELIGIBLE`)
                    │
                    ▼
 [SERIALIZER JOB (FEED EXPORT)] ────────► [merchant_products_feed.json]
                                                        │
                                                        ▼
                                         [CORE AI & RANKING BACKEND]
                                         (Boosts merchant items in
                                          Visual Search & Shoppable Media)
                                                        │
                                                        ▼
 [END-USER / VIEWER] ◄───────────────── [CHROME EXTENSION SIDEBAR]
 (Browses video content)                 (Renders interactive product card)
        │
        ▼ (Clicks "Buy Now")
 [PORTAL REDIRECT GATEWAY: GET /r/{product_id}?ext_uid={user_id}]
        │
        ├──► 3-TIER ANTI-FRAUD FILTER:
        │     • Tier 1: Bot / Web Crawler Detection (User-Agent analysis)
        │     • Tier 2: 30-Second Duplicate Click Window
        │     • Tier 3: IP Rate Limiting & frequency monitoring
        │
        ├──► [Invalid / Duplicate Click]: Cost = 0 VND ──► Immediate 302 Redirect
        └──► [Valid Unique Click]: Atomic Wallet Deduction (CPC) ──► Log to Click Ledger
                    │
                    ▼ (HTTP 302 Found)
 [DESTINATION E-COMMERCE PRODUCT PAGE (SHOPEE / TIKTOK SHOP / LAZADA)]
```

---

## 🚀 The 4-Stage Merchant System Workflow

The entire lifecycle strictly follows the architectural specifications defined in [DOCS.md](../DOCS.md):

### Stage 1: Merchant Onboarding, Ownership Verification & E-Contracting
1. **Self-Service Registration:** The merchant accesses the portal, enters their business credentials, email, password, and primary storefront URL (Shopee, TikTok Shop, or Lazada).
2. **Storefront Ownership Verification:**
   - The system generates a cryptographically unique verification token: `VERIFY-XXXX` (e.g., `VERIFY-FCAJ`).
   - The merchant places this token into their official Shop Bio or website meta tag.
   - The verification engine confirms store ownership to prevent fraudulent claims before authorizing distribution.
3. **Digital CPC Agreement Generation:**
   - The platform creates a standardized legal agreement specifying the baseline CPC rate (minimum 2,000 VND), escrow balance maintenance rules, and click fraud policies.
4. **Non-Repudiation E-Signature:**
   - The merchant verifies and signs the agreement using a secure one-time password (OTP) sent to their registered contact.
   - The system computes and logs an immutable SHA-256 cryptographic hash containing the contract body, timestamp, and party identities.
   - The contract transitions to **`ACTIVE`**, unlocking product registration and bidding campaigns.

---

### Stage 2: Product Registration, CPC Bidding & Prepaid Escrow Wallet
1. **Product Ingestion:** Supports single-item manual creation, bulk upload (CSV/JSON), and automated OpenGraph metadata scraping from product URLs.
2. **CPC Bidding & Budget Caps:**
   - Merchants set their committed Cost-Per-Click: `cpc_bid` (minimum 2,000 VND/click).
   - Optional `daily_budget` limits prevent rapid budget exhaustion during unexpected viral traffic spikes.
3. **Prepaid Escrow Wallet Funding:**
   - Merchants maintain an active prepaid balance via bank transfer or automated top-up.
4. **Automated Eligibility Transition:**
   - When the contract is `ACTIVE` and the wallet balance $\ge$ minimum CPC, product status automatically transitions to **`ELIGIBLE`** (ready for feed serialization).
   - If the escrow balance drops to 0 VND, product status automatically shifts to safe **`PAUSED_NO_BUDGET`** to prevent overdrafts.

---

### Stage 3: Standardized JSON Data Feed Export for Core Backend
1. **Periodic & On-Demand Serializer Jobs:**
   - The backend queries all products satisfying strict validation criteria:
     $$\text{Contract} = \text{ACTIVE} \quad\land\quad \text{Wallet\_Balance} \ge \text{Min\_CPC} \quad\land\quad \text{Product\_Status} = \text{ELIGIBLE}$$
2. **Standardized Feed Packaging (`merchant_products_feed.json`):**
   - Each payload record encapsulates: `product_id`, `shop_id`, `shop_name`, `title`, `price`, `affiliate_url`, `cpc_bid`, `status`, `contract_status`, and `updated_at`.
3. **Dispatch to Core AI Ranking Engine:**
   - The standardized feed is transmitted to TAP AI's Core Search & Ranking Pipeline, boosting merchant products to top priority within the visual detection overlays and extension side panel.

---

### Stage 4: Redirect Gateway, 3-Tier Anti-Fraud Filter & Real-Time Billing
1. **Extension Inbound Traffic:**
   - When a video viewer clicks a pinned product card on the Chrome Extension sidebar, the request hits the dedicated gateway:
     ```http
     GET https://portal.domain.com/r/{product_id}?ext_uid={user_id}
     ```
2. **Proprietary 3-Tier Anti-Fraud Validation:**
   - **Tier 1 (Bot Detection):** Inspects incoming `User-Agent` headers to block automated crawlers, spiders, and scrapers (only genuine browser clients pass).
   - **Tier 2 (Duplicate Click Window):** Imposes a 30-second deduplication window for identical user IDs (`ext_uid`) or IP addresses on the same item.
   - **Tier 3 (IP Rate Limiting):** Restricts burst click frequencies from single IP subnets to prevent click bombing attacks.
3. **Transparent Real-Time Billing:**
   - **Fraudulent / Duplicate Clicks:** Flagged as `FRAUD`, billed at **0 VND**, and immediately redirected to prevent disruption to end-user shopping.
   - **Valid Unique Clicks:** 
     - Recorded as `VALID` in the Click Ledger with a frozen `committed_cpc_at_click` snapshot.
     - Atomically deducted from the merchant's prepaid escrow balance.
4. **Shopper Redirection:** The server responds with `HTTP 302 Found`, routing the user directly to the product checkout page on the host marketplace.

---

## 📁 Directory Structure (`portal/`)

```text
TapAI/portal/
├── index.html                   # Entrypoint HTML for Vite React App
├── index.standalone.html        # Complete standalone Single-Page Application (Zero-dependency, runs directly in any browser)
├── package.json                 # Project configuration (React 19, Vite, Tailwind CSS, TypeScript)
├── vite.config.ts               # API reverse proxy configuration forwarding `/api/v1` to backend localhost:8000
├── tailwind.config.js           # E-Commerce Dark Theme palette & typography configurations
├── tsconfig.json                # TypeScript compiler settings
├── src/
│   ├── main.tsx                 # React DOM root mounting point
│   ├── App.tsx                  # Root state controller (Shop context, Auth, Tab Switcher, Demo login)
│   ├── index.css                # Global Tailwind directives & font imports
│   ├── types/
│   │   └── index.ts             # TypeScript definitions (Shop, Product, Feed, ClickLedger, Verification)
│   ├── services/
│   │   └── api.ts               # Type-safe API Client connecting to 29 FastAPI endpoints
│   └── components/
│       ├── Navbar.tsx           # Global navigation bar (Contract badge, Wallet balance, Auth buttons)
│       ├── DashboardTab.tsx     # KPI statistics, 7-day click/revenue charts, top products breakdown
│       ├── ProductsTab.tsx      # Inventory management, CPC bidding controls, JSON feed import & status filters
│       ├── VerificationTab.tsx  # Bio Token verification & OTP E-Signature interface
│       ├── ReconciliationTab.tsx# Real-time Click Ledger audit table & Escrow wallet deposit history
│       └── AuthModal.tsx        # Merchant registration, sign-in, and password reset modal
```

---

## 🌐 Key API Endpoints

All endpoints are secured via industry-standard Bearer JWT Authentication:

| Lifecycle Stage | HTTP Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **Auth** | `POST` | `/api/v1/auth/register` | Register a new merchant storefront account |
| **Auth** | `POST` | `/api/v1/auth/login` | Authenticate merchant and issue JWT tokens |
| **Stage 1** | `GET` | `/api/v1/shops/contract` | Retrieve Digital CPC Agreement terms and status |
| **Stage 1** | `POST` | `/api/v1/shops/ownership/verify` | Verify storefront ownership via Bio Token (`VERIFY-XXXX`) |
| **Stage 1** | `POST` | `/api/v1/shops/contract/sign` | Sign agreement via OTP and record SHA-256 hash |
| **Stage 2** | `GET` | `/api/v1/shops/wallet` | Query Prepaid Escrow Wallet balance and spend metrics |
| **Stage 2** | `POST` | `/api/v1/shops/wallet/deposit` | Deposit funds into Prepaid Escrow Wallet |
| **Stage 2** | `POST` | `/api/v1/products` | Register product and establish initial CPC bid |
| **Stage 2** | `PUT` | `/api/v1/products/{id}/bidding` | Update item `cpc_bid` and `daily_budget` |
| **Stage 3** | `GET` | `/api/v1/products/feed/export` | Download serialized `merchant_products_feed.json` |
| **Stage 3** | `POST` | `/api/v1/products/feed/dispatch` | Trigger Serializer Job to push feed to Core Backend |
| **Stage 4** | `GET` | `/r/{product_id}` | Dedicated Redirect Gateway with 3-tier Anti-Fraud |
| **Stage 4** | `GET` | `/api/v1/tracking/ledger` | Query immutable real-time Click Ledger records |
| **Report** | `GET` | `/api/v1/reports/daily` | Fetch time-series analytical reports (Clicks & CPC Spend) |

---

## 💻 Setup & Execution Guide

### Option 1: Standalone Web Interface (Quickstart - No Node.js Required)
`index.standalone.html` bundles the complete UI, Tailwind CSS styling, Chart.js telemetry, and REST API connectivity out-of-the-box.

1. **Start the FastAPI Unified Backend:**
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
   ```
   *The backend serves both REST APIs and the static portal application.*

2. **Access the Merchant Portal:**
   Open your web browser and navigate directly to:
   ```text
   http://localhost:8000/portal/index.standalone.html
   ```

3. **Pre-configured Demo Credentials:**
   - **Email:** `demo@tapai.vn`
   - **Password:** `123456`
   - **Contract Signing OTP:** `123456`
   - *Preloaded with a 2,000,000 VND escrow wallet balance for instant testing.*

---

### Option 2: Development with Node.js & Vite Dev Server
For developers looking to customize or build upon the modular React components:

```bash
cd portal
npm install
npm run dev
```
Access the hot-reloading development server at: `http://localhost:5173`

---

## 🧪 Automated E2E Testing

The repository includes a comprehensive integration test suite to validate all 4 stages of the CPC & Escrow workflow against live backend endpoints:

```bash
python backend/scripts/test_portal_cpc_workflow.py
```

**Standard Validation Output:**
- ✅ **Stage 1:** Storefront ownership verified, legal agreement generated, and signed with SHA-256 hash.
- ✅ **Stage 2:** Escrow wallet funded, product registered, CPC bid adjusted, and auto-activation confirmed.
- ✅ **Stage 3:** Standardized `merchant_products_feed.json` serialized and dispatched to Core AI.
- ✅ **Stage 4:** Redirect Gateway tested: valid click deducted exactly `cpc_bid`, while bot and duplicate clicks $(<30s)$ were safely intercepted at 0 VND and audited in the Click Ledger.
