"""Small, atomic, profile-scoped cache. Reading it never contacts the broker."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / 'data/cache/term_structure'


def _path(profile: str) -> Path:
    if profile not in {'dev', 'paper', 'live'}:
        raise ValueError('Unsupported profile')
    return CACHE_DIR / f'{profile}.json'


def read_cache(profile: str, symbols: list[str], top_n: int) -> dict:
    path = _path(profile)
    result = {'profile': profile, 'count': 0, 'top_n': top_n, 'sigma_levels': [1, 2],
              'items': [], 'captured_at': None, 'stale': True, 'cached': True}
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError('Oversized cache')
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Cache must be an object')
        if data.get('version') != 1 or data.get('profile') != profile or not isinstance(data.get('items'), list):
            raise ValueError('Invalid cache schema')
        captured = datetime.fromisoformat(data['captured_at'])
        age = (datetime.now(timezone.utc) - captured).total_seconds()
        if any(not isinstance(item, dict) or not isinstance(item.get('chains'), list)
               or any(not isinstance(chain, dict) for chain in item['chains']) for item in data['items']):
            raise ValueError('Invalid curve items')
        items = [dict(item, chains=list(item.get('chains') or [])[:top_n])
                 for item in data['items'] if isinstance(item, dict) and item.get('symbol') in symbols]
        result.update(items=items, count=len(items), captured_at=data['captured_at'], stale=not (0 <= age <= 1800))
    except (OSError, ValueError, KeyError, TypeError):
        result['error'] = 'No valid cached curves. Use the explicit curve refresh.'
    return result


def save_cache(profile: str, items: list[dict]) -> None:
    path = _path(profile)
    payload = {'version': 1, 'profile': profile, 'captured_at': datetime.now(timezone.utc).isoformat(), 'items': items}
    encoded = json.dumps(payload, allow_nan=False, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > 2_000_000:
        raise ValueError('Oversized cache')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(encoded, encoding='utf-8')
    os.replace(temporary, path)
