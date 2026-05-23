#!/usr/bin/env python3
"""
Fetches verified source code for high-value targets via Sourcify (free, no API key)
and saves them to ./sources/ for manual review of withdraw() logic.
"""
import os, json, ssl, urllib.request, time
import certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, 'sources')
os.makedirs(OUT_DIR, exist_ok=True)

# (chain_id, address, label) - high-priority candidates with native balance + withdraw()
TARGETS = [
    (1, '0xbf4ed7b27f1d666546e30d74d50d173d20bca754', 'WithdrawDAO'),
    (1, '0xB3775fB83F7D12A36E0475aBdD1FCA35c091efBe', 'PoWH3D'),
    (1, '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB', 'CryptoPunksMarketplace'),
    (1, '0x6BA6f2207e343923BA692e5Cae646Fb0F566DB8D', 'CryptoPunksOld'),
    (1, '0xd5524179cB7AE012f5B642C1D6D700Bbaa76B96b', 'AugurV1Cash'),
    (1, '0xE0B7927c4aF23765Cb51314A0E0521A9645F0E2A', 'DigixDAO'),
    (1, '0xb8901acB165ed027E32754E0FFe830802919727f', 'HopBridgeL1Old'),
    (1, '0x4Ddc2D193948926D02f9B1fE9e1daa0718270ED5', 'BabbageCompoundCETH'),
    (1, '0xDC24316b9AE028F1497c275EB9192a3Ea0f67022', 'CurveStETHPool'),
    (1, '0xA160cdAB225685dA1d56aa342Ad8841c3b53f291', 'TornadoCash100ETH'),
    (1, '0xb8c4Bd1bBD4f5ACAa55B18b3Ad9d3D72E08D5e8b', 'AcrossV1OptimisticOracle'),
    (1, '0x256C8919CE1AB0e33974CF6AA9c71561Ef3017b6', 'AcrossV1'),
    (1, '0x2796317b0fF8538F253012862c06787Adfb8cEb6', 'SynapseOldBridge'),
    (1, '0x88A69B4E698A4B090DF6CF5Bd7B2D47325Ad30A3', 'NomadBridge'),
    (1, '0xB21f8684f23Dbb1008508B4DE91a0aaEDEbdB7E4', 'Etheria'),
    (1, '0x12459C951127e0c374FF9105DdA097662A027093', '0xv1Exchange'),
    (1, '0x172E09691DfBbC035E37c73B62095caa16Ee2388', 'SynthetixDepot'),
    (1, '0x3FDA67f7583380E67ef93072294a7fAc882FD7E7', 'CompoundV1cETH'),
    (1, '0x448a5065aeBB8E423F0896E6c5D525C040f59af3', 'MakerSAITub'),
    (1, '0x8484Ef722627bf18ca5Ae6BcF031c23E6e922B30', 'PolygonPoSBridgeETH'),
    (1, '0x401F6c983eA34274ec46f84D70b31C151321188b', 'PolygonPlasmaBridge'),
    (1, '0x1A2a1c938CE3eC39b6D47113c7955bAa9DD454F2', 'RoninBridgeOld'),
    (1, '0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208', 'IDEX1'),
    (1, '0x8d12A197cB00D4747a1fe03395095ce2A5CC6819', 'ForkDeltaEtherDeltaV3'),
    (1, '0x1ce7AE555139c5EF5A57CC8d814a867ee6Ee33D8', 'TokenStore'),
    (1, '0x1E0447b19BB6EcFdAe1e4AE1694b0C3659614e4e', 'dYdXSoloV1'),
    (8453, '0xCF205808Ed36593aa40a44F10c7f7C2F67d4A4d4', 'FriendTech'),
    (137, '0xa3Fa99A148fA48D14Ed51d610c367C61876997F1', 'QiDaoOld'),
    (137, '0xBA12222222228d8Ba445958a75a0704d566BF2C8', 'BalancerV2Vault'),
    (1284, '0x96b244391D98B62D19aE89b1A4dCcf0fc56970C7', 'BeamswapMoonbeam'),
]


def get_url(url, timeout=20):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; sourcefetcher/1.0)',
        'Accept': 'application/json'
    })
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode('utf-8', errors='replace')


def try_sourcify(chain_id, addr):
    """Try Sourcify full_match then partial_match."""
    addr = addr.lower()
    for match in ('full_match', 'partial_match'):
        try:
            url = f'https://repo.sourcify.dev/contracts/{match}/{chain_id}/{addr}/'
            # First check metadata.json
            meta_url = url + 'metadata.json'
            txt = get_url(meta_url, timeout=12)
            return ('sourcify_' + match, txt, url)
        except Exception:
            pass
    return None


def try_etherscan_api(chain_id, addr):
    """Try Etherscan v2 unified API (requires API key for full access, but anonymous gives basic)."""
    # Map chain_id to Etherscan-family base URL
    api_map = {
        1: 'https://api.etherscan.io/api',
        8453: 'https://api.basescan.org/api',
        137: 'https://api.polygonscan.com/api',
        56: 'https://api.bscscan.com/api',
        42161: 'https://api.arbiscan.io/api',
        10: 'https://api-optimistic.etherscan.io/api',
        43114: 'https://api.snowtrace.io/api',
        1284: 'https://api-moonbeam.moonscan.io/api',
        100: 'https://api.gnosisscan.io/api',
    }
    base = api_map.get(chain_id)
    if not base:
        return None
    try:
        url = f'{base}?module=contract&action=getsourcecode&address={addr}'
        txt = get_url(url, timeout=20)
        d = json.loads(txt)
        if d.get('status') == '1' and d.get('result'):
            res = d['result'][0]
            if res.get('SourceCode'):
                return ('etherscan', json.dumps(res, indent=2), url)
    except Exception:
        pass
    return None


def main():
    summary = []
    for i, (cid, addr, label) in enumerate(TARGETS):
        out_file = os.path.join(OUT_DIR, f'{label}.txt')
        if os.path.exists(out_file) and os.path.getsize(out_file) > 500:
            print(f'  [{i+1:2d}/{len(TARGETS)}] {label:30s} -- already cached')
            continue
        print(f'  [{i+1:2d}/{len(TARGETS)}] {label:30s} {addr}')
        result = try_sourcify(cid, addr) or try_etherscan_api(cid, addr)
        if result:
            src, content, url = result
            with open(out_file, 'w') as f:
                f.write(f'# Source: {src}\n# URL: {url}\n# Address: {addr}\n# Chain: {cid}\n\n')
                f.write(content)
            print(f'      -> got from {src} ({len(content)} bytes)')
            summary.append((label, src, len(content)))
        else:
            print(f'      -> NOT FOUND in any source')
            with open(out_file, 'w') as f:
                f.write(f'# NOT FOUND - addr={addr} chain={cid}\n')
            summary.append((label, 'not_found', 0))
        time.sleep(0.3)

    print(f'\n[*] Summary:')
    for label, src, size in summary:
        print(f'    {label:35s} {src:25s} {size:>10,} bytes')


if __name__ == '__main__':
    main()
