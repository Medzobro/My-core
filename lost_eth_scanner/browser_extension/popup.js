// Browser extension popup logic
const RPCS = {
  ethereum: ['https://ethereum-rpc.publicnode.com', 'https://eth.llamarpc.com'],
  arbitrum: ['https://arbitrum-one-rpc.publicnode.com'],
  optimism: ['https://optimism-rpc.publicnode.com'],
  base: ['https://base-rpc.publicnode.com'],
  polygon: ['https://polygon-bor-rpc.publicnode.com'],
};

// Inline minimal contract DB (top 10)
const CONTRACTS = [
  { chain: 'ethereum', name: 'IDEX 1.0', address: '0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208', type: 'etherdelta' },
  { chain: 'ethereum', name: 'EtherDelta v3', address: '0x8d12A197cB00D4747a1fe03395095ce2A5CC6819', type: 'etherdelta' },
  { chain: 'ethereum', name: 'Token.Store', address: '0x1ce7AE555139c5EF5A57CC8d814a867ee6Ee33D8', type: 'etherdelta' },
  { chain: 'ethereum', name: 'Saturn Network', address: '0x1d52da498be2c862b0bbe2f053adda85f02c44df', type: 'etherdelta' },
];

const $ = id => document.getElementById(id);

function pad32(a) { return a.toLowerCase().replace('0x','').padStart(64, '0'); }

async function rpcCall(chain, method, params) {
  const rpcs = RPCS[chain] || [];
  for (const rpc of rpcs) {
    try {
      const r = await fetch(rpc, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', method, params, id: 1 }),
      });
      const d = await r.json();
      if (d.result !== undefined) return d.result;
    } catch (e) { continue; }
  }
  return null;
}

async function checkEthBalance(chain, contract, user) {
  const data = '0xf7888aec' + pad32('0x0000000000000000000000000000000000000000') + pad32(user);
  const res = await rpcCall(chain, 'eth_call', [{to: contract, data}, 'latest']);
  return res ? BigInt(res) : 0n;
}

async function checkNative(chain, user) {
  const res = await rpcCall(chain, 'eth_getBalance', [user, 'latest']);
  return res ? BigInt(res) : 0n;
}

async function scan(address) {
  $('results').innerHTML = 'Scanning...';
  const findings = [];

  // Native ETH on each chain
  for (const ch of Object.keys(RPCS)) {
    const bal = await checkNative(ch, address);
    if (bal > 0n) {
      findings.push({type: 'native', chain: ch, amount: Number(bal)/1e18, symbol: 'ETH/native'});
    }
  }

  // Stuck DEX balances
  for (const c of CONTRACTS) {
    if (c.type === 'etherdelta') {
      const bal = await checkEthBalance(c.chain, c.address, address);
      if (bal > 0n) {
        findings.push({type: 'stuck', chain: c.chain, name: c.name, amount: Number(bal)/1e18, symbol: 'ETH'});
      }
    }
  }

  if (findings.length === 0) {
    $('results').innerHTML = '<span class="muted">No stuck balances detected.</span>';
    return;
  }

  $('results').innerHTML = findings.map(f =>
    `<div class="finding">${f.type === 'native' ? 'WALLET' : f.name} [${f.chain}]: ${f.amount.toFixed(8)} ${f.symbol}</div>`
  ).join('');
}

$('scan').addEventListener('click', () => {
  const a = $('addr').value.trim();
  if (a.match(/^0x[a-fA-F0-9]{40}$/)) scan(a);
  else $('results').innerHTML = '<span style="color:#f87171">Invalid address.</span>';
});

$('useTab').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  const url = tab.url;
  const m = url.match(/0x[a-fA-F0-9]{40}/);
  if (m) {
    $('addr').value = m[0];
    scan(m[0]);
  } else {
    $('results').innerHTML = '<span style="color:#fbbf24">No address found in URL.</span>';
  }
});
