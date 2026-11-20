"""Contrast of each status label's text against its own background, in colour
and in greyscale (WCAG 2 formula; text = the pixel farthest from the background)."""
import sys, pathlib, json
from collections import Counter
from PIL import Image

def lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)

def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

def measure(p):
    im = Image.open(p).convert('RGB')
    px = list(im.getdata())
    bg = Counter(px).most_common(1)[0][0]
    return round(max(contrast(bg, c) for c in set(px)), 2), bg

d = pathlib.Path(sys.argv[1])
rows = {}
for f in sorted(d.glob('*__colour.png')):
    key = f.name[: -len('__colour.png')]
    rows[key] = {'colour': measure(f)[0], 'grey': measure(d / f'{key}__grey.png')[0]}
for k, v in rows.items():
    print(f"{k:60s} colour {v['colour']:5.2f}:1  greyscale {v['grey']:5.2f}:1")
json.dump(rows, open(d / 'contrast.json', 'w'), indent=2)
