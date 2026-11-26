"""U1: WCAG 2.2 contrast from labels_raw.json (colour and greyscale), label inventory, axe summary."""
import json, collections
import vlib
d = json.load(open(vlib.EVIDENCE / "U1" / "labels_raw.json"))
def lin(v):
    v /= 255; return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
def L(c): return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])
def cr(a, b):
    x, y = sorted((L(a), L(b)), reverse=True); return (x + 0.05) / (y + 0.05)
def grey(c):  # CSS grayscale(1) filter matrix on sRGB values
    g = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; return [g, g, g]
inv = collections.OrderedDict()
for l in d["labels"]:
    k = (l["text"], tuple(l["dot_rgb"]), tuple(l["text_rgb"]), tuple(l["bg_rgb"]))
    if k in inv: inv[k]["pages"].add(l["page"]); continue
    inv[k] = {"text": l["text"], "aria": l["aria"], "dot": l["dot_rgb"], "text_rgb": l["text_rgb"], "bg": l["bg_rgb"], "font_px": l["font_px"],
              "text_contrast": round(cr(l["text_rgb"], l["bg_rgb"]), 2), "dot_contrast": round(cr(l["dot_rgb"], l["bg_rgb"]), 2),
              "text_contrast_grey": round(cr(grey(l["text_rgb"]), grey(l["bg_rgb"])), 2), "dot_contrast_grey": round(cr(grey(l["dot_rgb"]), grey(l["bg_rgb"])), 2),
              "pages": {l["page"]}}
rows = [{**v, "pages": sorted(v["pages"])} for v in inv.values()]
json.dump(rows, open(vlib.EVIDENCE / "U1" / "labels.json", "w"), indent=1)
texts = sorted({r["text"] for r in rows})
print("distinct labels:", len(texts)); print(texts)
print("min text contrast", min(r["text_contrast"] for r in rows), "grey", min(r["text_contrast_grey"] for r in rows))
low_dot = sorted({(r["text"], r["dot_contrast"]) for r in rows if r["dot_contrast"] < 3})
print("dots under 3:1:", low_dot)
print("min dot contrast", min(r["dot_contrast"] for r in rows))
same_text_colour = {tuple(r["text_rgb"]) for r in rows}
print("text colours used by status labels:", same_text_colour)
ax = collections.Counter()
for p, vs in d["axe"].items():
    for v in vs: ax[(v["id"], v["impact"])] += v["nodes"]
print("axe violations (id, impact): nodes", dict(ax))
