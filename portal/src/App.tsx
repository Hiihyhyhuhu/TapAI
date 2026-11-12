import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { DashboardTab } from './components/DashboardTab';
import { ProductsTab } from './components/ProductsTab';
import { ReconciliationTab } from './components/ReconciliationTab';
import { VerificationTab } from './components/VerificationTab';
import { AuthModal } from './components/AuthModal';
import { api } from './services/api';
import { Shop } from './types';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<'dashboard' | 'products' | 'reconciliation' | 'verification'>('dashboard');
  const [shop, setShop] = useState<Shop | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [authModalOpen, setAuthModalOpen] = useState<boolean>(false);
  const [authModalMode, setAuthModalMode] = useState<'login' | 'register'>('login');
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'info' | 'error' } | null>(null);

  // Direct login form state on landing
  const [directEmail, setDirectEmail] = useState('');
  const [directPwd, setDirectPwd] = useState('');
  const [directLoading, setDirectLoading] = useState(false);

  useEffect(() => {
    checkAuth();
  }, []);

  const showToast = (message: string, type: 'success' | 'info' | 'error' = 'info') => {
    setNotification({ message, type });
    setTimeout(() => {
      setNotification(null);
    }, 3500);
  };

  const checkAuth = async () => {
    const token = localStorage.getItem('tapai_token');
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const shopData = await api.auth.getMe();
      setShop(shopData);
    } catch {
      localStorage.removeItem('tapai_token');
      setShop(null);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('tapai_token');
    setShop(null);
    setCurrentTab('dashboard');
    showToast('Đã đăng xuất khỏi portal', 'info');
  };

  const handleDirectLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setDirectLoading(true);
    try {
      const res = await api.auth.login(directEmail, directPwd);
      localStorage.setItem('tapai_token', res.access_token);
      const me = await api.auth.getMe();
      setShop(me);
      showToast('Đăng nhập thành công', 'success');
    } catch (err: any) {
      showToast(err.message || 'Sai thông tin đăng nhập', 'error');
    } finally {
      setDirectLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col selection:bg-brand selection:text-panel bg-panel text-slate-100">
      
      {/* Toast Notification */}
      {notification && (
        <div className="fixed bottom-5 right-5 z-50 pointer-events-none" role="status">
          <div className={`pointer-events-auto border px-4 py-2.5 rounded-lg shadow-xl text-xs flex items-center gap-2.5 toast-anim bg-surface ${
            notification.type === 'success' ? 'border-emerald-600' :
            notification.type === 'error' ? 'border-rose-600' : 'border-border-light'
          }`}>
            <span className={`w-2 h-2 rounded-full ${
              notification.type === 'success' ? 'bg-emerald-500' :
              notification.type === 'error' ? 'bg-rose-500' : 'bg-blue-500'
            }`}></span>
            <span>{notification.message}</span>
          </div>
        </div>
      )}

      {/* Primary Header */}
      <Navbar
        currentTab={currentTab}
        setCurrentTab={(tab) => setCurrentTab(tab as any)}
        shop={shop}
        onOpenAuth={(mode = 'login') => {
          setAuthModalMode(mode);
          setAuthModalOpen(true);
        }}
        onLogout={handleLogout}
      />

      {/* Main Content Workspace */}
      <main className="flex-1 max-w-[1400px] w-full mx-auto px-4 sm:px-6 py-6" role="main">
        {loading ? (
          <div className="space-y-6">
            <div className="h-28 skeleton"></div>
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div className="h-24 skeleton"></div>
              <div className="h-24 skeleton"></div>
              <div className="h-24 skeleton"></div>
              <div className="h-24 skeleton"></div>
            </div>
            <div className="h-72 skeleton"></div>
          </div>
        ) : !shop ? (
          /* Split Unauthenticated Merchant Landing */
          <div className="py-8 md:py-14">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              
              {/* Left 7 cols: Real Merchant Product Mechanism */}
              <div className="lg:col-span-7 space-y-6">
                <div>
                  <div className="inline-flex items-center gap-2 text-xs font-mono text-emerald-400 mb-3 bg-brand-subtle px-2.5 py-1 rounded border border-emerald-900/40">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                    AFFILIATE MERCHANT PROGRAM
                  </div>
                  <h1 className="text-2xl sm:text-4xl font-extrabold text-white tracking-tight leading-[1.2]">
                    Biến người xem video thành khách mua hàng trực tiếp trên gian hàng chính hãng
                  </h1>
                  <p className="text-sm sm:text-base text-slate-400 mt-3 leading-relaxed max-w-2xl">
                    TAP AI sử dụng thị giác máy tính nhận diện sản phẩm trong từng khung hình video clip (TikTok, YouTube, Facebook), tạo mã affiliate và điều hướng khách hàng tới sản phẩm của bạn trên Shopee &amp; TikTok Shop.
                  </p>
                </div>

                {/* Live Simulation Card */}
                <div className="bg-surface border-hairline rounded-xl overflow-hidden p-5 space-y-4">
                  <div className="flex items-center justify-between text-xs text-slate-400 border-hairline-b pb-3">
                    <span className="font-semibold text-slate-200 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                      Mô phỏng trải nghiệm Shoppable Video
                    </span>
                    <span className="font-mono text-[11px] text-slate-400">Chrome Extension Active</span>
                  </div>

                  <div className="relative bg-panel rounded-lg border border-border p-4 flex flex-col sm:flex-row items-center gap-5">
                    <div className="relative w-40 h-40 bg-slate-900 rounded-md overflow-hidden flex-shrink-0 border border-border">
                      <img src="https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=400&q=80" alt="T-Shirt" className="w-full h-full object-cover" />
                      <div className="absolute inset-2 border-2 border-dashed border-emerald-400/90 rounded pointer-events-none flex items-start justify-end p-1">
                        <span className="bg-emerald-500 text-panel font-mono text-[9px] font-bold px-1 rounded">MATCH 98%</span>
                      </div>
                    </div>

                    <div className="space-y-2 text-xs flex-1">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px] font-mono font-semibold">
                          CHÍNH HÃNG [SHOPEE MALL]
                        </span>
                        <span className="text-slate-400 text-[11px]">Coolmate Official</span>
                      </div>
                      <h4 className="font-semibold text-white text-sm">Áo thun nam Cotton Compact Clean Vietnam</h4>
                      <div className="flex items-baseline gap-3">
                        <span className="text-base font-bold text-white font-mono">189.000 ₫</span>
                        <span className="text-emerald-400 font-mono text-xs">+7.5% Extra Commission</span>
                      </div>
                      <p className="text-slate-400 text-[11px] leading-relaxed">
                        Sản phẩm được đẩy lên Top 1 kết quả tìm kiếm khi khán giả nhấn "Mua trang phục này".
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 text-xs">
                    <div className="p-3 bg-panel rounded border border-border">
                      <div className="font-semibold text-slate-200 mb-1">01. Đối soát tự động</div>
                      <p className="text-slate-400 text-[11px]">Đồng bộ đơn hàng và lượt nhấp qua webhook sàn TMĐT.</p>
                    </div>
                    <div className="p-3 bg-panel rounded border border-border">
                      <div className="font-semibold text-slate-200 mb-1">02. Không phí duy trì</div>
                      <p className="text-slate-400 text-[11px]">Chỉ chi trả hoa hồng affiliate khi phát sinh đơn hàng thành công.</p>
                    </div>
                    <div className="p-3 bg-panel rounded border border-border">
                      <div className="font-semibold text-slate-200 mb-1">03. Ưu tiên thuật toán</div>
                      <p className="text-slate-400 text-[11px]">Tự điều chỉnh Extra Commission % để tối ưu vị trí hiển thị.</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right 5 cols: Direct Merchant Login */}
              <div className="lg:col-span-5 bg-surface border-hairline rounded-xl p-6 shadow-xl space-y-5">
                <div>
                  <h3 className="font-bold text-white text-base">Cổng kết nối Gian hàng</h3>
                  <p className="text-xs text-slate-400 mt-1">Đăng nhập tài khoản đối tác để quản lý sản phẩm &amp; hoa hồng</p>
                </div>

                <form onSubmit={handleDirectLogin} className="space-y-4 text-xs">
                  <div>
                    <label className="block font-medium text-slate-300 mb-1.5">Email hoặc Số điện thoại</label>
                    <input
                      type="text"
                      required
                      placeholder="merchant@brand.vn hoặc 0901234567"
                      value={directEmail}
                      onChange={e => setDirectEmail(e.target.value)}
                      className="input-field"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="font-medium text-slate-300">Mật khẩu</label>
                      <button
                        type="button"
                        onClick={() => showToast('Vui lòng liên hệ support@tapai.vn để cấp lại mật khẩu', 'info')}
                        className="text-[11px] text-slate-400 hover:text-slate-300"
                      >
                        Quên mật khẩu?
                      </button>
                    </div>
                    <input
                      type="password"
                      required
                      placeholder="••••••••"
                      value={directPwd}
                      onChange={e => setDirectPwd(e.target.value)}
                      className="input-field"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={directLoading}
                    className="btn-solid-primary w-full justify-center py-2.5 disabled:opacity-50"
                  >
                    {directLoading ? 'Đang xác thực...' : 'Đăng nhập Portal'}
                  </button>
                </form>

                <div className="pt-3 border-hairline-t flex items-center justify-between text-xs text-slate-400">
                  <span>Chưa có tài khoản gian hàng?</span>
                  <button
                    onClick={() => {
                      setAuthModalMode('register');
                      setAuthModalOpen(true);
                    }}
                    className="text-brand hover:underline font-semibold"
                  >
                    Đăng ký hợp tác ngay →
                  </button>
                </div>
              </div>

            </div>
          </div>
        ) : (
          /* Authenticated Dashboard View */
          <div>
            {currentTab === 'dashboard' && <DashboardTab shop={shop} />}
            {currentTab === 'products' && <ProductsTab shop={shop} />}
            {currentTab === 'reconciliation' && <ReconciliationTab shop={shop} />}
            {currentTab === 'verification' && (
              <VerificationTab shop={shop} onRefreshShop={checkAuth} />
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-hairline-t bg-surface/50 py-4 mt-auto">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500 font-mono">
          <div className="flex items-center gap-3">
            <span className="inline-block w-2 h-2 rounded-full bg-brand"></span>
            <span>TAP AI Video Ingestion Engine: Online</span>
          </div>
          <div className="flex items-center gap-5">
            <a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer" className="hover:text-slate-300 transition">
              Swagger API ↗
            </a>
            <span>Endpoint: localhost:8000</span>
          </div>
        </div>
      </footer>

      {/* Auth Modal */}
      <AuthModal
        isOpen={authModalOpen}
        initialMode={authModalMode}
        onClose={() => setAuthModalOpen(false)}
        onSuccess={() => {
          checkAuth();
          showToast('Đăng nhập thành công', 'success');
        }}
      />
    </div>
  );
};

export default App;
