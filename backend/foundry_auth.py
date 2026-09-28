"""Azure CLI token helper, run by the CLI's bundled Python on Windows."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys


def main():
    handles = []
    workaround = Path(os.environ.get('LOCALAPPDATA', '')) / 'FoundryDiagnostics' / 'pywin32-py313'
    if sys.platform == 'win32' and workaround.is_dir():
        sys.path[:0] = [str(workaround), str(workaround / 'win32'), str(workaround / 'win32/lib')]
        handles.append(os.add_dll_directory(str(workaround / 'pywin32_system32')))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from azure.cli.core import get_default_cli
        cli = get_default_cli()
        status = cli.invoke(['account', 'get-access-token', '--resource', 'https://ai.azure.com', '--output', 'json'])
    if status:
        raise RuntimeError('Azure authentication unavailable')
    print(json.dumps({'accessToken': cli.result.result['accessToken']}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        sys.exit(1)