# PPT Project Template

A minimal native editable PPT generation template for OpenClaw / coding agents.

## Files

```text
build.py              # Entry point; creates output/deck.pptx
config.py             # Deck metadata and slide content
theme.py              # Colors, fonts, sizes, margins
layouts.py            # Reusable slide layout helpers
slides.py             # Slide assembly functions
validate.py           # Structural validation for generated pptx
export_preview.py     # Optional PDF/PNG preview export hook
assets/               # Images/icons
output/               # Generated deck and previews
```

## Quick Start

```bash
pip install python-pptx
python build.py
python validate.py output/deck.pptx --expected-slides 7
```

## Workflow

1. Edit `config.py` content and theme preset.
2. Run `python build.py`.
3. Run `python validate.py output/deck.pptx --expected-slides N`.
4. Export PDF/preview if available.
5. Only then report completion.

## Rules

- Keep all important text editable.
- Do not bake Chinese text into images.
- Split overflowing content into more slides.
- Use a design system; do not freestyle every slide.
