/// <reference types="chrome" />
import React, { useState, useEffect } from 'react';
import { ProductItem, ChromeMessage } from '../types';

const isProductItem = (value: unknown): value is ProductItem => {
  if (typeof value !== 'object' || value === null) {
    return false;
  }

  const item = value as Partial<ProductItem>;
  return (
    typeof item.id === 'string' &&
    typeof item.title === 'string' &&
    typeof item.price === 'string' &&
    typeof item.image === 'string' &&
    typeof item.link === 'string'
  );
};

const isChromeMessage = (value: unknown): value is ChromeMessage => {
  if (typeof value !== 'object' || value === null) {
    return false;
  }

  const message = value as Partial<ChromeMessage>;
  return (
    message.type === 'ITEM_CLICKED' ||
    message.type === 'SCENE_ITEMS_UPDATED' ||
    message.type === 'TOGGLE_OVERLAY'
  );
};

export const SidePanel: React.FC = () => {
  const [selectedItem, setSelectedItem] = useState<ProductItem | null>(null);
  const [detectedItems, setDetectedItems] = useState<ProductItem[]>([]);

  useEffect(() => {
    const runtime =
      typeof chrome !== 'undefined' && chrome.runtime
        ? chrome.runtime
        : undefined;

    const handleMessage = (
      message: unknown,
      _sender: chrome.runtime.MessageSender,
      _sendResponse: (response?: unknown) => void
    ) => {
      if (!isChromeMessage(message)) {
        return;
      }

      if (message.type === 'ITEM_CLICKED' && isProductItem(message.data)) {
        setSelectedItem(message.data);
      } else if (
        message.type === 'SCENE_ITEMS_UPDATED' &&
        Array.isArray(message.data) &&
        message.data.every(isProductItem)
      ) {
        setDetectedItems(message.data);
      }
    };

    if (runtime?.onMessage) {
      runtime.onMessage.addListener(handleMessage);
    }

    return () => {
      if (runtime?.onMessage) {
        runtime.onMessage.removeListener(handleMessage);
      }
    };
  }, []);

  return (
    <div className="w-full h-screen bg-slate-950 text-slate-100 font-sans flex flex-col overflow-hidden select-none">
      {/* 1. Header Cố định (Sticky Header) */}
      <header className="sticky top-0 z-20 bg-slate-900/90 backdrop-blur-md border-b border-slate-800/80 px-4 py-3 flex items-center justify-between shadow-md">
        <div className="flex items-center gap-2.5">
          <div className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
          </div>
          <h1 className="font-bold text-lg tracking-wider bg-gradient-to-r from-teal-400 via-emerald-400 to-cyan-400 bg-clip-text text-transparent">
            TAP AI
          </h1>
        </div>
        <span className="text-[11px] font-medium bg-slate-800/80 px-2.5 py-0.5 rounded-full text-teal-400 border border-teal-500/20">
          Shoppable Engine
        </span>
      </header>

      {/* 2. Container Cuộn Nội Dung (Scrollable Body) */}
      <main className="flex-1 overflow-y-auto px-4 py-4 space-y-5 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
        
        {/* --- NỔI BẬT: Sản phẩm được chọn từ Video/Ảnh --- */}
        {selectedItem ? (
          <section className="space-y-2">
            <span className="text-[11px] font-semibold text-teal-400 uppercase tracking-widest px-1">
              Vật thể đang chọn
            </span>
            <div className="group bg-slate-900/90 border border-teal-500/30 rounded-2xl p-3.5 shadow-2xl shadow-teal-950/40 backdrop-blur-md transition-all duration-300 hover:border-teal-500/60">
              {/* Ảnh sản phẩm */}
              <div className="relative aspect-square w-full rounded-xl overflow-hidden bg-slate-950 mb-3 border border-slate-800">
                <img
                  src={selectedItem.image}
                  alt={selectedItem.title}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                />
                <span className="absolute top-2 right-2 bg-emerald-500 text-slate-950 font-extrabold text-[10px] px-2.5 py-0.5 rounded-full uppercase tracking-wider shadow-lg">
                  {selectedItem.platform || 'Shopee'}
                </span>
              </div>

              {/* Thông tin sản phẩm */}
              <h2 className="font-medium text-slate-100 text-sm leading-snug line-clamp-2 mb-2">
                {selectedItem.title}
              </h2>

              <div className="flex items-baseline justify-between mb-3">
                <span className="text-xl font-bold text-emerald-400 tracking-tight">
                  {selectedItem.price}
                </span>
                {selectedItem.originalPrice && (
                  <span className="text-xs text-slate-500 line-through">
                    {selectedItem.originalPrice}
                  </span>
                )}
              </div>

              {/* Nút Mua Ngay -> Navigate Link */}
              <a
                href={selectedItem.link}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-400 hover:to-emerald-400 text-slate-950 font-bold py-2.5 px-4 rounded-xl shadow-lg shadow-emerald-500/20 active:scale-[0.98] transition-all duration-200"
              >
                <span>Mua ngay</span>
                <svg className="w-4 h-4 fill-current stroke-slate-950 stroke-2" viewBox="0 0 24 24">
                  <path d="M5 12h14M12 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </a>
            </div>
          </section>
        ) : (
          /* Empty State khi chưa click */
          <section className="h-52 border border-dashed border-slate-800/80 rounded-2xl flex flex-col items-center justify-center text-center p-6 bg-slate-900/30">
            <div className="w-12 h-12 rounded-full bg-slate-800/50 border border-slate-700/50 flex items-center justify-center mb-3 text-teal-400">
              <svg className="w-6 h-6 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
              </svg>
            </div>
            <p className="text-xs font-semibold text-slate-300">Chạm vào sản phẩm bất kỳ</p>
            <p className="text-[11px] text-slate-500 mt-1 max-w-[200px]">Rê chuột hoặc click vào vật thể trên Video/Ảnh để xem thông tin mua sắm.</p>
          </section>
        )}

        {/* --- DANH SÁCH THẺ SẢN PHẨM TRONG CẢNH --- */}
        <section className="space-y-3 pb-4">
          <div className="flex items-center justify-between px-1">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">
              Sản phẩm khác trong cảnh
            </span>
            <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-md font-mono">
              {detectedItems.length} món
            </span>
          </div>

          {detectedItems.length > 0 ? (
            <div className="grid grid-cols-1 gap-2.5">
              {detectedItems.map((item) => (
                <a
                  key={item.id}
                  href={item.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setSelectedItem(item)}
                  className={`group flex items-center gap-3 p-2.5 rounded-xl border transition-all duration-200 cursor-pointer ${
                    selectedItem?.id === item.id
                      ? 'bg-slate-800/90 border-teal-500/60 shadow-lg shadow-teal-950/30'
                      : 'bg-slate-900/60 border-slate-800/80 hover:bg-slate-800/60 hover:border-slate-700'
                  }`}
                >
                  {/* Thumbnail sản phẩm */}
                  <div className="relative w-16 h-16 rounded-lg overflow-hidden bg-slate-950 flex-shrink-0 border border-slate-800">
                    <img
                      src={item.image}
                      alt={item.title}
                      className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300"
                    />
                  </div>

                  {/* Chi tiết vắn tắt */}
                  <div className="flex-1 min-w-0 pr-1">
                    <p className="text-xs text-slate-200 font-medium line-clamp-1 group-hover:text-teal-300 transition-colors">
                      {item.title}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs font-bold text-emerald-400">
                        {item.price}
                      </span>
                      {item.platform && (
                        <span className="text-[9px] bg-slate-800 text-slate-400 px-1.5 py-0.2 rounded border border-slate-700">
                          {item.platform}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Icon Navigate sang link */}
                  <div className="p-1.5 rounded-lg text-slate-500 group-hover:text-teal-400 group-hover:bg-slate-800 transition-all flex-shrink-0">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </div>
                </a>
              ))}
            </div>
          ) : (
            <div className="text-center py-6 text-slate-600 text-xs bg-slate-900/20 rounded-xl border border-slate-900">
              Chưa phát hiện thêm sản phẩm khác.
            </div>
          )}
        </section>

      </main>
    </div>
  );
};

export default SidePanel;