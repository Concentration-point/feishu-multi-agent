from datetime import datetime
from pathlib import Path


def basic_health_check(auth_file: str | None, cookie_file: str | None):
    issues = []
    if not auth_file:
        issues.append('missing_auth_file')
    elif not Path(auth_file).exists():
        issues.append('auth_file_not_found')
    if cookie_file and not Path(cookie_file).exists():
        issues.append('cookie_file_not_found')
    return {
        'checked_at': datetime.now().isoformat(),
        'ok': len(issues) == 0,
        'issues': issues,
    }
