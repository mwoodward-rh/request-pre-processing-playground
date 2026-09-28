"""Stateless, tool-disabled Foundry Responses adapter for LangExtract."""
import os
import re
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
from langextract.core.base_model import BaseLanguageModel
from langextract.core.types import ScoredOutput


def validate_endpoint(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname
            or not parsed.hostname.endswith('.services.ai.azure.com')
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.port not in {None, 443}
            or not re.fullmatch(r'/api/projects/[\w-]+/agents/[\w-]+/endpoint/protocols/openai/responses', parsed.path)):
        raise ValueError('Foundry requires an HTTPS Azure agent Responses endpoint without a query or credentials')
    return url


def response_text(result):
    if result.get('status') != 'completed':
        raise RuntimeError('Foundry extraction did not complete')
    output = result.get('output', [])
    if any(item.get('type') not in {'message', 'reasoning', 'mcp_list_tools'} for item in output):
        raise RuntimeError('Foundry extraction returned an unexpected output type')
    text = '\n'.join(content['text'] for item in output if item.get('type') == 'message'
                     for content in item.get('content', []) if content.get('type') == 'output_text')
    if not text.strip():
        raise RuntimeError('Foundry extraction returned no text')
    return text


class FoundryCredential:
    def get_token(self, scope):
        if scope != 'https://ai.azure.com/.default':
            raise ValueError('Unsupported Foundry token scope')
        if os.name == 'nt':
            executable = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Microsoft SDKs/Azure/CLI2/python.exe'
            command = [str(executable), '-IB', str(Path(__file__).with_name('foundry_auth.py'))]
        else:
            executable = shutil.which('az')
            if not executable:
                raise RuntimeError('Install Azure CLI and sign in before using Foundry')
            command = [executable, 'account', 'get-access-token', '--resource', 'https://ai.azure.com', '--output', 'json']
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
            token = json.loads(result.stdout)['accessToken']
            if not isinstance(token, str) or not token:
                raise ValueError('Empty token')
            return SimpleNamespace(token=token)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            raise RuntimeError('Azure authentication unavailable; check your Azure CLI installation and login') from None


class FoundryLanguageModel(BaseLanguageModel):
    def __init__(self, endpoint, api_version='2025-11-15-preview', credential=None):
        super().__init__()
        self.endpoint = validate_endpoint(endpoint)
        self.api_version = api_version
        self.credential = credential or FoundryCredential()

    def infer(self, batch_prompts, **kwargs):
        with httpx.Client(timeout=90, follow_redirects=False) as client:
            for prompt in batch_prompts:
                token = self.credential.get_token('https://ai.azure.com/.default').token
                response = client.post(self.endpoint, params={'api-version': self.api_version},
                    headers={'Authorization': 'Bearer ' + token}, json={
                        'input': prompt, 'stream': False, 'tool_choice': 'none',
                    })
                if response.status_code != 200:
                    raise RuntimeError(f'Foundry extraction failed (HTTP {response.status_code})')
                yield [ScoredOutput(score=1.0, output=response_text(response.json()))]


def configured_model():
    return FoundryLanguageModel(os.environ['FOUNDRY_ENDPOINT'],
                                os.environ.get('FOUNDRY_API_VERSION', '2025-11-15-preview'))