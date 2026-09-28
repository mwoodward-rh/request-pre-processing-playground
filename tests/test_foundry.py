from types import SimpleNamespace

import httpx
import pytest

from backend.foundry import FoundryCredential, FoundryLanguageModel, response_text, validate_endpoint


ENDPOINT = 'https://example.services.ai.azure.com/api/projects/demo/agents/extractor/endpoint/protocols/openai/responses'


@pytest.mark.parametrize('url', [
    'http://example.services.ai.azure.com/api/projects/demo/agents/extractor/endpoint/protocols/openai/responses',
    ENDPOINT + '?key=secret', ENDPOINT + '#fragment', ENDPOINT.replace('services.ai.azure.com', 'example.com'),
    ENDPOINT.replace('/responses', '/chat/completions'),
    ENDPOINT.replace('https://', 'https://user:secret@'),
])
def test_rejects_unapproved_endpoints(url):
    with pytest.raises(ValueError):
        validate_endpoint(url)


@pytest.mark.parametrize('result', [
    {'status': 'incomplete', 'output': []},
    {'status': 'completed', 'output': [{'type': 'function_call'}]},
    {'status': 'completed', 'output': [{'type': 'mcp_call'}]},
    {'status': 'completed', 'output': [{'type': 'mcp_approval_request'}]},
    {'status': 'completed', 'output': []},
])
def test_rejects_incomplete_or_tool_output(result):
    with pytest.raises(RuntimeError):
        response_text(result)


def test_stateless_tool_disabled_contract(monkeypatch):
    calls = []
    def post(client, url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'mcp_list_tools', 'tools': []},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': '{"extractions": []}'}]}]})
    monkeypatch.setattr(httpx.Client, 'post', post)
    credential = SimpleNamespace(get_token=lambda scope: SimpleNamespace(token='test-token'))
    model = FoundryLanguageModel(ENDPOINT, credential=credential)
    results = list(model.infer(['first', 'second']))
    assert len(results) == 2
    assert results[0][0].output == '{"extractions": []}'
    for url, call in calls:
        assert url == ENDPOINT
        assert call['json']['tool_choice'] == 'none'
        assert call['json']['stream'] is False
        assert set(call['json']) == {'input', 'stream', 'tool_choice'}
        assert 'previous_response_id' not in call['json']
        assert 'conversation' not in call['json']


def test_upstream_error_body_is_not_exposed(monkeypatch):
    monkeypatch.setattr(httpx.Client, 'post', lambda *args, **kwargs: httpx.Response(403, text='private error'))
    credential = SimpleNamespace(get_token=lambda scope: SimpleNamespace(token='test-token'))
    with pytest.raises(RuntimeError, match=r'^Foundry extraction failed \(HTTP 403\)$'):
        list(FoundryLanguageModel(ENDPOINT, credential=credential).infer(['synthetic']))


def test_auth_errors_do_not_expose_output(monkeypatch):
    import subprocess
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ['az'], output='private token', stderr='private diagnostic')
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(RuntimeError, match='^Azure authentication unavailable; check your Azure CLI installation and login$'):
        FoundryCredential().get_token('https://ai.azure.com/.default')