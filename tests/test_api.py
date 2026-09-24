import asyncio
from types import SimpleNamespace as NS
from fastapi.testclient import TestClient
from backend import app as api
from backend.core import grounded_spans, aggregate, LABELS

client = TestClient(api.app)

def test_health_and_origin():
    assert client.get('/api/health').json()['persistence'] is False
    assert client.post('/api/analyze', json={'text':'hello'}, headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.post('/api/analyze', content='text').status_code == 415

def test_input_limits():
    for body in [{'text':'  '}, {'text':'x'*12001}, {'text':'x','context':'y'*6001}, {'text':'x','extra':True}]:
        assert client.post('/api/analyze', json=body).status_code == 422
    assert client.post('/api/analyze',content=b'x'*100001,headers={'Content-Type':'application/json'}).status_code == 413

def test_partial_and_no_error_payload_leak(monkeypatch):
    async def good(body): return {'label':'explain'}
    async def bad(text): raise ValueError('PRIVATE_PAYLOAD_SHOULD_NOT_ESCAPE')
    monkeypatch.setattr(api,'classify',good);monkeypatch.setattr(api,'extraction',bad)
    result=client.post('/api/analyze',json={'text':'Explain the cache.'}).json()
    assert result['status']=='partial'
    assert result['stages']['jev']['result']['label']=='explain'
    assert 'PRIVATE_PAYLOAD' not in str(result)

def test_parallel_stages(monkeypatch):
    async def good(_): await asyncio.sleep(.03); return {'model':'test'}
    monkeypatch.setattr(api,'classify',good);monkeypatch.setattr(api,'extraction',good)
    result=client.post('/api/analyze',json={'text':'Explain the cache.'}).json()
    assert result['status']=='complete'
    assert result['elapsed_ms'] < sum(s['duration_ms'] for s in result['stages'].values())

def test_grounding_and_utf16():
    def item(start,end,text): return NS(char_interval=NS(start_pos=start,end_pos=end),extraction_class='entity',extraction_text=text,attributes={})
    spans,rejected=grounded_spans('😀 Atlas',[item(2,7,'Atlas'),item(0,1,'invented'),item(-1,1,'')])
    assert rejected==2 and spans[0]['start']==3 and spans[0]['end']==8

def test_aggregation():
    output={'intent':{'probabilities':{label:1 if label=='explain' else 0 for label in LABELS}},
            'signal':{'probabilities':{'noise':.2,'episodic':.3,'durable':.5}},'memory':{'noul':.2},'multiple':{'noul':.1}}
    result=aggregate([output,output]);assert result['label']=='explain' and not result['uncertain']

def test_busy_rejection():
    async def run():
        async with api.busy:
            try: await api.analyze(api.Input(text='test'))
            except api.HTTPException as error: assert error.status_code==429
            else: assert False
    asyncio.run(run())

def test_private_endpoint_validation(monkeypatch):
    monkeypatch.setattr(api.socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('8.8.8.8',80))])
    import pytest
    with pytest.raises(ValueError): api.private_endpoint('http://example.test')
    monkeypatch.setattr(api.socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('127.0.0.1',80))])
    api.private_endpoint('http://localhost:11434')
    with pytest.raises(ValueError): api.private_endpoint('https://user:password@localhost')

def test_jev_adapter_contract(monkeypatch):
    from backend import jev_server
    from backend.core import QUESTIONS
    class Model:
        def decide(self, state, questions):
            assert state == 'Synthetic test'
            assert questions == list(QUESTIONS.values())
            return [{'test': key} for key in QUESTIONS]
    monkeypatch.setattr(jev_server, 'model', Model())
    with_client = TestClient(jev_server.app)
    result = with_client.post('/v1/systemone', json={'state':'Synthetic test','questions':QUESTIONS})
    assert result.status_code == 200
    assert list(result.json()['answers']) == list(QUESTIONS)
    assert with_client.post('/v1/systemone', json={'state':'test','questions':{'arbitrary':{}}}).status_code == 422

def test_chunking_preserves_tail_and_whitespace():
    from backend.core import chunks, envelope
    class Tokenizer:
        def encode(self, text, **kwargs):
            return NS(offsets=[(0,3),(4,7),(8,13)])
    text='one two three'
    parts, count = chunks(text, Tokenizer(), 2)
    assert count == 3 and ''.join(parts) == text and parts[-1] == 'three'
    assert envelope('current','prior').endswith('[CURRENT USER REQUEST]\ncurrent')
