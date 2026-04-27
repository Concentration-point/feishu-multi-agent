from pathlib import Path
import subprocess, json, re, sys

results=[]

def ok(name, passed, detail):
    results.append((name, passed, detail))

# 1. Rules exist
checks=[
    ('AGENTS.md','Retrieval Escalation Rule'),
    ('AGENTS.md','Skill Activation Contract'),
    ('AGENTS.md','Feishu Formatting Contract'),
    ('memory/skills-inventory.md','日常贯彻矩阵'),
    ('.learnings/LEARNINGS.md','retrieval.auto.escalate.real-browser'),
]
for f,s in checks:
    text=Path(f).read_text(encoding='utf-8-sig', errors='replace')
    ok(f'规则存在: {s}', s in text, f)

# 2. Git commits exist
log=subprocess.check_output(['git','log','--oneline','-5'], text=True, encoding='utf-8', errors='replace')
for s in ['auto-escalate blocked retrieval to browser','standardize feishu reply formatting','operationalize skill usage']:
    ok(f'提交存在: {s}', s in log, s)

# 3. Simulated retrieval routing decision
failure_signals=['Blocked: resolves to private/internal/special-use IP address','mp/wappoc_appmsgcaptcha','(empty page)','captcha','正文缺失']
def should_escalate(msg):
    m=msg.lower()
    return any(x.lower() in m for x in ['blocked','captcha','empty page','正文缺失','wappoc_appmsgcaptcha','js 渲染缺正文'])
for sig in failure_signals:
    ok(f'检索失败信号触发浏览器: {sig[:28]}', should_escalate(sig), sig)

# 4. Feishu formatting lint for a sample reply: no markdown headings, no deep bullets
sample='''**结论**\n这是一段短回复。\n\n**下一步**\n- 做 A\n- 做 B\n'''
ok('飞书样例无 Markdown 大标题', not re.search(r'(?m)^#{1,6}\s+', sample), 'no # headings')
ok('飞书样例无二级缩进列表', not re.search(r'(?m)^\s{2,}-\s+', sample), 'no nested bullets')

passed=sum(1 for _,p,_ in results if p)
print(f'SKILL_OPERATIONALIZATION_SMOKE {passed}/{len(results)} passed')
for name,p,detail in results:
    print(('PASS' if p else 'FAIL'), '-', name, '|', detail)
if passed != len(results):
    sys.exit(1)
