"""Track-condition inference service.

NOTE: classify_image() below is a deterministic HSV-heuristic placeholder,
not a trained model. It exists so the full pipeline (upload -> inference ->
trend -> suggestion -> UI) is real and runnable end to end before a labeled
dataset and trained classifier exist. See docs/PLANNING.md section 4 for the
plan to replace this with an ONNX Runtime model — the POST /infer contract
below (label + confidence) is designed to stay stable across that swap.
"""

import io

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

app = FastAPI(title="Track Condition AI — Inference")

LABELS = ["Dry", "Damp", "Wet", "Drying"]


class InferenceResult(BaseModel):
    label: str
    confidence: float


def classify_image(image: Image.Image) -> InferenceResult:
    img = image.convert("RGB").resize((64, 64))
    hsv = np.asarray(img.convert("HSV")).astype(np.float32) / 255.0
    saturation = hsv[..., 1]
    value = hsv[..., 2]

    highlight_ratio = float((value > 0.85).mean())
    mean_saturation = float(saturation.mean())

    wetness_score = highlight_ratio * 2.0 - mean_saturation * 0.5

    if wetness_score > 0.5:
        label, confidence = "Wet", min(0.55 + wetness_score, 0.98)
    elif wetness_score > 0.25:
        label, confidence = "Drying", 0.60
    elif wetness_score > 0.1:
        label, confidence = "Damp", 0.60
    else:
        label, confidence = "Dry", min(0.60 + (0.1 - wetness_score), 0.95)

    return InferenceResult(label=label, confidence=round(confidence, 2))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/infer", response_model=InferenceResult)
async def infer(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image file.") from exc

    return classify_image(image)
