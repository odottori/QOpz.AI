from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    actions: list[str] = []
    node_modules = ROOT / 'ui' / 'node_modules'
    if node_modules.exists():
        shutil.rmtree(node_modules, ignore_errors=True)
        actions.append('delete ui/node_modules (stale packaged dependency snapshot)')

    vite_bin = ROOT / 'ui' / 'node_modules' / '.bin' / 'vite'
    if vite_bin.exists():
        actions.append('note: vite bin still exists unexpectedly')

    if actions:
        print('QOPZ_004_UI_OK')
        for item in actions:
            print(f'- {item}')
        print('- next: run OPZ_UI_SETUP.bat (or npm ci) only if you need dev/build locally')
    else:
        print('QOPZ_004_UI_NOOP')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
