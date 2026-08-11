from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.db import Base


class Frame(Base):
    __tablename__ = "frames"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    label = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    image_name = Column(String, nullable=True)
