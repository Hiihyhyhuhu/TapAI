export interface Shop {
  id: string;
  email: string;
  phone: string;
  shop_name: string;
  platform: 'shopee' | 'lazada' | 'tiki' | 'tiktok_shop' | string;
  shop_url: string;
  status: 'unverified' | 'pending_review' | 'verified' | 'suspended' | 'rejected';
  email_verified: boolean;
  phone_verified: boolean;
  ownership_token?: string;
  contract_status?: 'PENDING_SIGNATURE' | 'ACTIVE' | string;
  contract_signed_at?: string;
  contract_hash?: string;
  wallet_balance?: number;
  total_deposited?: number;
  total_cpc_spent?: number;
  created_at: string;
}

export interface Commission {
  id: string;
  platform: string;
  commission_type: 'percentage' | 'fixed_amount';
  platform_rate: number;
  extra_rate: number;
  extra_fixed_amount: number;
  total_rate: number;
  min_rate: number;
}

export interface Product {
  id: string;
  shop_id: string;
  shop_name: string;
  name: string;
  category: string;
  product_url: string;
  platform: string;
  image_urls: string[];
  thumbnail_url: string;
  description?: string;
  price: number;
  currency: string;
  status: 'active' | 'paused' | 'rejected' | 'deleted';
  commission?: Commission;
  platform_base_rate?: number;
  seller_extra_rate?: number;
  total_commission_rate?: number;
  cpc_bid?: number;
  daily_budget?: number;
  today_spent?: number;
  sync_status?: string;
  priority_score?: number;
  last_synced_at?: string;
  export_file_name?: string;
  export_download_url?: string;
  created_at: string;
  updated_at: string;
}

export interface Verification {
  id: string;
  shop_id: string;
  business_license_url: string;
  shop_screenshot_url: string;
  shop_url_submitted: string;
  status: 'pending' | 'approved' | 'rejected' | 'resubmit_required';
  admin_note?: string;
  reviewed_by?: string;
  submitted_at: string;
  reviewed_at?: string;
}

export interface VerificationStatusResponse {
  shop_id: string;
  shop_status: string;
  has_pending_verification: boolean;
  latest_verification?: Verification;
  history: Verification[];
}

export interface ReportOverview {
  shop_id: string;
  shop_name: string;
  total_products: number;
  total_clicks: number;
  total_conversions: number;
  total_order_value: number;
  total_commission_earned: number;
  pending_commission: number;
  confirmed_commission: number;
  conversion_rate_percent: number;
}

export interface DailyMetric {
  date: string;
  clicks: number;
  conversions: number;
  order_value: number;
  commission_earned: number;
}

export interface DailyReport {
  shop_id: string;
  start_date: string;
  end_date: string;
  daily_metrics: DailyMetric[];
}

export interface ProductPerformance {
  product_id: string;
  product_name: string;
  price: number;
  platform: string;
  clicks: number;
  conversions: number;
  order_value: number;
  commission_earned: number;
  conversion_rate_percent: number;
}

export interface OrderItem {
  id: string;
  platform: string;
  platform_order_id: string;
  platform_item_id: string;
  product_title: string;
  click_id?: string;
  order_gmv: number;
  base_commission_amount: number;
  extra_commission_amount: number;
  total_commission_amount: number;
  order_status: 'PENDING' | 'COMPLETED' | 'CANCELLED' | string;
  ordered_at: string;
  completed_at?: string;
}

export interface ReconciliationSummary {
  total_orders: number;
  total_gmv: number;
  pending_commission: number;
  completed_commission: number;
  cancelled_orders: number;
  payout_ready_amount: number;
  currency: string;
}

export interface ReconciliationOrdersResponse {
  total: number;
  page: number;
  limit: number;
  orders: OrderItem[];
}

