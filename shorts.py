"""DailyMindShift Shorts pipeline: script -> AI voiceover -> captioned 9:16 video -> YouTube.

Commands:
  python shorts.py build [SCRIPT ...]   Build videos (all scripts if none given)
  python shorts.py upload-next          Upload the next video that hasn't been posted
  python shorts.py schedule             Stay running and post one Short a day at post_time
  python shorts.py status               Show what's built and what's posted
  python shorts.py prompt               Print a prompt for writing new scripts with any AI chatbot
  python shorts.py voices               List English voices you can put in config.json
"""

import asyncio
import hashlib
import json
import random
import re
import subprocess
import sys
import tempfile
import time
import wave
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
OUTPUT = ROOT / "output"
BACKGROUNDS = ROOT / "backgrounds"
MUSIC = ROOT / "music"
FONTS = ROOT / "fonts"
POSTED = OUTPUT / "posted.json"

W, H, FPS = 1080, 1920, 30
PAUSE = 0.25  # seconds of silence between sentences

GRADIENTS = [
    ((20, 30, 70), (90, 40, 120)),
    ((10, 60, 70), (20, 120, 110)),
    ((60, 20, 40), (160, 70, 60)),
    ((15, 15, 25), (60, 60, 90)),
    ((30, 50, 20), (110, 130, 50)),
    ((70, 40, 10), (170, 110, 40)),
]


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def ffmpeg():
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit("ffmpeg failed:\n" + result.stderr[-2000:])


# ---------- scripts ----------


def parse_script(path):
    """A script is 'key: value' header lines, a '---' line, then one sentence or line per row."""
    text = path.read_text(encoding="utf-8")
    if "---" not in text:
        sys.exit(f"{path.name}: missing the '---' line between the header and the script.")
    head, body = text.split("---", 1)
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    if not lines:
        sys.exit(f"{path.name}: the script is empty.")
    return {
        "slug": path.stem,
        "title": meta.get("title", path.stem),
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        "lines": lines,
    }


def all_scripts():
    return sorted(SCRIPTS.glob("*.txt"))


def find_script(name):
    path = SCRIPTS / name
    for candidate in (path, path.with_suffix(".txt")):
        if candidate.is_file():
            return candidate
    matches = [p for p in all_scripts() if p.stem.startswith(name)]
    if len(matches) == 1:
        return matches[0]
    sys.exit(f"No single script matches '{name}'.")


# ---------- voiceover ----------


async def _tts(text, voice, rate, out_path):
    import edge_tts

    for attempt in range(3):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(str(out_path))
            return
        except Exception as e:  # network hiccups are common; retry a couple of times
            if attempt == 2:
                sys.exit(f"Voiceover failed (check your internet connection): {e}")
            await asyncio.sleep(2)


def voiceover(lines, cfg, tmp):
    """Speak each line separately so captions can be timed exactly. Returns (wav path, durations)."""
    rate = 24000
    durations = []
    combined = tmp / "voice.wav"
    silence = b"\x00\x00" * int(rate * PAUSE)
    with wave.open(str(combined), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        for i, line in enumerate(lines):
            mp3, wav = tmp / f"line{i}.mp3", tmp / f"line{i}.wav"
            asyncio.run(_tts(line, cfg["voice"], cfg["voice_rate"], mp3))
            run([ffmpeg(), "-y", "-i", str(mp3), "-ac", "1", "-ar", str(rate), str(wav)])
            with wave.open(str(wav), "rb") as w:
                frames = w.readframes(w.getnframes())
            out.writeframes(frames + silence)
            durations.append(len(frames) / 2 / rate + PAUSE)
    return combined, durations


# ---------- visuals ----------


def find_font(cfg, size):
    from PIL import ImageFont

    candidates = [cfg.get("font") or ""]
    candidates += [str(p) for p in sorted(FONTS.glob("*.[ot]tf"))]
    candidates += [
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def pick(items, slug):
    """Deterministic choice so rebuilding a video gives the same look."""
    return items[int(hashlib.md5(slug.encode()).hexdigest(), 16) % len(items)]


def background(slug):
    from PIL import Image, ImageEnhance, ImageOps

    images = sorted(p for p in BACKGROUNDS.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    if images:
        img = ImageOps.fit(Image.open(pick(images, slug)).convert("RGB"), (W, H))
        return ImageEnhance.Brightness(img).enhance(0.55)
    top, bottom = pick(GRADIENTS, slug)
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        color = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
        for x in range(W):
            px[x, y] = color
    return img


def wrap(text, font, max_width):
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def caption_chunks(line, duration, max_words):
    """Split a line into short on-screen captions, timed by character count."""
    chunks = []
    for phrase in re.findall(r"[^.,?!;:]+[.,?!;:]*", line):
        words = phrase.split()
        if not words:
            continue
        parts = -(-len(words) // max_words)  # ceil: split long phrases into even pieces
        size = -(-len(words) // parts)
        chunks += [" ".join(words[i : i + size]) for i in range(0, len(words), size)]
    # Merge tiny fragments ("Right?") into the previous caption when there's room.
    merged = []
    for c in chunks:
        if merged and len(c.split()) <= 2 and len((merged[-1] + " " + c).split()) <= max_words:
            merged[-1] += " " + c
        else:
            merged.append(c)
    chunks = merged
    total = sum(len(c) for c in chunks)
    return [(c, duration * len(c) / total) for c in chunks]


def render_frame(base, text, cfg, font, small_font):
    from PIL import ImageDraw

    img = base.copy()
    draw = ImageDraw.Draw(img)
    rows = wrap(text, font, W - 160)
    line_h = font.size * 1.25
    y = (H - line_h * len(rows)) / 2
    for row in rows:
        x = (W - font.getlength(row)) / 2
        draw.text((x, y), row, font=font, fill="white", stroke_width=8, stroke_fill="black")
        y += line_h
    handle = "@" + cfg["channel_name"]
    draw.text(((W - small_font.getlength(handle)) / 2, H - 260), handle, font=small_font,
              fill=(255, 255, 255, 200), stroke_width=3, stroke_fill="black")
    return img


# ---------- build ----------


def build(path, cfg):
    script = parse_script(path)
    OUTPUT.mkdir(exist_ok=True)
    out = OUTPUT / f"{script['slug']}.mp4"
    print(f"Building {out.name} ...")

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        voice, durations = voiceover(script["lines"], cfg, tmp)
        base = background(script["slug"])
        font = find_font(cfg, cfg["caption_size"])
        small = find_font(cfg, 44)

        concat = []
        n = 0
        for line, dur in zip(script["lines"], durations):
            for text, d in caption_chunks(line, dur, cfg["words_per_caption"]):
                frame = tmp / f"f{n:04d}.png"
                render_frame(base, text, cfg, font, small).save(frame)
                concat.append(f"file '{frame.as_posix()}'\nduration {d:.3f}")
                n += 1
        concat.append(f"file '{(tmp / f'f{n - 1:04d}.png').as_posix()}'")  # concat demuxer needs the last frame twice
        (tmp / "frames.txt").write_text("\n".join(concat), encoding="utf-8")

        cmd = [ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "frames.txt"), "-i", str(voice)]
        tracks = sorted(p for p in MUSIC.glob("*") if p.suffix.lower() in {".mp3", ".m4a", ".wav", ".ogg"})
        if tracks:
            cmd += ["-stream_loop", "-1", "-i", str(pick(tracks, script["slug"]))]
            cmd += ["-filter_complex",
                    f"[2:a]volume={cfg['music_volume']}[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]"]
        else:
            cmd += ["-map", "0:v", "-map", "1:a"]
        cmd += ["-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
                "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)]
        run(cmd)

    # Copy-paste sheet for uploading by hand in YouTube Studio.
    out.with_suffix(".txt").write_text(
        f"TITLE\n{script['title'][:100]}\n\nDESCRIPTION\n{description(script, cfg)}\n\nTAGS\n{', '.join(script['tags'])}\n",
        encoding="utf-8",
    )
    length = sum(durations)
    note = "  (over 3 minutes, so YouTube won't treat it as a Short)" if length > 180 else ""
    print(f"  done: {out.relative_to(ROOT)}  {length:.0f}s{note}")
    return out


# ---------- upload ----------


def load_posted():
    return json.loads(POSTED.read_text()) if POSTED.exists() else {}


def youtube_client():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as gbuild

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    token, secret = ROOT / "token.json", ROOT / "client_secret.json"
    creds = Credentials.from_authorized_user_file(str(token), scopes) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not secret.exists():
            sys.exit("client_secret.json not found. Follow step 4 in the README to create it.")
        creds = InstalledAppFlow.from_client_secrets_file(str(secret), scopes).run_local_server(port=0)
    token.write_text(creds.to_json())
    return gbuild("youtube", "v3", credentials=creds)


def description(script, cfg):
    tags = " ".join("#" + re.sub(r"\W", "", t) for t in script["tags"][:3])
    parts = [script["title"], "", cfg["description_cta"], "", tags + " #shorts"]
    if cfg.get("affiliate_disclosure"):
        parts += ["", cfg["affiliate_disclosure"]]
    return "\n".join(parts)


def upload_next(cfg):
    posted = load_posted()
    pending = [p for p in all_scripts() if p.stem not in posted]
    if not pending:
        print("Every script has been posted. Add new ones to the scripts folder (try: python shorts.py prompt).")
        return False
    path = pending[0]
    script = parse_script(path)
    video = OUTPUT / f"{path.stem}.mp4"
    if not video.exists():
        build(path, cfg)

    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": script["title"][:100],
            "description": description(script, cfg),
            "tags": script["tags"],
            "categoryId": cfg["category_id"],
        },
        "status": {"privacyStatus": cfg["privacy"], "selfDeclaredMadeForKids": False},
    }
    print(f"Uploading {video.name} ...")
    request = youtube_client().videos().insert(
        part="snippet,status", body=body, media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True)
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    posted[path.stem] = {"id": response["id"], "at": datetime.now().isoformat(timespec="seconds")}
    POSTED.write_text(json.dumps(posted, indent=2))
    print(f"  posted: https://youtube.com/shorts/{response['id']}")
    return True


def schedule(cfg):
    hour, minute = map(int, cfg["post_time"].split(":"))
    print(f"Posting one Short a day at {cfg['post_time']}. Leave this window open. Ctrl+C to stop.")
    while True:
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        print(f"Next post: {target:%a %d %b %H:%M}")
        time.sleep((target - now).total_seconds())
        try:
            if not upload_next(cfg):
                return
        except Exception as e:  # keep the schedule alive; try again tomorrow
            print(f"Upload failed, will retry tomorrow: {e}")


# ---------- helpers ----------


def status():
    posted = load_posted()
    for p in all_scripts():
        built = "built " if (OUTPUT / f"{p.stem}.mp4").exists() else "      "
        done = f"posted {posted[p.stem]['at']}" if p.stem in posted else ""
        print(f"{built} {p.stem:32} {done}")


PROMPT = """Write {n} new YouTube Shorts scripts for a faceless mindset channel called {channel}.
Each one is read aloud by an AI voice over captions, and should last 35 to 50 seconds (about 100 to 130 words).

Rules:
- Open with a hook line that stops the scroll.
- One idea per script, practical and specific, in plain everyday words.
- Short sentences, one per line, no emojis, no stage directions, no made-up statistics.
- Last line is exactly: Follow for one mindset shift a day.
- Avoid these topics, which are already covered: {done}

Format each script exactly like this, with a blank line between scripts:

FILE: 11-short-topic-name.txt
title: A Catchy Title Under 60 Characters
tags: five, comma, separated, search, tags
---
Line one.
Line two.
"""


def prompt(cfg):
    done = ", ".join(parse_script(p)["title"] for p in all_scripts())
    print(PROMPT.format(n=10, channel=cfg["channel_name"], done=done))
    print("Save each script as its own file in the scripts folder, named as on its FILE: line.")


def voices():
    import edge_tts

    for v in asyncio.run(edge_tts.list_voices()):
        if v["Locale"].startswith("en-"):
            print(f"{v['ShortName']:32} {v['Gender']}")


def main():
    cfg = load_config()
    args = sys.argv[1:]
    cmd = args[0] if args else "help"
    if cmd == "build":
        for path in [find_script(a) for a in args[1:]] or all_scripts():
            build(path, cfg)
    elif cmd == "upload-next":
        upload_next(cfg)
    elif cmd == "schedule":
        schedule(cfg)
    elif cmd == "status":
        status()
    elif cmd == "prompt":
        prompt(cfg)
    elif cmd == "voices":
        voices()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
