"""SQLite storage for per-frame predictions.

One row per classified frame: which session it belongs to, when it was taken,
what the model said, and the full per-class score distribution (so the trend
logic in smoothing.py can compute a confidence-weighted wetness average
instead of just looking at the argmax label).
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List

DB_PATH = os.getenv("DB_PATH", "track.db")


@contextmanager
def _connect():
    parent = Path(DB_PATH).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session TEXT NOT NULL,
                ts REAL NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                scores TEXT NOT NULL,
                backend TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predictions_session_ts ON predictions(session, ts)"
        )


def insert_prediction(
    session: str, label: str, confidence: float, scores: dict, backend: str
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO predictions (session, ts, label, confidence, scores, backend) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session, time.time(), label, confidence, json.dumps(scores), backend),
        )


def get_window(session: str, window_s: float) -> List[dict]:
    cutoff = time.time() - window_s
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ts, label, confidence, scores FROM predictions "
            "WHERE session = ? AND ts >= ? ORDER BY ts ASC",
            (session, cutoff),
        ).fetchall()
    return [
        {"ts": ts, "label": label, "confidence": confidence, "scores": json.loads(scores)}
        for ts, label, confidence, scores in rows
    ]
