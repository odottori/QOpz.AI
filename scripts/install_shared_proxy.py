"""Install only QOpz locations, with nginx validation and reversible backups."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

NGINX = Path('/etc/nginx')


def preflight_http(address: str) -> dict:
    baseline = {}
    for path in ['/', '/polyedge/', '/quantlens/']:
        connection = http.client.HTTPConnection('127.0.0.1', 80, timeout=5)
        try:
            connection.request('GET', path, headers={'Host': address})
            response = connection.getresponse()
            baseline[path] = response.status
            response.read(4096)
        finally:
            connection.close()
    if any(status != 404 for status in baseline.values()):
        raise RuntimeError(f'IP HTTP origin already serves other routes; refusing new vhost: {baseline}')
    return baseline


def run(*args: str) -> None:
    subprocess.run(args, check=True)


@contextmanager
def config_lock():
    with (NGINX / '.qopz-proxy.lock').open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.qopz-', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, target.stat().st_mode & 0o777 if target.exists() else 0o644)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def tls_locations(text: str, host: str, include: str) -> str:
    # Mask comments/quoted braces without changing offsets in the source.
    masked = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|#[^\n]*',
                    lambda match: ' ' * len(match.group()), text)
    insertions = []
    matched = 0
    for match in re.finditer(r'\bserver\s*\{', masked):
        opening = masked.index('{', match.start())
        depth, end = 1, opening + 1
        while depth and end < len(masked):
            depth += (masked[end] == '{') - (masked[end] == '}')
            end += 1
        if depth:
            raise RuntimeError('Unbalanced nginx server block')
        block = masked[opening:end]
        names = re.search(r'\bserver_name\s+([^;]+);', block)
        if not names or host not in names.group(1).split() or not re.search(r'\blisten\s+[^;]*\b443\b', block):
            continue
        matched += 1
        active = re.sub(r'#[^\n]*', '', text[opening:end])
        if include.strip() not in active:
            insertions.append(opening + 1)
    if not matched:
        raise RuntimeError(f'Expected TLS server for {host} not found')
    newline = '\r\n' if '\r\n' in text else '\n'
    for offset in reversed(insertions):
        text = text[:offset] + newline + include + text[offset:]
    return text


def restore(backup: Path) -> None:
    with config_lock():
        _restore(backup)


def _restore(backup: Path) -> None:
    manifest = json.loads((backup / 'proxy-manifest.json').read_text())
    operations = []
    for row in reversed(manifest):
        target = Path(row['path'])
        if not target.is_relative_to(NGINX):
            raise RuntimeError('Rollback path outside nginx configuration')
        current = target.read_bytes() if target.exists() else None
        original = (backup / row['backup']).read_bytes() if row['existed'] else None
        if current != original and (current is None or hashlib.sha256(current).hexdigest() != row['installed_hash']):
            raise RuntimeError(f'Refusing to overwrite a concurrent config change: {target}')
        operations.append((target, original))
    # Check every conflict before changing any file.
    for target, original in operations:
        if original is not None:
            atomic_write(target, original)
        else:
            target.unlink(missing_ok=True)
    run('nginx', '-t')
    run('systemctl', 'reload', 'nginx')


def install(backup: Path, address: str) -> None:
    with config_lock():
        _install(backup, address)


def _install(backup: Path, address: str) -> None:
    ipaddress.ip_address(address)
    backup.mkdir(parents=True, exist_ok=True)
    manifest_path = backup / 'proxy-manifest.json'
    if manifest_path.exists():
        raise RuntimeError('Backup already used; choose a fresh deployment backup')
    atomic_write(backup / 'http-baseline.json', json.dumps(preflight_http(address), sort_keys=True).encode())
    source = Path(__file__).resolve().parents[1] / 'docker/qopz-shared-location.conf'
    snippet = NGINX / 'snippets/qopz-shared-location.conf'
    http = NGINX / 'sites-enabled/qopz-shared-http.conf'
    changes = {snippet: source.read_bytes()}
    include = '    include /etc/nginx/snippets/qopz-shared-location.conf;'
    for name, host in [('qopzai.conf', 'qopzai.duckdns.org'), ('qedgeai.conf', 'qedgeai.duckdns.org')]:
        target = (NGINX / 'sites-enabled' / name).resolve(strict=True)
        if not target.is_relative_to(NGINX):
            raise RuntimeError('nginx site resolves outside /etc/nginx')
        text = target.read_bytes().decode('utf-8')
        updated = tls_locations(text, host, include)
        if updated != text:
            changes[target] = updated.encode('utf-8')
    http_text = (f'# QOpz shared HTTP gateway (managed)\nserver {{\n    listen 80;\n'
                 f'    server_name {address};\n{include}\n    location / {{ return 404; }}\n}}\n').encode()
    if http.exists() and http.read_bytes() != http_text:
        raise RuntimeError('Existing HTTP site differs; refusing to overwrite it')
    changes[http] = http_text
    if snippet.exists() and snippet.read_bytes() != changes[snippet]:
        raise RuntimeError('Existing QOpz snippet differs; review before replacing')
    manifest = []
    # Journal all originals before the first mutation.
    for index, target in enumerate(changes):
        row = {'path': str(target), 'existed': target.exists(), 'backup': f'proxy-{index}.conf',
               'installed_hash': hashlib.sha256(changes[target]).hexdigest()}
        if target.exists():
            (backup / row['backup']).write_bytes(target.read_bytes())
        manifest.append(row)
    atomic_write(manifest_path, json.dumps(manifest, indent=2).encode())
    try:
        for target, content in changes.items():
            atomic_write(target, content)
        run('nginx', '-t')
        run('systemctl', 'reload', 'nginx')
    except BaseException:
        _restore(backup)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--address', default='178.104.94.34')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if args.restore:
        restore(args.backup)
    else:
        install(args.backup, args.address)
