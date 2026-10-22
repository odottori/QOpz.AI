"""Atomic release descriptors, with restoration of both previous pointers."""
import json
import os
import sys
from pathlib import Path

if __package__:
    from .install_shared_proxy import atomic_write
else:
    from install_shared_proxy import atomic_write


def publish(base: Path, backup: Path, root: Path, env: Path) -> None:
    content = json.dumps({'commit': root.name, 'backup': str(backup), 'env': str(env)}).encode()
    atomic_write(base / 'current-release.json', content)
    temporary = base / f'.current-{backup.name}'
    try:
        temporary.symlink_to(root, target_is_directory=True)
        os.replace(temporary, base / 'current')
    finally:
        temporary.unlink(missing_ok=True)


def restore(base: Path, backup: Path, root: Path) -> None:
    previous = (backup / 'current-link.before').read_text().strip()
    current = base / 'current'
    original = backup / 'current-release.before.json'
    descriptor = base / 'current-release.json'
    if current.exists() and not current.is_symlink():
        raise RuntimeError('Release pointer is no longer a symlink')
    if current.is_symlink() and current.readlink() not in {root, Path(previous)}:
        raise RuntimeError('Release pointer changed concurrently; refusing metadata rollback')
    if descriptor.exists() and (not original.exists() or descriptor.read_bytes() != original.read_bytes()):
        data = json.loads(descriptor.read_text())
        if data.get('commit') != root.name or data.get('backup') != str(backup):
            raise RuntimeError('Release descriptor changed concurrently; refusing metadata rollback')
    if previous:
        temporary = base / f'.current-restore-{backup.name}'
        try:
            temporary.symlink_to(previous, target_is_directory=True)
            os.replace(temporary, current)
        finally:
            temporary.unlink(missing_ok=True)
    elif current.is_symlink():
        current.unlink()
    if original.exists():
        atomic_write(base / 'current-release.json', original.read_bytes())
    else:
        (base / 'current-release.json').unlink(missing_ok=True)


if __name__ == '__main__':
    mode, base, backup, root, *extra = sys.argv[1:]
    if mode == 'publish':
        publish(Path(base), Path(backup), Path(root), Path(extra[0]))
    elif mode == 'restore':
        restore(Path(base), Path(backup), Path(root))
    else:
        raise SystemExit(2)
