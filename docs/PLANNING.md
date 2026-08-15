# Track Condition AI (Weather Whiplash) — Planning & Deployment Documentation

## 1. Project Overview

**Problem:** Track conditions (dry, wet, drying) can change faster than weather reports update. Race teams need a real-time read on whether the track is getting safer or riskier so they can decide when to change tires.

**Solution:** Feed in camera images or video frames (trackside or onboard). A trained model classifies each frame's moisture level, the backend tracks the trend over time and derives a **Drying**/**Wetting** direction, and the "Pit Wall" frontend surfaces a plain-language suggestion (e.g. *"Track drying: tyre change window approaching"*).

**Core loop:**
```
Camera/video frame → Backend API → Inference service → moisture label + per-class confidence
                                  → stored in SQLite (per session)
                                  → trend smoothing derives Drying/Wetting + a strategy suggestion
                                  → Frontend ("Pit Wall") shows the frame, condition, trend, suggestion
```

This document is the living plan for what's been built, what's stubbed, and what's left before race-day use.

---

## 2. System Architecture

```
┌─────────────────┐        ┌──────────────────────┐        ┌────────────────────┐
│   Frontend        │  HTTP  │   Backend API          │  HTTP  │   Inference service  │
│  (React/Vite,      │◄──────►│  (FastAPI)             │◄──────►│  (FastAPI)            │
│   "Pit Wall")      │        │  - POST /predict        │        │  - POST /infer         │
│  - Upload frame     │        │  - GET  /trend          │        │    (stub | onnx)       │
│  - Wetness trace    │        │  - GET  /suggestion      │        │  - real trained model  │
│  - Strategy call    │        │  - smoothing.py: trend   │        └────────────────────┘
└─────────────────┘        │    + Drying/Wetting rules │
                             │  - SQLite (track_data vol)│
                             └──────────────────────┘
```

**Why inference is its own service:** the classifier can move to a GPU image and scale independently of the lightweight API/storage layer. The model is a swappable file behind a fixed `/infer` contract — `MODEL_BACKEND=onnx` (real trained model) or `MODEL_BACKEND=stub` (brightness heuristic, no model file needed) — so replacing or retraining the model never touches the API or frontend.

**Why "Drying" isn't a model class:** a single still frame cannot show a *change over time* — a drying track and a stably-damp track can look identical in one photo. So the model only predicts the **moisture level** (Dry/Damp/Wet) of a single frame; the **direction** (Drying/Wetting) is computed in `backend/app/smoothing.py` from how that level moves across a confidence-weighted window of recent frames, with hysteresis so single-frame noise (glare, spray) doesn't flip the readout.

---

## 3. Current Implementation Status

| Component | Status | Notes |
|---|---|---|
| Frontend | ✅ Working | React + Vite "Pit Wall" dashboard — Chart.js wetness trace, tyre-compound badge, per-class confidence bars |
| Backend API | ✅ Working | FastAPI, `/predict`, `/trend`, `/suggestion`, `/health` |
| Trend/suggestion logic | ✅ Working | `backend/app/smoothing.py` — confidence-weighted moving average + hysteresis for Drying/Wetting |
| Database | ✅ Working | SQLite (`backend/app/db.py`), one row per frame, session-scoped, on a Docker volume |
| Inference service | ✅ Working — real model | `inference/server.py`, `MODEL_BACKEND=onnx` by default; `stub` heuristic kept as a no-model-file fallback |
| Trained classifier | ✅ Done | MobileNetV3-Small transfer-learned, exported to `inference/model/model.onnx` — see `training/train_colab.ipynb` |
| Docker / docker-compose | ✅ Working | All three services start with `docker compose up --build`, verified end to end |
| CI | ✅ Working | GitHub Actions builds all three images; pushes to GHCR on `main` |
| Cloud deployment | ❌ Not done | See §7 — plan only, no live environment yet |

### 3.1 About the classifier

`inference/server.py` supports two backends, selected by `MODEL_BACKEND`:

- **`onnx` (default)** — loads `inference/model/model.onnx` (a MobileNetV3-Small fine-tuned on Dry/Damp/Wet, see §4) via ONNX Runtime. `inference/model/class_names.json` records the trained class order so it can be remapped to the app's canonical `["Dry","Damp","Wet"]` order regardless of training order.
- **`stub`** — a deterministic brightness/saturation heuristic requiring no model file at all. Useful for environments without `model.onnx`, or for testing the rest of the pipeline in isolation from the model.

Both return the same shape: `{label, confidence, scores, backend}`.

---

## 4. Data & Model Plan

1. **Data collection:** trackside/onboard images labeled Dry/Damp/Wet. (The shipped `model.onnx` was trained on a small/synthetic smoke-test set via the Colab notebook's Option C — good enough to prove the pipeline end to end, **not** yet validated on real track photography. Swapping in a real labeled dataset is the next accuracy milestone, not a code change.)
2. **Labeling:** spreadsheet + image folder is enough at this scale; revisit tooling if volume grows.
3. **Model:** transfer learning on MobileNetV3-Small (ImageNet-pretrained), 3-class softmax head (Dry/Damp/Wet) — see `training/train_colab.ipynb`.
4. **Packaging:** exported to ONNX (opset 13, dynamic batch axis) for fast, portable CPU inference — no PyTorch runtime needed in the production container.
5. **Evaluation:** the notebook prints a confusion matrix; watch Damp↔Wet confusion especially (visually similar, different implications for a tire call).
6. **Retraining loop:** rerun `training/train_colab.ipynb` with real labeled data, download `model.onnx` + `class_names.json`, drop both into `inference/model/`, rebuild the inference image. No other service changes.

---

## 5. Components & Responsibilities

### 5.1 Frontend (`frontend/`)
- Single page ("Pit Wall"): camera-frame upload, tyre-compound condition badge, per-class confidence bars, live wetness trace (Chart.js), strategy-call banner.
- Polls `GET /trend` and `GET /health` every 3s so the trace and LIVE/OFFLINE indicator stay current.
- Stack: React + Vite + Chart.js, served via nginx in production.

### 5.2 Backend API (`backend/`)
- `POST /predict?session=` — accepts an uploaded image, calls the inference service, persists the result, returns the frame result plus the current readout (condition/trend/suggestion/count). Fails safe to `condition: "Unknown"` if inference is unreachable, rather than showing a stale or confident-but-wrong label.
- `GET /trend?session=&window_s=` — time series (for the chart) plus the current readout.
- `GET /suggestion?session=` — just the strategy-call message.
- `GET /health` — liveness plus whether the inference service is reachable and which model backend it's running.
- Stack: FastAPI, SQLite (stdlib `sqlite3`), httpx (to call inference).

### 5.3 Inference Service (`inference/`)
- `POST /infer` — JSON body `{"image_b64": "..."}`, returns `{label, confidence, scores, backend}`. This is what the backend calls.
- `POST /infer_file` — same response, multipart upload — convenient for manual `curl -F` testing.
- Backends: `onnx` (real trained model, §3.1/§4) and `stub` (heuristic fallback).

### 5.4 Database (`backend/app/db.py`)
- SQLite, single `predictions` table: `id, session, ts, label, confidence, scores (json), backend`.
- Lives on the `track_data` Docker volume (`DB_PATH=/data/track.db`), so predictions survive container restarts.
- Session-scoped so multiple simultaneous camera feeds don't mix trends.

### 5.5 Trend & Suggestion Logic (`backend/app/smoothing.py`)
Rule-based and explainable — no black-box trend model:
- `smooth_current()` — confidence-weighted average moisture over the last 8 frames → a stable Dry/Damp/Wet state that resists single-frame flicker.
- `trend_direction()` — compares the last 6 frames' average wetness against the 6 before that; a sustained drop beyond a hysteresis threshold → **Drying**, a sustained rise → **Wetting**, otherwise **Stable**.
- `make_suggestion()` — maps (state, direction) to a strategy-call message, e.g. *"Track drying: tyre change window approaching — ready slicks/inters."*
- `display_condition()` — folds direction into state for the headline badge (e.g. shows **Drying** instead of Damp/Wet when the trend is confidently improving).

---

## 6. Dockerization

### 6.1 Repo layout
```
weather-whiplash/
├── frontend/
│   ├── Dockerfile
│   └── src/...
├── backend/
│   ├── Dockerfile
│   └── app/            # main.py, db.py, smoothing.py
├── inference/
│   ├── Dockerfile
│   ├── model/           # model.onnx + class_names.json (trained model)
│   └── server.py
├── training/
│   └── train_colab.ipynb   # reproduces model.onnx from labeled data
├── sample/
│   └── simulate.py         # demo driver — synthetic wet→dry sequence against the running API
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── .github/workflows/build.yml
└── docs/PLANNING.md
```

### 6.2 Local dev
```bash
cp .env.example .env
docker compose up --build
```
- Frontend: http://localhost:3000
- Backend: http://localhost:8000/docs (Swagger UI)
- Inference: http://localhost:8500/health (internal, exposed locally for debugging)

Or, without any real camera footage, drive it with synthetic frames:
```bash
python sample/simulate.py --session demo
```

### 6.3 Production overrides (`docker-compose.prod.yml`)
- Resource limits, `restart: always`.
- No separate DB service to manage — SQLite on the `track_data` volume. Make sure that volume is on durable, backed-up storage; move to a shared/managed DB only if the backend ever needs multiple replicas.
- TLS termination via a reverse proxy (Traefik/nginx) or cloud load balancer, in front of the frontend/backend.

---

## 7. Deployment Plan

### 7.1 Environments
| Env | Purpose | Notes |
|---|---|---|
| Local | dev with `docker compose up` | hot reload for frontend/backend |
| Staging | pre-race testing with recorded footage | mirrors prod config, smaller instance |
| Production (race day) | live inference at trackside or cloud | low latency required — consider edge/on-prem near the track if network is unreliable |

### 7.2 Hosting options
- **Cloud:** frontend as static hosting (S3+CloudFront or Vercel/Netlify); backend + inference as containers on ECS/Cloud Run/AKS; `track_data` volume on durable block storage (or move to managed Postgres if multi-replica is ever needed).
- **On-prem/edge at the track:** if venue network is unreliable, run the whole `docker-compose` stack on a rugged mini-PC trackside; sync summarized trend snapshots to the cloud when connectivity allows.
- **Hybrid (recommended for race day):** inference + backend run locally at the track for low latency; a lightweight sync job pushes trend snapshots to a cloud dashboard for remote viewers.

### 7.3 CI/CD (`.github/workflows/build.yml`)
1. **Build** — on every push, GitHub Actions builds all three Docker images (matrix over `frontend` / `backend` / `inference`).
2. **Push** — on push to `main`, images are tagged with the commit SHA and pushed to GHCR (`ghcr.io/<owner>/weather-whiplash-<service>`), using the workflow's built-in `GITHUB_TOKEN` — no extra secrets needed to get this far.
3. **Deploy** — not yet wired up. Staging auto-deploy and a manual production trigger are the next step once a hosting target (§7.2) is chosen.

### 7.4 Monitoring & reliability (race-day critical, partially done)
- Health checks exist on all three services (`/health`); wiring them into the orchestrator's restart policy is still open.
- Predictions are logged with timestamps for post-race review and future model retraining (already happening via the `predictions` table).
- Fallback implemented: if the inference service is unreachable, `/predict` returns `condition: "Unknown"` with a "check the track visually" suggestion instead of a stale or confidently-wrong label.

---

## 8. Build Order / Milestones

- [x] **M0 — Wiring skeleton:** all services running end to end locally via docker-compose.
- [x] **M1 — Real classifier:** MobileNetV3-Small trained and exported to ONNX, running as the default inference backend. *(Still trained on a small/synthetic set — swapping in a real labeled dataset is the next accuracy pass, via the same notebook.)*
- [ ] **M2 — Frontend polish:** live/webcam capture, not just file upload; the "per-frame confidence" panel currently only shows data right after an upload in that browser session (resets on the next poll) — carry the last frame's scores forward instead.
- [ ] **M3 — Staging deploy:** pick a hosting target, deploy with recorded race footage end-to-end.
- [ ] **M4 — Production hardening:** health-check-driven restarts, monitoring/alerting, race-day deployment runbook, manual-trigger production deploy in CI.

---

## 9. Open Questions

- How much real labeled trackside data is available to retrain M1's model beyond the synthetic smoke-test set?
- Is a weather-data feed available/needed for v1, or vision-only first?
- Trackside network reliability — does this force an edge-deployment design from day one?
- Who reviews/labels the training data, and how does the dataset stay in sync as more footage comes in?
