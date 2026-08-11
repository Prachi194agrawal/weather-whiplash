from datetime import datetime

from pydantic import BaseModel


class PredictionOut(BaseModel):
    id: int
    timestamp: datetime
    label: str
    confidence: float
    image_name: str | None = None

    class Config:
        from_attributes = True


class SuggestionOut(BaseModel):
    suggestion: str
    direction: str
    latest_label: str | None = None
    window_size: int
