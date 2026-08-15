# Weather Whiplash — Track Condition AI ("Pit Wall")

Track conditions (dry, wet, drying) can change faster than weather reports update. This app takes trackside/onboard camera frames, classifies the surface, plots the trend, and suggests when a tire change window is approaching — e.g. *"Track drying: tyre change window approaching."*

Full planning, architecture, and deployment doc: [docs/PLANNING.md](docs/PLANNING.md)

> **Status:** running end to end with a **real trained ONNX model**, not a placeholder. The model predicts per-frame moisture (Dry/Damp/Wet) only — a single frame can't show "drying," since that's a change over time, not a texture. The backend's trend logic (`backend/app/smoothing.py`) derives the headline **Drying**/**Wetting** direction from a confidence-weighted moving window across recent frames. See [docs/PLANNING.md §3](docs/PLANNING.md).

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend ("Pit Wall" dashboard): http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Inference service: http://localhost:8500/health

Upload a track image in the frontend to see a condition badge, per-class confidence bars, and a live wetness trace. Upload a few more to watch the trend and strategy suggestion update.

## Repo layout

```
frontend/     React + Vite "Pit Wall" dashboard (Chart.js wetness trace, tyre-compound badge)
backend/      FastAPI: /predict, /trend, /suggestion, /health — SQLite storage + trend smoothing
inference/    FastAPI classifier: /infer, /infer_file — real ONNX model (stub heuristic fallback)
docs/         Planning, architecture, and deployment documentation
```

## Model backends

Set via `MODEL_BACKEND` (see `.env.example`):

- `onnx` (default) — the trained model in `inference/model/model.onnx`, classes in `inference/model/class_names.json`.
- `stub` — a brightness/saturation heuristic requiring no model file, useful if `model.onnx` isn't present.

## Running services individually (without Docker)

```bash
# inference
cd inference && pip install -r requirements.txt && uvicorn server:app --port 8500 --reload

# backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000 --reload

# frontend
cd frontend && npm install && npm run dev
```

## CI

`.github/workflows/build.yml` builds all three images on every push/PR, and pushes them to `ghcr.io/<owner>/weather-whiplash-<service>` on pushes to `main`.

## License

MIT
