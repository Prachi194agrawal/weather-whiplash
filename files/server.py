"""
Inference service for track/road surface condition.

ONE service, THREE interchangeable model backends, chosen by the MODEL_BACKEND env var:

  stub  -> a dependency-light brightness/contrast heuristic. Runs instantly, no model
           download, no torch. Great for getting the whole app running end-to-end today.
  clip  -> OpenAI CLIP zero-shot (via transformers). No training or dataset needed.
           Classifies each frame by comparing it to text prompts for each class.
  onnx  -> your own fine-tuned model exported from the Colab notebook (training/).
           This is the "real ML" path. Drop model/model.onnx + model/class_names.json in
           and set MODEL_BACKEND=onnx. Nothing else in the app changes.

Every backend returns the SAME shape:
  { "label": "Wet", "confidence": 0.83, "scores": {"Dry":0.02,"Damp":0.15,"Wet":0.83} }

IMPORTANT design note about "Drying":
  A single still frame cannot tell "damp" apart from "drying" — drying is a *change over
  time*, not something visible in one image. So this per-frame model only predicts the
  MOISTURE LEVEL (Dry / Damp / Wet). The direction (Drying / Wetting) is derived later in
  the backend from how the level moves across a window of frames. See backend/app/smoothing.py.
"""
import base64
import io
import os
from typing import Dict

import numpy as np
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from PIL import Image

# The per-frame classes the model can see in a single image.
# Keep this order consistent with training/class_names.json for the ONNX backend.
CLASS_NAMES = ["Dry", "Damp", "Wet"]

MODEL_BACKEND = os.getenv("MODEL_BACKEND", "stub").lower()

app = FastAPI(title="Track Condition Inference", version="1.0")


# --------------------------------------------------------------------------------------
# Request/response models
# --------------------------------------------------------------------------------------
class InferRequest(BaseModel):
    image_b64: str


class InferResponse(BaseModel):
    label: str
    confidence: float
    scores: Dict[str, float]
    backend: str


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _load_image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - np.max(x)
    e = np.exp(x)
    return e / np.sum(e)


# --------------------------------------------------------------------------------------
# Backend: STUB  (no heavy deps, instant)
# --------------------------------------------------------------------------------------
# Cheap physical intuition: wet asphalt is darker and has stronger specular highlights
# (bright reflections) than dry asphalt. We turn mean brightness + a highlight measure
# into a crude 3-class score. It is NOT accurate — it just lets the whole pipeline run
# with zero model setup so you can build/test frontend, trend, and suggestion logic.
def infer_stub(img: Image.Image) -> np.ndarray:
    g = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    brightness = float(g.mean())
    highlights = float((g > 0.85).mean())  # fraction of very-bright pixels (reflections)

    # wetness score rises as it gets darker and as specular highlights increase
    wetness = (1.0 - brightness) * 0.7 + highlights * 0.6
    wetness = max(0.0, min(1.0, wetness))

    # map a single wetness scalar onto 3 class logits with soft peaks at 0 / 0.5 / 1.0
    centers = np.array([0.15, 0.5, 0.85])  # Dry, Damp, Wet
    logits = -((wetness - centers) ** 2) / 0.05
    return _softmax(logits)


# --------------------------------------------------------------------------------------
# Backend: CLIP  (zero-shot, no training)
# --------------------------------------------------------------------------------------
_clip_model = None
_clip_processor = None
# Several prompts per class ("prompt ensembling") — averaging them is more robust than one.
CLIP_PROMPTS = {
    "Dry": [
        "a dry road surface, pale grey asphalt, no water",
        "a completely dry race track, matte dry tarmac",
    ],
    "Damp": [
        "a damp road surface, darker asphalt but no standing water",
        "a slightly wet track, moist tarmac without reflections",
    ],
    "Wet": [
        "a wet road surface with standing water and bright reflections",
        "a soaking wet race track with puddles and glare",
    ],
}


def _init_clip():
    global _clip_model, _clip_processor
    if _clip_model is not None:
        return
    import torch  # noqa
    from transformers import CLIPModel, CLIPProcessor

    name = os.getenv("CLIP_MODEL", "openai/clip-vit-base-patch32")
    _clip_model = CLIPModel.from_pretrained(name)
    _clip_processor = CLIPProcessor.from_pretrained(name)
    _clip_model.eval()


def infer_clip(img: Image.Image) -> np.ndarray:
    import torch

    _init_clip()
    prompts, owners = [], []
    for cls in CLASS_NAMES:
        for p in CLIP_PROMPTS[cls]:
            prompts.append(p)
            owners.append(cls)

    inputs = _clip_processor(text=prompts, images=img, return_tensors="pt", padding=True)
    with torch.no_grad():
        out = _clip_model(**inputs)
    # similarity of the image to each text prompt
    sims = out.logits_per_image.squeeze(0).numpy()  # shape [num_prompts]

    # average the prompt similarities within each class, then softmax over classes
    class_logits = np.array(
        [sims[[i for i, o in enumerate(owners) if o == cls]].mean() for cls in CLASS_NAMES]
    )
    return _softmax(class_logits)


# --------------------------------------------------------------------------------------
# Backend: ONNX  (your fine-tuned model)
# --------------------------------------------------------------------------------------
_onnx_session = None
_onnx_classes = CLASS_NAMES
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _init_onnx():
    global _onnx_session, _onnx_classes
    if _onnx_session is not None:
        return
    import json
    import onnxruntime as ort

    model_path = os.getenv("ONNX_MODEL_PATH", "model/model.onnx")
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"MODEL_BACKEND=onnx but no model at {model_path}. "
            f"Train one with training/train_colab.ipynb and drop model.onnx in inference/model/."
        )
    _onnx_session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    classes_path = os.path.join(os.path.dirname(model_path), "class_names.json")
    if os.path.exists(classes_path):
        with open(classes_path) as f:
            _onnx_classes = json.load(f)


def _preprocess_224(img: Image.Image) -> np.ndarray:
    img = img.resize((224, 224), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    arr = np.transpose(arr, (2, 0, 1))[None, ...]  # NCHW
    return arr.astype(np.float32)


def infer_onnx(img: Image.Image) -> np.ndarray:
    global _onnx_classes
    _init_onnx()
    x = _preprocess_224(img)
    inp = _onnx_session.get_inputs()[0].name
    logits = _onnx_session.run(None, {inp: x})[0].squeeze(0)
    probs = _softmax(np.asarray(logits, dtype=np.float32))
    # reorder to global CLASS_NAMES if the trained order differs
    out = np.zeros(len(CLASS_NAMES), dtype=np.float32)
    for i, cls in enumerate(_onnx_classes):
        if cls in CLASS_NAMES:
            out[CLASS_NAMES.index(cls)] = probs[i]
    s = out.sum()
    return out / s if s > 0 else _softmax(out)


BACKENDS = {"stub": infer_stub, "clip": infer_clip, "onnx": infer_onnx}


def run_inference(img: Image.Image) -> InferResponse:
    fn = BACKENDS.get(MODEL_BACKEND, infer_stub)
    scores = fn(img)
    idx = int(np.argmax(scores))
    return InferResponse(
        label=CLASS_NAMES[idx],
        confidence=round(float(scores[idx]), 4),
        scores={c: round(float(s), 4) for c, s in zip(CLASS_NAMES, scores)},
        backend=MODEL_BACKEND,
    )


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------
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
