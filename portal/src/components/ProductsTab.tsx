import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Product, Shop } from '../types';

interface ProductsTabProps {
  shop: Shop;
}

export const ProductsTab: React.FC<ProductsTabProps> = ({ shop }) => {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // 1-Click Import URL State (Zero Manual Rate Input)
  const [productUrlInput, setProductUrlInput] = useState('');

  useEffect(() => {
    fetchProducts();
  }, [shop.id]);

  const fetchProducts = async () => {
    setLoading(true);
    try {
      const res = await api.products.list({ limit: 50 });
      setProducts(res.products || []);
    } catch (err: any) {
      setError(err.message || 'Lỗi khi tải danh sách sản phẩm');
    } finally {
      setLoading(false);
    }
  };

  const handleImportProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!productUrlInput.trim()) return;
    setSubmitting(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const res = await api.products.importUrl(productUrlInput.trim());

      // Tự động tải xuống file JSON của sản phẩm vừa đồng bộ
      downloadProductJson({
        id: res.id,
        shop_id: res.shop_id,
        shop_name: shop.shop_name,
        name: res.title,
        category: 'Thời trang',
        product_url: res.original_url,
        platform: res.platform,
        image_urls: res.image_url ? [res.image_url] : [],
        thumbnail_url: res.image_url || '',
        price: res.current_price,
        currency: 'VND',
        status: res.sync_status === 'ACTIVE' || res.sync_status === 'ELIGIBLE' ? 'active' : 'paused',
        sync_status: res.sync_status,
        cpc_bid: res.cpc_bid,
        daily_budget: res.daily_budget,
        today_spent: res.today_spent,
        platform_base_rate: res.platform_base_rate,
        seller_extra_rate: res.seller_extra_rate,
        total_commission_rate: res.total_commission_rate,
        priority_score: res.priority_score,
        commission: {
          id: res.id,
          platform: res.platform,
          commission_type: 'percentage',
          platform_rate: res.platform_base_rate,
          extra_rate: res.seller_extra_rate,
          extra_fixed_amount: 0,
          total_rate: res.total_commission_rate,
          min_rate: 0
        },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      });

      setSuccessMsg(`Đã đồng bộ sản phẩm thành công! Hoa hồng sàn: ${res.total_commission_rate}% (Tự động xuất JSON product_${res.id}.json)`);
      setShowAddForm(false);
      setProductUrlInput('');
      fetchProducts();
    } catch (err: any) {
      setError(err.message || 'Lỗi khi quét hoa hồng sản phẩm từ sàn');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSyncNow = async (productId: string) => {
    try {
      const res = await api.products.sync(productId);
      setSuccessMsg(`Đã làm mới hoa hồng sàn cho sản phẩm! Mức mới: ${res.total_commission_rate}%`);
      fetchProducts();
    } catch (err: any) {
      setError(`Lỗi đồng bộ: ${err.message}`);
    }
  };

  const handleDelete = async (productId: string, productName: string) => {
    if (!confirm(`Xóa sản phẩm "${productName}" khỏi danh mục đối tác?`)) return;
    try {
      await api.products.delete(productId);
      setSuccessMsg('Đã xóa sản phẩm thành công!');
      fetchProducts();
    } catch (err: any) {
      setError(`Lỗi: ${err.message}`);
    }
  };

  const formatVND = (v: number) =>
    new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(v);

  const downloadProductJson = (p: Product) => {
    const totalRate = p.commission ? Number(p.commission.total_rate || (p.commission.platform_rate + p.commission.extra_rate)) : 0;
    const estCommission = p.commission?.commission_type === 'fixed_amount' && (p.commission.extra_fixed_amount || 0) > 0
      ? (p.commission.extra_fixed_amount || 0)
      : Math.round(p.price * (totalRate / 100));

    const exportData = {
      order_item_name: p.name,
      product_name: p.name,
      category: p.category,
      platform: p.platform,
      product_id: p.id,
      shop_id: p.shop_id,
      shop_name: p.shop_name || shop.shop_name,
      pricing: {
        price: p.price,
        currency: p.currency || 'VND',
        price_formatted: formatVND(p.price)
      },
      commission_rate: {
        commission_type: p.commission?.commission_type || 'percentage',
        total_rate_percent: totalRate,
        platform_rate_percent: p.commission?.platform_rate || 0,
        extra_rate_percent: p.commission?.extra_rate || 0,
        extra_fixed_amount: p.commission?.extra_fixed_amount || 0,
        estimated_commission_per_order: estCommission,
        estimated_commission_formatted: formatVND(estCommission)
      },
      product_url: p.product_url,
      thumbnail_url: p.thumbnail_url || (p.image_urls && p.image_urls[0]) || '',
      image_urls: p.image_urls || [],
      description: p.description || '',
      status: p.status,
      registered_at: p.created_at,
      export_metadata: {
        exported_at: new Date().toISOString(),
        generator: 'TAP AI Partner Engine',
        schema_version: '1.0.0',
        export_filename: `product_${p.id}.json`
      }
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `product_${p.id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const downloadAllProductsJson = () => {
    if (products.length === 0) {
      alert('Chưa có sản phẩm nào để xuất!');
      return;
    }
    const allData = products.map(p => {
      const totalRate = p.commission ? Number(p.commission.total_rate || (p.commission.platform_rate + p.commission.extra_rate)) : 0;
      const estCommission = p.commission?.commission_type === 'fixed_amount' && (p.commission.extra_fixed_amount || 0) > 0
        ? (p.commission.extra_fixed_amount || 0)
        : Math.round(p.price * (totalRate / 100));

      return {
        order_item_name: p.name,
        product_name: p.name,
        category: p.category,
        platform: p.platform,
        product_id: p.id,
        shop_id: p.shop_id,
        shop_name: p.shop_name || shop.shop_name,
        pricing: {
          price: p.price,
          currency: p.currency || 'VND',
          price_formatted: formatVND(p.price)
        },
        commission_rate: {
          commission_type: p.commission?.commission_type || 'percentage',
          total_rate_percent: totalRate,
          platform_rate_percent: p.commission?.platform_rate || 0,
          extra_rate_percent: p.commission?.extra_rate || 0,
          extra_fixed_amount: p.commission?.extra_fixed_amount || 0,
          estimated_commission_per_order: estCommission,
          estimated_commission_formatted: formatVND(estCommission)
        },
        product_url: p.product_url,
        thumbnail_url: p.thumbnail_url || (p.image_urls && p.image_urls[0]) || '',
        image_urls: p.image_urls || [],
        description: p.description || '',
        status: p.status,
        registered_at: p.created_at
      };
    });

    const blob = new Blob([JSON.stringify({ total: allData.length, exported_at: new Date().toISOString(), products: allData }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `products_all_${shop.id.slice(0, 8)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Top Action Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-surface border-hairline p-4 rounded-xl">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <span>Danh mục sản phẩm</span>
            <span className="font-mono text-xs text-slate-400">({products.length})</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Sản phẩm có hoa hồng ưu tiên sẽ được gắn nhãn [Đối tác chính hãng] và ưu tiên số 1 trên video
          </p>
        </div>

        <div className="flex items-center gap-2">
          {products.length > 0 && (
            <button
              onClick={downloadAllProductsJson}
              className="btn-subtle text-xs flex items-center gap-1.5"
              title="Xuất toàn bộ danh mục sản phẩm của shop thành file JSON"
            >
              <span>📥 Xuất tất cả JSON</span>
            </button>
          )}
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="btn-solid-primary text-xs flex items-center gap-1.5"
          >
            <span>{showAddForm ? 'Đóng form' : '+ Dán link sản phẩm (1-Click Import)'}</span>
          </button>
        </div>
      </div>

      {successMsg && (
        <div className="p-3 bg-panel border border-emerald-900/60 rounded-lg text-xs text-emerald-400 flex items-center justify-between">
          <span>✓ {successMsg}</span>
          <button onClick={() => setSuccessMsg(null)} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {error && (
        <div className="p-3 bg-panel border border-rose-900/60 rounded-lg text-xs text-rose-400 flex items-center justify-between">
          <span>⚠️ {error}</span>
          <button onClick={() => setError(null)} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {/* 1-CLICK IMPORT FORM (ZERO MANUAL RATE INPUT) */}
      {showAddForm && (
        <div className="bg-surface border border-emerald-900/50 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-hairline-b pb-3">
            <div>
              <h3 className="font-semibold text-xs text-white">1-Click Import — Đăng ký tự động qua Link Sàn TMĐT</h3>
              <p className="text-[11px] text-slate-400">Dán link sản phẩm Shopee/TikTok Shop, hệ thống tự bóc tách và kích hoạt hoa hồng.</p>
            </div>
            <span className="text-slate-400 font-mono text-[11px]">Sàn: {shop.platform.toUpperCase()}</span>
          </div>

          <form onSubmit={handleImportProduct} className="space-y-3">
            <div>
              <label className="block font-medium text-slate-300 mb-1.5 text-xs">Đường dẫn sản phẩm trên Sàn TMĐT (*)</label>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="url"
                  required
                  placeholder="VD: https://shopee.vn/product/123/456 hoặc https://vt.tiktok.com/..."
                  value={productUrlInput}
                  onChange={e => setProductUrlInput(e.target.value)}
                  className="input-field flex-1 text-xs font-mono"
                />
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-solid-primary text-xs whitespace-nowrap disabled:opacity-50"
                >
                  {submitting ? '⏳ Đang quét sàn...' : '⚡ Quét & Đăng ký ngay'}
                </button>
              </div>
            </div>

            <div className="p-3 bg-panel border border-border rounded-lg text-[11px] text-slate-400 space-y-1">
              <div className="text-slate-300 font-semibold flex items-center gap-1.5">
                <span className="text-emerald-400">✓</span> Cơ chế hoạt động tự động:
              </div>
              <div>• <strong>Shopee:</strong> Tổng hoa hồng = 3.5% Standard (Shopee chi trả) + Hoa hồng Xtra (Shop đang bật trên Kênh Người Bán Shopee).</div>
              <div>• <strong>TikTok Shop:</strong> Mức hoa hồng theo Open Plan / Targeted Plan mà Shop đang bật trên TikTok Seller Center.</div>
              <div className="italic text-slate-400">• Bạn không cần nhập % hoa hồng thủ công. Khi muốn tăng thứ hạng, hãy vào Kênh Người Bán chỉnh tăng % rồi bấm nút <strong>"Đồng bộ lại"</strong>.</div>
            </div>
          </form>
        </div>
      )}

      {/* Product Data Table */}
      <div className="bg-surface border-hairline rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-panel border-hairline-b text-slate-400 font-mono text-[11px]">
                <th className="py-2.5 px-4 font-medium w-16">Hình ảnh</th>
                <th className="py-2.5 px-4 font-medium">Tên sản phẩm</th>
                <th className="py-2.5 px-4 font-medium">Danh mục / Sàn</th>
                <th className="py-2.5 px-4 font-medium text-right">Giá niêm yết</th>
                <th className="py-2.5 px-4 font-medium text-center">Hoa hồng Sàn tự động</th>
                <th className="py-2.5 px-4 font-medium text-center">Trạng thái</th>
                <th className="py-2.5 px-4 font-medium text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {products.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    Chưa có sản phẩm nào. Hãy bấm <strong>"+ Dán link sản phẩm"</strong> để thêm sản phẩm đầu tiên!
                  </td>
                </tr>
              ) : products.map(p => {
                let img = 'https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=400&q=80';
                if (p.image_urls && p.image_urls.length > 0) {
                  img = p.image_urls[0];
                } else if (p.thumbnail_url) {
                  img = p.thumbnail_url;
                }
                const platRate = p.commission?.platform_rate || 3.5;
                const extraRate = p.commission?.extra_rate || 0;
                const totalRate = p.commission?.total_rate || (platRate + extraRate);
                const isNoComm = totalRate <= 0;

                const sellerCenterUrl = (p.platform || '').toLowerCase().includes('tiktok')
                  ? 'https://seller-vn.tiktok.com/'
                  : 'https://banhang.shopee.vn/';

                return (
                  <tr key={p.id} className="hover:bg-elevated/60 transition">
                    <td className="py-2.5 px-4">
                      <img src={img} alt={p.name} className="w-10 h-10 object-cover rounded bg-panel border border-border" />
                    </td>
                    <td className="py-2.5 px-4 font-medium text-slate-200 max-w-xs">
                      <a href={p.product_url} target="_blank" rel="noopener noreferrer" className="hover:text-emerald-400 transition line-clamp-1">
                        {p.name}
                      </a>
                    </td>
                    <td className="py-2.5 px-4 text-slate-400">
                      <div>{p.category}</div>
                      <span className="inline-block mt-0.5 px-1.5 py-0.2 rounded text-[10px] font-mono bg-panel border border-border text-slate-400 uppercase">
                        {p.platform || shop.platform}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-white font-semibold tabular">{formatVND(p.price)}</td>
                    <td className="py-2.5 px-4 text-center font-mono">
                      {isNoComm ? (
                        <div className="inline-flex flex-col items-center">
                          <span className="px-2 py-0.5 rounded bg-amber-950/80 text-amber-400 border border-amber-800/60 font-bold text-[11px]">
                            0.0% (Chưa bật)
                          </span>
                          <a href={sellerCenterUrl} target="_blank" rel="noopener noreferrer" className="text-[10px] text-teal-400 hover:underline mt-0.5">
                            ↗ Bật trên Kênh Người Bán
                          </a>
                        </div>
                      ) : (
                        <div className="inline-flex flex-col items-center">
                          <span className="px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 font-bold">
                            {totalRate.toFixed(1)}%
                          </span>
                          <span className="text-[10px] text-slate-400 mt-0.5">
                            ({platRate.toFixed(1)}% Sàn + {extraRate.toFixed(1)}% Shop)
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="py-2.5 px-4 text-center">
                      {isNoComm ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-mono text-amber-400">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                          Cần bật Sàn
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-mono text-emerald-400">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                          Hoạt động
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-4 text-right">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          onClick={() => handleSyncNow(p.id)}
                          className="btn-subtle py-1 px-2 text-[11px] text-teal-400 hover:text-teal-300"
                          title="Quét lại hoa hồng hiện hành trên Sàn TMĐT"
                        >
                          🔄 Đồng bộ
                        </button>
                        <button
                          onClick={() => downloadProductJson(p)}
                          className="btn-subtle py-1 px-2.5 text-[11px] text-emerald-400 hover:text-emerald-300"
                          title="Tải file JSON chi tiết của sản phẩm này"
                        >
                          📄 Xuất JSON
                        </button>
                        <button
                          onClick={() => handleDelete(p.id, p.name)}
                          className="btn-danger-ghost"
                        >
                          Xóa
                        </button>
                      </div>
                    </td>
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
