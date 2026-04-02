import argparse
import uuid
from datetime import datetime

from core.storage import init_db, get_conn
from registrars.mailtm import create_mailbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', default='openai')
    args = parser.parse_args()

    init_db()
    task_id = str(uuid.uuid4())
    mailbox = create_mailbox()
    now = datetime.now().isoformat()

    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO registration_tasks
            (id, email, mail_token, provider, status, stage, error_code, detail, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                task_id,
                mailbox.email or None,
                mailbox.token or None,
                args.provider,
                'ok' if mailbox.ok else 'failed',
                mailbox.stage,
                mailbox.error_code or None,
                mailbox.detail or None,
                now,
                now,
            ),
        )
    print({
        'task_id': task_id,
        'mailbox_ok': mailbox.ok,
        'email': mailbox.email,
        'stage': mailbox.stage,
        'error_code': mailbox.error_code,
    })


if __name__ == '__main__':
    main()
