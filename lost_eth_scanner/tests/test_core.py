"""
Test suite for the Lost ETH Scanner core modules.
Run with: pytest tests/ -v
"""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scanner_v2 import load_config, encode_addr
from bytecode_analyzer import extract_selectors, extract_opcodes, detect_proxy_patterns, classify_contract
from storage_db import LostEthDB


def test_chains_loaded():
    chains, contracts, tokens = load_config()
    assert len(chains) >= 8
    assert 'ethereum' in chains
    assert 'arbitrum' in chains
    assert chains['ethereum']['chain_id'] == 1
    assert chains['arbitrum']['chain_id'] == 42161


def test_contracts_loaded():
    chains, contracts, tokens = load_config()
    assert len(contracts) >= 100
    # Each contract has required fields
    for c in contracts:
        assert 'address' in c
        assert c['address'].startswith('0x')
        assert len(c['address']) == 42
        assert 'chain' in c


def test_tokens_loaded():
    chains, contracts, tokens = load_config()
    assert len(tokens) >= 6
    eth_tokens = tokens.get('ethereum', {})
    assert len(eth_tokens) >= 30
    # Each token entry has [symbol, decimals]
    for addr, meta in eth_tokens.items():
        assert addr.startswith('0x')
        assert isinstance(meta, list)
        assert len(meta) == 2
        assert isinstance(meta[1], int)


def test_encode_addr():
    a = '0xd3301469347BaD6A767b2bf4af5Da486eeFb4cdf'
    encoded = encode_addr(a)
    assert len(encoded) == 64
    assert encoded == '000000000000000000000000d3301469347bad6a767b2bf4af5da486eefb4cdf'


def test_extract_selectors():
    # Synthetic bytecode containing PUSH4 (0x63) + 4 bytes
    code = '0x6080604052' + '6370a08231' + '6018160ddd' + '5f5ffd'
    sels = extract_selectors(code)
    assert '0x70a08231' in sels  # balanceOf(address)


def test_extract_opcodes():
    # Bytecode with SELFDESTRUCT (0xff) and DELEGATECALL (0xf4)
    code = '0x60806040ff60f4'
    ops = extract_opcodes(code)
    assert 'SELFDESTRUCT' in ops
    assert 'DELEGATECALL' in ops


def test_detect_proxy_patterns():
    # EIP-1167 minimal proxy bytecode contains the magic pattern
    eip1167 = '0x363d3d373d3d3d363d731234567890123456789012345678901234567890'
    flags = detect_proxy_patterns(eip1167)
    assert any('1167' in f for f in flags)


def test_classify_contract_etherdelta():
    decoded = {
        '0xf3fef3a3': 'withdraw(address,uint256)',
        '0x508493bc': 'tokens(address,address)',
        '0x2295115b': 'adminWithdraw(address,uint256,address,uint256,uint8,bytes32,bytes32,uint256)',
        '0xef343588': 'trade(uint256[8],address[4],uint8[2],bytes32[4])',
        '0x65e17c9d': 'feeAccount()',
    }
    cls = classify_contract(decoded, {}, [])
    assert any('EtherDelta' in c for c in cls) or any('DEX' in c for c in cls)


def test_classify_contract_erc20():
    decoded = {
        '0xa9059cbb': 'transfer(address,uint256)',
        '0x70a08231': 'balanceOf(address)',
        '0x18160ddd': 'totalSupply()',
        '0x06fdde03': 'name()',
    }
    cls = classify_contract(decoded, {}, [])
    assert any('ERC-20' in c for c in cls)


def test_storage_db_basic(tmp_path):
    db = LostEthDB(path=str(tmp_path / 'test.db'))
    db.add_address('0xabc1234567890123456789012345678901234567', label='test')
    addrs = db.list_addresses()
    assert len(addrs) == 1
    assert addrs[0]['address'] == '0xabc1234567890123456789012345678901234567'
    stats = db.stats()
    assert stats['addresses_tracked'] == 1
    assert stats['total_scans'] == 0


def test_storage_db_record_scan(tmp_path):
    db = LostEthDB(path=str(tmp_path / 'test.db'))
    addr = '0xabc1234567890123456789012345678901234567'
    db.add_address(addr)
    findings = [
        {'chain': 'ethereum', 'contract': '0x123', 'contract_name': 'TestDEX',
         'token': '0x0', 'symbol': 'ETH', 'amount_raw': '1000000000000000000', 'amount': 1.0},
    ]
    scan_id = db.record_scan(addr, findings, duration=1.5, rpc_calls=10, rpc_fails=0)
    assert scan_id > 0
    history = db.get_history(addr)
    assert len(history) == 1
    assert history[0]['findings_count'] == 1
    assert len(history[0]['findings']) == 1


def test_storage_db_change_detection(tmp_path):
    db = LostEthDB(path=str(tmp_path / 'test.db'))
    addr = '0xabc1234567890123456789012345678901234567'
    db.add_address(addr)
    # First scan: 1 finding
    db.record_scan(addr, [
        {'chain': 'ethereum', 'contract': '0x123', 'token': '0x0', 'amount_raw': '1000', 'amount': 0.001},
    ])
    # Second scan: 2 findings, one new + one changed
    db.record_scan(addr, [
        {'chain': 'ethereum', 'contract': '0x123', 'token': '0x0', 'amount_raw': '2000', 'amount': 0.002},
        {'chain': 'ethereum', 'contract': '0x456', 'token': '0x0', 'amount_raw': '500', 'amount': 0.0005},
    ])
    changes = db.detect_changes(addr)
    types = {c['type'] for c in changes}
    assert 'NEW' in types
    assert 'CHANGED' in types


def test_airdrops_data():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from airdrop_checker import AIRDROPS
    assert len(AIRDROPS) >= 18
    for ad in AIRDROPS:
        assert 'name' in ad
        # most have token addresses
        if ad.get('chain') != 'solana':
            assert 'date' in ad


def test_nft_collections_data():
    from nft_scanner import NFT_COLLECTIONS
    assert len(NFT_COLLECTIONS) >= 30
    for col in NFT_COLLECTIONS:
        assert col['address'].startswith('0x')
        assert len(col['address']) == 42
