"""Reconstruct owned QOpz services for configuration-exact rollback."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def snapshot(containers: list[dict]) -> dict:
    result = {'services': {}, 'volumes': {}, 'networks': {}}
    for container in containers:
        config, host = container['Config'], container['HostConfig']
        labels = config.get('Labels') or {}
        service = labels.get('com.docker.compose.service')
        if labels.get('com.docker.compose.project') != 'qopz' or service not in {'api', 'nginx', 'control-plane', 'broker-proxy'}:
            raise ValueError('Snapshot must contain only owned QOpz release services')
        if host.get('NetworkMode') == 'host' or host.get('PidMode') or host.get('Privileged') or host.get('Devices'):
            raise ValueError('Unsupported privileged runtime; manual rollback review required')
        item = {'image': container['Image'], 'container_name': container['Name'].lstrip('/'),
                'environment': dict(entry.split('=', 1) for entry in config.get('Env') or []),
                'command': config.get('Cmd'), 'entrypoint': config.get('Entrypoint'),
                'working_dir': config.get('WorkingDir') or '/', 'user': config.get('User') or '',
                'restart': host.get('RestartPolicy', {}).get('Name') or 'no',
                'read_only': bool(host.get('ReadonlyRootfs')), 'volumes': [], 'networks': {}, 'ports': []}
        custom_labels = {key: value for key, value in labels.items() if not key.startswith('com.docker.compose.')}
        if custom_labels:
            item['labels'] = custom_labels
        maximum = host.get('RestartPolicy', {}).get('MaximumRetryCount') or 0
        if maximum:
            item['restart'] += f':{maximum}'
        for original, target in [('Memory', 'mem_limit'), ('MemoryReservation', 'mem_reservation'),
                                 ('MemorySwap', 'memswap_limit'), ('CpuShares', 'cpu_shares'),
                                 ('CpuPeriod', 'cpu_period'), ('CpuQuota', 'cpu_quota'),
                                 ('CpusetCpus', 'cpuset'), ('PidsLimit', 'pids_limit'),
                                 ('ShmSize', 'shm_size'), ('OomScoreAdj', 'oom_score_adj')]:
            if host.get(original):
                item[target] = host[original]
        if host.get('MemorySwappiness') is not None:
            item['mem_swappiness'] = host['MemorySwappiness']
        if host.get('NanoCpus'):
            item['cpus'] = host['NanoCpus'] / 1_000_000_000
        if host.get('GroupAdd'):
            item['group_add'] = host['GroupAdd']
        if host.get('OomKillDisable'):
            item['oom_kill_disable'] = True
        if host.get('Ulimits'):
            item['ulimits'] = {row['Name']: {'soft': row['Soft'], 'hard': row['Hard']} for row in host['Ulimits']}
        for mount in container.get('Mounts') or []:
            if mount['Type'] not in {'bind', 'volume'}:
                raise ValueError('Unsupported mount type')
            source = mount['Name'] if mount['Type'] == 'volume' else mount['Source']
            if mount['Type'] == 'volume':
                result['volumes'][source] = {'external': True, 'name': source}
            item['volumes'].append({'type': mount['Type'], 'source': source, 'target': mount['Destination'],
                                    'read_only': not mount.get('RW', False)})
        for network, info in container['NetworkSettings']['Networks'].items():
            result['networks'][network] = {'external': True, 'name': network}
            item['networks'][network] = {'aliases': info.get('Aliases') or []}
        for port, bindings in (host.get('PortBindings') or {}).items():
            target, protocol = port.split('/')
            for binding in bindings or []:
                item['ports'].append({'target': int(target), 'published': str(binding['HostPort']),
                                      'host_ip': binding.get('HostIp') or '0.0.0.0', 'protocol': protocol})
        for original, target in [('CapDrop', 'cap_drop'), ('CapAdd', 'cap_add'), ('SecurityOpt', 'security_opt'),
                                  ('ExtraHosts', 'extra_hosts'), ('Dns', 'dns')]:
            if host.get(original):
                item[target] = host[original]
        if host.get('Tmpfs'):
            item['tmpfs'] = [f'{target}:{options}' for target, options in host['Tmpfs'].items()]
        if host.get('LogConfig', {}).get('Type'):
            item['logging'] = {'driver': host['LogConfig']['Type'], 'options': host['LogConfig'].get('Config') or {}}
        health = config.get('Healthcheck')
        if health:
            item['healthcheck'] = {'test': health['Test']}
            for original, target in [('Interval', 'interval'), ('Timeout', 'timeout'), ('StartPeriod', 'start_period')]:
                if health.get(original):
                    item['healthcheck'][target] = f'{health[original]}ns'
            if health.get('Retries'):
                item['healthcheck']['retries'] = health['Retries']
        item['volumes'].sort(key=lambda row: row['target'])
        item['ports'].sort(key=lambda row: (row['target'], row['protocol'], row['host_ip'], row['published']))
        result['services'][service] = item
    if not {'api', 'nginx', 'control-plane'}.issubset(result['services']):
        raise ValueError('Incomplete running-service snapshot')
    return result


def verify_runtime(previous: list[dict], current: list[dict]) -> None:
    expected, actual = snapshot(previous), snapshot(current)
    states = {row['Name'].lstrip('/'): row.get('State') or {} for row in current}
    for service, old in expected['services'].items():
        new = actual['services'].get(service)
        if not new:
            raise ValueError(f'Missing restored service: {service}')
        status = states[old['container_name']]
        if not status.get('Running') or status.get('Health', {}).get('Status', 'healthy') != 'healthy':
            raise ValueError(f'Restored service not healthy/running: {service}')
        for network, settings in old['networks'].items():
            if not set(settings['aliases']).issubset(new['networks'].get(network, {}).get('aliases', [])):
                raise ValueError(f'Restored network aliases differ: {service}')
        # Docker adds a new container-ID alias; compare all other captured settings exactly.
        old = {key: value for key, value in old.items() if key != 'networks'}
        new = {key: value for key, value in new.items() if key != 'networks'}
        if old != new or set(expected['services'][service]['networks']) != set(actual['services'][service]['networks']):
            raise ValueError(f'Restored runtime configuration differs: {service}')


def verify_running(previous: list[dict]) -> None:
    names = [row['Name'].lstrip('/') for row in previous]
    for attempt in range(90):
        try:
            process = subprocess.run(['docker', 'inspect', *names], check=True, capture_output=True, text=True, timeout=10)
            verify_runtime(previous, json.loads(process.stdout))
            return
        except (ValueError, subprocess.SubprocessError):
            if attempt == 89:
                raise
            time.sleep(2)


def literal(value):
    """Prevent Compose from interpolating dollars a second time, including secrets."""
    if isinstance(value, str):
        return value.replace('$', '$$')
    if isinstance(value, list):
        return [literal(item) for item in value]
    if isinstance(value, dict):
        return {key: literal(item) for key, item in value.items()}
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('inspection', type=Path)
    parser.add_argument('output', nargs='?', type=Path)
    parser.add_argument('--verify-running', action='store_true')
    args = parser.parse_args()
    previous = json.loads(args.inspection.read_text())
    if args.verify_running:
        verify_running(previous)
    elif args.output:
        args.output.write_text(json.dumps(literal(snapshot(previous)), indent=2))
    else:
        parser.error('output required unless --verify-running')
