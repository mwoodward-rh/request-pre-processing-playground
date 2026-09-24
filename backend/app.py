"""Loopback-only, stateless analysis API. No Guardian imports or persistence."""
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
import time
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from backend.core import QUESTIONS, aggregate, chunks, envelope

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title='Request Intelligence Lab', version='0.1.0')
busy = asyncio.Lock()
tokenizer = None

def private_endpoint(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid endpoint')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 80, type=socket.SOCK_STREAM)
    if not addresses or any(not (ipaddress.ip_address(a[4][0]).is_private or ipaddress.ip_address(a[4][0]).is_loopback
                                or ipaddress.ip_address(a[4][0]) in ipaddress.ip_network('100.64.0.0/10')) for a in addresses):
        raise ValueError('Only local/private model endpoints are supported')

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=12000)
    context: str = Field(default='', max_length=6000)

    @field_validator('text')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Request cannot be blank')
        return value

@app.middleware('http')
async def boundary(request: Request, call_next):
    # Host/Origin checks protect the unauthenticated loopback demo from browser drive-by requests.
    if request.url.hostname not in {'127.0.0.1', 'localhost', 'testserver'}:
        return JSONResponse({'detail': 'Loopback access only'}, status_code=403)
    origin = request.headers.get('origin')
    port = os.environ.get('LAB_PORT', '8030')
    allowed_origins = {f'http://{host}:{p}' for host in ['127.0.0.1', 'localhost'] for p in ['5186', port]}
    if origin and origin not in allowed_origins:
        return JSONResponse({'detail': 'Origin denied'}, status_code=403)
    if request.method == 'POST':
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'detail': 'JSON required'}, status_code=415)
        # Read incrementally, bounding even chunked bodies before validation.
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 100000:
                return JSONResponse({'detail': 'Request too large'}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

async def classify(body):
    global tokenizer
    url = os.environ.get('JEV_URL', 'http://127.0.0.1:8022')
    await asyncio.to_thread(private_endpoint, url)
    if tokenizer is None:
        from tokenizers import Tokenizer
        path = os.environ.get('JEV_TOKENIZER', 'models/open-jev/tokenizer.json')
        tokenizer = Tokenizer.from_file(path)  # No silent model downloads at request time.
    parts, tokens = chunks(body.text, tokenizer, 130 if body.context else 220)
    if len(parts) > 32:
        raise ValueError('Too many Jev chunks')
    offsets = tokenizer.encode(body.context, add_special_tokens=False).offsets
    context = body.context[offsets[-70][0]:] if len(offsets) > 70 else body.context
    outputs = []
    async with httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False) as client:
        for part in parts:
            response = await client.post(url.rstrip('/') + '/v1/systemone', json={'state': envelope(part, context), 'questions': QUESTIONS})
            response.raise_for_status()
            outputs.append(response.json()['answers'])
    return {**aggregate(outputs), 'model': os.environ.get('JEV_MODEL', 'com-kotobalabs/open-jev-deberta-v3-large'),
            'tokens': tokens, 'chunks': len(parts), 'context_tokens_used': min(len(offsets), 70),
            'context_truncated': len(offsets) > 70, 'aggregation': 'mean chunk distributions; maximum reference/task flags'}

async def extraction(text):
    await asyncio.to_thread(private_endpoint, os.environ.get('EXTRACTION_URL', 'http://127.0.0.1:11434'))
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'backend.extract', cwd=ROOT,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(json.dumps(text).encode()), timeout=180)
        if process.returncode:
            raise RuntimeError('Extraction failed')
        return json.loads(output)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

async def stage(fn):
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(fn(), timeout=190)
        return {'status': 'complete', 'duration_ms': round((time.perf_counter()-start)*1000), 'result': result}
    except Exception:
        return {'status': 'failed', 'duration_ms': round((time.perf_counter()-start)*1000),
                'error': 'Model stage unavailable. Check server configuration, model availability, and input limits. No fallback was substituted.'}

@app.get('/api/health')
def health():
    return {'ok': True, 'mode': 'passive', 'persistence': False, 'pii_redaction': False,
            'note': 'API health only; model availability is verified by analysis.'}

@app.post('/api/analyze')
async def analyze(body: Input):
    if busy.locked():
        raise HTTPException(429, 'One analysis is already running; retry when it finishes.')
    async with busy:
        source = envelope(body.text, body.context)
        start = time.perf_counter()
        jev, semantics = await asyncio.gather(stage(lambda: classify(body)), stage(lambda: extraction(source)))
        count = sum(s['status'] == 'complete' for s in [jev, semantics])
        return {'status': ['failed', 'partial', 'complete'][count], 'source': source,
                'elapsed_ms': round((time.perf_counter()-start)*1000), 'stages': {'jev': jev, 'langextract': semantics}}

if (ROOT / 'dist').is_dir():
    app.mount('/', StaticFiles(directory=ROOT / 'dist', html=True), name='dashboard')
