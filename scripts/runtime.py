"""Shared, standard-library-only configuration and process ownership helpers."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = {
    'JEV_MODE': 'local', 'JEV_URL': 'http://127.0.0.1:8022',
    'JEV_MODEL': 'com-kotobalabs/open-jev-deberta-v3-large',
    'JEV_MODEL_PATH': 'models/open-jev', 'JEV_TOKENIZER': 'models/open-jev/tokenizer.json',
    'JEV_DEVICE': 'cpu', 'EXTRACTION_URL': 'http://127.0.0.1:11434',
    'EXTRACTION_MODEL': 'gemma4:e4b', 'LAB_PORT': '8030', 'OLLAMA_AUTOSTART': '1',
}

def config(root=ROOT, environ=None):
    env = dict(os.environ if environ is None else environ)
    values = dict(DEFAULTS)
    configured = set()
    path = root / '.env'
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, sep, value = line.partition('=')
            if not sep or key.strip() not in DEFAULTS:
                raise ValueError(f'Unsupported .env entry on line {number}')
            value = value.strip()
            if value[:1] in {'"', "'"}:
                if len(value) < 2 or value[-1] != value[0]:
                    raise ValueError(f'Unclosed quote on .env line {number}')
                value = value[1:-1]
            values[key.strip()] = value
            configured.add(key.strip())
    for key in values:
        if key in env:
            values[key] = env[key]
            configured.add(key)
    if 'JEV_TOKENIZER' not in configured:
        values['JEV_TOKENIZER'] = str(Path(values['JEV_MODEL_PATH']) / 'tokenizer.json')
    if values['JEV_MODE'] not in {'local', 'external'}:
        raise ValueError('JEV_MODE must be local or external')
    if values['OLLAMA_AUTOSTART'] not in {'0', '1'}:
        raise ValueError('OLLAMA_AUTOSTART must be 0 or 1')
    port = int(values['LAB_PORT'])
    if not 1024 <= port <= 65535:
        raise ValueError('LAB_PORT must be 1024–65535')
    for key in ['JEV_MODEL_PATH', 'JEV_TOKENIZER']:
        values[key] = str((root / Path(values[key]).expanduser()).resolve())
    for key in ['JEV_URL', 'EXTRACTION_URL']:
        parsed = urlsplit(values[key])
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(f'{key} must be an HTTP endpoint without credentials, query or fragment')
    if values['JEV_MODE'] == 'local':
        parsed = urlsplit(values['JEV_URL'])
        if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.path not in {'', '/'}:
            raise ValueError('Local Jev requires a loopback HTTP JEV_URL without a path; use JEV_MODE=external otherwise')
        if not parsed.port or not 1024 <= parsed.port <= 65535:
            raise ValueError('Local JEV_URL needs an explicit unprivileged port')
        if parsed.port == port:
            raise ValueError('Jev and dashboard ports must differ')
    return {**env, **values}

def python(root, name='.venv'):
    return root / name / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

def request(url, payload=None, timeout=5):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers={'Content-Type': 'application/json'})
    # Local inference should not inherit a system HTTP proxy.
    with build_opener(ProxyHandler({})).open(req, timeout=timeout) as response:
        return json.load(response)

def check_ollama(env):
    result = request(env['EXTRACTION_URL'].rstrip('/') + '/api/tags')
    wanted = env['EXTRACTION_MODEL']
    names = {m.get('name', m.get('model')) for m in result.get('models', [])}
    if wanted not in names and (':' in wanted or wanted + ':latest' not in names):
        raise RuntimeError('Configured extraction model is not installed. Run setup without --skip-downloads.')

def free_port(port):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))

class Processes:
    def __init__(self):
        self.children = []

    def start(self, args, env):
        child = subprocess.Popen([str(a) for a in args], cwd=ROOT, env=env)
        self.children.append(child)
        return child

    def close(self):
        # Never look up or kill arbitrary listeners. Only stop children we own.
        for child in reversed(self.children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()

def wait_ready(check, child, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('A managed service exited before readiness')
        try:
            check()
            return
        except (OSError, ValueError, RuntimeError):
            time.sleep(.5)
    raise RuntimeError('Service readiness timed out; check model installation and available memory')

def ensure_ollama(env, owned):
    url = env['EXTRACTION_URL'].rstrip('/')
    try:
        request(url + '/api/tags')
        return
    except (OSError, ValueError):
        pass
    if env['OLLAMA_AUTOSTART'] != '1' or url not in {'http://127.0.0.1:11434', 'http://localhost:11434'}:
        raise RuntimeError('Configured Ollama endpoint is unavailable; start it before launching')
    import shutil
    binary = shutil.which('ollama')
    if not binary:
        raise RuntimeError('Install Ollama from https://ollama.com, or configure an existing EXTRACTION_URL')
    free_port(11434)
    print('Starting local Ollama…', flush=True)
    child = owned.start([binary, 'serve'], {**env, 'OLLAMA_HOST': '127.0.0.1:11434'})
    wait_ready(lambda: request(url + '/api/tags'), child, 30)
