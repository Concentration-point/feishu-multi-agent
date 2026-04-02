from datetime import datetime
from .storage import get_conn

BLOCKED = {'cooling', 'challenged', 'dead'}
PREFERRED = {'active', 'fresh', 'limited'}


def select_best_account(provider: str | None = None):
    sql = 'SELECT id, label, provider, region, status, priority, auth_file, cookie_file, created_at, last_checked_at, last_success_at, last_failure_at, failure_count, cooldown_until, notes FROM accounts'
    params = []
    if provider:
        sql += ' WHERE provider = ?'
        params.append(provider)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    candidates = []
    now = datetime.now().isoformat()
    for row in rows:
        status = row[4]
        cooldown_until = row[13]
        if status in BLOCKED:
            continue
        if cooldown_until and cooldown_until > now:
            continue
        candidates.append(row)
    if not candidates:
        return None
    status_rank = {'active': 0, 'fresh': 1, 'limited': 2}
    candidates.sort(key=lambda r: (status_rank.get(r[4], 9), r[5], -(r[12] or 0)))
    return candidates[0]
