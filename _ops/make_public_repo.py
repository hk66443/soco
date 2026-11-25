#!/usr/bin/env python3
"""Build the public (sanitized) repo tree for https://github.com/boos663/soco.

Reads the local engineering tree, copies the *text* subset only (no 80-90 MB binaries),
redacts every credential, and writes .gitignore.  Run:  python _ops/make_public_repo.py
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / '_push'
PUBLIC = ROOT / '_ops' / 'public'

# ---------------------------------------------------------------- file selection
AM64_DIRS = ['src', 'deploy', 'manifest', 'evidence']
ARM64_DIRS = ['src', 'deploy', 'analysis', 'manifest', 'evidence']

ROOT_FILES = ['HANDOFF.md', 'BYPASS.md', 'MANIFEST.sha256']

PACKAGING = [
    'README.md', 'VERSION', 'install-soco.sh', 'install.sh', 'uninstall.sh', 'verify.sh',
    'soco-multi.sh', 'soco@.service', 'soco.service', 'soco-watchdog.py', 'soco-watchdog.service',
    'routes-guard.py', 'soco-routes-guard.path', 'soco-routes-guard.service', 'MULTI_INSTANCE.md',
    'soga-compat.sh',
]

OPS = [
    'probe_many.py', 'probe_conc.py', 'run_remote.py', 'ssh_tunnel.py',
    'amd_launch497.sh', 'amd_poll497.sh', 'amd_post497.sh',
    'build_variantA.py', 'build_variantB.py', 'build_variantC.py', 'build_variantC_min.py',
    'build_variantD.py', 'build_variantE.py', 'build_variantF.py',
    'variantB_patchlist.txt', 'variantC_patchlist.txt', 'routes_tw_patch.toml',
    'make_public_repo.py',
]

TEXT_EXT = {'.md', '.txt', '.py', '.sh', '.c', '.h', '.service', '.path', '.json', '.toml',
            '.yml', '.yaml', '.log', '.out', '.conf', '.unit', '.patch', '.diff'}
MAX_BYTES = 2 * 1024 * 1024

# ---------------------------------------------------------------- redaction
LITERALS = [
    '<REDACTED>', '<REDACTED>',
    '<REDACTED>', '<REDACTED>',
    '<REDACTED>', '<REDACTED>',
    '<REDACTED>',
]
REGEXES = [
    (re.compile(r'<REDACTED-NF-PASSWORD>[0-9a-fA-F]*'), '<REDACTED-NF-PASSWORD>'),
    (re.compile(r'<REDACTED-PANEL-UUID>[0-9a-fA-F-]*'), '<REDACTED-PANEL-UUID>'),
    (re.compile(r'<REDACTED-REALITY-PBK>[A-Za-z0-9_\-]*'), '<REDACTED-REALITY-PBK>'),
    (re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'), '<UUID>'),
    # key = value style, but never touch shell/python expressions like ${X} or os.environ
    (re.compile(r'(?im)^(\s*[-*]?\s*(?:soga_key|webapi_key|api_key|secret|passwd|password)\s*[=:]\s*)'
                r'(?!["\']?(?:\$|\{|<|os\.|self\.|None|null))[^\s\'"#]{4,}[^\n]*$'), r'\1<REDACTED>'),
    (re.compile(r'([?&](?:token|key|api_key|password)=)[^\s&"\']{6,}'), r'\1<REDACTED>'),
]
# any of these left in a copied file = fail the build
BLOCK = ['<REDACTED>', '<REDACTED>', '<REDACTED>', '<REDACTED>',
         '<REDACTED>', '<REDACTED-NF-PASSWORD>', '<REDACTED-PANEL-UUID>', '<REDACTED-REALITY-PBK>', '<REDACTED>']


def sanitize(text: str) -> str:
    for lit in LITERALS:
        text = text.replace(lit, '<REDACTED>')
    for rx, repl in REGEXES:
        text = rx.sub(repl, text)
    return text


def copy_one(src: Path, rel: str, report: list) -> None:
    """Copy src -> OUT/rel, sanitized; skip binaries / oversized files."""
    if not src.is_file() or src.suffix.lower() not in TEXT_EXT:
        return
    if src.stat().st_size > MAX_BYTES:
        report.append(('skip-big', rel, src.stat().st_size))
        return
    raw = src.read_bytes()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        report.append(('skip-binary', rel, len(raw)))
        return
    clean = sanitize(text)
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(clean, encoding='utf-8', newline='\n')


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    report = []

    # 1) authored docs
    for name in ['README.md', 'USAGE-AMD.md', 'USAGE-ARM.md', 'SECURITY.md']:
        copy_one(PUBLIC / name, name, report)
    # 2) root docs from the engineering tree (sanitized)
    for rel in ROOT_FILES:
        copy_one(ROOT / rel, rel, report)
    # 3) per-architecture trees
    for base, dirs in (('amd64', AM64_DIRS), ('arm64', ARM64_DIRS)):
        for d in dirs:
            for f in sorted((ROOT / base / d).rglob('*')):
                copy_one(f, str(f.relative_to(ROOT)), report)
    # 4) curated packaging + ops
    for name in PACKAGING:
        copy_one(ROOT / 'packaging' / name, f'packaging/{name}', report)
    for name in OPS:
        copy_one(ROOT / '_ops' / name, f'_ops/{name}', report)

    # 5) .gitignore
    (OUT / '.gitignore').write_text("""# binaries / large artifacts never enter this repo
*.exe
*.zip
*.7z
soco-arm64.*
soco-amd64*
soga-arm64*
libsoco*.so
sing-box*
xray*
*.jsonl
*__result.partial.json

# local scratch
_push/
tmp/
*.pyc
__pycache__/
.DS_Store
Thumbs.db
""", encoding='utf-8')

    # 6) verify no credential survived
    bad = []
    for f in sorted(OUT.rglob('*')):
        if not f.is_file():
            continue
        t = f.read_text(encoding='utf-8', errors='replace')
        for lit in BLOCK:
            if lit in t:
                bad.append((str(f.relative_to(OUT)), lit))
    files = [f for f in OUT.rglob('*') if f.is_file()]
    size = sum(f.stat().st_size for f in files)
    print('files=%d  bytes=%d (%.1f KB)' % (len(files), size, size / 1024))
    for kind, rel, info in report:
        print('  %-12s %s (%s)' % (kind, rel, info))
    if bad:
        print('!! LEAK:')
        for rel, lit in bad:
            print('   %s <- %s' % (rel, lit))
        return 1
    print('no credential literals left: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())