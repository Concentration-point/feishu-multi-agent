from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_FILE = BASE_DIR / 'runtime' / 'current_auth.json'


def load_runtime_auth():
    if not RUNTIME_FILE.exists():
        return None
    return json.loads(RUNTIME_FILE.read_text(encoding='utf-8'))


if __name__ == '__main__':
    payload = load_runtime_auth()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
