#!/usr/bin/env python3
"""
STORAGE DB - SQLite persistence layer
=====================================
Persists scan history, findings, and watch-list addresses to SQLite.
Enables historical analysis, trend tracking, and avoiding redundant scans.

Tables:
  - addresses: tracked wallet addresses with metadata
  - scans:     individual scan runs (timestamp, duration, RPC stats)
  - findings:  balance findings discovered in each scan
  - alerts:    triggered alerts (when balances change)
  - contracts_cache: cached contract metadata

Usage:
    from storage_db import LostEthDB
    db = LostEthDB()
    db.add_address('0xAddr', label='My Old MetaMask')
    db.record_scan('0xAddr', findings, duration=1.5)
    print(db.get_history('0xAddr'))
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Optional

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lost_eth.db')


class LostEthDB:
    def __init__(self, path=DEFAULT_DB):
        self.path = path
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self):
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS addresses (
                    address TEXT PRIMARY KEY,
                    label TEXT,
                    added_at INTEGER NOT NULL,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    duration REAL,
                    rpc_calls INTEGER,
                    rpc_fails INTEGER,
                    findings_count INTEGER,
                    FOREIGN KEY (address) REFERENCES addresses(address)
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id INTEGER NOT NULL,
                    address TEXT NOT NULL,
                    chain TEXT,
                    contract TEXT,
                    contract_name TEXT,
                    token TEXT,
                    symbol TEXT,
                    amount_raw TEXT,
                    amount_decimal REAL,
                    timestamp INTEGER NOT NULL,
                    FOREIGN KEY (scan_id) REFERENCES scans(id)
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT NOT NULL,
                    type TEXT,
                    message TEXT,
                    timestamp INTEGER NOT NULL,
                    seen INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS contracts_cache (
                    address TEXT PRIMARY KEY,
                    chain TEXT NOT NULL,
                    code_size INTEGER,
                    selectors TEXT,
                    classification TEXT,
                    cached_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_findings_addr ON findings(address);
                CREATE INDEX IF NOT EXISTS idx_findings_chain ON findings(chain);
                CREATE INDEX IF NOT EXISTS idx_scans_addr ON scans(address);
                CREATE INDEX IF NOT EXISTS idx_alerts_addr ON alerts(address);
            """)

    def add_address(self, address: str, label: str = '', notes: str = ''):
        address = address.lower()
        with self._conn() as c:
            c.execute(
                'INSERT OR REPLACE INTO addresses (address, label, added_at, notes) VALUES (?,?,?,?)',
                (address, label, int(time.time()), notes)
            )

    def list_addresses(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute('SELECT * FROM addresses ORDER BY added_at DESC')]

    def record_scan(self, address: str, findings: list, duration: float = 0.0,
                    rpc_calls: int = 0, rpc_fails: int = 0):
        address = address.lower()
        with self._conn() as c:
            cur = c.execute(
                'INSERT INTO scans (address, timestamp, duration, rpc_calls, rpc_fails, findings_count) VALUES (?,?,?,?,?,?)',
                (address, int(time.time()), duration, rpc_calls, rpc_fails, len(findings))
            )
            scan_id = cur.lastrowid
            for f in findings:
                c.execute(
                    'INSERT INTO findings (scan_id, address, chain, contract, contract_name, token, symbol, amount_raw, amount_decimal, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (scan_id, address, f.get('chain'), f.get('contract'),
                     f.get('contract_name'), f.get('token'), f.get('symbol'),
                     str(f.get('amount_raw', '0')), float(f.get('amount', 0)),
                     int(time.time()))
                )
            return scan_id

    def get_history(self, address: str, limit: int = 50):
        address = address.lower()
        with self._conn() as c:
            scans = [dict(r) for r in c.execute(
                'SELECT * FROM scans WHERE address=? ORDER BY id DESC LIMIT ?',
                (address, limit)
            )]
            for s in scans:
                s['findings'] = [dict(r) for r in c.execute(
                    'SELECT * FROM findings WHERE scan_id=?', (s['id'],)
                )]
            return scans

    def detect_changes(self, address: str):
        """Compare last 2 scans, return changes."""
        address = address.lower()
        history = self.get_history(address, limit=2)
        if len(history) < 2:
            return []
        latest, previous = history[0], history[1]

        def fkey(f): return (f.get('contract'), f.get('token'))

        prev_map = {fkey(f): f for f in previous['findings']}
        latest_map = {fkey(f): f for f in latest['findings']}

        changes = []
        for k in set(prev_map) | set(latest_map):
            p, l = prev_map.get(k), latest_map.get(k)
            if not p:
                changes.append({'type': 'NEW', 'finding': l})
            elif not l:
                changes.append({'type': 'GONE', 'finding': p})
            elif p.get('amount_raw') != l.get('amount_raw'):
                changes.append({'type': 'CHANGED',
                                'before': p, 'after': l})
        return changes

    def add_alert(self, address: str, type_: str, message: str):
        with self._conn() as c:
            c.execute(
                'INSERT INTO alerts (address, type, message, timestamp) VALUES (?,?,?,?)',
                (address.lower(), type_, message, int(time.time()))
            )

    def get_alerts(self, address: Optional[str] = None, unseen_only: bool = True):
        with self._conn() as c:
            if address:
                q = 'SELECT * FROM alerts WHERE address=?'
                params = [address.lower()]
            else:
                q = 'SELECT * FROM alerts'
                params = []
            if unseen_only:
                q += ' AND seen=0' if 'WHERE' in q else ' WHERE seen=0'
            q += ' ORDER BY timestamp DESC'
            return [dict(r) for r in c.execute(q, params)]

    def cache_contract(self, address: str, chain: str, code_size: int = 0,
                       selectors: list = None, classification: str = ''):
        with self._conn() as c:
            c.execute(
                'INSERT OR REPLACE INTO contracts_cache (address, chain, code_size, selectors, classification, cached_at) VALUES (?,?,?,?,?,?)',
                (address.lower(), chain, code_size,
                 json.dumps(selectors or []), classification, int(time.time()))
            )

    def get_cached_contract(self, address: str, max_age_seconds: int = 86400):
        with self._conn() as c:
            row = c.execute(
                'SELECT * FROM contracts_cache WHERE address=? AND cached_at > ?',
                (address.lower(), int(time.time()) - max_age_seconds)
            ).fetchone()
            if row:
                d = dict(row)
                d['selectors'] = json.loads(d['selectors'] or '[]')
                return d
            return None

    def stats(self):
        with self._conn() as c:
            return {
                'addresses_tracked': c.execute('SELECT COUNT(*) FROM addresses').fetchone()[0],
                'total_scans': c.execute('SELECT COUNT(*) FROM scans').fetchone()[0],
                'total_findings': c.execute('SELECT COUNT(*) FROM findings').fetchone()[0],
                'unread_alerts': c.execute('SELECT COUNT(*) FROM alerts WHERE seen=0').fetchone()[0],
                'cached_contracts': c.execute('SELECT COUNT(*) FROM contracts_cache').fetchone()[0],
            }


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd')
    sub.add_parser('stats')
    a = sub.add_parser('add'); a.add_argument('address'); a.add_argument('--label', default='')
    h = sub.add_parser('history'); h.add_argument('address')
    sub.add_parser('list')
    args = p.parse_args()

    db = LostEthDB()
    if args.cmd == 'stats':
        print(json.dumps(db.stats(), indent=2))
    elif args.cmd == 'add':
        db.add_address(args.address, args.label)
        print(f'Added {args.address}')
    elif args.cmd == 'list':
        for a in db.list_addresses():
            print(f'  {a["address"]}  "{a["label"]}"  added {time.strftime("%Y-%m-%d", time.gmtime(a["added_at"]))}')
    elif args.cmd == 'history':
        for s in db.get_history(args.address):
            print(f'  scan {s["id"]} at {time.strftime("%Y-%m-%d %H:%M", time.gmtime(s["timestamp"]))}: {s["findings_count"]} findings')
            for f in s['findings']:
                print(f'    [{f["chain"]}] {f["contract_name"] or f["contract"][:10]}  {f["amount_decimal"]} {f["symbol"]}')
    else:
        p.print_help()
