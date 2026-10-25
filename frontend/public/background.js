// Cho phép mở Side Panel ngay khi bấm vào Icon Extension
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error));