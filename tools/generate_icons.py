"""
Generate PWA icon PNGs from SVG or create them programmatically.
Usage: python tools/generate_icons.py
"""
import os, sys, math, io

SVG_PATH = os.path.join("static", "icon.svg")
OUT_DIR = "static"
SIZES = [192, 512]

def make_png(size):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (size, size), (26, 26, 46, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 - size // 8
    r = size * 0.28
    pts = []
    for i in range(6):
        a = i * 60 - 90
        pts.append((cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))))
    for i in range(3):
        draw.line([pts[i], pts[(i + 3) % 6]], fill=(10, 108, 255, 255), width=max(2, size // 40))
    er = size * 0.08
    draw.ellipse([cx - er, cy - er, cx + er, cy + er], outline=(255, 217, 102, 255), width=max(1, size // 50))
    draw.ellipse([cx - er // 4, cy - er // 4, cx + er // 4, cy + er // 4], fill=(255, 217, 102, 255))
    try:
        font = ImageFont.truetype("arial.ttf", int(size * 0.1))
    except:
        font = ImageFont.load_default()
    text = "COC"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, int(size * 0.82)), text, fill=(136, 136, 136, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for size in SIZES:
        data = make_png(size)
        out = os.path.join(OUT_DIR, f"icon-{size}.png")
        with open(out, "wb") as f:
            f.write(data)
        print(f"[OK] {out} ({size}x{size})")
    print("Done! Icons generated in static/")

if __name__ == "__main__":
    main()
