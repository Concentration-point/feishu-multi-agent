# frontend-slides Vetting & Method Notes — 2026-04-30

## Source

- Repo: `zarazhangrui/frontend-slides`
- URL: `https://github.com/zarazhangrui/frontend-slides`
- Description: Claude Code skill for creating animation-rich HTML presentations from scratch or converting PPTX to web.
- Stars at review: `16045`
- Forks at review: `1304`
- Updated at review: `2026-04-29T16:07:12Z`

## Review Scope

Files downloaded to local review temp only, not installed or enabled:

- `SKILL.md`
- `STYLE_PRESETS.md`
- `viewport-base.css`
- `html-template.md`
- `animation-patterns.md`
- `scripts/extract-pptx.py`
- `scripts/export-pdf.sh`
- `scripts/deploy.sh`
- `.claude-plugin/marketplace.json`
- `plugins/frontend-slides/.claude-plugin/plugin.json`

## Security / Risk Notes

Risk level for **methodology reference only**: low.

Risk level if **installed and executed fully**: medium.

Reasons:

- Core skill is mostly Markdown/CSS/HTML guidance.
- `extract-pptx.py` reads a user-provided PPTX and writes extracted JSON/assets; requires `python-pptx`.
- Optional `export-pdf.sh` uses local browser automation / Playwright and may run `npm install playwright`.
- Optional `deploy.sh` uses Vercel CLI and may run `npm install -g vercel`, deploy files to Vercel, and creates public URLs.
- No evidence in reviewed files of reading `MEMORY.md`, `USER.md`, `SOUL.md`, `IDENTITY.md`, SSH keys, browser cookies, or credential stores.
- No install or enable action was performed.

## Do Not Auto-Use These Parts

- Do not run deployment flow without explicit user approval.
- Do not install Vercel CLI or Playwright without explicit approval.
- Do not deploy generated decks to public URLs by default.
- Do not convert local PPTX files unless user explicitly supplies / authorizes the file.

## Useful Methodology Absorbed

- Show, Don't Tell: generate visual previews so user chooses from real options.
- Anti-AI-Slop: avoid generic AI aesthetics such as Inter/Arial, purple gradient on white, default centered cards.
- Distinctive design: every presentation should feel context-specific.
- Viewport fitting: each slide must fit; if content overflows, split slides instead of cramming.
- Content density limits: restrict each slide type to a sane content maximum.
- Style presets: treat presets as design systems, not templates.

## Adaptation for Native PPT Workflow

Use frontend-slides as a design-system reference, not as a direct PPT executor:

```text
frontend-slides → visual discovery / design system
python-pptx or pptxgenjs → editable native PPT generation
image model → optional separate visual assets
PDF / preview export → validation
```

## Files Updated

- `PPT-GENERATION-SOP.md`: added frontend-slides methodology and style preset translation.
- `memory/skills-inventory.md`: recorded as evaluated / methodology absorbed, not installed.
