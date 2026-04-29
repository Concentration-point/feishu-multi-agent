from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import textwrap, json

ROOT = Path('deckforge_output/surgical_robot_aesthetic_regression')
ROOT.mkdir(parents=True, exist_ok=True)
OUT = ROOT / 'aesthetic_regression_contact_sheet.png'

W, H = 480, 270
PAD = 18
GAP = 18
COLS, ROWS = 4, 3
SHEET_W = COLS * W + (COLS + 1) * GAP
SHEET_H = ROWS * H + (ROWS + 1) * GAP + 70

try:
    FONT_HEAD = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 26)
    FONT_BODY = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 16)
    FONT_SMALL = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 12)
    FONT_MONO = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 14)
except Exception:
    FONT_HEAD = FONT_BODY = FONT_SMALL = FONT_MONO = ImageFont.load_default()

slides = [
    ('封面', '专利权利要求 + 引文\n技术起源与演化分析', ['Qiu & Wang · AEI 2023', 'Surgical robot domain']),
    ('方法框架', 'Claims + Citations', ['Patent data', 'TI: claim inheritance', 'TEP: persistence', 'Main path', 'Origin analysis']),
    ('案例发现', '四条技术主路径', ['定位与切割', 'X-ray / scanning', '眼科与头部手术', '骨科定位操作']),
    ('结论', 'Claim-level 视角让技术融合可解释', ['贡献：TI / TEP / Main Path', '发现：定位 + 影像 + 导航', '局限：claim 结构与 NLP'])
]

styles = [
    {
        'name': 'Calm Academic',
        'tag': '冷静学术：适合课堂论文汇报',
        'bg': '#F7F8FA', 'panel': '#FFFFFF', 'text': '#222222', 'muted': '#6B7280', 'primary': '#1F4E79', 'accent': '#D89A2B',
        'mode': 'academic'
    },
    {
        'name': 'Swiss Tech',
        'tag': '瑞士网格：技术感、结构化、少废话',
        'bg': '#FFFFFF', 'panel': '#F1F5F9', 'text': '#111111', 'muted': '#64748B', 'primary': '#000000', 'accent': '#FF3300',
        'mode': 'swiss'
    },
    {
        'name': 'Bold Signal',
        'tag': '强信号：深色高冲击，反 AI 味',
        'bg': '#111111', 'panel': '#1C1C1C', 'text': '#FFFFFF', 'muted': '#B8B8B8', 'primary': '#FF5722', 'accent': '#D4FF00',
        'mode': 'bold'
    },
]

def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2],16) for i in (0,2,4))

def draw_wrapped(draw, xy, text, font, fill, max_width, line_gap=4):
    x,y = xy
    # crude mixed CJK/English wrap by display chars
    lines=[]
    for para in text.split('\n'):
        cur=''
        for ch in para:
            test=cur+ch
            if draw.textbbox((0,0), test, font=font)[2] <= max_width:
                cur=test
            else:
                if cur: lines.append(cur)
                cur=ch
        if cur: lines.append(cur)
    for line in lines:
        draw.text((x,y), line, font=font, fill=fill)
        y += font.size + line_gap
    return y

def rounded(draw, box, r, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)

def draw_slide(style, slide):
    img = Image.new('RGB', (W,H), hex_to_rgb(style['bg']))
    d = ImageDraw.Draw(img)
    bg=hex_to_rgb(style['bg']); panel=hex_to_rgb(style['panel']); text=hex_to_rgb(style['text']); muted=hex_to_rgb(style['muted']); primary=hex_to_rgb(style['primary']); accent=hex_to_rgb(style['accent'])
    label, title, items = slide
    mode = style['mode']
    if mode == 'academic':
        rounded(d, (20,20,W-20,H-20), 18, panel)
        d.rectangle((20,20,30,H-20), fill=primary)
        d.text((42,34), label.upper(), font=FONT_SMALL, fill=accent)
        draw_wrapped(d, (42,70), title, FONT_HEAD, primary, W-90)
        y=145
        for it in items[:4]:
            d.ellipse((46,y+5,54,y+13), fill=accent)
            y = draw_wrapped(d, (66,y), it, FONT_BODY, text, W-110, 3) + 4
    elif mode == 'swiss':
        # visible grid
        for x in range(30, W, 60): d.line((x,22,x,H-22), fill=(235,238,242), width=1)
        for y in range(30, H, 48): d.line((22,y,W-22,y), fill=(235,238,242), width=1)
        d.rectangle((28,28,88,36), fill=accent)
        d.text((28,48), label, font=FONT_SMALL, fill=primary)
        draw_wrapped(d, (118,46), title, FONT_HEAD, primary, W-150)
        y=145
        for i,it in enumerate(items[:4],1):
            d.text((118,y), f'{i:02d}', font=FONT_MONO, fill=accent)
            y = draw_wrapped(d, (158,y-1), it, FONT_BODY, text, W-185, 3) + 3
    else:
        # bold signal: dark + strong card
        d.rectangle((0,0,W,H), fill=bg)
        rounded(d, (32,35,W-38,H-35), 22, panel)
        rounded(d, (55,58,200,130), 18, primary)
        d.text((75,80), label, font=FONT_BODY, fill=(20,20,20))
        draw_wrapped(d, (55,150), title, FONT_HEAD, text, W-100)
        y=78
        for it in items[:3]:
            rounded(d, (230,y, W-58, y+28), 12, (38,38,38), outline=accent, width=1)
            draw_wrapped(d, (244,y+5), it, FONT_SMALL, text, W-300, 2)
            y += 42
    return img

sheet = Image.new('RGB', (SHEET_W, SHEET_H), (245,246,248))
d = ImageDraw.Draw(sheet)
d.text((GAP, 16), 'PPT Aesthetic Regression · same content, three style systems', font=FONT_HEAD, fill=(20,25,35))
d.text((GAP, 48), 'Goal: verify frontend-slides methodology — Show, Don’t Tell / Anti-AI-Slop / density limits / design systems', font=FONT_BODY, fill=(80,88,105))

for r, style in enumerate(styles):
    y0 = GAP + 70 + r*(H+GAP)
    d.text((GAP, y0-18), f"{style['name']} · {style['tag']}", font=FONT_BODY, fill=hex_to_rgb(style['primary']) if style['mode']!='bold' else (40,40,40))
    for c, sl in enumerate(slides):
        x0 = GAP + c*(W+GAP)
        tile = draw_slide(style, sl)
        sheet.paste(tile, (x0, y0))

sheet.save(OUT)

report = {
    'styles': [{'name': s['name'], 'tag': s['tag']} for s in styles],
    'slides': [s[0] for s in slides],
    'criteria': ['font personality', 'color memory', 'anti AI-slop', 'density comfort', 'story clarity'],
    'recommended_for_this_paper': 'Calm Academic for classroom; Swiss Tech if the audience is technical; Bold Signal for pitch-style presentation.'
}
(ROOT/'aesthetic_regression_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(OUT)
