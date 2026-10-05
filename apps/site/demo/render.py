"""Turn a recording from record.mjs into the site's demo video: the app in a rounded window, with a
camera that eases in on what matters and the pointer and its clicks drawn on top, beside a panel
that plays the conversation with the researcher's coding agent.

    python apps/site/demo/render.py <recording dir> <out.mp4>

Needs Pillow and ffmpeg (libx264). The app's frames are the browser's own; the panel is drawn
here from the lines record.mjs scripted.
"""

from __future__ import annotations

import bisect
import json
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FPS = 30
APP = (40, 140, 1280, 800)  # x, y, width, height: 1440 x 900 scaled
PANEL = (1344, 140, 536, 800)
RADIUS = 14
EASE_S = 0.9  # how long the camera takes to move
FONTS = Path(__file__).parents[1] / "node_modules/geist/dist/fonts"
#: Milliseconds per character: the person types, the agent streams.
TYPE_MS = {"you": 34, "agent": 14, "tool": 0}


def ease(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return 4 * u**3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def background() -> Image.Image:
    """A soft vertical gradient, with each window's shadow."""
    top, bottom = (246, 246, 247), (226, 228, 233)
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        u = y / (H - 1)
        grad.putpixel(
            (0, y), tuple(round(a + (b - a) * u) for a, b in zip(top, bottom, strict=True))
        )
    out = grad.resize((W, H)).convert("RGBA")
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for x, y, w, h in (APP, PANEL):
        box = (x + 6, y + 22, x + w - 6, y + h + 18)
        ImageDraw.Draw(shadow).rounded_rectangle(box, RADIUS, fill=(15, 23, 42, 70))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(28)))
    return out.convert("RGB")


def rounded(size: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), RADIUS, fill=255)
    return mask


def cursor(size: int) -> Image.Image:
    """An arrow pointer, drawn large and scaled down so its edges are smooth."""
    k = 8
    arrow = [(0, 0), (0, 17), (4.5, 13), (7.5, 20), (10, 19), (7, 12), (12.5, 12)]
    img = Image.new("RGBA", (16 * k, 24 * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(1.5 * k + x * k, 1.5 * k + y * k) for x, y in arrow], fill=(255, 255, 255, 255))
    inner = [(1.5 * k + x * k * 0.82 + 0.9 * k, 1.5 * k + y * k * 0.82 + 1.6 * k) for x, y in arrow]
    d.polygon(inner, fill=(17, 17, 17, 255))
    return img.resize((round(size * 16 / 24), size), Image.LANCZOS)


class Track:
    """The last timed sample at or before a time."""

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


class Panel:
    """The agent's terminal: what the person typed, the tools the agent called, and what it
    answered, each revealed as it is typed or streamed, scrolled to the latest."""

    PAD, LINE, GAP, HEAD = 24, 27, 16, 46
    INK: ClassVar = {"you": (250, 250, 250), "agent": (212, 212, 216), "tool": (161, 161, 170)}

    def __init__(self, lines: list[dict]):
        self.lines = lines
        self.text = font("geist-mono/GeistMono-Regular.ttf", 17)
        self.bold = font("geist-mono/GeistMono-Medium.ttf", 17)
        self.small = font("geist-mono/GeistMono-Regular.ttf", 14)
        self.width = PANEL[2] - 2 * self.PAD - 26  # after the "> " or "● " mark
        self.wrapped = [self.wrap(m["text"], self.bold if m["who"] == "you" else self.text)
                        for m in lines]  # fmt: skip

    def wrap(self, text: str, f: ImageFont.FreeTypeFont) -> list[str]:
        out, line = [], ""
        for word in text.split(" "):
            test = f"{line} {word}".strip()
            if f.getlength(test) <= self.width:
                line = test
            else:
                out.append(line)
                line = word
        return [*out, line]

    def draw(self, t: float) -> Image.Image:
        w, h = PANEL[2], PANEL[3]
        img = Image.new("RGB", (w, h), (24, 24, 27))
        d = ImageDraw.Draw(img)
        d.line((0, self.HEAD, w, self.HEAD), fill=(39, 39, 42), width=1)
        for i, c in enumerate(((63, 63, 70),) * 3):
            d.ellipse((20 + i * 18, 18, 30 + i * 18, 28), fill=c)
        d.text((86, 14), "your coding agent · louped mcp", font=self.small, fill=(113, 113, 122))

        # what each message shows by now: (who, lines), the last line cut to the typed length
        shown: list[tuple[str, list[str], bool]] = []
        for m, lines in zip(self.lines, self.wrapped, strict=True):
            if t < m["t"]:
                break
            per = TYPE_MS[m["who"]]
            chars = len(m["text"]) if per == 0 else int((t - m["t"]) * 1000 / per)
            kept, left = [], chars
            for line in lines:
                if left <= 0:
                    break
                kept.append(line[:left])
                left -= len(line) + 1
            typing = chars < len(m["text"])
            shown.append((m["who"], kept or [""], typing))

        height = sum(len(ls) * self.LINE + self.GAP for _, ls, _ in shown)
        room = h - self.HEAD - 2 * self.PAD
        y = self.HEAD + self.PAD - max(0, height - room)
        for who, lines, typing in shown:
            mark = {"you": ">", "agent": " ", "tool": "●"}[who]
            ink = self.INK[who]
            f = self.bold if who == "you" else self.text
            if y + len(lines) * self.LINE > self.HEAD:
                d.text((self.PAD, y), mark, font=f, fill=(113, 113, 122) if who != "tool"
                       else (74, 222, 128))  # fmt: skip
            for line in lines:
                if y > self.HEAD:
                    d.text((self.PAD + 26, y), line, font=f, fill=ink)
                y += self.LINE
            if typing and who == "you":
                end = self.PAD + 26 + f.getlength(lines[-1]) + 2
                d.rectangle((end, y - self.LINE + 4, end + 9, y - 5), fill=(250, 250, 250))
            y += self.GAP
        return img


def main(rec: Path, out: Path) -> None:
    tl = json.loads((rec / "timeline.json").read_text())
    view, px = tl["view"], tl["scale"]
    full = (view["width"] * px, view["height"] * px)
    win = (APP[2], APP[3])
    frames, pointer = Track(tl["frames"]), Track(tl["pointer"])
    look = camera(tl["camera"], view)
    panel = Panel(tl["chat"])
    base = background()
    app_mask, panel_mask = rounded(win), rounded((PANEL[2], PANEL[3]))
    arrow = cursor(28)
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
        frame = base.copy()
        frame.paste(shot.resize(win, Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch)),
                    APP[:2], app_mask)  # fmt: skip
        frame.paste(panel.draw(t), PANEL[:2], panel_mask)

        # the pointer, where the page had it, through the same camera
        p = pointer.at(t)
        if p:
            k = win[0] / cw
            sx = APP[0] + (p["x"] * px - x0) * k
            sy = APP[1] + (p["y"] * px - y0) * k
            draw = ImageDraw.Draw(frame, "RGBA")
            for c in tl["clicks"]:
                age = t - c["t"]
                if 0 <= age < 0.5:
                    r = 10 + 34 * ease(age / 0.5)
                    a = round(110 * (1 - age / 0.5))
                    draw.ellipse((sx - r, sy - r, sx + r, sy + r), fill=(59, 130, 246, a // 2),
                                 outline=(59, 130, 246, a), width=3)  # fmt: skip
            frame.paste(arrow, (round(sx - 4), round(sy - 4)), arrow)
        ffmpeg.stdin.write(frame.tobytes())
    ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print(f"{out}: {n} frames, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
