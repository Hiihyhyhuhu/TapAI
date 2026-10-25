import React, { useState, useEffect } from 'react';
import { ProductItem, ChromeMessage } from './types';

export const SidePanel: React.FC = () => {
  const [selectedItem, setSelectedItem] = useState<ProductItem | null>(null);
  const [detectedItems, setDetectedItems] = useState<ProductItem[]>([]);

  useEffect(() => {
    const handleMessage = (
      message: ChromeMessage,
      _sender: chrome.runtime.MessageSender,
      _sendResponse: (response?: any) => void
    ) => {
      if (message.type === 'ITEM_CLICKED' && message.data) {
        setSelectedItem(message.data as ProductItem);
      } else if (message.type === 'SCENE_ITEMS_UPDATED' && Array.isArray(message.data)) {
        setDetectedItems(message.data as ProductItem[]);
      }
    };

    if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
      chrome.runtime.onMessage.addListener(handleMessage);
    }

    return () => {
      if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
        chrome.runtime.onMessage.removeListener(handleMessage);
      }
    };
  }, []);

  return (
    <div className="w-full min-h-screen bg-slate-900 text-slate-100 p-4 font-sans flex flex-col gap-4">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse" />
          <h1 className="font-bold text-lg tracking-wide bg-gradient-to-r from-teal-400 to-blue-500 bg-clip-text text-transparent">
            TAP AI
          </h1>
        </div>
        <span className="text-xs bg-slate-800 px-2 py-1 rounded-full text-slate-400 border border-slate-700">
          v1.0 Demo
        </span>
      </header>

      {/* Main Content */}
      <main className="flex-1">
        {selectedItem ? (
          <div className="bg-slate-800/90 border border-slate-700/80 rounded-xl p-4 shadow-xl backdrop-blur transition-all duration-300">
            <div className="relative aspect-square w-full rounded-lg overflow-hidden bg-slate-950 mb-3 border border-slate-800">
              <img
                src={selectedItem.image}
                alt={selectedItem.title}
                className="w-full h-full object-cover"
              />
              <span className="absolute top-2 right-2 bg-emerald-500/90 text-slate-950 font-bold text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wider">
                {selectedItem.platform || 'Shopee'}
              </span>
            </div>

            <h2 className="font-semibold text-slate-100 text-base leading-snug line-clamp-2 mb-2">
              {selectedItem.title}
            </h2>

            <div className="flex items-baseline justify-between mb-4">
              <span className="text-xl font-bold text-emerald-400">
                {selectedItem.price}
              </span>
              {selectedItem.originalPrice && (
                <span className="text-xs text-slate-500 line-through">
                  {selectedItem.originalPrice}
                </span>
              )}
            </div>

            <a
              href={selectedItem.link}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-blue-600 to-teal-500 hover:from-blue-500 hover:to-teal-400 text-white font-semibold py-2.5 px-4 rounded-lg shadow-lg shadow-teal-500/10 active:scale-[0.98] transition-all duration-150"
            >
              <span>Mua ngay</span>
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </a>
          </div>
        ) : (
          <div className="h-64 border-2 border-dashed border-slate-800 rounded-xl flex flex-col items-center justify-center text-center p-6 text-slate-500">
            <div className="w-12 h-12 rounded-full bg-slate-800/60 flex items-center justify-center mb-3 text-teal-400">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
              </svg>
            </div>
            <p className="text-sm font-medium text-slate-400">Chưa chọn món đồ nào</p>
            <p className="text-xs text-slate-600 mt-1">Chạm vào bất kỳ vật thể nào trên video/ảnh để xem giá và link mua.</p>
          </div>
        )}

        {detectedItems.length > 0 && (
          <div className="mt-6">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Món đồ khác trong cảnh ({detectedItems.length})
            </h3>
            <div className="flex flex-col gap-2">
              {detectedItems.map((item) => (
                <div
                  key={item.id}
                  onClick={() => setSelectedItem(item)}
                  className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer border transition-all ${
                    selectedItem?.id === item.id
                      ? 'bg-slate-800 border-teal-500/50'
                      : 'bg-slate-900/60 border-slate-800 hover:bg-slate-800/50'
                  }`}
                >
                  <img
                    src={item.image}
                    alt={item.title}
                    className="w-12 h-12 rounded object-cover bg-slate-950 flex-shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-slate-200 font-medium truncate">{item.title}</p>
                    <p className="text-xs text-emerald-400 font-semibold mt-0.5">{item.price}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default SidePanel;