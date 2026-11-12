import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  initialMode?: 'login' | 'register';
}

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  initialMode = 'login'
}) => {
  const [mode, setMode] = useState<'login' | 'register' | 'otp'>(initialMode);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form Fields
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [shopName, setShopName] = useState('');
  const [platform, setPlatform] = useState('shopee');
  const [shopUrl, setShopUrl] = useState('');

  // OTP Fields
  const [otpCode, setOtpCode] = useState('');

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode, isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.auth.login(email, password);
      localStorage.setItem('tapai_token', res.access_token);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Email hoặc mật khẩu không chính xác');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.auth.register({
        email,
        phone,
        password,
        shop_name: shopName,
        platform,
        shop_url: shopUrl
      });
      if (res?.data?.dev_otp) {
        setOtpCode(res.data.dev_otp);
      }
      setMode('otp');
    } catch (err: any) {
      setError(err.message || 'Đăng ký thất bại');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.auth.verifyEmail(email, otpCode);
      const res = await api.auth.login(email, password);
      localStorage.setItem('tapai_token', res.access_token);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Mã OTP không đúng hoặc đã hết hạn');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-[2px]" role="dialog">
      <div className="bg-surface border-hairline rounded-xl max-w-[420px] w-full p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white w-7 h-7 flex items-center justify-center rounded-md hover:bg-elevated transition"
          aria-label="Đóng"
        >
          ✕
        </button>

        {/* Tab Switcher */}
        {mode !== 'otp' && (
          <div className="flex gap-2 p-1 bg-panel rounded-lg mb-5 border border-border">
            <button
              type="button"
              onClick={() => {
                setMode('login');
                setError(null);
              }}
              className={`flex-1 py-1.5 rounded text-xs transition ${
                mode === 'login'
                  ? 'font-semibold bg-elevated text-white border border-border'
                  : 'font-medium text-slate-400 hover:text-white'
              }`}
            >
              Đăng nhập
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('register');
                setError(null);
              }}
              className={`flex-1 py-1.5 rounded text-xs transition ${
                mode === 'register'
                  ? 'font-semibold bg-elevated text-white border border-border'
                  : 'font-medium text-slate-400 hover:text-white'
              }`}
            >
              Tạo tài khoản gian hàng
            </button>
          </div>
        )}

        {error && (
          <div className="p-3 bg-panel border border-rose-900/60 rounded-lg text-xs text-rose-400 mb-4">
            ⚠️ {error}
          </div>
        )}

        {/* LOGIN FORM */}
        {mode === 'login' && (
          <form onSubmit={handleLogin} className="space-y-4 text-xs">
            <div>
              <label className="block font-medium text-slate-300 mb-1.5">Email hoặc Số điện thoại</label>
              <input
                type="text"
                required
                placeholder="contact@brand.vn hoặc 0988..."
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="input-field"
                autoComplete="username"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-300 mb-1.5">Mật khẩu</label>
              <input
                type="password"
                required
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="input-field"
                autoComplete="current-password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-solid-primary w-full justify-center py-2.5 mt-2 disabled:opacity-50"
            >
              {loading ? 'Đang xác thực...' : 'Đăng nhập vào Portal'}
            </button>
          </form>
        )}

        {/* REGISTER FORM */}
        {mode === 'register' && (
          <form onSubmit={handleRegister} className="space-y-3 text-xs">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Tên thương hiệu / Gian hàng (*)</label>
              <input
                type="text"
                required
                placeholder="VD: Coolmate Vietnam"
                value={shopName}
                onChange={e => setShopName(e.target.value)}
                className="input-field"
              />
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="block font-medium text-slate-300 mb-1">Nền tảng TMĐT</label>
                <select
                  value={platform}
                  onChange={e => setPlatform(e.target.value)}
                  className="input-field"
                >
                  <option value="shopee">Shopee</option>
                  <option value="tiktok_shop">TikTok Shop</option>
                  <option value="lazada">Lazada</option>
                  <option value="tiki">Tiki</option>
                </select>
              </div>
              <div>
                <label className="block font-medium text-slate-300 mb-1">Số điện thoại</label>
                <input
                  type="tel"
                  required
                  placeholder="0988112233"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  className="input-field"
                  autoComplete="tel"
                />
              </div>
            </div>

            <div>
              <label className="block font-medium text-slate-300 mb-1">Email doanh nghiệp</label>
              <input
                type="email"
                required
                placeholder="contact@brand.vn"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="input-field"
                autoComplete="email"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-300 mb-1">Link gian hàng</label>
              <input
                type="url"
                required
                placeholder="https://shopee.vn/coolmate.vn"
                value={shopUrl}
                onChange={e => setShopUrl(e.target.value)}
                className="input-field"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-300 mb-1">Mật khẩu (≥ 8 ký tự)</label>
              <input
                type="password"
                required
                minLength={8}
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="input-field"
                autoComplete="new-password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-solid-primary w-full justify-center py-2.5 mt-2 disabled:opacity-50"
            >
              {loading ? 'Đang gửi...' : 'Gửi mã OTP xác thực'}
            </button>
          </form>
        )}

        {/* OTP FORM */}
        {mode === 'otp' && (
          <form onSubmit={handleVerifyOtp} className="space-y-4 text-xs">
            <p className="text-slate-300 text-center">
              Nhập mã OTP 6 chữ số vừa gửi đến <span className="text-white font-mono">{email}</span>
            </p>

            <input
              type="text"
              required
              maxLength={6}
              placeholder="000000"
              value={otpCode}
              onChange={e => setOtpCode(e.target.value)}
              className="input-field text-center font-mono text-xl tracking-[0.5em] font-bold py-2.5"
              inputMode="numeric"
              pattern="[0-9]*"
              autoComplete="one-time-code"
              autoFocus
            />

            <button
              type="submit"
              disabled={loading}
              className="btn-solid-primary w-full justify-center py-2.5 disabled:opacity-50"
            >
              {loading ? 'Đang kiểm tra...' : 'Xác thực & Vào Bảng điều khiển'}
            </button>

            <div className="text-center pt-2">
              <button
                type="button"
                onClick={() => setMode('login')}
                className="btn-ghost text-xs"
              >
                ← Quay lại đăng nhập
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
