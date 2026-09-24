"""Launch the built dashboard and local dependencies; Ctrl+C stops only owned services."""
import argparse
from pathlib import Path
import signal
import sys
import time
from urllib.parse import urlsplit
from runtime import ROOT, Processes, check_ollama, config, ensure_ollama, free_port, python, request, wait_ready

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only configuration/readiness checks; starts no processes')
    args = parser.parse_args()
    env = config()
    if not python(ROOT).is_file() or not (ROOT/'dist/index.html').is_file():
        raise RuntimeError('Run setup first: the Python environment or frontend build is missing')
    if not Path(env['JEV_TOKENIZER']).is_file():
        raise RuntimeError('JEV_TOKENIZER does not point to a tokenizer.json file')
    if env['JEV_MODE'] == 'local' and (not python(ROOT, '.venv-jev').is_file() or not Path(env['JEV_MODEL_PATH']).is_dir()):
        raise RuntimeError('Local Jev is not installed; run setup first')
    # Use the same endpoint policy as the API, without requiring dependencies in this launcher.
    import subprocess
    subprocess.run([str(python(ROOT)), '-c',
        'import os; from backend.app import private_endpoint; [private_endpoint(os.environ[k]) for k in ["JEV_URL","EXTRACTION_URL"]]'],
        cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def jev_ready():
        if request(env['JEV_URL'].rstrip('/') + '/healthz').get('ok') is not True:
            raise RuntimeError('Jev is not ready')

    if args.check:
        check_ollama(env)
        jev_ready()
        print('Configuration and existing model endpoints are ready. No inference performed; no processes started.')
        return
    port = int(env['LAB_PORT'])
    free_port(port)
    owned = Processes()
    try:
        ensure_ollama(env, owned)
        check_ollama(env)
        if env['JEV_MODE'] == 'local':
            jev_port = urlsplit(env['JEV_URL']).port
            free_port(jev_port)  # An existing service must be selected explicitly via external mode.
            print('Loading local Jev (CPU by default)…', flush=True)
            child = owned.start([python(ROOT, '.venv-jev'), '-m', 'uvicorn', 'backend.jev_server:app',
                                 '--host', '127.0.0.1', '--port', str(jev_port), '--no-access-log'], env)
            wait_ready(jev_ready, child)
        else:
            jev_ready()
        child = owned.start([python(ROOT), '-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1',
                             '--port', str(port), '--no-access-log'], env)
        wait_ready(lambda: request(f'http://127.0.0.1:{port}/api/health'), child, 30)
        print(f'Open http://127.0.0.1:{port} — Ctrl+C stops only services started by this launcher.', flush=True)
        while True:
            if any(p.poll() is not None for p in owned.children):
                raise RuntimeError('A managed service stopped unexpectedly')
            time.sleep(.5)
    finally:
        owned.close()

if __name__ == '__main__':
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        main()
    except KeyboardInterrupt:
        print('Launcher stopped; existing external services were left running.')
    except Exception as error:
        # Configuration diagnostics are safe; upstream HTTP bodies/credentials are not printed.
        message = str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
        print(f'Cannot launch: {message}', file=sys.stderr)
        sys.exit(1)
