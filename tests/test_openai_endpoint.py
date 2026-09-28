import json

import httpx
import pytest

from backend.openai_endpoint import OpenAIEndpointModel, validate_base_url, validate_config


@pytest.mark.parametrize('url', ['', 'http://public.example/v1', 'https://user:secret@example.com/v1',
                                  'https://example.com/v1?key=secret', 'https://example.com/v1#part',
                                  'https://example.com/v1/chat/completions', 'https://example.com/v1/responses'])
def test_invalid_base_urls(url):
    with pytest.raises(ValueError):
        validate_base_url(url)


@pytest.mark.parametrize('url', ['https://example.com/v1', 'https://example.com/openai/v1/',
                                  'http://127.0.0.1:8080/v1'])
def test_supported_base_urls(url):
    assert validate_base_url(url) == url.rstrip('/')


def test_config_requires_explicit_model_and_credentials():
    env = {'OPENAI_BASE_URL': 'https://example.com/v1'}
    with pytest.raises(ValueError, match='EXTRACTION_MODEL'):
        validate_config(env)
    env['EXTRACTION_MODEL'] = 'chosen-model'
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        validate_config(env)
    env['OPENAI_API_KEY'] = 'test-key'
    validate_config(env)


def test_langextract_uses_configured_endpoint(monkeypatch):
    from types import SimpleNamespace
    import langextract
    from backend import extract

    monkeypatch.setenv('EXTRACTION_PROVIDER', 'openai')
    monkeypatch.setenv('EXTRACTION_MODEL', 'chosen-model')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://example.com/v1')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    captured = {}

    def fake_extract(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(extractions=[])

    monkeypatch.setattr(langextract, 'extract', fake_extract)
    result = extract.extract('Synthetic request')
    assert isinstance(captured['model'], OpenAIEndpointModel)
    assert captured['model'].model_id == 'chosen-model'
    assert captured['model'].base_url == 'https://example.com/v1'
    assert result['provider'] == 'openai'


def completion(content='{"extractions": []}', finish_reason='stop', **message):
    return {'id': 'synthetic', 'object': 'chat.completion', 'created': 0, 'model': 'chosen-model',
            'choices': [{'index': 0, 'finish_reason': finish_reason,
                         'message': {'role': 'assistant', 'content': content, **message}}]}


def test_stateless_request_and_bearer_auth(monkeypatch):
    calls = []
    def send(client, request, **kwargs):
        calls.append(request)
        assert client.follow_redirects is False
        return httpx.Response(200, json=completion(), request=request)
    monkeypatch.setattr(httpx.Client, 'send', send)
    model = OpenAIEndpointModel('https://example.com/v1', 'chosen-model', 'test-key')
    result = list(model.infer(['first', 'second']))
    assert result[0][0].output == '{"extractions": []}'
    assert len(calls) == 2
    for request, prompt in zip(calls, ['first', 'second']):
        assert str(request.url) == 'https://example.com/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer test-key'
        body = json.loads(request.content)
        assert set(body) == {'model', 'messages', 'stream'}
        assert body['model'] == 'chosen-model'
        assert body['messages'][-1] == {'role': 'user', 'content': prompt}
        assert len(body['messages']) == 2


@pytest.mark.parametrize('result', [completion(finish_reason='length'), completion(content=''),
    completion(refusal='refused'), completion(function_call={'name': 'test', 'arguments': '{}'}),
    completion(tool_calls=[{'id': 'call', 'type': 'function', 'function': {'name': 'test', 'arguments': '{}'}}])])
def test_rejects_unusable_output(monkeypatch, result):
    monkeypatch.setattr(httpx.Client, 'send', lambda client, request, **kwargs: httpx.Response(200, json=result, request=request))
    with pytest.raises(RuntimeError, match='incomplete, tool, refused, or empty'):
        list(OpenAIEndpointModel('https://example.com/v1', 'chosen-model', 'test-key').infer(['synthetic']))


@pytest.mark.parametrize('status', [302, 401, 429, 500])
def test_errors_are_private_and_not_retried(monkeypatch, status):
    calls = []
    def send(client, request, **kwargs):
        calls.append(request)
        return httpx.Response(status, text='private upstream data', headers={'Location': 'https://elsewhere.example/'}, request=request)
    monkeypatch.setattr(httpx.Client, 'send', send)
    with pytest.raises(RuntimeError, match='^OpenAI endpoint extraction failed;'):
        list(OpenAIEndpointModel('https://example.com/v1', 'chosen-model', 'test-key').infer(['synthetic']))
    assert len(calls) == 1