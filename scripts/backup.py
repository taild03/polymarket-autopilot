#!/usr/bin/env python3
"""Create a consistent SQLite backup without stopping the worker."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import DB_PATH

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DB_PATH.parent / 'backups')
    args = parser.parse_args()
    if not DB_PATH.exists():
        parser.error('Database is not initialized')
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / (datetime.now(timezone.utc).strftime('autopilot-%Y%m%dT%H%M%S%fZ') + '.db')
    with sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup integrity check failed')
    target.chmod(0o600)
    print(target)
