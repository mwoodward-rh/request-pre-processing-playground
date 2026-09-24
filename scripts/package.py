"""Build a shareable source archive from an explicit allowlist, never the parent repo."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent.parent
files = ['.gitignore', '.env.example', 'README.md', 'package.json', 'package-lock.json',
         'vite.config.js', 'index.html', 'requirements.txt', 'requirements-test.txt', 'requirements-jev.txt']
for directory, pattern in [('backend','*.py'), ('src','*'), ('tests','test_*.py'), ('tests','*.test.mjs'), ('scripts','*.py')]:
    files.extend(str(path.relative_to(root)) for path in sorted((root/directory).glob(pattern)) if path.is_file())
target = root / 'artifacts' / 'request-intelligence-lab-source.zip'
target.parent.mkdir(exist_ok=True)
with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
    for name in sorted(set(files)):
        path = root/name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Invalid source file: {name}')
        archive.write(path, 'request-intelligence-lab/' + name)
print(f'{target.name}: {len(set(files))} source files; dependencies, model files and runtime artifacts excluded')
