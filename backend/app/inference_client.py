import os

import httpx

INFERENCE_URL = os.getenv("INFERENCE_URL", "http://localhost:8500")


async def classify(image_bytes: bytes, filename: str, content_type: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{INFERENCE_URL}/infer",
            files={"file": (filename, image_bytes, content_type)},
        )
        response.raise_for_status()
        return response.json()
