import React from 'react';
import { Shop } from '../types';
import { ZapIcon } from './Icons';

interface NavbarProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  shop: Shop | null;
  onOpenAuth: (mode?: 'login' | 'register') => void;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  setCurrentTab,
  shop,
  onOpenAuth,
  onLogout
}) => {
  return (
    <header className="bg-surface border-hairline-b sticky top-0 z-30">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        
        {/* Left: Brand & Context */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded bg-brand flex items-center justify-center font-bold text-panel text-xs">
              <ZapIcon size={15} />
            </div>
            <span className="font-bold text-[14px] text-white tracking-tight">TAP AI</span>
            <span className="text-[11px] font-mono font-medium px-1.5 py-0.5 rounded bg-subtle text-slate-300">MERCHANT</span>
          </div>

          {/* Breadcrumb Context */}
          {shop && (
            <div className="hidden md:flex items-center gap-2 text-xs border-l border-border pl-4 text-slate-400">
              <span className="font-semibold text-white">{shop.shop_name}</span>
              <span>·</span>
              <span className="uppercase font-mono text-[11px]">{shop.platform}</span>
              <span>·</span>
              <span className={`font-mono text-[11px] ${shop.status === 'verified' ? 'text-emerald-400' : 'text-amber-400'}`}>
                {shop.status === 'verified' ? '● Đã xác minh' : '○ Chờ duyệt'}
              </span>
            </div>
          )}
        </div>

        {/* Center: Navigation Tabs */}
        {shop && (
          <nav className="hidden md:flex items-center gap-1 bg-panel p-1 rounded-lg border border-border" role="tablist">
            <button
              onClick={() => setCurrentTab('dashboard')}
              role="tab"
              aria-selected={currentTab === 'dashboard'}
              className={`px-3.5 py-1.5 rounded-md text-xs transition ${
                currentTab === 'dashboard'
                  ? 'font-semibold text-brand bg-elevated border border-border'
                  : 'font-medium text-slate-400 hover:text-white'
              }`}
            >
              Tổng quan
            </button>
            <button
              onClick={() => setCurrentTab('products')}
              role="tab"
              aria-selected={currentTab === 'products'}
              className={`px-3.5 py-1.5 rounded-md text-xs transition ${
                currentTab === 'products'
                  ? 'font-semibold text-brand bg-elevated border border-border'
                  : 'font-medium text-slate-400 hover:text-white'
              }`}
            >
              Sản phẩm
            </button>
            <button
              onClick={() => setCurrentTab('reconciliation')}
              role="tab"
              aria-selected={currentTab === 'reconciliation'}
              className={`px-3.5 py-1.5 rounded-md text-xs transition ${
                currentTab === 'reconciliation'
                  ? 'font-semibold text-brand bg-elevated border border-border'
                  : 'font-medium text-slate-400 hover:text-white'
              }`}
            >
              Đối soát & Nhận tiền
            </button>
            <button
              onClick={() => setCurrentTab('verification')}
              role="tab"
              aria-selected={currentTab === 'verification'}
              className={`px-3.5 py-1.5 rounded-md text-xs transition ${
                currentTab === 'verification'
                  ? 'font-semibold text-brand bg-elevated border border-border'
                  : 'font-medium text-slate-400 hover:text-white'
              }`}
            >
              Xác minh danh tính
            </button>
          </nav>
        )}

        {/* Right: Actions */}
        <div className="flex items-center gap-2.5 text-xs">
          {shop ? (
            <>
              <div className="hidden sm:block text-right font-mono text-[11px] text-slate-400 mr-2">
                {shop.email}
              </div>
              <button onClick={onLogout} className="btn-subtle">
                Đăng xuất
              </button>
            </>
          ) : (
            <>
              <button onClick={() => onOpenAuth('login')} className="btn-ghost">
                Đăng nhập
              </button>
              <button onClick={() => onOpenAuth('register')} className="btn-solid-primary">
                Đăng ký Gian hàng
              </button>
            </>
          )}
        </div>

      </div>

      {/* Mobile Sub-Nav */}
      {shop && (
        <div className="flex md:hidden border-t border-border px-4 py-2 gap-2 overflow-x-auto text-xs bg-panel">
          <button
            onClick={() => setCurrentTab('dashboard')}
            className={`px-3 py-1 rounded ${currentTab === 'dashboard' ? 'bg-elevated text-brand font-semibold' : 'text-slate-400'}`}
          >
            Tổng quan
          </button>
          <button
            onClick={() => setCurrentTab('products')}
            className={`px-3 py-1 rounded ${currentTab === 'products' ? 'bg-elevated text-brand font-semibold' : 'text-slate-400'}`}
          >
            Sản phẩm
          </button>
          <button
            onClick={() => setCurrentTab('verification')}
            className={`px-3 py-1 rounded ${currentTab === 'verification' ? 'bg-elevated text-brand font-semibold' : 'text-slate-400'}`}
          >
            Xác minh
          </button>
        </div>
      )}
    </header>
  );
};
