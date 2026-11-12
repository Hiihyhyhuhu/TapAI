import {
  Shop,
  Product,
  VerificationStatusResponse,
  ReportOverview,
  DailyReport,
  ProductPerformance,
  ReconciliationSummary,
  ReconciliationOrdersResponse
} from '../types';

const API_BASE_URL = typeof window !== 'undefined' && window.location.origin.startsWith('http')
  ? (window.location.port === '5173' || window.location.port === '3000'
      ? 'http://localhost:8000'
      : window.location.origin)
  : 'http://localhost:8000';

function getHeaders(isFormData: boolean = false): HeadersInit {
  const headers: Record<string, string> = {};
  if (!isFormData) {
    headers['Content-Type'] = 'application/json';
  }
  const token = localStorage.getItem('tapai_token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const config: RequestInit = {
    ...options,
    headers: {
      ...getHeaders(isFormData),
      ...(options.headers || {})
    }
  };

  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      let errorDetail = 'Lỗi phản hồi máy chủ';
      try {
        const errorJson = await response.json();
        errorDetail = errorJson.detail || errorJson.message || JSON.stringify(errorJson);
      } catch {
        errorDetail = `Lỗi HTTP ${response.status}: ${response.statusText}`;
      }
      throw new Error(errorDetail);
    }

    return response.json();
  } catch (err: any) {
    if (err.name === 'TypeError' && (err.message?.includes('fetch') || err.message?.includes('Failed') || err.message?.includes('NetworkError'))) {
      throw new Error('Không thể kết nối đến máy chủ backend (http://localhost:8000). Vui lòng kiểm tra backend.');
    }
    throw err;
  }
}

export const api = {
  // --- AUTHENTICATION ---
  auth: {
    register: (data: any) => request<any>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
    verifyEmail: (email: string, otp_code: string) => request<any>('/api/v1/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ email, otp_code })
    }),
    verifyPhone: (phone: string, otp_code: string) => request<any>('/api/v1/auth/verify-phone', {
      method: 'POST',
      body: JSON.stringify({ phone, otp_code })
    }),
    login: (email_or_phone: string, password: string) => request<any>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email_or_phone, password })
    }),
    getMe: () => request<Shop>('/api/v1/auth/me')
  },

  // --- SHOP MANAGEMENT ---
  shops: {
    getVerificationStatus: () => request<VerificationStatusResponse>('/api/v1/shops/verification/status'),
    submitVerification: (formData: FormData) => request<any>('/api/v1/shops/verification/submit', {
      method: 'POST',
      body: formData
    }),
    getProfile: () => request<Shop>('/api/v1/shops/profile'),
    updateProfile: (data: any) => request<Shop>('/api/v1/shops/profile', {
      method: 'PUT',
      body: JSON.stringify(data)
    }),
    getContract: () => request<any>('/api/v1/shops/contract'),
    verifyOwnership: () => request<any>('/api/v1/shops/ownership/verify', { method: 'POST' }),
    signContract: (otp_code: string) => request<any>('/api/v1/shops/contract/sign', {
      method: 'POST',
      body: JSON.stringify({ otp_code })
    }),
    getWallet: () => request<any>('/api/v1/shops/wallet'),
    depositWallet: (amount: number) => request<any>('/api/v1/shops/wallet/deposit', {
      method: 'POST',
      body: JSON.stringify({ amount })
    })
  },

  // --- AFFILIATE PRODUCTS ---
  products: {
    list: (params: { status?: string; search?: string; page?: number; limit?: number } = {}) => {
      const query = new URLSearchParams();
      if (params.status) query.set('status', params.status);
      if (params.search) query.set('search', params.search);
      if (params.page) query.set('page', params.page.toString());
      if (params.limit) query.set('limit', params.limit.toString());
      return request<{ total: number; page: number; limit: number; products: Product[] }>(
        `/api/v1/affiliate/products?${query.toString()}`
      );
    },
    create: (data: any) => request<Product>('/api/v1/affiliate/products', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
    get: (id: string) => request<Product>(`/api/v1/affiliate/products/${id}`),
    update: (id: string, data: any) => request<Product>(`/api/v1/affiliate/products/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    }),
    updateStatus: (id: string, status: 'active' | 'paused') =>
      request<Product>(`/api/v1/affiliate/products/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status })
      }),
    delete: (id: string) => request<any>(`/api/v1/affiliate/products/${id}`, {
      method: 'DELETE'
    }),
    importUrl: (product_url: string, cpc_bid: number = 2000, daily_budget: number = 100000) => request<any>('/api/v1/affiliate/products/import-url', {
      method: 'POST',
      body: JSON.stringify({ product_url, cpc_bid, daily_budget })
    }),
    sync: (id: string) => request<any>(`/api/v1/affiliate/products/${id}/sync`, {
      method: 'POST'
    }),
    updateBidding: (id: string, cpc_bid: number, daily_budget: number) =>
      request<any>(`/api/v1/affiliate/products/${id}/bidding`, {
        method: 'PATCH',
        body: JSON.stringify({ cpc_bid, daily_budget })
      }),
    getFeed: (download: boolean = false) =>
      request<any>(`/api/v1/affiliate/products/feed/merchant-products?download=${download}`),
    dispatchFeed: () => request<any>('/api/v1/affiliate/products/feed/dispatch', { method: 'POST' })
  },

  // --- STAGE 4: TRACKING & ANTI-FRAUD LEDGER ---
  tracking: {
    getCpcLedger: (limit: number = 50) => request<any>(`/api/v1/tracking/cpc-ledger?limit=${limit}`)
  },

  // --- RECONCILIATION & ORDERS (DOCS.MD) ---
  reconciliation: {
    getSummary: () => request<ReconciliationSummary>('/api/v1/reconciliation/summary'),
    getOrders: (params: { order_status?: string; search?: string; page?: number; limit?: number } = {}) => {
      const query = new URLSearchParams();
      if (params.order_status) query.set('order_status', params.order_status);
      if (params.search) query.set('search', params.search);
      if (params.page) query.set('page', params.page.toString());
      if (params.limit) query.set('limit', params.limit.toString());
      return request<ReconciliationOrdersResponse>(`/api/v1/reconciliation/orders?${query.toString()}`);
    }
  },

  // --- REPORTS & DASHBOARD ---
  reports: {
    getOverview: () => request<ReportOverview>('/api/v1/reports/overview'),
    getDaily: (days: number = 7) => request<DailyReport>(`/api/v1/reports/daily?days=${days}`),
    getProducts: () => request<{ total_products: number; products: ProductPerformance[] }>('/api/v1/reports/products')
  }
};

