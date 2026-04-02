import argparse
from datetime import datetime

from core.storage import init_db, get_conn
from registrars.mailtm import wait_openai_otp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--max-polls', type=int, default=40)
    parser.add_argument('--poll-interval', type=int, default=3)
    args = parser.parse_args()

    init_db()
    with get_conn() as conn:
        row = conn.execute(
            'SELECT email, mail_token FROM registration_tasks WHERE id = ?',
            (args.task_id,),
        ).fetchone()
        if not row:
            raise SystemExit('TASK_NOT_FOUND')
        email, token = row

    result = wait_openai_otp(token=token, email=email, max_polls=args.max_polls, poll_interval=args.poll_interval)
    with get_conn() as conn:
        conn.execute(
            'UPDATE registration_tasks SET status = ?, stage = ?, error_code = ?, detail = ?, updated_at = ? WHERE id = ?',
            (
                'otp_ready' if result.ok else 'failed',
                result.stage,
                result.error_code or None,
                result.otp_code if result.ok else result.detail,
                datetime.now().isoformat(),
                args.task_id,
            ),
        )
    print({
        'task_id': args.task_id,
        'otp_ok': result.ok,
        'otp_code': result.otp_code,
        'error_code': result.error_code,
    })


if __name__ == '__main__':
    main()
