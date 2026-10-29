#!/usr/bin/env python3
"""Package the host source; exclude all private runtime."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent


def main():
    files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py', '.sh', '.md', '.txt')]
    files.append(ROOT/'.gitignore')
    files += [p for folder in ('web', 'tests', 'tools') for p in (ROOT/folder).rglob('*')
              if p.is_file() and p.suffix in ('.html', '.css', '.mjs', '.py', '.sh')]
    target = ROOT/'artifacts/sofa-link.zip'
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(files):
            bundle.write(path, Path('sofa-link')/path.relative_to(ROOT))
    with zipfile.ZipFile(target) as bundle:
        assert bundle.testzip() is None
        assert not any('/runtime/' in name or '/.venv/' in name for name in bundle.namelist())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.sha256').write_text(digest+'  '+target.name+'\n')
    print(json.dumps(dict(path=str(target), files=len(files), bytes=target.stat().st_size, sha256=digest)))


if __name__ == '__main__':
    main()
