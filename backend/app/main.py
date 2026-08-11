from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.inference_client import classify
from app.models import Frame
from app.schemas import PredictionOut, SuggestionOut
from app.trend import build_suggestion

app = FastAPI(title="Track Condition AI — Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict", response_model=PredictionOut)
async def predict(file: UploadFile = File(...), db: Session = Depends(get_db)):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file upload.")

    try:
        result = await classify(image_bytes, file.filename, file.content_type)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Inference service unreachable: {exc}"
        ) from exc

    frame = Frame(
        label=result["label"],
        confidence=result["confidence"],
        image_name=file.filename,
    )
    db.add(frame)
    db.commit()
    db.refresh(frame)
    return frame


@app.get("/trend", response_model=list[PredictionOut])
def trend(window_minutes: int = 15, db: Session = Depends(get_db)):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    frames = (
        db.query(Frame)
        .filter(Frame.timestamp >= cutoff)
        .order_by(Frame.timestamp.asc())
        .all()
    )
    return frames


@app.get("/suggestion", response_model=SuggestionOut)
def suggestion(window_minutes: int = 15, db: Session = Depends(get_db)):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    frames = (
        db.query(Frame)
        .filter(Frame.timestamp >= cutoff)
        .order_by(Frame.timestamp.asc())
        .all()
    )
    return build_suggestion(frames)
