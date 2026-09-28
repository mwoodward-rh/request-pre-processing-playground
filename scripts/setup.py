"""One-time bootstrap. Model downloads are explicit; existing .env is never overwritten."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from runtime import ROOT, Processes, config, ensure_ollama, python, request

def run(args, env):
    command = [str(a) for a in args]
    executable = shutil.which(command[0], path=env.get('PATH'))
    if not executable:
        raise RuntimeError(f'Cannot find executable: {command[0]}. Install it or fix PATH in the terminal running setup.')
    command[0] = executable
    try:
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    except FileNotFoundError as error:
        # Do not print the entire command or environment: either can contain private configuration.
        raise RuntimeError(f'Could not start {command[0]}. Check its interpreter and that the project directory exists.') from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f'{Path(command[0]).name} exited with code {error.returncode}; see its output above.') from error

def prerequisites(env):
    required = ['node', 'npm'] + (['git'] if env['JEV_MODE'] == 'local' else [])
    missing = [name for name in required if not shutil.which(name, path=env.get('PATH'))]
    if missing:
        raise RuntimeError('Missing prerequisite(s) on PATH: ' + ', '.join(missing) +
                           '. Install Node.js (includes npm) and Git as needed, then reopen your terminal.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-downloads', action='store_true', help='Install dependencies/build only; no model downloads or local services')
    parser.add_argument('--check', action='store_true', help='Check prerequisites only; no installs, downloads, or services')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        raise RuntimeError('Use Python 3.12 or newer')
    env = config()
    prerequisites(env)
    if args.check:
        print('Configuration, Python version, Node/npm and required Git are available. No changes made.')
        return
    owned = Processes()
    try:
        targets = [('.venv', 'requirements.txt')]
        if env['JEV_MODE'] == 'local':
            targets.append(('.venv-jev', 'requirements-jev.txt'))
        for name, requirements in targets:
            print(f'Preparing {name} using {requirements}…', flush=True)
            executable = python(ROOT, name)
            if not executable.exists():
                run([sys.executable, '-m', 'venv', ROOT/name], env)
            run([executable, '-m', 'pip', 'install', '-r', requirements], env)
        print('Installing dashboard dependencies…', flush=True)
        run(['npm', 'ci'], env)
        print('Building dashboard…', flush=True)
        run(['npm', 'run', 'build'], env)
        if not args.skip_downloads:
            run([python(ROOT), '-c', 'import os; from backend.app import private_endpoint, extraction_endpoint; private_endpoint(os.environ["JEV_URL"]); extraction_endpoint()'], env)
            if env['JEV_MODE'] == 'local':
                print('Downloading/caching the configured Jev model (may be several GB)…', flush=True)
                run([python(ROOT, '.venv-jev'), '-c',
                     'import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1], local_dir=sys.argv[2])',
                     env['JEV_MODEL'], env['JEV_MODEL_PATH']], env)
            if not Path(env['JEV_TOKENIZER']).is_file():
                raise RuntimeError('JEV_TOKENIZER is missing. Set it to the matching tokenizer.json, including in external mode.')
            if env['EXTRACTION_PROVIDER'] == 'ollama':
                ensure_ollama(env, owned)
                print('Downloading/caching the configured Ollama model; this may take several minutes…', flush=True)
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
        if isinstance(error, FileNotFoundError):
            detail = f'Missing file or executable: {error.filename or "unknown"}'
        else:
            detail = str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
        print(f'Setup failed: {detail}. Check prerequisites, model paths, and service configuration.', file=sys.stderr)
        sys.exit(1)
