import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { ReportOverview, DailyReport, ProductPerformance, Shop } from '../types';
import { RefreshIcon } from './Icons';

interface DashboardTabProps {
  shop: Shop;
}

export const DashboardTab: React.FC<DashboardTabProps> = ({ shop }) => {
  const [overview, setOverview] = useState<ReportOverview | null>(null);
  const [daily, setDaily] = useState<DailyReport | null>(null);
  const [productStats, setProductStats] = useState<ProductPerformance[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDashboardData();
  }, [shop.id]);

  const fetchDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [overviewData, dailyData, productsData] = await Promise.all([
        api.reports.getOverview(),
        api.reports.getDaily(7),
        api.reports.getProducts()
      ]);
      setOverview(overviewData);
      setDaily(dailyData);
      setProductStats(productsData.products || []);
    } catch (err: any) {
      setError(err.message || 'Không thể tải dữ liệu báo cáo');
    } finally {
      setLoading(false);
    }
  };

  const formatVND = (v: number) =>
    new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(v);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-24 skeleton"></div>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div className="h-24 skeleton"></div>
          <div className="h-24 skeleton"></div>
          <div className="h-24 skeleton"></div>
          <div className="h-24 skeleton"></div>
        </div>
        <div className="h-72 skeleton"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-surface border-hairline rounded-xl text-center space-y-3">
        <p className="text-rose-400 text-xs font-mono">{error}</p>
        <button onClick={fetchDashboardData} className="btn-subtle text-xs">
          Thử tải lại
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      
      {/* Operational Control Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-surface border-hairline p-4 rounded-xl">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <span>Báo cáo hiệu quả kinh doanh</span>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-panel border border-border text-slate-400">
              Khoảng thời gian: 7 ngày qua
            </span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">Dữ liệu đối soát trực tiếp từ API sàn {shop.platform.toUpperCase()}</p>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={fetchDashboardData} className="btn-subtle text-xs">
            <RefreshIcon size={13} />
            <span>Làm mới</span>
          </button>
        </div>
      </div>

      {/* Financial GMV Strip & Metric Counters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* GMV Card */}
        <div className="bg-surface border-hairline p-5 rounded-xl">
          <div className="text-xs text-slate-400 font-medium">Doanh số tạo ra (GMV)</div>
          <div className="text-2xl font-bold text-white font-mono mt-1 tabular">
            {overview ? formatVND(overview.total_order_value) : '0 ₫'}
          </div>
          <div className="mt-2 text-[11px] text-emerald-400 flex items-center gap-1">
            <span>↑ Tăng trưởng tích cực</span>
            <span className="text-slate-500">·</span>
            <span className="text-slate-400">{overview?.total_conversions || 0} đơn hoàn tất</span>
          </div>
        </div>

        {/* Lượt Clicks */}
        <div className="bg-surface border-hairline p-5 rounded-xl">
          <div className="text-xs text-slate-400 font-medium">Lượt nhấp từ video (Clicks)</div>
          <div className="text-2xl font-bold text-white font-mono mt-1 tabular">
            {overview?.total_clicks ? overview.total_clicks.toLocaleString('vi-VN') : 0}
          </div>
          <div className="mt-2 text-[11px] text-slate-400">
            Tỷ lệ CVR: <span className="font-mono text-white font-semibold">{(overview?.conversion_rate_percent || 0).toFixed(2)}%</span>
          </div>
        </div>

        {/* Hoa hồng phát sinh */}
        <div className="bg-surface border-hairline p-5 rounded-xl">
          <div className="text-xs text-slate-400 font-medium">Tổng hoa hồng chi trả</div>
          <div className="text-2xl font-bold text-emerald-400 font-mono mt-1 tabular">
            {overview?.total_commission_earned ? formatVND(overview.total_commission_earned) : '0 ₫'}
          </div>
          <div className="mt-2 text-[11px] text-slate-400">
            Đối soát định kỳ tự động 24/7
          </div>
        </div>

        {/* Số sản phẩm đang đẩy */}
        <div className="bg-surface border-hairline p-5 rounded-xl">
          <div className="text-xs text-slate-400 font-medium">Sản phẩm kích hoạt</div>
          <div className="text-2xl font-bold text-white font-mono mt-1 tabular">
            {overview?.total_products || productStats.length}
          </div>
          <div className="mt-2 text-[11px] text-slate-400">
            Gắn nhãn [Đối tác chính hãng]
          </div>
        </div>

      </div>

      {/* Top Products Data Table */}
      <div className="bg-surface border-hairline rounded-xl overflow-hidden">
        <div className="px-5 py-3.5 border-hairline-b flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-white text-xs uppercase tracking-wider font-mono">
              Bảng hiệu quả sản phẩm (Top Products)
            </h3>
            <p className="text-[11px] text-slate-400">Hiệu quả phân phối trực tiếp từ AI Vision Model</p>
          </div>
          <span className="text-xs font-mono text-slate-400 bg-panel px-2.5 py-1 rounded border border-border">
            {productStats.length} mục
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-panel border-hairline-b text-slate-400 font-mono text-[11px]">
                <th className="py-2.5 px-4 font-medium">Sản phẩm</th>
                <th className="py-2.5 px-4 font-medium text-right">Lượt Clicks</th>
                <th className="py-2.5 px-4 font-medium text-right">Đơn hàng</th>
                <th className="py-2.5 px-4 font-medium text-right">Tỷ lệ CVR</th>
                <th className="py-2.5 px-4 font-medium text-right">Doanh số (GMV)</th>
                <th className="py-2.5 px-4 font-medium text-right text-emerald-400">Hoa hồng</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {productStats.map(p => (
                <tr key={p.product_id} className="hover:bg-elevated/60 transition">
                  <td className="py-3 px-4 font-medium text-slate-200">{p.product_name}</td>
                  <td className="py-3 px-4 text-right font-mono text-slate-300 tabular">{p.clicks}</td>
                  <td className="py-3 px-4 text-right font-mono font-semibold text-emerald-400 tabular">{p.conversions}</td>
                  <td className="py-3 px-4 text-right font-mono text-slate-400 tabular">{p.conversion_rate_percent}%</td>
                  <td className="py-3 px-4 text-right font-mono font-bold text-white tabular">{formatVND(p.order_value)}</td>
                  <td className="py-3 px-4 text-right font-mono font-semibold text-emerald-400 tabular">{formatVND(p.commission_earned)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
};
