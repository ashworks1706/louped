"""Turn a recording from record.mjs into the site's demo video. The left window is the
researcher's terminal, then the app in a browser window, with a camera that eases in on what
matters and the pointer and its clicks drawn on top; beside it, a panel plays the conversation
with their coding agent. A long wait plays faster, marked as such, and a card ends it.

    python apps/site/demo/render.py <recording dir> <out.mp4>

Needs Pillow and ffmpeg (libx264). The app's frames are the browser's own; the terminal and the
panel are drawn here from what record.mjs logged.
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
WIN = (40, 80, 1280, 840)  # x, y, width, height of the left window, its bar included
BAR = 40  # the window's title bar; below it the 1440 x 900 page, scaled to 1280 x 800
CONTENT = (WIN[0], WIN[1] + BAR, WIN[2], WIN[3] - BAR)
PANEL = (1344, 80, 536, 840)
RADIUS = 14
EASE_S = 0.9  # how long the camera takes to move
PACE = 1.25  # how much faster than recorded the whole plays
FADE_S = 0.45  # the terminal giving way to the app
END_S = 3.2  # the closing card
FONTS = Path(__file__).parents[1] / "node_modules/geist/dist/fonts"
#: Milliseconds per character, as record.mjs typed and waited: set from its timeline.
TYPE_MS = {"cmd": 30, "you": 24, "agent": 9, "tool": 0, "note": 0}
CAPTION_Y = 1000  # the middle of the caption, under the windows
CLOSE_IN = 1.28  # how far the stage closes in on the agent's panel while the person types
DARK, RULE, DIM = (24, 24, 27), (39, 39, 42), (113, 113, 122)


def ease(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return 4 * u**3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def mono(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    return font(f"geist-mono/GeistMono-{weight}.ttf", size)


def sans(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    return font(f"geist-sans/Geist-{weight}.ttf", size)


def gradient() -> Image.Image:
    top, bottom = (246, 246, 247), (226, 228, 233)
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        u = y / (H - 1)
        grad.putpixel(
            (0, y), tuple(round(a + (b - a) * u) for a, b in zip(top, bottom, strict=True))
        )
    return grad.resize((W, H))


def background() -> Image.Image:
    """The gradient, with each window's shadow."""
    out = gradient().convert("RGBA")
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for x, y, w, h in (WIN, PANEL):
        box = (x + 6, y + 22, x + w - 6, y + h + 18)
        ImageDraw.Draw(shadow).rounded_rectangle(box, RADIUS, fill=(15, 23, 42, 70))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(28)))
    return out.convert("RGB")


def rounded(size: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), RADIUS, fill=255)
    return mask


def dots(d: ImageDraw.ImageDraw, y: int, fill: tuple[int, int, int]) -> None:
    for i in range(3):
        d.ellipse((20 + i * 18, y - 5, 30 + i * 18, y + 5), fill=fill)


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


def clock(speed: list[dict], duration: float):
    """The video's length, and the recording's time at a time in the video: the whole plays at
    PACE, and each sped-up span at its own rate."""
    cuts, t = [], 0.0
    for s in sorted(speed, key=lambda s: s["t0"]):
        cuts += [(t, s["t0"], PACE, False), (s["t0"], s["t1"], s["rate"], True)]
        t = s["t1"]
    cuts.append((t, duration, PACE, False))
    length = sum((b - a) / rate for a, b, rate, _ in cuts)

    def source(v: float) -> tuple[float, float]:
        """(recording time, the span's rate or 1) at video time v."""
        for a, b, rate, marked in cuts:
            played = (b - a) / rate
            if v < played:
                return a + v * rate, rate if marked else 1.0
            v -= played
        return duration, 1.0

    return length, source


def wrap(text: str, f: ImageFont.FreeTypeFont, width: float) -> list[str]:
    out = []
    for para in text.split("\n"):
        indent = para[: len(para) - len(para.lstrip(" "))]  # code and JSON keep theirs
        line = indent
        words = []
        for word in para.lstrip(" ").split(" "):  # a path too long for a line breaks anywhere
            while f.getlength(word) > width:
                cut = max(k for k in range(1, len(word) + 1) if f.getlength(word[:k]) <= width)
                words.append(word[:cut])
                word = word[cut:]
            words.append(word)
        for word in words:
            test = f"{line} {word}" if line.strip() else line + word
            if f.getlength(test) <= width or not line.strip():
                line = test
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


class Terminal:
    """The researcher's terminal: each command typed at its prompt, then its output."""

    PAD, LINE = 28, 26

    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.text = mono(17)
        self.bold = mono(17, "Medium")
        self.width = WIN[2] - 2 * self.PAD

    def draw(self, t: float) -> Image.Image:
        w, h = WIN[2], WIN[3]
        img = Image.new("RGB", (w, h), DARK)
        d = ImageDraw.Draw(img)
        d.line((0, BAR, w, BAR), fill=RULE)
        dots(d, BAR // 2, (63, 63, 70))
        title = "Terminal"
        d.text(((w - self.text.getlength(title)) / 2, 11), title, font=self.text, fill=DIM)

        lines: list[tuple[str, str, tuple[int, int, int], bool]] = []  # (prompt, text, ink, cur)
        for e in self.entries:
            if t < e["t"]:
                break
            if e["kind"] == "cmd":
                typed = int((t - e["t"]) * 1000 / TYPE_MS["cmd"])
                lines.append((f"{e['prompt']} $ ", e["text"][:typed], (250, 250, 250), True))
            else:
                for line in wrap(e["text"], self.text, self.width):
                    lines.append(("", line, (190, 190, 198), False))
        # the cursor sits on the last command until output arrives
        if lines and not lines[-1][3]:
            lines = [(p, s, ink, False) for p, s, ink, _ in lines]
        room = (h - BAR - 2 * self.PAD) // self.LINE
        y = BAR + self.PAD
        for i, (prompt, s, ink, cur) in enumerate(lines[-room:]):
            x = self.PAD
            if prompt:
                d.text((x, y), prompt, font=self.text, fill=(74, 222, 128))
                x += self.text.getlength(prompt)
            d.text((x, y), s, font=self.bold if prompt else self.text, fill=ink)
            if cur and i == len(lines[-room:]) - 1:
                end = x + self.bold.getlength(s) + 2
                d.rectangle((end, y + 3, end + 9, y + self.LINE - 5), fill=(250, 250, 250))
            y += self.LINE
        return img


class Panel:
    """The agent's terminal: what the person typed, the tools the agent called, and what it
    answered, each revealed as it is typed or streamed, scrolled to the latest."""

    PAD, LINE, GAP = 24, 27, 16
    INK: ClassVar = {
        "you": (250, 250, 250),
        "agent": (212, 212, 216),
        "tool": (161, 161, 170),
        "note": DIM,
    }
    MARK: ClassVar = {"you": ">", "agent": " ", "tool": "●", "note": " "}

    def __init__(self, lines: list[dict]):
        self.lines = lines
        self.text = mono(17)
        self.bold = mono(17, "Medium")
        self.small = mono(14)
        self.width = PANEL[2] - 2 * self.PAD - 26  # after the "> " or "● " mark
        self.wrapped = [wrap(m["text"], self.face(m["who"]), self.width) for m in lines]

    def face(self, who: str) -> ImageFont.FreeTypeFont:
        return self.bold if who == "you" else self.small if who == "note" else self.text

    def draw(self, t: float) -> Image.Image:
        w, h = PANEL[2], PANEL[3]
        img = Image.new("RGB", (w, h), DARK)
        d = ImageDraw.Draw(img)
        d.line((0, BAR, w, BAR), fill=RULE)
        dots(d, BAR // 2, (63, 63, 70))
        d.text((86, 12), "your coding agent", font=self.small, fill=DIM)

        # what each message shows by now: (who, lines, typing), the last line cut to the length
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
            shown.append((m["who"], kept or [""], chars < len(m["text"])))

        if not shown:
            d.text((self.PAD, BAR + self.PAD), "waiting for the app", font=self.small, fill=DIM)
            return img
        height = sum(len(ls) * self.LINE + self.GAP for _, ls, _ in shown)
        room = h - BAR - 2 * self.PAD
        y = BAR + self.PAD - max(0, height - room)
        for who, lines, typing in shown:
            f = self.face(who)
            if y + len(lines) * self.LINE > BAR:
                mark = (74, 222, 128) if who == "tool" else DIM
                d.text((self.PAD, y), self.MARK[who], font=f, fill=mark)
            for line in lines:
                if y > BAR:
                    d.text((self.PAD + 26, y), line, font=f, fill=self.INK[who])
                y += self.LINE
            if typing and who == "you":
                end = self.PAD + 26 + f.getlength(lines[-1]) + 2
                d.rectangle((end, y - self.LINE + 4, end + 9, y - 5), fill=(250, 250, 250))
            y += self.GAP
        return img


def browser_bar(url: str) -> Image.Image:
    """The browser window's bar, with the page's address."""
    img = Image.new("RGB", (WIN[2], BAR), (241, 241, 243))
    d = ImageDraw.Draw(img)
    d.line((0, BAR - 1, WIN[2], BAR - 1), fill=(222, 222, 226))
    dots(d, BAR // 2, (208, 208, 214))
    f = mono(14)
    text = f"127.0.0.1:8000{url}"
    while f.getlength(text) > 760:
        text = text[:-2]
    left = (WIN[2] - 800) // 2
    d.rounded_rectangle((left, 7, left + 800, BAR - 8), 7, fill=(255, 255, 255))
    d.text((left + 18, 11), text, font=f, fill=(82, 82, 91))
    return img


def badge(rate: float) -> Image.Image:
    f = sans(18, "Medium")
    text = f"{rate:g}\N{MULTIPLICATION SIGN}"
    w = round(f.getlength(text)) + 28
    img = Image.new("RGBA", (w, 34), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, 33), 17, fill=(17, 17, 17, 220))
    d.text((14, 5), text, font=f, fill=(255, 255, 255, 255))
    return img


def end_card() -> Image.Image:
    img = gradient()
    d = ImageDraw.Draw(img)
    for f, text, y, ink in (
        (sans(84, "SemiBold"), "louped", 400, (17, 17, 17)),
        (sans(32), "An astute harness for LLM behavior and inference research.", 520, (82, 82, 91)),
        (mono(28), "pip install louped", 610, (17, 17, 17)),
    ):
        d.text(((W - f.getlength(text)) / 2, y), text, font=f, fill=ink)
    return img


def captioned(frame: Image.Image, captions: Track, t: float) -> None:
    """The scene's caption under the windows, faded in as it changes."""
    c = captions.at(t)
    if c is None:
        return
    f = sans(30, "Medium")
    a = ease((t - c["t"]) / 0.35)
    ink = tuple(round(232 + (17 - 232) * a) for _ in range(3))
    width = f.getlength(c["text"])
    ImageDraw.Draw(frame).text(((W - width) / 2, CAPTION_Y - 20), c["text"], font=f, fill=ink)


def stage(chat: list[dict]):
    """How far the stage closes in on the agent's panel at a time, 1 for not at all: from just
    before the person starts typing a message until just after they send it."""
    spans = [(m["t"] - 0.2, m["t"] + 0.35 + len(m["text"]) * TYPE_MS["you"] / 1000 + 0.4)
             for m in chat if m["who"] == "you"]  # fmt: skip

    def at(t: float) -> float:
        u = max((min(ease((t - a) / 0.5), ease((b + 0.5 - t) / 0.5)) for a, b in spans), default=0)
        return 1 + (CLOSE_IN - 1) * max(u, 0)

    return at


def closed_in(frame: Image.Image, scale: float) -> Image.Image:
    """The frame closed in on the lower half of the agent's panel."""
    if scale <= 1.001:
        return frame
    cx, cy = PANEL[0] + PANEL[2] / 2, PANEL[1] + PANEL[3] * 0.62
    w, h = W / scale, H / scale
    x0, y0 = min(max(cx - w / 2, 0), W - w), min(max(cy - h / 2, 0), H - h)
    return frame.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))


def main(rec: Path, out: Path) -> None:
    tl = json.loads((rec / "timeline.json").read_text())
    TYPE_MS.update(tl["typing"])
    captions, close = Track(tl["captions"]), stage(tl["chat"])
    view, px = tl["view"], tl["scale"]
    full = (view["width"] * px, view["height"] * px)
    win = (CONTENT[2], CONTENT[3])
    frames, pointer, urls = Track(tl["frames"]), Track(tl["pointer"]), Track(tl["urls"])
    screens = Track(tl["screens"])
    look = camera(tl["camera"], view)
    term, panel = Terminal(tl["term"]), Panel(tl["chat"])
    base = background()
    win_mask, panel_mask = rounded((WIN[2], WIN[3])), rounded((PANEL[2], PANEL[3]))
    arrow = cursor(28)
    card = end_card()
    length, source = clock(tl["speed"], tl["duration"])
    loaded: tuple[str, Image.Image] | None = None

    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
         "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
    )  # fmt: skip
    assert ffmpeg.stdin
    n = int((length + END_S) * FPS)
    for i in range(n):
        v = i / FPS
        if v >= length + 0.6:  # the card, faded in over 0.6 s
            ffmpeg.stdin.write(card.tobytes())
            continue
        t, rate = source(min(v, length))
        screen = screens.at(t) or {"screen": "terminal", "t": 0}
        frame = base.copy()

        app = None
        if screen["screen"] == "app":
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
            app = Image.new("RGB", (WIN[2], WIN[3]))
            app.paste(browser_bar((urls.at(t) or {"url": "/"})["url"]), (0, 0))
            app.paste(shot.resize(win, Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch)), (0, BAR))
            fade = ease((t - screen["t"]) / FADE_S)
            left = app if fade >= 1 else Image.blend(term.draw(t), app, fade)
        else:
            left = term.draw(t)
        frame.paste(left, WIN[:2], win_mask)
        frame.paste(panel.draw(t), PANEL[:2], panel_mask)
        draw = ImageDraw.Draw(frame, "RGBA")

        # the pointer, where the page had it, through the same camera; only inside the page
        p = pointer.at(t)
        if app is not None and p and t - screen["t"] > FADE_S:
            k = win[0] / cw
            sx = CONTENT[0] + (p["x"] * px - x0) * k
            sy = CONTENT[1] + (p["y"] * px - y0) * k
            inside = CONTENT[0] <= sx <= CONTENT[0] + win[0] - 12
            if inside and CONTENT[1] <= sy <= CONTENT[1] + win[1] - 16:
                for c in tl["clicks"]:
                    age = t - c["t"]
                    if 0 <= age < 0.5:
                        r = 10 + 34 * ease(age / 0.5)
                        a = round(110 * (1 - age / 0.5))
                        draw.ellipse((sx - r, sy - r, sx + r, sy + r),
                                     fill=(59, 130, 246, a // 2),
                                     outline=(59, 130, 246, a), width=3)  # fmt: skip
                frame.paste(arrow, (round(sx - 4), round(sy - 4)), arrow)
        if rate > 1:
            b = badge(rate)
            frame.paste(b, (CONTENT[0] + 18, CONTENT[1] + win[1] - b.height - 18), b)
        frame = closed_in(frame, close(t))
        captioned(frame, captions, t)
        if v > length:
            frame = Image.blend(frame, card, ease((v - length) / 0.6))
        ffmpeg.stdin.write(frame.tobytes())
    ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print(f"{out}: {n} frames, {n / FPS:.1f} s, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
