from pathlib import Path
import re, sys
text = Path('IMAGE-GENERATION-SOP.md').read_text(encoding='utf-8-sig')
checks = [
    'Prompt Mode Router',
    'Raw Prompt Mode',
    'Minimal Compile Mode',
    'Design Rewrite Mode',
    'A/B 生成策略',
    'Prompt Mutation Lint',
    '不默认重写',
]
missing = [c for c in checks if c not in text]
print(f'IMAGE_PROMPT_ROUTER_SMOKE {len(checks)-len(missing)}/{len(checks)} passed')
for c in checks:
    print(('PASS' if c not in missing else 'FAIL'), '-', c)
if missing:
    sys.exit(1)
