import argparse
import subprocess
import sys
from datetime import datetime

from core.storage import init_db, get_conn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--proxy', default='')
    args = parser.parse_args()

    init_db()
    with get_conn() as conn:
        row = conn.execute('SELECT email FROM registration_tasks WHERE id = ?', (args.task_id,)).fetchone()
        if not row:
            raise SystemExit('TASK_NOT_FOUND')
        email = row[0]

    cmd = [
        sys.executable,
        'account-pool\\registrars\\openai_signup_flow.py',
        '--email',
        email,
    ]
    if args.proxy:
        cmd.extend(['--proxy', args.proxy])

    result = subprocess.run(cmd, capture_output=True, text=True, cwd='C:\\Users\\25723\\.openclaw\\workspace')

    with get_conn() as conn:
        conn.execute(
            'UPDATE registration_tasks SET status = ?, stage = ?, detail = ?, updated_at = ? WHERE id = ?',
            (
                'signup_started' if result.returncode == 0 else 'signup_failed',
                'openai_signup_flow',
                result.stdout[-4000:] if result.stdout else result.stderr[-4000:],
                datetime.now().isoformat(),
                args.task_id,
            ),
        )

    print(result.stdout if result.stdout else result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
