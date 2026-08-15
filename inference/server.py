"""Track-condition inference service.

Two interchangeable backends, chosen by the MODEL_BACKEND env var:

  onnx  -> the trained model in model/model.onnx (default, now that one exists).
           Predicts moisture LEVEL only: Dry / Damp / Wet.
  stub  -> deterministic brightness/saturation heuristic, no model file needed.
           Kept as a fallback for environments without a model.onnx.

NOTE on "Drying": a single still frame can't distinguish "damp" from "drying" —
drying is a change over time, not something visible in one image. So this
service only ever predicts the moisture LEVEL. The headline "Drying" condition
is derived by the backend's trend logic (backend/app/smoothing.py) from how
that level moves across a window of frames.

Every backend returns the same shape:
  { "label": "Wet", "confidence": 0.83, "scores": {"Dry":0.02,"Damp":0.15,"Wet":0.83},
    "backend": "onnx" }
"""

import base64
import io
import json
import os
from pathlib import Path
from typing import Dict

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

app = FastAPI(title="Track Condition AI — Inference")

MODEL_BACKEND = os.getenv("MODEL_BACKEND", "onnx").lower()
ONNX_MODEL_PATH = os.getenv("ONNX_MODEL_PATH", str(Path(__file__).parent / "model" / "model.onnx"))
ONNX_CLASSES_PATH = os.getenv(
    "ONNX_CLASSES_PATH", str(Path(__file__).parent / "model" / "class_names.json")
)

# Canonical class order the rest of the app expects.
CLASS_NAMES = ["Dry", "Damp", "Wet"]

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class InferRequest(BaseModel):
    image_b64: str


class InferResponse(BaseModel):
    label: str
    confidence: float
    scores: Dict[str, float]
    backend: str


def _load_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image file.") from exc


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - np.max(x)
    e = np.exp(x)
    return e / np.sum(e)


# --------------------------------------------------------------------------
# Backend: stub — brightness/saturation heuristic (no model file needed)
# --------------------------------------------------------------------------
def infer_stub(img: Image.Image) -> np.ndarray:
    g = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    brightness = float(g.mean())
    highlights = float((g > 0.85).mean())  # fraction of very-bright pixels (reflections)

    wetness = (1.0 - brightness) * 0.7 + highlights * 0.6
    wetness = max(0.0, min(1.0, wetness))

    centers = np.array([0.15, 0.5, 0.85])  # Dry, Damp, Wet
    logits = -((wetness - centers) ** 2) / 0.05
    return _softmax(logits)


# --------------------------------------------------------------------------
# Backend: onnx — the trained model
# --------------------------------------------------------------------------
_onnx_session = None
_onnx_classes = CLASS_NAMES


def _init_onnx():
    global _onnx_session, _onnx_classes
    if _onnx_session is not None:
        return
    import onnxruntime as ort

    if not os.path.exists(ONNX_MODEL_PATH):
        raise FileNotFoundError(
            f"MODEL_BACKEND=onnx but no model at {ONNX_MODEL_PATH}. "
            f"Train one and drop model.onnx into inference/model/, or set "
            f"MODEL_BACKEND=stub to run without a trained model."
        )
    _onnx_session = ort.InferenceSession(ONNX_MODEL_PATH, providers=["CPUExecutionProvider"])

    if os.path.exists(ONNX_CLASSES_PATH):
        with open(ONNX_CLASSES_PATH) as f:
            _onnx_classes = json.load(f)


def _preprocess_224(img: Image.Image) -> np.ndarray:
    img = img.resize((224, 224), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    arr = np.transpose(arr, (2, 0, 1))[None, ...]  # NCHW
    return arr.astype(np.float32)


def infer_onnx(img: Image.Image) -> np.ndarray:
    _init_onnx()
    x = _preprocess_224(img)
    inp = _onnx_session.get_inputs()[0].name
    logits = _onnx_session.run(None, {inp: x})[0].squeeze(0)
    probs = _softmax(np.asarray(logits, dtype=np.float32))

    # reorder from the model's trained class order into our canonical order
    out = np.zeros(len(CLASS_NAMES), dtype=np.float32)
    for i, cls in enumerate(_onnx_classes):
        if cls in CLASS_NAMES:
            out[CLASS_NAMES.index(cls)] = probs[i]
    s = out.sum()
    return out / s if s > 0 else _softmax(out)


BACKENDS = {"stub": infer_stub, "onnx": infer_onnx}


def run_inference(img: Image.Image) -> InferResponse:
    fn = BACKENDS.get(MODEL_BACKEND, infer_stub)
    try:
        scores = fn(img)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    idx = int(np.argmax(scores))
    return InferResponse(
        label=CLASS_NAMES[idx],
        confidence=round(float(scores[idx]), 4),
        scores={c: round(float(s), 4) for c, s in zip(CLASS_NAMES, scores)},
        backend=MODEL_BACKEND,
    )


@app.get("/health")
def health():
    return {"status": "ok", "backend": MODEL_BACKEND, "classes": CLASS_NAMES}


@app.post("/infer", response_model=InferResponse)
def infer(req: InferRequest):
    raw = base64.b64decode(req.image_b64)
    return run_inference(_load_image(raw))


@app.post("/infer_file", response_model=InferResponse)
async def infer_file(file: UploadFile = File(...)):
    raw = await file.read()
    return run_inference(_load_image(raw))
