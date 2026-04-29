from pathlib import Path

PROJECT_TITLE = "AI-Generated PPT Workflow"
SUBTITLE = "Storyboard → Design System → Editable PPT → Validation"
AUTHOR = "OpenClaw"
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_FILE = OUTPUT_DIR / "deck.pptx"

# Pick one: calm_academic, bold_signal, swiss_tech, clean_friendly
THEME_PRESET = "calm_academic"

SLIDES = [
    {
        "type": "title",
        "title": PROJECT_TITLE,
        "subtitle": SUBTITLE,
        "meta": "PPT project template",
    },
    {
        "type": "agenda",
        "title": "Today’s Flow",
        "items": ["Material intake", "Storyboard", "Design system", "Native PPT build", "Validation"],
    },
    {
        "type": "section",
        "section_no": "01",
        "title": "Why native generation",
        "subtitle": "New-born decks are more stable than lossy edits of old templates.",
    },
    {
        "type": "three_cards",
        "title": "Core Rules",
        "cards": [
            {"title": "Editable", "body": "Titles, body text, labels and page numbers stay as PPT text boxes."},
            {"title": "Structured", "body": "Every slide comes from a storyboard and a reusable layout."},
            {"title": "Validated", "body": "Generation is not done until the deck passes structural checks."},
        ],
    },
    {
        "type": "process",
        "title": "Production Pipeline",
        "steps": ["Read", "Plan", "Design", "Build", "Validate"],
    },
    {
        "type": "summary",
        "title": "Takeaways",
        "points": [
            "Do not start by modifying a fragile old PPT.",
            "Use frontend-slides as design-system inspiration, not the final executor.",
            "Use python-pptx or pptxgenjs to produce editable native decks.",
        ],
    },
    {"type": "qa", "title": "Q&A"},
]
