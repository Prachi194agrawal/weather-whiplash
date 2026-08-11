# Weather Whiplash — Track Condition AI

Track conditions (dry, wet, drying) can change faster than weather reports update. This app takes trackside/onboard camera frames, classifies the surface as **Dry / Damp / Wet / Drying**, plots the trend, and suggests when a tire change window is approaching.

Full planning, architecture, and deployment doc: [docs/PLANNING.md](docs/PLANNING.md)

> **Status:** end-to-end skeleton is working (upload → classify → store → trend → suggestion → UI). The classifier is currently a deterministic image-heuristic placeholder, **not a trained model** — see [docs/PLANNING.md §3.1](docs/PLANNING.md#31-about-the-current-classifier--read-this-first) before trusting its output.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Inference service: http://localhost:8500/health
- Postgres: localhost:5432 (user/pass `postgres`/`postgres`, db `track`)

Upload any image in the frontend to see a label, then upload a few more to watch the trend chart and suggestion update.

## Repo layout

```
frontend/     React + Vite UI (upload, condition badge, trend chart, suggestion)
backend/      FastAPI: /predict, /trend, /suggestion, /health, Postgres via SQLAlchemy
inference/    FastAPI classifier service: /infer (heuristic placeholder, see docs)
docs/         Planning, architecture, and deployment documentation
```

## Running services individually (without Docker)

```bash
# inference
cd inference && pip install -r requirements.txt && uvicorn server:app --port 8500 --reload

# backend (needs Postgres reachable at DATABASE_URL)
cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000 --reload

# frontend
cd frontend && npm install && npm run dev
```

## CI

`.github/workflows/build.yml` builds all three images on every push/PR, and pushes them to `ghcr.io/<owner>/weather-whiplash-<service>` on pushes to `main`.

## License

MIT
