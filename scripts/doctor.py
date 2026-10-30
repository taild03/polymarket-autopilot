#!/usr/bin/env python3
"""Read-only checks. --network verifies public Gamma/CLOB without placing paper orders."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import DB_PATH, STATE_JSON_PATH
from src.polymarket_client import PolymarketClient


def probe_books(client, markets, max_checks=8):
    candidates = sorted((m for m in markets if m.yes_token_id and not m.closed),
                        key=lambda m: (m.days_to_expiry > 0, m.liquidity_usd, m.volume_24h_usd), reverse=True)
    checked, reachable, liquid = 0, 0, False
    seen = set()
    for market in candidates:
        if market.yes_token_id in seen:
            continue
        seen.add(market.yes_token_id)
        book = client.fetch_clob_book_top(market.yes_token_id)
        checked += 1
        if book is not None:
            reachable += 1
            if book['bids'] and book['asks']:
                liquid = True
                break
        if checked >= max_checks:
            break
    return {'status': 'ok' if reachable else 'unavailable',
            'books_checked': checked, 'books_reachable': reachable,
            'two_sided_liquidity_found': liquid}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network', action='store_true')
    args = parser.parse_args()
    checks = {'python': sys.version.split()[0], 'node': bool(shutil.which('node')), 'npm': bool(shutil.which('npm')),
              'data_directory': str(DB_PATH.parent), 'database': 'not_initialized', 'snapshot': 'not_initialized'}
    ok = True
    if DB_PATH.exists():
        try:
            with sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True) as conn:
                checks['database'] = conn.execute('PRAGMA integrity_check').fetchone()[0]
            ok &= checks['database'] == 'ok'
        except sqlite3.Error as exc:
            checks['database'] = str(exc)
            ok = False
    if STATE_JSON_PATH.exists():
        try:
            state = json.loads(STATE_JSON_PATH.read_text())
            checks['snapshot'] = {'generated_at': state['generated_at'], 'data_source': state['data_source'], 'equity': state['metrics']['total_equity_usdc']}
        except (ValueError, KeyError) as exc:
            checks['snapshot'] = str(exc)
            ok = False
    if args.network:
        checks['dns'] = {}
        for host in ('gamma-api.polymarket.com', 'clob.polymarket.com'):
            try: checks['dns'][host] = sorted({r[4][0] for r in socket.getaddrinfo(host, 443)})
            except OSError as exc: checks['dns'][host] = str(exc)
        client = PolymarketClient()
        markets = client.fetch_active_markets(limit=10)
        checks['gamma'] = client.last_source
        live = client.last_source == 'LIVE_POLYMARKET_GAMMA_API'
        checks['server_time'] = client.server_now.isoformat() if client.server_now else None
        probe = probe_books(client, markets) if live else {'status': 'unavailable'}
        checks['clob'] = probe['status']
        checks['clob_probe'] = probe
        ok &= live and checks['clob'] == 'ok'
    print(json.dumps(checks, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
