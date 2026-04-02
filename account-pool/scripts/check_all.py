from datetime import datetime

from core.storage import init_db, get_conn
from core.health import basic_health_check

if __name__ == '__main__':
    init_db()
    with get_conn() as conn:
        rows = conn.execute('SELECT id, auth_file, cookie_file, status FROM accounts').fetchall()
        for account_id, auth_file, cookie_file, status in rows:
            result = basic_health_check(auth_file, cookie_file)
            new_status = status
            if result['ok'] and status == 'fresh':
                new_status = 'active'
            elif not result['ok']:
                new_status = 'limited'
            conn.execute(
                'UPDATE accounts SET status = ?, last_checked_at = ? WHERE id = ?',
                (new_status, datetime.now().isoformat(), account_id),
            )
            print(account_id, result)
