"""Optional standalone adapter for OpenJev; run on loopback, not the public internet."""
import asyncio
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from backend.core import QUESTIONS

model = None
lock = asyncio.Lock()

@asynccontextmanager
async def lifespan(app):
    global model
    from typed_decisions.open_jev import OpenJev
    model = OpenJev.from_pretrained(os.environ.get('JEV_MODEL_PATH', 'models/open-jev'),
                                    device=os.environ.get('JEV_DEVICE', 'cpu'))
    yield
    model = None

app = FastAPI(title='OpenJev local inference', lifespan=lifespan)

class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    state: str = Field(min_length=1, max_length=18000)
    questions: dict = Field(min_length=1, max_length=4)

@app.get('/healthz')
def health():
    return {'ok': model is not None, 'model': os.environ.get('JEV_MODEL', 'com-kotobalabs/open-jev-deberta-v3-large')}

@app.post('/v1/systemone')
async def decide(body: Decision):
    # This example exposes only its fixed analysis questions, not arbitrary workloads.
    if body.questions != QUESTIONS:
        raise HTTPException(422, 'Unsupported question schema')
    if model is None or lock.locked():
        raise HTTPException(503, 'Model unavailable or busy')
    async with lock:
        try:
            answers = await asyncio.to_thread(model.decide, body.state, list(QUESTIONS.values()))
            return {'answers': dict(zip(QUESTIONS, answers))}
        except Exception:
            raise HTTPException(502, 'Inference failed') from None
