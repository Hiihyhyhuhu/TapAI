/// <reference types="chrome" />
import React, { useState, useEffect } from 'react';
import { ProductItem, ChromeMessage, TapAiStorageState } from '../types';

const isProductItem = (value: unknown): value is ProductItem => {
  if (typeof value !== 'object' || value === null) {
    return false;
  }

  const item = value as Partial<ProductItem>;
  return (
    typeof item.id !== 'undefined' &&
    typeof item.title === 'string' &&
    Boolean(item.title)
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
    message.type === 'TOGGLE_OVERLAY' ||
    message.type === 'SEARCH_LOADING' ||
    message.type === 'SEARCH_ERROR'
  );
};

const FALLBACK_IMAGE_SVG =
  'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 24 24" fill="none" stroke="%23475569" stroke-width="1.5"><rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>';

export const SidePanel: React.FC = () => {
  const [selectedItem, setSelectedItem] = useState<ProductItem | null>(null);
  const [detectedItems, setDetectedItems] = useState<ProductItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadingText, setLoadingText] = useState<string>(
    'AI đang phân tích trang phục & tìm kiếm Shopee...'
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const runtime =
      typeof chrome !== 'undefined' && chrome.runtime
        ? chrome.runtime
        : undefined;

    // 1. Khôi phục state gần nhất từ chrome.storage.local (tránh miss message khi panel mới mở)
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(['tapAiState'], (res) => {
        const saved = res?.tapAiState as TapAiStorageState | undefined;
        if (!saved) return;

        // Chỉ khôi phục các tác vụ trong vòng 5 phút gần đây
        if (saved.updatedAt && Date.now() - saved.updatedAt > 5 * 60 * 1000) {
          return;
        }

        if (saved.status === 'loading') {
          setIsLoading(true);
          setErrorMessage(null);
          if (saved.loadingText) setLoadingText(saved.loadingText);
        } else if (saved.status === 'error') {
          setIsLoading(false);
          setErrorMessage(saved.errorMessage || 'Không thể kết nối Backend http://localhost:8000.');
        } else if (saved.status === 'success') {
          setIsLoading(false);
          setErrorMessage(null);
          if (saved.selectedItem && isProductItem(saved.selectedItem)) {
            setSelectedItem(saved.selectedItem);
          }
          if (Array.isArray(saved.detectedItems)) {
            setDetectedItems(saved.detectedItems.filter(isProductItem));
          }
        }
      });
    }

    // 2. Lắng nghe cập nhật real-time từ Background Service Worker
    const handleMessage = (
      message: unknown,
      _sender: chrome.runtime.MessageSender,
      _sendResponse: (response?: unknown) => void
    ) => {
      if (!isChromeMessage(message)) {
        return;
      }

      if (message.type === 'SEARCH_LOADING') {
        setIsLoading(true);
        setErrorMessage(null);
        if (typeof message.data === 'string') {
          setLoadingText(message.data);
        }
      } else if (message.type === 'SEARCH_ERROR') {
        setIsLoading(false);
        setErrorMessage(
          typeof message.data === 'string'
            ? message.data
            : 'Không thể kết nối Backend http://localhost:8000.'
        );
      } else if (message.type === 'ITEM_CLICKED') {
        setIsLoading(false);
        setErrorMessage(null);
        if (isProductItem(message.data)) {
          setSelectedItem(message.data);
        }
      } else if (message.type === 'SCENE_ITEMS_UPDATED') {
        setIsLoading(false);
        if (Array.isArray(message.data)) {
          setDetectedItems(message.data.filter(isProductItem));
        }
      }
    };

    // 3. Lắng nghe thay đổi Storage trực tiếp để đảm bảo không bao giờ bị miss state
    const handleStorageChange = (
      changes: { [key: string]: chrome.storage.StorageChange },
      areaName: string
    ) => {
      if (areaName === 'local' && changes.tapAiState?.newValue) {
        const saved = changes.tapAiState.newValue as TapAiStorageState;
        if (saved.status === 'loading') {
          setIsLoading(true);
          setErrorMessage(null);
          if (saved.loadingText) setLoadingText(saved.loadingText);
        } else if (saved.status === 'error') {
          setIsLoading(false);
          setErrorMessage(saved.errorMessage || 'Không thể kết nối Backend http://localhost:8000.');
        } else if (saved.status === 'success') {
          setIsLoading(false);
          setErrorMessage(null);
          if (saved.selectedItem && isProductItem(saved.selectedItem)) {
            setSelectedItem(saved.selectedItem);
          }
          if (Array.isArray(saved.detectedItems)) {
            setDetectedItems(saved.detectedItems.filter(isProductItem));
          }
        }
      }
    };

    if (runtime?.onMessage) {
      runtime.onMessage.addListener(handleMessage);
    }
    if (typeof chrome !== 'undefined' && chrome.storage?.onChanged) {
      chrome.storage.onChanged.addListener(handleStorageChange);
    }

    return () => {
      if (runtime?.onMessage) {
        runtime.onMessage.removeListener(handleMessage);
      }
      if (typeof chrome !== 'undefined' && chrome.storage?.onChanged) {
        chrome.storage.onChanged.removeListener(handleStorageChange);
      }
    };
  }, []);

  return (
    <div className="w-full h-screen bg-slate-950 text-slate-100 font-sans flex flex-col overflow-hidden select-none">
      {/* 1. Header Cố định (Sticky Header) */}
      <header className="sticky top-0 z-20 bg-slate-900/90 backdrop-blur-md border-b border-slate-800/80 px-4 py-3 flex items-center justify-between shadow-md">
        <div className="flex items-center gap-2.5">
          <div className="relative flex h-3 w-3">
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full ${
                isLoading ? 'bg-amber-400' : 'bg-emerald-400'
              } opacity-75`}
            ></span>
            <span
              className={`relative inline-flex rounded-full h-3 w-3 ${
                isLoading ? 'bg-amber-500' : 'bg-emerald-500'
              }`}
            ></span>
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

        {/* --- TRẠNG THÁI: Đang xử lý AI (Loading Shimmer) --- */}
        {isLoading && (
          <section className="bg-slate-900/90 border border-teal-500/40 rounded-2xl p-4 shadow-xl shadow-teal-950/40 backdrop-blur-md animate-pulse">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-5 h-5 border-2 border-teal-400 border-t-transparent rounded-full animate-spin"></div>
              <span className="text-xs font-semibold text-teal-400 uppercase tracking-wider">
                AI Vision Processing
              </span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              {loadingText}
            </p>
            <div className="mt-3 w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div className="bg-gradient-to-r from-teal-400 to-emerald-400 h-1.5 w-2/3 rounded-full animate-pulse"></div>
            </div>
          </section>
        )}

        {/* --- TRẠNG THÁI: Lỗi kết nối / Xử lý --- */}
        {errorMessage && !isLoading && (
          <section className="bg-rose-950/40 border border-rose-500/40 rounded-2xl p-3.5 shadow-lg text-rose-200">
            <div className="flex items-center gap-2 mb-1.5 text-rose-400">
              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-xs font-bold uppercase tracking-wide">Thông báo sự cố</span>
            </div>
            <p className="text-xs text-slate-300 mb-2 leading-relaxed">{errorMessage}</p>
            <p className="text-[11px] text-slate-400">
              💡 Hãy kiểm tra server Backend: Chạy file <code className="bg-slate-900 px-1 py-0.5 rounded text-teal-300">run_server.bat</code> tại thư mục dự án.
            </p>
          </section>
        )}

        {/* --- NỔI BẬT: Sản phẩm được chọn từ Video/Ảnh --- */}
        {selectedItem ? (
          <section className="space-y-2">
            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-semibold text-teal-400 uppercase tracking-widest">
                Vật thể đang chọn
              </span>
              {selectedItem.matchScore !== undefined && (
                <span className="text-[10px] font-bold bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-500/40">
                  Độ khớp: {Math.round(selectedItem.matchScore * 100)}%
                </span>
              )}
            </div>

            <div className="group bg-slate-900/90 border border-teal-500/30 rounded-2xl p-3.5 shadow-2xl shadow-teal-950/40 backdrop-blur-md transition-all duration-300 hover:border-teal-500/60">
              {/* Ảnh sản phẩm */}
              <div className="relative aspect-square w-full rounded-xl overflow-hidden bg-slate-950 mb-3 border border-slate-800">
                <img
                  src={selectedItem.image}
                  alt={selectedItem.title}
                  referrerPolicy="no-referrer"
                  loading="lazy"
                  onError={(e) => {
                    const target = e.target as HTMLImageElement;
                    if (!target.dataset.triedProxy && target.src && (target.src.startsWith('http://') || target.src.startsWith('https://')) && !target.src.includes('127.0.0.1') && !target.src.includes('localhost')) {
                      target.dataset.triedProxy = 'true';
                      target.src = `http://localhost:8000/api/v1/image-proxy?url=${encodeURIComponent(target.src)}`;
                    } else {
                      target.onerror = null;
                      target.src = FALLBACK_IMAGE_SVG;
                    }
                  }}
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

              {selectedItem.matchReason && (
                <p className="text-[11px] text-slate-400 bg-slate-950/60 border border-slate-800/80 rounded-lg p-2 mb-3 leading-relaxed">
                  💬 <span className="text-slate-300">{selectedItem.matchReason}</span>
                </p>
              )}

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
                  <path d="M5 12h14M12 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </a>
            </div>
          </section>
        ) : (
          !isLoading &&
          !errorMessage && (
            <section className="h-52 border border-dashed border-slate-800/80 rounded-2xl flex flex-col items-center justify-center text-center p-6 bg-slate-900/30">
              <div className="w-12 h-12 rounded-full bg-slate-800/50 border border-slate-700/50 flex items-center justify-center mb-3 text-teal-400">
                <svg className="w-6 h-6 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                </svg>
              </div>
              <p className="text-xs font-semibold text-slate-300">Chạm vào sản phẩm bất kỳ</p>
              <p className="text-[11px] text-slate-500 mt-1 max-w-[220px]">
                Giữ phím <kbd className="bg-slate-800 text-teal-300 px-1 py-0.5 rounded text-[10px]">Alt</kbd> + click vào ảnh/video, hoặc bấm nút <span className="text-teal-400 font-semibold">✨ TAP AI</span> ở góc màn hình.
              </p>
            </section>
          )
        )}

        {/* --- DANH SÁCH THẺ SẢN PHẨM TRONG CẢNH --- */}
        <section className="space-y-3 pb-4">
          <div className="flex items-center justify-between px-1">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">
              Sản phẩm tương tự khác
            </span>
            <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-md font-mono">
              {detectedItems.length} món
            </span>
          </div>

          {detectedItems.length > 0 ? (
            <div className="grid grid-cols-1 gap-2.5">
              {detectedItems.map((item) => (
                <div
                  key={item.id}
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
                      referrerPolicy="no-referrer"
                      loading="lazy"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        if (!target.dataset.triedProxy && target.src && (target.src.startsWith('http://') || target.src.startsWith('https://')) && !target.src.includes('127.0.0.1') && !target.src.includes('localhost')) {
                          target.dataset.triedProxy = 'true';
                          target.src = `http://localhost:8000/api/v1/image-proxy?url=${encodeURIComponent(target.src)}`;
                        } else {
                          target.onerror = null;
                          target.src = FALLBACK_IMAGE_SVG;
                        }
                      }}
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

                  {/* Nút xem trực tiếp link */}
                  <a
                    href={item.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    title="Mở trên sàn mua hàng"
                    className="p-1.5 rounded-lg text-slate-500 hover:text-teal-400 hover:bg-slate-800 transition-all flex-shrink-0"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-6 text-slate-600 text-xs bg-slate-900/20 rounded-xl border border-slate-900">
              Chưa có danh sách sản phẩm phụ.
            </div>
          )}
        </section>

      </main>
    </div>
  );
};

export default SidePanel;
