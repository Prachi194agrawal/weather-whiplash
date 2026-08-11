# Track Condition AI (Weather Whiplash) — Planning & Deployment Documentation

## 1. Project Overview

**Problem:** Track conditions (dry, wet, drying) can change faster than weather reports update. Race teams need a real-time read on whether the track is getting safer or riskier so they can decide when to change tires.

**Solution:** Feed in camera images or video frames (trackside or onboard). The AI classifies each frame as **Dry / Damp / Wet / Drying**, tracks the trend over time, and surfaces a plain-language suggestion (e.g. *"Track drying: tire change window approaching"*).

**Core loop:**
```
Camera/video frame → Backend API → Inference service → Condition label + confidence
                                                       → stored in trend DB
                                                       → Frontend shows image, label, trend, suggestion
```

This document is the living plan for what's been built, what's stubbed, and what's left before race-day use.

---

## 2. System Architecture

```
┌─────────────────┐        ┌──────────────────────┐        ┌────────────────┐
│   Frontend       │  HTTP  │   Backend API         │  SQL   │   Database      │
│  (React/Vite)    │◄──────►│  (FastAPI)            │◄──────►│ (Postgres)      │
│  - Upload image   │        │  - POST /predict      │        │  - frames       │
│  - Trend chart    │        │  - GET  /trend        │        │                 │
│  - Suggestion box │        │  - GET  /suggestion    │        │                 │
└─────────────────┘        └──────────┬────────────┘        └────────────────┘
                                       │ HTTP
                             ┌─────────▼─────────┐
                             │  Inference Service │
                             │  (FastAPI + Pillow) │
                             │  runs in its own    │
                             │  container           │
                             └─────────────────────┘
```

**Why inference is its own service:** the classifier will eventually need a GPU image and different scaling rules than the lightweight API/DB layer. Keeping it separate means the model can be swapped (heuristic → trained ONNX model) without touching the API or frontend contracts.

---

## 3. Current Implementation Status

| Component | Status | Notes |
|---|---|---|
| Frontend | ✅ Working | React + Vite, upload panel, condition badge, trend chart (Recharts), suggestion banner |
| Backend API | ✅ Working | FastAPI, `/predict`, `/trend`, `/suggestion`, `/health` |
| Database | ✅ Working | Postgres via SQLAlchemy, single `frames` table |
| Inference service | ⚠️ Heuristic placeholder | See below — **not a trained model yet** |
| Docker / docker-compose | ✅ Working | All four services start with `docker-compose up` |
| CI | ✅ Working | GitHub Actions builds all three images; pushes to GHCR on `main` |
| Cloud deployment | ❌ Not done | See §6 — plan only, no live environment yet |
| Trained classifier | ❌ Not done | See §4 — this is the biggest open item |

### 3.1 About the current classifier — read this first

`inference/server.py` does **not** contain a trained model. It uses a simple, deterministic image-heuristic (brightness/saturation/highlight-ratio in HSV space) to guess a label so the *entire pipeline* — upload → inference → DB → trend → suggestion → UI — is real and runnable end to end today. It will produce plausible-looking but **not trustworthy** predictions. Treat it as a wiring placeholder for Milestone M1 (§7), to be replaced by an actual trained/exported model without changing any other service.

---

## 4. Data & Model Plan (not yet started)

1. **Data collection:** trackside/onboard images labeled Dry/Damp/Wet/Drying. "Drying" is the hardest class — may need short sequences rather than single frames to label reliably.
2. **Labeling:** start with a spreadsheet + image folder, or weak-label from weather station timestamps.
3. **Model v1:** transfer learning on a pretrained lightweight CNN (MobileNetV3 or EfficientNet-lite), 4-class softmax output.
4. **Packaging:** export to ONNX for fast, portable CPU/GPU inference (avoids shipping a full PyTorch runtime in the production container).
5. **Evaluation:** confusion matrix across the 4 classes; pay special attention to Damp vs Drying confusion (visually similar, different implications for a tire-change call).
6. **Swap-in point:** replace `classify_image()` in `inference/server.py` with a real ONNX Runtime session; the REST contract (`POST /infer` → `{label, confidence}`) stays the same, so nothing else in the stack changes.

---

## 5. Components & Responsibilities

### 5.1 Frontend (`frontend/`)
- Single page: upload panel, condition badge (label + confidence), trend line chart (last N minutes), suggestion banner.
- Polls `GET /trend` and `GET /suggestion` on an interval after each upload.
- Stack: React + Vite + Recharts, served via nginx in production.

### 5.2 Backend API (`backend/`)
- `POST /predict` — accepts an uploaded image, calls the inference service, persists the result, returns `{label, confidence, timestamp}`.
- `GET /trend?window_minutes=15` — returns the time series of labels/confidence for the chart.
- `GET /suggestion` — derives a rule-based suggestion from the recent trend window.
- `GET /health` — liveness check.
- Stack: FastAPI, SQLAlchemy, Postgres, httpx (to call inference).

### 5.3 Inference Service (`inference/`)
- `POST /infer` — accepts an image, returns `{label, confidence}`. Internal-only, not exposed publicly.
- Current implementation: HSV-heuristic placeholder (§3.1).
- Planned: ONNX Runtime session loading `model/model.onnx` (§4).

### 5.4 Database
- Postgres, single `frames` table: `id, timestamp, label, confidence, image_name`.
- Enough for v1. If frame volume grows, consider the TimescaleDB extension for the time-series queries.

### 5.5 Trend & Suggestion Logic (`backend/app/trend.py`)
Rule-based, no ML needed for v1:
- Map labels to a wetness severity score (`Dry=0, Drying=1, Damp=2, Wet=3`).
- Compare the average severity of the first half vs. second half of the current window.
- Falling severity + recent labels trending toward Dry → *"Track improving — drying out."*
- Rising severity → *"Track worsening — consider wet-weather tires."*
- Consistent "Drying" reads → *"Track drying: tire change window approaching."*
- Not enough data yet → *"Not enough data yet."*

This can later be upgraded to a small time-series model, but rules are enough for v1 and are easy to explain to race engineers.

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
│   └── app/...
├── inference/
│   ├── Dockerfile
│   ├── model/            # trained model drops in here later (§4)
│   └── server.py
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
- Postgres: localhost:5432

### 6.3 Production overrides (`docker-compose.prod.yml`)
- Resource limits, `restart: always`.
- Managed DB connection string instead of the local Postgres container.
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
- **Cloud:** frontend as static hosting (S3+CloudFront or Vercel/Netlify); backend + inference as containers on ECS/Cloud Run/AKS; Postgres as managed RDS/Cloud SQL.
- **On-prem/edge at the track:** if venue network is unreliable, run the whole `docker-compose` stack on a rugged mini-PC trackside; sync summarized trend snapshots to the cloud when connectivity allows.
- **Hybrid (recommended for race day):** inference + backend run locally at the track for low latency; a lightweight sync job pushes trend snapshots to a cloud dashboard for remote viewers.

### 7.3 CI/CD (`.github/workflows/build.yml`)
1. **Build** — on every push, GitHub Actions builds all three Docker images (matrix over `frontend` / `backend` / `inference`).
2. **Push** — on push to `main`, images are tagged with the commit SHA and pushed to GHCR (`ghcr.io/<owner>/weather-whiplash-<service>`), using the workflow's built-in `GITHUB_TOKEN` — no extra secrets needed to get this far.
3. **Deploy** — not yet wired up. Staging auto-deploy and a manual production trigger are the next step once a hosting target (§7.2) is chosen.

### 7.4 Monitoring & reliability (race-day critical, not yet implemented)
- Health checks on all three services (`/health` already exists on backend and inference — wire these into the orchestrator's restart policy).
- Log predictions with timestamps for post-race review and future model retraining (already happening via the `frames` table).
- Fallback: if the inference service is unreachable, the frontend should show "condition unknown — check visually" rather than a stale label (not yet implemented in the frontend).

---

## 8. Build Order / Milestones

- [x] **M0 — Wiring skeleton:** all four services running end to end locally via docker-compose, heuristic classifier standing in for a trained model.
- [ ] **M1 — Real classifier:** collect/label data, train, export ONNX, swap into `inference/server.py`.
- [ ] **M2 — Frontend polish:** live/webcam capture, not just file upload; graceful "inference unreachable" state.
- [ ] **M3 — Staging deploy:** pick a hosting target, deploy with recorded race footage end-to-end.
- [ ] **M4 — Production hardening:** health-check-driven restarts, monitoring/alerting, race-day deployment runbook, manual-trigger production deploy in CI.

---

## 9. Open Questions

- Single-frame classification vs. short video-clip classification for better "Drying" detection?
- Is a weather-data feed available/needed for v1, or vision-only first?
- Trackside network reliability — does this force an edge-deployment design from day one?
- Who reviews/labels the training data, and how does the dataset stay in sync as more footage comes in?
