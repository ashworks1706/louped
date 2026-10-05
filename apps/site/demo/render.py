"""Turn a recording from record.mjs into the site's demo video: the app in a rounded window on a
soft background, a camera that eases in on what matters, the pointer and its clicks drawn on top,
and one caption per step.

    python apps/site/demo/render.py <recording dir> <out.mp4>

Needs Pillow and ffmpeg (libx264). Every frame is the browser's own: nothing is drawn into the app.
"""

from __future__ import annotations

import bisect
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FPS = 30
WIN = (1472, 920)  # the app's window, 1440 x 900 in its own pixels, scaled
WIN_AT = ((W - WIN[0]) // 2, 44)
RADIUS = 14
EASE_S = 0.9  # how long the camera takes to move
FONT = Path(__file__).parents[1] / "node_modules/geist/dist/fonts/geist-sans/Geist-Medium.ttf"


def ease(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return 4 * u**3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def background() -> Image.Image:
    """A soft vertical gradient, light grey to a little darker."""
    top, bottom = (246, 246, 247), (226, 228, 233)
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        u = y / (H - 1)
        grad.putpixel(
            (0, y), tuple(round(a + (b - a) * u) for a, b in zip(top, bottom, strict=True))
        )
    return grad.resize((W, H))


def window_mask() -> Image.Image:
    mask = Image.new("L", WIN, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, WIN[0] - 1, WIN[1] - 1), RADIUS, fill=255)
    return mask


def shadow() -> Image.Image:
    """The window's shadow, as an RGBA layer the size of the frame."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x, y = WIN_AT
    box = (x + 6, y + 22, x + WIN[0] - 6, y + WIN[1] + 18)
    ImageDraw.Draw(layer).rounded_rectangle(box, RADIUS, fill=(15, 23, 42, 70))
    return layer.filter(ImageFilter.GaussianBlur(28))


def cursor(size: int) -> Image.Image:
    """An arrow pointer, drawn large and scaled down so its edges are smooth."""
    k = 8
    arrow = [(0, 0), (0, 17), (4.5, 13), (7.5, 20), (10, 19), (7, 12), (12.5, 12)]
    img = Image.new("RGBA", (16 * k, 24 * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = [(1.5 * k + x * k, 1.5 * k + y * k) for x, y in arrow]
    d.polygon(pts, fill=(255, 255, 255, 255))
    inner = [(1.5 * k + x * k * 0.82 + 0.9 * k, 1.5 * k + y * k * 0.82 + 1.6 * k) for x, y in arrow]
    d.polygon(inner, fill=(17, 17, 17, 255))
    return img.resize((round(size * 16 / 24), size), Image.LANCZOS)


class Track:
    """A value over time from timed samples: the last sample at or before a time."""

    def __init__(self, samples: list[dict]):
        self.t = [s["t"] for s in samples]
        self.s = samples

    def at(self, t: float) -> dict | None:
        i = bisect.bisect_right(self.t, t) - 1
        return self.s[i] if i >= 0 else None


def camera(keys: list[dict], view: dict):
    """(scale, x, y) at a time. Each key eases the camera, over EASE_S, from wherever the last
    key had brought it, so a key that comes mid-move starts from mid-move."""
    fields = ("scale", "x", "y")
    rest = {"scale": 1.0, "x": view["width"] / 2, "y": view["height"] / 2}
    moves: list[tuple[float, dict, dict]] = []  # (start, from, to)

    def at(t: float) -> dict:
        i = bisect.bisect_right([m[0] for m in moves], t) - 1
        if i < 0:
            return rest
        start, a, b = moves[i]
        u = ease((t - start) / EASE_S)
        return {f: a[f] + (b[f] - a[f]) * u for f in fields}

    for k in keys:
        moves.append((k["t"], at(k["t"]), {f: k[f] for f in fields}))
    return lambda t: tuple(at(t)[f] for f in fields)


def main(rec: Path, out: Path) -> None:
    tl = json.loads((rec / "timeline.json").read_text())
    view, px = tl["view"], tl["scale"]
    full = (view["width"] * px, view["height"] * px)
    frames, pointer, captions = Track(tl["frames"]), Track(tl["pointer"]), Track(tl["captions"])
    look = camera(tl["camera"], view)
    base = background()
    base.paste(shadow(), (0, 0), shadow())
    mask = window_mask()
    font = ImageFont.truetype(str(FONT), 26)
    arrow = cursor(30)
    loaded: tuple[str, Image.Image] | None = None

    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
         "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
    )  # fmt: skip
    assert ffmpeg.stdin
    n = int(tl["duration"] * FPS)
    for i in range(n):
        t = i / FPS
        f = frames.at(t) or tl["frames"][0]
        if loaded is None or loaded[0] != f["file"]:
            loaded = (f["file"], Image.open(rec / f["file"]).convert("RGB"))
        shot = loaded[1]
        if shot.size != full:
            shot = shot.resize(full, Image.LANCZOS)
        scale, cx, cy = look(t)
        cw, ch = full[0] / scale, full[1] / scale
        x0 = min(max(cx * px - cw / 2, 0), full[0] - cw)
        y0 = min(max(cy * px - ch / 2, 0), full[1] - ch)
        win = shot.resize(WIN, Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))
        frame = base.copy()
        frame.paste(win, WIN_AT, mask)

        # the pointer, where the page had it, through the same camera
        p = pointer.at(t)
        if p:
            k = WIN[0] / cw
            sx = WIN_AT[0] + (p["x"] * px - x0) * k
            sy = WIN_AT[1] + (p["y"] * px - y0) * k
            draw = ImageDraw.Draw(frame, "RGBA")
            for c in tl["clicks"]:
                age = t - c["t"]
                if 0 <= age < 0.5:
                    r = 10 + 34 * ease(age / 0.5)
                    a = round(110 * (1 - age / 0.5))
                    draw.ellipse((sx - r, sy - r, sx + r, sy + r), fill=(59, 130, 246, a // 2),
                                 outline=(59, 130, 246, a), width=3)  # fmt: skip
            frame.paste(arrow, (round(sx - 4), round(sy - 4)), arrow)

        # the step's caption, fading in
        c = captions.at(t)
        if c:
            a = ease((t - c["t"]) / 0.4)
            draw = ImageDraw.Draw(frame, "RGBA")
            w = draw.textlength(c["text"], font=font)
            y = WIN_AT[1] + WIN[1] + 30 + round(8 * (1 - a))
            draw.text(((W - w) / 2, y), c["text"], font=font, fill=(39, 39, 42, round(255 * a)))
        ffmpeg.stdin.write(frame.tobytes())
    ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print(f"{out}: {n} frames, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
