import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Shop } from '../types';

interface ReconciliationTabProps {
  shop: Shop;
}

interface OrderItem {
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

interface ReconciliationSummary {
  total_orders: number;
  total_gmv: number;
  pending_commission: number;
  completed_commission: number;
  cancelled_orders: number;
  payout_ready_amount: number;
  currency: string;
}

export const ReconciliationTab: React.FC<ReconciliationTabProps> = ({ shop }) => {
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [searchTerm, setSearchTerm] = useState<string>('');

  useEffect(() => {
    fetchData();
  }, [shop.id, filterStatus]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [sumRes, ordersRes] = await Promise.all([
        api.reconciliation.getSummary().catch(() => ({
          total_orders: 0,
          total_gmv: 0,
          pending_commission: 0,
          completed_commission: 0,
          cancelled_orders: 0,
          payout_ready_amount: 0,
          currency: 'VND'
        })),
        api.reconciliation.getOrders({
          order_status: filterStatus || undefined,
          search: searchTerm || undefined,
          limit: 50
        }).catch(() => ({ total: 0, orders: [] }))
      ]);
      setSummary(sumRes);
      setOrders(ordersRes.orders || []);
    } catch (err) {
      console.error('Lỗi tải dữ liệu đối soát:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatVND = (v: number) =>
    new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(v);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-surface border-hairline p-4 rounded-xl">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <span>Đối soát & Nhận tiền hoa hồng</span>
            <span className="font-mono text-xs text-emerald-400 bg-emerald-950/80 px-2.5 py-0.5 rounded border border-emerald-800/60">
              Auto-Attribution
            </span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Sàn TMĐT tự động trừ doanh thu đơn hàng và đối soát hoa hồng về ví đối tác minh bạch theo mã sub_id lượt click.
          </p>
        </div>

        <button
          onClick={fetchData}
          className="btn-subtle text-xs flex items-center gap-1.5 self-start sm:self-auto"
        >
          <span>🔄 Làm mới đối soát</span>
        </button>
      </div>

      {/* Financial KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-4">
          <div className="text-xs text-slate-400 font-medium">Tổng Đơn hàng Đối soát</div>
          <div className="text-2xl font-bold text-white font-mono mt-1 tabular">
            {summary?.total_orders || 0} <span className="text-xs text-slate-500 font-sans font-normal">đơn</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400">Khớp qua mã sub_id1</div>
        </div>

        <div className="card p-4">
          <div className="text-xs text-slate-400 font-medium">Doanh số GMV phát sinh</div>
          <div className="text-2xl font-bold text-white font-mono mt-1 tabular">
            {formatVND(summary?.total_gmv || 0)}
          </div>
          <div className="mt-2 text-[11px] text-slate-400">Giá trị đơn hàng tính hoa hồng</div>
        </div>

        <div className="card p-4 border-amber-900/40">
          <div className="text-xs text-amber-400 font-medium">Hoa hồng Chờ duyệt (Pending)</div>
          <div className="text-2xl font-bold text-amber-400 font-mono mt-1 tabular">
            {formatVND(summary?.pending_commission || 0)}
          </div>
          <div className="mt-2 text-[11px] text-slate-400">Đang giao / trong hạn đổi trả</div>
        </div>

        <div className="card p-4 border-emerald-800/60 bg-emerald-950/20">
          <div className="text-xs text-emerald-400 font-medium">Hoa hồng ĐÃ DUYỆT (Thực nhận)</div>
          <div className="text-2xl font-bold text-emerald-400 font-mono mt-1 tabular">
            {formatVND(summary?.completed_commission || 0)}
          </div>
          <div className="mt-2 text-[11px] text-emerald-500 font-medium">✓ Sẵn sàng chi trả về tài khoản</div>
        </div>
      </div>

      {/* Orders Filter Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between bg-panel p-3 rounded-lg border border-border text-xs">
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <span className="text-slate-400 font-medium">Trạng thái:</span>
          <select
            value={filterStatus}
            onChange={e => setFilterStatus(e.target.value)}
            className="input-field py-1 px-2.5 text-xs font-mono"
          >
            <option value="">Tất cả trạng thái</option>
            <option value="COMPLETED">COMPLETED (Đã duyệt tiền)</option>
            <option value="PENDING">PENDING (Chờ duyệt)</option>
            <option value="CANCELLED">CANCELLED (Hủy/Hoàn)</option>
          </select>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <input
            type="text"
            placeholder="Tìm theo mã đơn, item_id, click_id..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && fetchData()}
            className="input-field py-1 px-3 text-xs w-full sm:w-64"
          />
          <button onClick={fetchData} className="btn-solid-primary py-1 px-3 text-xs">
            Tìm
          </button>
        </div>
      </div>

      {/* Orders Table */}
      <div className="bg-surface border-hairline rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse font-mono text-[11px]">
            <thead>
              <tr className="bg-panel border-hairline-b text-slate-400 font-medium">
                <th className="py-2.5 px-4">Mã đơn hàng</th>
                <th className="py-2.5 px-4">Sàn</th>
                <th className="py-2.5 px-4 font-sans">Sản phẩm</th>
                <th className="py-2.5 px-4">Click ID (sub_id1)</th>
                <th className="py-2.5 px-4 text-right">GMV (Đơn)</th>
                <th className="py-2.5 px-4 text-right">Sàn trả (Base)</th>
                <th className="py-2.5 px-4 text-right">Shop trả (Extra)</th>
                <th className="py-2.5 px-4 text-right font-bold text-emerald-400">Tổng hoa hồng</th>
                <th className="py-2.5 px-4 text-center">Trạng thái</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500 font-sans">
                    {loading ? 'Đang tải dữ liệu đối soát...' : 'Chưa có đơn hàng nào khớp với điều kiện lọc.'}
                  </td>
                </tr>
              ) : orders.map(o => {
                let badge = (
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/80 text-amber-400 border border-amber-800/60">
                    ⏳ Đang duyệt
                  </span>
                );
                if (o.order_status === 'COMPLETED') {
                  badge = (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-800/60">
                      ✓ Đã chốt tiền
                    </span>
                  );
                } else if (o.order_status === 'CANCELLED') {
                  badge = (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950/80 text-rose-400 border border-rose-800/60">
                      ✕ Đã hủy
                    </span>
                  );
                }

                return (
                  <tr key={o.id} className="hover:bg-elevated/60 transition">
                    <td className="py-2.5 px-4 font-bold text-white">{o.platform_order_id}</td>
                    <td className="py-2.5 px-4">
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-panel border border-border text-slate-300">
                        {o.platform}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 font-sans text-slate-300 max-w-[200px] truncate">
                      {o.product_title}
                    </td>
                    <td className="py-2.5 px-4 text-slate-500 text-[10px]">
                      {o.click_id ? o.click_id.slice(0, 12) + '...' : 'Organic'}
                    </td>
                    <td className="py-2.5 px-4 text-right text-slate-200 tabular">{formatVND(o.order_gmv)}</td>
                    <td className="py-2.5 px-4 text-right text-slate-400 tabular">{formatVND(o.base_commission_amount)}</td>
                    <td className="py-2.5 px-4 text-right text-slate-400 tabular">{formatVND(o.extra_commission_amount)}</td>
                    <td className="py-2.5 px-4 text-right font-bold text-emerald-400 tabular">{formatVND(o.total_commission_amount)}</td>
                    <td className="py-2.5 px-4 text-center">{badge}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

