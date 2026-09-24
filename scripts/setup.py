"""One-time bootstrap. Model downloads are explicit; existing .env is never overwritten."""
import argparse
import subprocess
import sys
from pathlib import Path
from runtime import ROOT, Processes, config, ensure_ollama, python, request

def run(args, env):
    subprocess.run([str(a) for a in args], cwd=ROOT, env=env, check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-downloads', action='store_true', help='Install dependencies/build only; no model downloads or Ollama startup')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        raise RuntimeError('Use Python 3.12 or newer')
    env = config()
    owned = Processes()
    try:
        targets = [('.venv', 'requirements.txt')]
        if env['JEV_MODE'] == 'local':
            targets.append(('.venv-jev', 'requirements-jev.txt'))
        for name, requirements in targets:
            executable = python(ROOT, name)
            if not executable.exists():
                run([sys.executable, '-m', 'venv', ROOT/name], env)
            run([executable, '-m', 'pip', 'install', '-r', requirements], env)
        run(['npm', 'ci'], env)
        run(['npm', 'run', 'build'], env)
        if not args.skip_downloads:
            run([python(ROOT), '-c', 'import os; from backend.app import private_endpoint; [private_endpoint(os.environ[k]) for k in ["JEV_URL","EXTRACTION_URL"]]'], env)
            if env['JEV_MODE'] == 'local':
                print('Downloading/caching the configured Jev model (may be several GB)…', flush=True)
                run([python(ROOT, '.venv-jev'), '-c',
                     'import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1], local_dir=sys.argv[2])',
                     env['JEV_MODEL'], env['JEV_MODEL_PATH']], env)
            if not Path(env['JEV_TOKENIZER']).is_file():
                raise RuntimeError('JEV_TOKENIZER is missing. Set it to the matching tokenizer.json, including in external mode.')
            ensure_ollama(env, owned)
            print('Downloading/caching the configured Ollama model; this may take several minutes…', flush=True)
            # Ollama supports a non-streaming pull; any returned provider error is kept out of logs.
            result = request(env['EXTRACTION_URL'].rstrip('/') + '/api/pull',
                             {'model': env['EXTRACTION_MODEL'], 'stream': False}, timeout=3600)
            if result.get('status') != 'success':
                raise RuntimeError('Ollama model pull failed')
        print('Setup complete. Start with: python3.12 scripts/launch.py', flush=True)
    finally:
        owned.close()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Setup interrupted.', file=sys.stderr)
        sys.exit(130)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        detail = str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
        print(f'Setup failed: {detail}. Check prerequisites, model paths, and service configuration.', file=sys.stderr)
        sys.exit(1)
