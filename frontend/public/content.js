/**
 * TAP AI - Content Script
 * Chạy trực tiếp trên các trang web để bắt sự kiện click/tap vào trang phục, ảnh, video.
 */
(() => {
  if (window.__TAP_AI_CONTENT_LOADED__) return;
  window.__TAP_AI_CONTENT_LOADED__ = true;

  let isTapModeActive = false;
  let isProcessing = false;
  let toastTimer = null;

  // 1. Tạo hiệu ứng gợn sóng Glowing Ripple tại điểm click
  function showRipple(x, y) {
    const ripple = document.createElement("div");
    ripple.style.position = "fixed";
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;
    ripple.style.width = "10px";
    ripple.style.height = "10px";
    ripple.style.borderRadius = "50%";
    ripple.style.pointerEvents = "none";
    ripple.style.zIndex = "2147483647";
    ripple.style.transform = "translate(-50%, -50%) scale(1)";
    ripple.style.border = "2px solid #2dd4bf";
    ripple.style.boxShadow = "0 0 15px #14b8a6, inset 0 0 10px #14b8a6";
    ripple.style.transition = "transform 0.6s cubic-bezier(0, 0.5, 0.5, 1), opacity 0.6s ease-out";
    ripple.style.opacity = "1";

    document.body.appendChild(ripple);

    requestAnimationFrame(() => {
      ripple.style.transform = "translate(-50%, -50%) scale(7)";
      ripple.style.opacity = "0";
    });

    setTimeout(() => {
      ripple.remove();
    }, 650);
  }

  // 2. Tạo thông báo Toast nổi nhanh trên góc màn hình
  function showToast(text, isError = false) {
    let toast = document.getElementById("tap-ai-floating-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "tap-ai-floating-toast";
      toast.style.position = "fixed";
      toast.style.top = "20px";
      toast.style.right = "20px";
      toast.style.zIndex = "2147483647";
      toast.style.padding = "10px 16px";
      toast.style.borderRadius = "12px";
      toast.style.fontSize = "13px";
      toast.style.fontWeight = "600";
      toast.style.fontFamily = "system-ui, -apple-system, sans-serif";
      toast.style.boxShadow = "0 10px 25px -5px rgba(0, 0, 0, 0.4)";
      toast.style.transition = "all 0.3s ease";
      toast.style.pointerEvents = "none";
      document.body.appendChild(toast);
    }

    toast.style.backgroundColor = isError ? "rgba(225, 29, 72, 0.95)" : "rgba(15, 23, 42, 0.92)";
    toast.style.color = isError ? "#fff" : "#2dd4bf";
    toast.style.border = isError ? "1px solid #f43f5e" : "1px solid rgba(45, 212, 191, 0.4)";
    toast.innerText = text;
    toast.style.opacity = "1";
    toast.style.transform = "translateY(0)";

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      if (toast) {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(-10px)";
      }
    }, 3000);
  }

  // 3. Tạo nút nổi Bật/Tắt chế độ TAP AI ở góc dưới màn hình
  function createFloatingButton() {
    if (!document.body || document.getElementById("tap-ai-toggle-btn")) return;

    const btn = document.createElement("button");
    btn.id = "tap-ai-toggle-btn";
    btn.type = "button";
    btn.title = "Bật/Tắt chế độ tìm kiếm TAP AI (hoặc giữ phím Alt + Click vào món đồ)";
    btn.innerText = "✨ TAP AI";
    btn.style.position = "fixed";
    btn.style.bottom = "24px";
    btn.style.right = "24px";
    btn.style.zIndex = "2147483646";
    btn.style.padding = "10px 16px";
    btn.style.backgroundColor = "#0f172a";
    btn.style.color = "#2dd4bf";
    btn.style.border = "1.5px solid rgba(45, 212, 191, 0.5)";
    btn.style.borderRadius = "9999px";
    btn.style.fontSize = "13px";
    btn.style.fontWeight = "700";
    btn.style.fontFamily = "system-ui, -apple-system, sans-serif";
    btn.style.cursor = "pointer";
    btn.style.boxShadow = "0 4px 20px rgba(20, 184, 166, 0.25)";
    btn.style.transition = "all 0.25s ease";

    btn.addEventListener("mouseenter", () => {
      btn.style.transform = "scale(1.05)";
      btn.style.boxShadow = "0 6px 24px rgba(20, 184, 166, 0.4)";
    });
    btn.addEventListener("mouseleave", () => {
      btn.style.transform = "scale(1)";
      btn.style.boxShadow = "0 4px 20px rgba(20, 184, 166, 0.25)";
    });

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      isTapModeActive = !isTapModeActive;
      if (isTapModeActive) {
        btn.style.backgroundColor = "#14b8a6";
        btn.style.color = "#022c22";
        btn.style.borderColor = "#2dd4bf";
        btn.innerText = "🎯 TAP: BẬT";
        showToast("🎯 Chế độ TAP AI đã bật! Nhấp vào bất kỳ ảnh/video nào để tìm kiếm.");
      } else {
        btn.style.backgroundColor = "#0f172a";
        btn.style.color = "#2dd4bf";
        btn.style.borderColor = "rgba(45, 212, 191, 0.5)";
        btn.innerText = "✨ TAP AI";
        showToast("Đã tắt chế độ TAP AI.");
      }
    });

    document.body.appendChild(btn);
  }

  // Helper: Tìm URL ảnh tại tọa độ click (kể cả khi bị thẻ overlay che phía trên)
  function findImageUrlAtPoint(x, y, target) {
    const elements = document.elementsFromPoint(x, y);
    for (const el of elements) {
      const tag = el.tagName ? el.tagName.toLowerCase() : "";
      if (tag === "img" && (el.currentSrc || el.src)) {
        return el.currentSrc || el.src;
      }
      if (tag === "video" && el.poster) {
        return el.poster;
      }
    }

    if (target && target.closest) {
      const imgAncestor = target.closest("img");
      if (imgAncestor && (imgAncestor.currentSrc || imgAncestor.src)) {
        return imgAncestor.currentSrc || imgAncestor.src;
      }
    }

    if (target) {
      const bgImg = window.getComputedStyle(target).backgroundImage;
      if (bgImg && bgImg.startsWith('url("') && bgImg.endsWith('")')) {
        return bgImg.slice(5, -2);
      }
    }
    return null;
  }

  // 4. Bắt sự kiện Click trên trang web
  document.addEventListener(
    "click",
    (e) => {
      if (
        e.target &&
        (e.target.id === "tap-ai-toggle-btn" || e.target.id === "tap-ai-floating-toast")
      ) {
        return;
      }

      const isAltClick = e.altKey;
      if (!isTapModeActive && !isAltClick) {
        return;
      }

      if (isProcessing) {
        showToast("⏳ Đang xử lý yêu cầu trước đó, vui lòng đợi...");
        return;
      }

      e.preventDefault();
      e.stopPropagation();

      const clickX = e.clientX;
      const clickY = e.clientY;

      const tapX = Math.max(0.0, Math.min(1.0, clickX / window.innerWidth));
      const tapY = Math.max(0.0, Math.min(1.0, clickY / window.innerHeight));
      const imageUrl = findImageUrlAtPoint(clickX, clickY, e.target);

      // Kiểm tra nếu extension vừa được reload nhưng tab web chưa F5
      if (!chrome.runtime?.id) {
        showToast("⚠️ Extension vừa được cập nhật! Vui lòng F5 (tải lại) trang web này.", true);
        return;
      }

      isProcessing = true;
      showToast("🔍 TAP AI đang phân tích món đồ... Hãy xem Side Panel!");

      // Dự phòng tự mở khóa sau 2.5 giây tránh kẹt trạng thái
      const unlockTimer = setTimeout(() => {
        isProcessing = false;
      }, 2500);

      try {
        chrome.runtime.sendMessage(
          {
            type: "TAP_TRIGGERED",
            tap_x: tapX,
            tap_y: tapY,
            image_url: imageUrl,
            tag_name: e.target?.tagName ? e.target.tagName.toLowerCase() : "unknown",
          },
          (res) => {
            clearTimeout(unlockTimer);
            isProcessing = false;
            // Hiển thị hiệu ứng gợn sóng CHỈ SAU KHI chụp màn hình hoàn tất
            // Tránh tuyệt đối việc dính chấm tròn ngọc UI vào ảnh chụp gửi Backend VLM
            showRipple(clickX, clickY);
            if (chrome.runtime?.lastError) {
              console.warn("TAP AI runtime message:", chrome.runtime.lastError.message);
            }
          }
        );
      } catch (err) {
        clearTimeout(unlockTimer);
        isProcessing = false;
        showToast("⚠️ Vui lòng F5 (tải lại) trang web để kết nối Extension!", true);
      }
    },
    true
  );

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createFloatingButton);
  } else {
    createFloatingButton();
  }
})();
