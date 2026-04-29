from pptx import Presentation
from theme import SLIDE_W, SLIDE_H, THEMES
from config import OUTPUT_DIR, OUTPUT_FILE, THEME_PRESET, SLIDES
from slides import BUILDERS


def build():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    theme = THEMES[THEME_PRESET]

    for idx, data in enumerate(SLIDES, 1):
        slide_type = data.get("type")
        if slide_type not in BUILDERS:
            raise ValueError(f"Unknown slide type: {slide_type}")
        BUILDERS[slide_type](prs, theme, data, idx)

    prs.save(OUTPUT_FILE)
    print(f"Wrote {OUTPUT_FILE} ({len(SLIDES)} slides)")


if __name__ == "__main__":
    build()
