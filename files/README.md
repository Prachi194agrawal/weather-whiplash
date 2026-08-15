# Track Condition AI — Pit Wall

Real-time track surface reader for race strategy. Feed it trackside/onboard camera frames; it
classifies each as **Dry / Damp / Wet**, tracks the **trend over time**, decides whether the track
is **Drying or Wetting**, and gives a plain-language **tyre suggestion** — e.g. *"Track drying: tyre
change window approaching."*

The whole thing runs on a laptop with one command, and the ML model is a **swappable file** — start
with zero setup, upgrade to a trained model later without touching any other code.

---

## Why the design looks like this (the important bit)

**A single frame cannot show "Drying."** Drying is a *change over time*, not something visible in one
photo — a drying track and a stably-damp track look identical in a still image. So:

- The **model** only predicts the **moisture level** (Dry / Damp / Wet) of a single frame.
- The **direction** (Drying / Wetting) is computed in the backend from how that level moves across a
  window of recent frames (`backend/app/smoothing.py`).
- "Drying" then appears as the headline condition and drives the tyre suggestion.

This is why you don't train a "Drying" class — you'd be trying to learn something that isn't in the
pixels. Getting this right is what separates a working tool from a demo that flickers.

---

## Architecture

```
 ┌───────────┐   image    ┌───────────────┐  /infer  ┌────────────────────┐
 │ Frontend  │ ─────────► │  Backend API   │ ───────► │ Inference service   │
 │ (React)   │            │  (FastAPI)     │          │  stub | clip | onnx │
 │ trend UI  │ ◄───────── │  trend + rules │ ◄─────── │  (swappable model)  │
 └───────────┘   readout   └──────┬─────────┘          └────────────────────┘
                                  │ store
                             ┌────▼─────┐
                             │ SQLite   │  (predictions + timestamps)
                             └──────────┘
```

Three containers: `frontend` (nginx), `backend` (FastAPI + SQLite), `inference` (the model).
The inference service is the only thing that knows about models — swap the model, nothing else changes.

---

## Quick start (30 seconds, no ML setup)

Requires Docker.

```bash
docker compose up --build
```

Open **http://localhost:3000**. Upload a frame — you'll get a condition + confidence.
This uses `MODEL_BACKEND=stub` (a brightness heuristic) so it runs instantly with no model download.

Watch the trend + "Drying" suggestion fire using the demo driver:

```bash
pip install requests pillow numpy
python sample/simulate.py            # pushes a wet -> dry sequence
```

---

## The three model backends

Set `MODEL_BACKEND` in `.env`:

| Backend | What it is | Setup | Use it for |
|---|---|---|---|
| `stub` | brightness heuristic | none | first run, building UI/trend logic |
| `clip` | CLIP zero-shot (no training) | uncomment `torch`+`transformers` in `inference/requirements.txt` | a real classifier today, no dataset |
| `onnx` | your fine-tuned model | put `model.onnx` + `class_names.json` in `inference/model/` | best accuracy, the "real ML" path |

All three return the same response shape, so the backend and frontend never change.

---

## Train your own model (the real ML path)

1. Open `training/train_colab.ipynb` in **Google Colab** (Runtime → GPU).
2. Point it at a dataset (your own labelled frames, or a public one — see below). Run all cells.
3. It fine-tunes **MobileNetV3** and exports **`model.onnx`** + **`class_names.json`**.
4. Copy both into `inference/model/`, set `MODEL_BACKEND=onnx` in `.env`, then:
   ```bash
   docker compose up --build
   ```
   The app now uses your model. No other change.

**Public datasets** that match these classes:
- **RoadSaW** — dry / damp / wet / very wet (merge *very wet* → *Wet*). CVPR 2022 workshop dataset.
- **RSCD** — ~1M road patch images with friction/condition labels.
- **NYSDOT traffic-camera set** — ~22k hand-labelled camera images (closest to a fixed trackside camera).

Links and details are in the planning doc. Start with a few hundred images per class; transfer
learning needs far less data than training from scratch.

---

## Running without Docker (dev mode)

Three terminals:

```bash
# 1) inference
cd inference && pip install -r requirements.txt && MODEL_BACKEND=stub uvicorn server:app --port 8500

# 2) backend
cd backend && pip install -r requirements.txt && INFERENCE_URL=http://localhost:8500 DB_PATH=./track.db uvicorn app.main:app --port 8000

# 3) frontend
cd frontend && npm install && npm run dev      # opens http://localhost:5173
```

---

## API

| Method | Route | Purpose |
|---|---|---|
| POST | `/predict?session=default` | classify a frame (multipart `file`), store it, return live readout |
| GET | `/trend?session=default&window_s=900` | time series + smoothed state + direction |
| GET | `/suggestion?session=default` | current tyre suggestion |
| GET | `/health` | liveness + whether inference is reachable |

If inference is down, `/predict` returns **"condition unknown — check visually"** rather than a stale
or confident-wrong label. On race day that fail-safe matters.

---

## Push this to GitHub

From inside the `track-condition-ai/` folder:

```bash
git init
git add .
git commit -m "Track Condition AI: swappable-model real-time pipeline"

# create an empty repo on github.com first (no README), then:
git branch -M main
git remote add origin https://github.com/<your-username>/track-condition-ai.git
git push -u origin main
```

If you have the GitHub CLI, it's one line instead of the last four:

```bash
gh repo create track-condition-ai --public --source=. --push
```

> `.gitignore` already excludes `node_modules/`, `*.onnx`, `*.db`, and `.env`. Ship trained models
> via GitHub Releases or DVC rather than committing large binaries.

---

## What to build next

- Per-zone condition (racing line vs off-line) via light segmentation — the racing line dries first.
- Confidence calibration + an explicit "can't tell" output for glare/night/heavy spray.
- Weather + track-temperature fusion (track temp predicts drying rate; also gives free weak labels).
- Edge deployment (Jetson + TensorRT) for trackside use when the venue network is unreliable.
- Swap the rule engine for an HMM over {Dry, Damp, Wet} for even smoother, physics-respecting tracks.
```
