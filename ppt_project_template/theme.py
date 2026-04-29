from dataclasses import dataclass
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

SLIDE_W = Inches(13.333333)
SLIDE_H = Inches(7.5)
MARGIN_X = Inches(0.65)
MARGIN_Y = Inches(0.45)

@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    panel: str
    primary: str
    accent: str
    text: str
    muted: str
    font_head: str
    font_body: str

THEMES = {
    "calm_academic": Theme(
        name="Calm Academic",
        bg="F7F8FA",
        panel="FFFFFF",
        primary="1F4E79",
        accent="D89A2B",
        text="222222",
        muted="6B7280",
        font_head="Microsoft YaHei",
        font_body="Microsoft YaHei",
    ),
    "bold_signal": Theme(
        name="Bold Signal Deck",
        bg="111111",
        panel="1A1A1A",
        primary="FF5722",
        accent="D4FF00",
        text="FFFFFF",
        muted="B8B8B8",
        font_head="Microsoft YaHei",
        font_body="Microsoft YaHei",
    ),
    "swiss_tech": Theme(
        name="Swiss Tech",
        bg="FFFFFF",
        panel="F1F5F9",
        primary="000000",
        accent="FF3300",
        text="111111",
        muted="64748B",
        font_head="Microsoft YaHei",
        font_body="Microsoft YaHei",
    ),
    "clean_friendly": Theme(
        name="Clean Friendly",
        bg="FAF9F7",
        panel="FFFFFF",
        primary="5A7C6A",
        accent="F0B4D4",
        text="1A1A1A",
        muted="667085",
        font_head="Microsoft YaHei",
        font_body="Microsoft YaHei",
    ),
}

def rgb(hex_color: str) -> RGBColor:
    h = hex_color.strip().lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

TITLE_SIZE = Pt(34)
SUBTITLE_SIZE = Pt(18)
BODY_SIZE = Pt(15)
SMALL_SIZE = Pt(10)
