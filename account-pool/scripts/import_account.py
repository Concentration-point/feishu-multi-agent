import argparse
import shutil
from datetime import datetime
from pathlib import Path

from core.storage import init_db, get_conn, write_json

BASE_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = BASE_DIR / 'data' / 'accounts'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--provider', default='openai')
    parser.add_argument('--region', default='')
    parser.add_argument('--auth-file', default='')
    parser.add_argument('--cookie-file', default='')
    parser.add_argument('--notes', default='')
    args = parser.parse_args()

    init_db()
    account_dir = ACCOUNTS_DIR / args.id
    account_dir.mkdir(parents=True, exist_ok=True)

    auth_target = ''
    if args.auth_file:
        auth_src = Path(args.auth_file)
        auth_target = str((account_dir / auth_src.name).resolve())
        shutil.copy2(auth_src, auth_target)

    cookie_target = ''
    if args.cookie_file:
        cookie_src = Path(args.cookie_file)
        cookie_target = str((account_dir / cookie_src.name).resolve())
        shutil.copy2(cookie_src, cookie_target)

    meta = {
        'id': args.id,
        'label': args.label,
        'provider': args.provider,
        'region': args.region,
        'created_at': datetime.now().isoformat(),
        'notes': args.notes,
    }
    write_json(account_dir / 'meta.json', meta)

    with get_conn() as conn:
        conn.execute(
            '''
            INSERT OR REPLACE INTO accounts
            (id, label, provider, region, status, priority, auth_file, cookie_file, created_at, notes)
            VALUES (?, ?, ?, ?, 'fresh', 100, ?, ?, ?, ?)
            ''',
            (args.id, args.label, args.provider, args.region or None, auth_target or None, cookie_target or None, datetime.now().isoformat(), args.notes or None)
        )
    print(f'imported {args.id}')


if __name__ == '__main__':
    main()
