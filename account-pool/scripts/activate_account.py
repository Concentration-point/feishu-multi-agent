import json
from pathlib import Path

from core.storage import init_db, write_json
from core.selector import select_best_account

BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE_DIR / 'runtime'

if __name__ == '__main__':
    init_db()
    account = select_best_account()
    if not account:
        print('NO_ACCOUNT')
        raise SystemExit(1)

    payload = {
        'account_id': account[0],
        'label': account[1],
        'provider': account[2],
        'region': account[3],
        'status': account[4],
        'auth_file': account[6],
        'cookie_file': account[7],
    }
    write_json(RUNTIME_DIR / 'current_account.json', payload)

    auth_payload = {
        'source_account_id': account[0],
        'auth_file': account[6],
        'cookie_file': account[7],
    }
    write_json(RUNTIME_DIR / 'current_auth.json', auth_payload)
    print(json.dumps(payload, ensure_ascii=False))
