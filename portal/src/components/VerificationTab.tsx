import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { VerificationStatusResponse, Shop } from '../types';

interface VerificationTabProps {
  shop: Shop;
  onRefreshShop: () => void;
}

export const VerificationTab: React.FC<VerificationTabProps> = ({ shop, onRefreshShop }) => {
  const [data, setData] = useState<VerificationStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Upload Form
  const [licenseFile, setLicenseFile] = useState<File | null>(null);
  const [screenshotFile, setScreenshotFile] = useState<File | null>(null);
  const [shopUrl, setShopUrl] = useState<string>(shop.shop_url || '');

  useEffect(() => {
    fetchStatus();
  }, [shop.id]);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const res = await api.shops.getVerificationStatus();
      setData(res);
    } catch (err: any) {
      setError(err.message || 'Không thể tải trạng thái xác minh');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!licenseFile || !screenshotFile) {
      alert('Vui lòng chọn đầy đủ cả file Giấy phép kinh doanh/CCCD và ảnh chụp Seller Dashboard');
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccessMsg(null);

    const formData = new FormData();
    formData.append('business_license', licenseFile);
    formData.append('shop_screenshot', screenshotFile);
    if (shopUrl) formData.append('shop_url', shopUrl);

    try {
      await api.shops.submitVerification(formData);
      setSuccessMsg('Nộp hồ sơ thành công! Quản trị viên TAP AI sẽ xét duyệt trong vòng 24h.');
      fetchStatus();
      onRefreshShop();
    } catch (err: any) {
      setError(err.message || 'Lỗi khi nộp hồ sơ xác minh');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="h-64 skeleton max-w-2xl mx-auto"></div>;
  }

  const isApproved = shop.status === 'verified';
  const isPending = shop.status === 'pending_review' || data?.has_pending_verification;

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="bg-surface border-hairline rounded-xl p-6 space-y-4">
        <div>
          <h2 className="text-base font-bold text-white">Xác minh định danh gian hàng</h2>
          <p className="text-xs text-slate-400 mt-1">
            Yêu cầu bắt buộc để chứng thực tư cách đối tác chính hãng, bảo vệ quyền lợi người mua và cấp huy hiệu tin cậy trên video.
          </p>
        </div>

        {successMsg && (
          <div className="p-3 bg-panel border border-emerald-900/60 rounded-lg text-xs text-emerald-400">
            ✓ {successMsg}
          </div>
        )}

        {error && (
          <div className="p-3 bg-panel border border-rose-900/60 rounded-lg text-xs text-rose-400">
            ⚠️ {error}
          </div>
        )}

        {/* Status Block */}
        <div className="p-4 rounded-lg bg-panel border border-border flex items-start gap-3 text-xs">
          <span className={`w-2.5 h-2.5 rounded-full mt-1 ${isApproved ? 'bg-emerald-400' : isPending ? 'bg-amber-400' : 'bg-slate-400'}`}></span>
          <div className="space-y-1">
            <div className="font-bold text-white">
              {isApproved ? 'Đã xác minh (Đối tác chính hãng)' : isPending ? 'Hồ sơ đang chờ phê duyệt' : 'Chưa nộp hồ sơ xác minh'}
            </div>
            <p className="text-slate-400 text-[11px] leading-relaxed">
              {isApproved
                ? 'Gian hàng của bạn được kích hoạt toàn bộ tính năng đẩy sản phẩm vào video AI.'
                : isPending
                ? 'Đội ngũ quản trị viên TAP AI đang đối soát giấy phép và thông tin gian hàng trong 24h.'
                : 'Vui lòng tải lên Giấy phép kinh doanh/CCCD và ảnh chụp màn hình Seller Center để hoàn tất xác minh.'}
            </p>
          </div>
        </div>

        {/* Form Upload nếu chưa duyệt */}
        {!isApproved && !isPending ? (
          <form onSubmit={handleSubmit} className="space-y-3.5 text-xs pt-2">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Đường dẫn gian hàng chính thức (*)</label>
              <input
                type="url"
                required
                value={shopUrl}
                onChange={e => setShopUrl(e.target.value)}
                className="input-field"
                placeholder="https://shopee.vn/coolmate.vn"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block font-medium text-slate-300 mb-1">Giấy phép kinh doanh hoặc CCCD (*)</label>
                <input
                  type="file"
                  required
                  accept=".pdf,.jpg,.jpeg,.png"
                  onChange={e => setLicenseFile(e.target.files ? e.target.files[0] : null)}
                  className="input-field text-slate-400 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-[11px] file:bg-elevated file:text-slate-300"
                />
              </div>
              <div>
                <label className="block font-medium text-slate-300 mb-1">Ảnh chụp Seller Dashboard (*)</label>
                <input
                  type="file"
                  required
                  accept=".jpg,.jpeg,.png"
                  onChange={e => setScreenshotFile(e.target.files ? e.target.files[0] : null)}
                  className="input-field text-slate-400 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-[11px] file:bg-elevated file:text-slate-300"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="btn-solid-primary w-full justify-center py-2.5 mt-2 disabled:opacity-50"
            >
              {submitting ? 'Đang gửi hồ sơ...' : 'Nộp hồ sơ xét duyệt'}
            </button>
          </form>
        ) : (
          <div className="p-3.5 bg-panel rounded border border-border text-xs font-mono space-y-1.5 text-slate-400">
            <div className="flex justify-between">
              <span>Đơn vị duyệt:</span> <span className="text-slate-200">{data?.verification?.reviewed_by || 'Admin System'}</span>
            </div>
            <div className="flex justify-between">
              <span>Ngày duyệt:</span>{' '}
              <span className="text-slate-200">
                {data?.verification?.reviewed_at ? data.verification.reviewed_at.slice(0, 10) : '2026-11-10'}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Huy hiệu hiển thị:</span> <span className="text-emerald-400 font-bold">[Đối tác chính hãng]</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
