/**
 * TAP AI - Background Service Worker (Manifest V3)
 * Điều phối Side Panel, bắt sự kiện Context Menu, đồng bộ Storage và gọi API Backend.
 */

const BACKEND_BASE_URL = "http://localhost:8000";

// 1. Cho phép mở Side Panel ngay khi bấm vào Icon Extension trên thanh công cụ
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error("SidePanel behavior error:", error));

// 2. Tạo Menu chuột phải (Context Menu) cho Ảnh & Video
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "tap_ai_search_context",
      title: "✨ Tìm kiếm sản phẩm với TAP AI",
      contexts: ["image", "video"],
    });
  });
});

// Helper: Mở Side Panel cho cửa sổ hiện tại
async function openSidePanelForTab(tab) {
  if (tab && tab.windowId && chrome.sidePanel && chrome.sidePanel.open) {
    try {
      await chrome.sidePanel.open({ windowId: tab.windowId });
    } catch (err) {
      console.warn("Không thể tự động mở Side Panel:", err);
    }
  }
}

// Helper: Lưu trạng thái vào chrome.storage.local để SidePanel không bị mất state khi mới mở
function saveStateToStorage(state) {
  if (chrome.storage && chrome.storage.local) {
    chrome.storage.local.set({
      tapAiState: {
        ...state,
        updatedAt: Date.now(),
      },
    });
  }
}

// Helper: Gửi tin nhắn an toàn sang Side Panel
function notifySidePanel(message) {
  chrome.runtime.sendMessage(message).catch(() => {
    // Bỏ qua lỗi nếu Side Panel đang đóng hoặc đang mount
  });
}

// Helper: Chuẩn hóa danh sách sản phẩm từ Backend sang chuẩn ProductItem của Frontend
function mapBackendProducts(rawProducts) {
  if (!Array.isArray(rawProducts)) return [];

  return rawProducts.map((p, idx) => {
    // Dùng trực tiếp thumbnail_url từ CDN sàn qua HTTPS (nhanh tức thì, không bị nghẽn proxy)
    const rawThumb = p.thumbnail_url || "";

    return {
      id: p.item_id || `prod_${Date.now()}_${idx}`,
      title: p.title || "Sản phẩm tìm thấy",
      price: p.price || "Xem trên sàn",
      image: rawThumb,
      link: p.product_url || "https://shopee.vn",
      platform: p.platform || "Shopee",
      matchScore: typeof p.match_score === "number" ? p.match_score : undefined,
      matchReason: p.match_reason || undefined,
    };
  });
}

// 3. Xử lý gọi Backend khi có ảnh màn hình + tọa độ tap hoặc URL ảnh
async function processSearch({ imageUrl, screenshotBase64, tapX, tapY }) {
  const loadingMsg = "AI đang bóc tách món đồ & quét các sàn Shopee/Lazada...";
  saveStateToStorage({
    status: "loading",
    loadingText: loadingMsg,
    errorMessage: null,
  });
  notifySidePanel({
    type: "SEARCH_LOADING",
    data: loadingMsg,
  });

  // Heartbeat duy trì Service Worker không bị Chrome kill trong lúc xử lý ngầm
  const keepAliveTimer = setInterval(() => {
    if (chrome.runtime?.getPlatformInfo) {
      chrome.runtime.getPlatformInfo(() => {});
    }
  }, 6000);

  try {
    let responseData = null;

    // Ưu tiên 1: Nếu có ảnh chụp màn hình + tọa độ tap, chạy qua SAM 3 tap-to-buy để bóc tách đúng vật thể được click
    if (screenshotBase64 && tapX !== undefined && tapY !== undefined) {
      try {
        const samResp = await fetch(`${BACKEND_BASE_URL}/api/v1/sam/tap-to-buy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            image_base64: screenshotBase64,
            tap_x: tapX,
            tap_y: tapY,
            is_normalized: true,
            send_to_rag: true,
          }),
        });

        if (samResp.ok) {
          const samData = await samResp.json();
          const ragResult = samData?.rag_search_result;
          // Hỗ trợ cả 2 định dạng:
          // 1. In-memory/webhook RAG pipeline thành công: ragResult.data.products
          // 2. Mock RAG preview khi chờ kết nối API: ragResult.products
          if (ragResult) {
            if (Array.isArray(ragResult?.data?.products)) {
              responseData = ragResult.data;
            } else if (Array.isArray(ragResult?.products)) {
              responseData = { products: ragResult.products };
            }
          }
        }
      } catch (samErr) {
        console.warn("SAM tap-to-buy fallback:", samErr);
      }
    }

    // Ưu tiên 2: Nếu dùng Context Menu trực tiếp trên ảnh hoặc SAM chưa trả về kết quả RAG -> gọi /api/v1/match-item
    if (!responseData || !Array.isArray(responseData.products)) {
      const payload =
        imageUrl && (imageUrl.startsWith("http://") || imageUrl.startsWith("https://"))
          ? { image_url: imageUrl, object_id: "obj_tap_web", top_k: 10 }
          : screenshotBase64
            ? { image_base64: screenshotBase64, object_id: "obj_tap_screen", top_k: 10 }
            : null;

      if (!payload) {
        throw new Error("Không có dữ liệu ảnh hợp lệ để tìm kiếm.");
      }

      const resp = await fetch(`${BACKEND_BASE_URL}/api/v1/match-item`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const errorText = await resp.text();
        throw new Error(`Backend lỗi (HTTP ${resp.status}): ${errorText}`);
      }
      responseData = await resp.json();
    }

    const mapped = mapBackendProducts(responseData.products || []);

    if (mapped.length > 0) {
      const topItem = mapped[0];
      const otherItems = mapped.slice(1);

      saveStateToStorage({
        status: "success",
        selectedItem: topItem,
        detectedItems: otherItems,
        errorMessage: null,
      });

      notifySidePanel({ type: "ITEM_CLICKED", data: topItem });
      notifySidePanel({ type: "SCENE_ITEMS_UPDATED", data: otherItems });
    } else {
      const emptyMsg = "Không tìm thấy sản phẩm tương tự trên sàn TMĐT.";
      saveStateToStorage({ status: "error", errorMessage: emptyMsg });
      notifySidePanel({ type: "SEARCH_ERROR", data: emptyMsg });
    }
  } catch (err) {
    console.error("Lỗi khi xử lý tìm kiếm TAP AI:", err);
    const errMsg = `Không thể kết nối Backend (${err.message}). Vui lòng kiểm tra server tại ${BACKEND_BASE_URL}.`;
    saveStateToStorage({ status: "error", errorMessage: errMsg });
    notifySidePanel({ type: "SEARCH_ERROR", data: errMsg });
  } finally {
    clearInterval(keepAliveTimer);
  }
}

// 4. Lắng nghe Context Menu click (Chuột phải lên ảnh/video -> Tìm kiếm)
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "tap_ai_search_context") {
    await openSidePanelForTab(tab);
    if (
      info.srcUrl &&
      info.mediaType === "image" &&
      (info.srcUrl.startsWith("http://") || info.srcUrl.startsWith("https://") || info.srcUrl.startsWith("data:"))
    ) {
      await processSearch({ imageUrl: info.srcUrl });
    } else if (tab && tab.windowId) {
      // Với video hoặc ảnh không có srcUrl http/https trực tiếp, chụp khung hình hiện tại của tab
      chrome.tabs.captureVisibleTab(
        tab.windowId,
        { format: "jpeg", quality: 85 },
        (dataUrl) => {
          if (!chrome.runtime.lastError && dataUrl) {
            processSearch({ screenshotBase64: dataUrl, tapX: 0.5, tapY: 0.5 });
          } else {
            const err = "Không thể chụp khung hình từ trang web để phân tích.";
            saveStateToStorage({ status: "error", errorMessage: err });
            notifySidePanel({ type: "SEARCH_ERROR", data: err });
          }
        }
      );
    }
  }
});

// 5. Lắng nghe tin nhắn từ Content Script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "TAP_TRIGGERED") {
    const tab = sender.tab;
    (async () => {
      try {
        await openSidePanelForTab(tab);
        if (tab && tab.windowId) {
          chrome.tabs.captureVisibleTab(
            tab.windowId,
            { format: "jpeg", quality: 85 },
            async (dataUrl) => {
              try {
                if (chrome.runtime.lastError || !dataUrl) {
                  if (
                    message.image_url &&
                    (message.image_url.startsWith("http://") || message.image_url.startsWith("https://"))
                  ) {
                    await processSearch({
                      imageUrl: message.image_url,
                      tapX: message.tap_x,
                      tapY: message.tap_y,
                    });
                  } else {
                    const capErr = "Không thể chụp màn hình trang web để phân tích.";
                    saveStateToStorage({ status: "error", errorMessage: capErr });
                    notifySidePanel({ type: "SEARCH_ERROR", data: capErr });
                  }
                  sendResponse({ status: "error", message: "capture_failed" });
                  return;
                }

                await processSearch({
                  imageUrl: message.image_url,
                  screenshotBase64: dataUrl,
                  tapX: message.tap_x,
                  tapY: message.tap_y,
                });
                sendResponse({ status: "done" });
              } catch (innerErr) {
                console.error("Lỗi processSearch:", innerErr);
                sendResponse({ status: "error", message: innerErr.message });
              }
            }
          );
        }
      } catch (err) {
        console.error("Lỗi khi mở side panel / capture:", err);
        sendResponse({ status: "error", message: err.message });
      }
    })();

    return true; // Giữ channel mở cho tới khi sendResponse được gọi
  }
});
