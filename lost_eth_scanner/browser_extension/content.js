// Injects a "Scan with Lost ETH" button on Etherscan-like address pages
(function() {
  const m = location.pathname.match(/\/address\/(0x[a-fA-F0-9]{40})/);
  if (!m) return;
  const address = m[1];

  const banner = document.createElement('div');
  banner.style.cssText = `
    position: fixed; top: 12px; right: 12px; z-index: 99999;
    background: #0a0e1a; color: #4ade80; padding: 10px 16px;
    border: 1px solid #4ade80; border-radius: 8px;
    font-family: system-ui, sans-serif; font-size: 13px; cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
  `;
  banner.textContent = 'Scan with Lost ETH';
  banner.addEventListener('click', () => {
    chrome.runtime.sendMessage({type: 'open_popup', address});
    chrome.action.openPopup && chrome.action.openPopup();
  });
  document.body.appendChild(banner);

  setTimeout(() => banner.remove(), 30000);  // auto-hide after 30s
})();
