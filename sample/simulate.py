"""
Demo driver: push a sequence of frames at the running backend so you can watch the trend go
Wet -> Damp -> Dry and see the "Drying" suggestion fire, without needing real footage.

Usage (with the app running via docker compose, backend on :8000):
    python sample/simulate.py
    python sample/simulate.py --url http://localhost:8000 --session demo

It generates synthetic frames (dark = wet, bright = dry). Swap in real trackside images by
pointing --dir at a folder of .jpg/.png files instead.
"""
import argparse
import io
import time
import glob
import os

import numpy as np
import requests
from PIL import Image


def synth_frame(brightness: int) -> bytes:
    arr = np.clip(
        np.full((224, 224, 3), brightness) + np.random.randint(-12, 12, (224, 224, 3)),
        0, 255,
    ).astype("uint8")
    if brightness < 90:  # specular highlights on wet asphalt
        arr[40:48, 60:130] = 255
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--session", default="demo")
    ap.add_argument("--dir", default=None, help="folder of real frames instead of synthetic")
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args()

    if args.dir:
        paths = sorted(glob.glob(os.path.join(args.dir, "*")))
        frames = [(open(p, "rb").read(), os.path.basename(p)) for p in paths]
    else:
        # a drying track: wet (dark) -> damp -> dry (bright)
        brightness_seq = [55, 60, 58, 62, 65, 70, 95, 115, 130, 150, 175, 195, 205, 200]
        frames = [(synth_frame(b), f"synthetic b={b}") for b in brightness_seq]

    print(f"sending {len(frames)} frames to {args.url} (session={args.session})\n")
    for data, name in frames:
        r = requests.post(
            f"{args.url}/predict",
            params={"session": args.session},
            files={"file": ("frame.png", data, "image/png")},
            timeout=30,
        )
        d = r.json()
        f = d.get("frame", {})
        print(f"{name:16} -> {f.get('label','?'):5} "
              f"conf={f.get('confidence','?')}  | headline={d.get('condition','?'):8} "
              f"dir={d.get('trend',{}).get('direction','?'):8} "
              f"| {d.get('suggestion',{}).get('message','')}")
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
