"""Draw Pulse Control's app icon and build launcher/icon/PulseControl.icns.

    ~/.venvs/sdp07/bin/python launcher/icon/make_icon.py

Needs pillow (already in baselines/requirements.txt) and macOS's iconutil.
Re-run only if you change the drawing; the .icns is committed.
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024                      # master size; every other size is resampled from it

BG_TOP = (18, 34, 54)         # deep navy, so the white trace carries at 16 px
BG_BOT = (13, 88, 112)        # teal, the dashboards' accent
TRACE = (124, 196, 255)       # the log pane's "head" blue
FLAG = (95, 211, 141)         # the log pane's "ok" green


def squircle_mask(size: int, radius_frac: float = 0.2237) -> Image.Image:
    """macOS's rounded-square silhouette, antialiased by drawing 4x and shrinking."""
    k = 4
    m = Image.new("L", (size * k, size * k), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, size * k - 1, size * k - 1], radius=int(size * k * radius_frac), fill=255)
    return m.resize((size, size), Image.LANCZOS)


def gradient(size: int) -> Image.Image:
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))
    return g.resize((size, size), Image.BICUBIC)


def pulse_points(size: int):
    """one ECG-ish beat across the middle: flat, small dip, spike, undershoot, flat.

    inset from the edges -- a trace running into the squircle's corners looks
    like a crop, and the Dock rounds it off anyway.
    """
    x0, x1 = size * 0.13, size * 0.87
    mid = size * 0.54
    amp = size * 0.25
    # (x fraction across the inset, y offset in amplitudes; negative is up)
    key = [(0.00, 0.0), (0.26, 0.0), (0.34, 0.18), (0.42, -0.10),
           (0.50, -1.00), (0.58, 0.58), (0.66, 0.0), (1.00, 0.0)]
    return [(x0 + (x1 - x0) * x, mid + amp * y) for x, y in key]


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg = gradient(size).convert("RGBA")
    bg.putalpha(squircle_mask(size))
    img.alpha_composite(bg)

    d = ImageDraw.Draw(img)
    pts = pulse_points(size)
    w = max(2, round(size * 0.062))
    d.line(pts, fill=TRACE, width=w, joint="curve")
    for x, y in pts:                       # round the joints and the two ends
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=TRACE)

    # the flag dot ON the spike -- this is an anomaly detector, not a pulse meter.
    # a background-coloured ring keeps it from merging into the trace behind it.
    cx, cy = pts[4]
    r = size * 0.085
    ring = r + max(1.5, size * 0.022)
    d.ellipse([cx - ring, cy - ring, cx + ring, cy + ring], fill=BG_TOP)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=FLAG)
    return img


def main() -> int:
    master = draw(S)
    iconset = os.path.join(HERE, "PulseControl.iconset")
    os.makedirs(iconset, exist_ok=True)
    for px in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            n = px * scale
            # redraw rather than downsample at the small end: a 1024->16 resample
            # turns the trace into grey mush
            im = draw(n) if n <= 64 else master.resize((n, n), Image.LANCZOS)
            suffix = "@2x" if scale == 2 else ""
            im.save(os.path.join(iconset, "icon_%dx%d%s.png" % (px, px, suffix)))
    master.save(os.path.join(HERE, "preview.png"))

    icns = os.path.join(HERE, "PulseControl.icns")
    try:
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print("iconutil failed (%s) -- the .iconset is still in %s" % (e, iconset))
        return 1
    print("wrote %s (%.0f KB)" % (icns, os.path.getsize(icns) / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
