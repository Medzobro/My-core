# Lost ETH Scanner - Browser Extension (Chrome MV3)

A lightweight Chrome extension that scans any Ethereum address you paste,
or auto-detects the address you are viewing on Etherscan/Arbiscan/etc.

## Install (developer mode)

1. Open `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select this `browser_extension/` directory
5. Pin the extension to your toolbar

## Usage

- Click the extension icon, paste any address, click Scan
- Or visit any address page on Etherscan and click "Scan with Lost ETH"
  (small green banner appears in the top right)

## Limitations

- Lightweight: only checks 4 famous DEX contracts inline (IDEX, EtherDelta v3, Token.Store, Saturn)
- For full 107-contract scan, use the Web UI or CLI version
- Native balances on 5 chains: ETH, Arbitrum, Optimism, Base, Polygon

## Add Icons

Drop `icon16.png`, `icon48.png`, `icon128.png` files in this directory before publishing.
