from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TASK_RE = re.compile(r"\b(F[1-6]-T[A-Za-z0-9_]+)\b")

DEFAULT_CANONICAL_TEST_PATH = Path('.canonici/02_TEST.md')
DEFAULT_PLANNER_PATH = Path('planner/master_plan.json')
DEFAULT_STEP_INDEX_PATH = Path('.step_index.json')
DEFAULT_ALIASES_PATH = Path('config/progress_task_aliases.json')


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _load_aliases(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    raw = _load_json(path)
    out: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v):
            out[k] = v
    return out


def _canonical_tasks(path: Path) -> list[str]:
    txt = path.read_text(encoding='utf-8', errors='replace') if path.exists() else ''
    return sorted(set(TASK_RE.findall(txt)))


def _phase_of(step_id: str) -> str | None:
    s = (step_id or '').upper()
    for p in ('F1', 'F2', 'F3', 'F4', 'F5', 'F6'):
        if s.startswith(p):
            return p
    return None


def _completed_ids_from_step_index(step_index: dict[str, Any]) -> set[str]:
    raw = step_index.get('steps_completed', [])
    if not isinstance(raw, list):
        return set()
    out: set[str] = set()
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.add(item.strip())
    return out


def build_payload(
    *,
    canonical_test_path: Path = DEFAULT_CANONICAL_TEST_PATH,
    planner_path: Path = DEFAULT_PLANNER_PATH,
    step_index_path: Path = DEFAULT_STEP_INDEX_PATH,
    aliases_path: Path = DEFAULT_ALIASES_PATH,
) -> dict[str, Any]:
    planner = _load_json(planner_path)
    step_index = _load_json(step_index_path)
    aliases = _load_aliases(aliases_path)

    canonical_tasks = _canonical_tasks(canonical_test_path)
    canonical_set = set(canonical_tasks)

    completed_ids = _completed_ids_from_step_index(step_index)
    canonical_done: set[str] = set()
    for sid in completed_ids:
        if sid in canonical_set:
            canonical_done.add(sid)
        for aliased in aliases.get(sid, []):
            if aliased in canonical_set:
                canonical_done.add(aliased)

    planner_steps = [k for k, v in planner.get('steps', {}).items() if isinstance(k, str) and isinstance(v, dict)]
    planner_set = set(planner_steps)
    planner_done = planner_set & completed_ids

    milestone_rows: list[dict[str, Any]] = []
    milestone_done: dict[str, bool] = {}
    for m in planner.get('secondary_milestones', []):
        if not isinstance(m, dict):
            continue
        mid = str(m.get('id', '?'))
        req = [s for s in m.get('required_steps', []) if isinstance(s, str)]
        done = [s for s in req if s in completed_ids]
        missing = [s for s in req if s not in completed_ids]
        is_done = bool(req) and len(missing) == 0
        milestone_done[mid] = is_done
        milestone_rows.append(
            {
                'id': mid,
                'planned': len(req),
                'done': len(done),
                'missing': len(missing),
                'missing_ids': missing,
                'is_done': is_done,
            }
        )

    target_rows: list[dict[str, Any]] = []
    for t in planner.get('primary_targets', []):
        if not isinstance(t, dict):
            continue
        tid = str(t.get('id', '?'))
        req_ms = [x for x in t.get('required_secondary_milestones', []) if isinstance(x, str)]
        done_ms = [x for x in req_ms if milestone_done.get(x, False)]
        missing_ms = [x for x in req_ms if not milestone_done.get(x, False)]
        target_rows.append(
            {
                'id': tid,
                'planned': len(req_ms),
                'done': len(done_ms),
                'missing': len(missing_ms),
                'missing_ids': missing_ms,
            }
        )

    canonical_phase_rows: list[dict[str, Any]] = []
    planner_phase_rows: list[dict[str, Any]] = []
    for phase in ('F1', 'F2', 'F3', 'F4', 'F5', 'F6'):
        c = [x for x in canonical_tasks if _phase_of(x) == phase]
        p = [x for x in planner_steps if _phase_of(x) == phase]
        canonical_phase_rows.append(
            {
                'phase': phase,
                'planned': len(c),
                'done': len([x for x in c if x in canonical_done]),
                'missing': len([x for x in c if x not in canonical_done]),
            }
        )
        planner_phase_rows.append(
            {
                'phase': phase,
                'planned': len(p),
                'done': len([x for x in p if x in planner_done]),
                'missing': len([x for x in p if x not in planner_done]),
            }
        )

    canonical_missing_ids = sorted(canonical_set - canonical_done)
    planner_missing_ids = sorted(planner_set - planner_done)

    def _pct(done: int, total: int) -> float:
        return round((done / total) * 100, 1) if total else 0.0

    return {
        'project': planner.get('project', step_index.get('project', 'QuantOptionAI')),
        'next_step': step_index.get('next_step'),
        'summary': {
            'canonical': {
                'planned': len(canonical_tasks),
                'done': len(canonical_done),
                'missing': len(canonical_missing_ids),
                'percent': _pct(len(canonical_done), len(canonical_tasks)),
            },
            'planner': {
                'planned': len(planner_steps),
                'done': len(planner_done),
                'missing': len(planner_missing_ids),
                'percent': _pct(len(planner_done), len(planner_steps)),
            },
        },
        'canonical_by_phase': canonical_phase_rows,
        'planner_by_phase': planner_phase_rows,
        'milestones': milestone_rows,
        'primary_targets': target_rows,
        'canonical_missing_ids': canonical_missing_ids,
        'planner_missing_ids': planner_missing_ids,
    }


def _fmt_md_table(title: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [f'## {title}', '| Item | Previsti | Fatti | Mancanti |', '|---|---:|---:|---:|']
    for r in rows:
        item = r.get('phase') or r.get('id') or '?'
        lines.append(f"| {item} | {r.get('planned', 0)} | {r.get('done', 0)} | {r.get('missing', 0)} |")
    return lines


def to_markdown(payload: dict[str, Any]) -> str:
    c = payload['summary']['canonical']
    p = payload['summary']['planner']
    lines: list[str] = []
    lines.append('## AVANZAMENTO')
    lines.append(f"- Project: `{payload.get('project')}`")
    lines.append(f"- Next step: `{payload.get('next_step')}`")
    lines.append('')
    lines.append('| Vista | Previsto | Fatto | Mancante | % |')
    lines.append('|---|---:|---:|---:|---:|')
    lines.append(f"| Canonico | {c['planned']} | {c['done']} | {c['missing']} | {c['percent']:.1f}% |")
    lines.append(f"| Planner | {p['planned']} | {p['done']} | {p['missing']} | {p['percent']:.1f}% |")
    lines.append('')
    lines.extend(_fmt_md_table('PER FASE (Canonico)', payload.get('canonical_by_phase', [])))
    lines.append('')
    lines.extend(_fmt_md_table('PER FASE (Planner)', payload.get('planner_by_phase', [])))
    lines.append('')
    lines.extend(_fmt_md_table('PER MILESTONE', payload.get('milestones', [])))
    lines.append('')
    lines.extend(_fmt_md_table('PER TARGET', payload.get('primary_targets', [])))
    lines.append('')
    missing = payload.get('canonical_missing_ids', [])
    lines.append('- Missing canonico IDs:')
    lines.append(f"  - {', '.join(missing) if missing else '-'}")
    return '\n'.join(lines)


def to_line(payload: dict[str, Any]) -> str:
    c = payload['summary']['canonical']
    p = payload['summary']['planner']
    return (
        f"ADV_MATRIX canonical={c['done']}/{c['planned']} ({c['percent']:.1f}%) "
        f"planner={p['done']}/{p['planned']} ({p['percent']:.1f}%) "
        f"next={payload.get('next_step')}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog='advancement_matrix')
    p.add_argument('--format', choices=['md', 'line', 'json'], default='md')
    p.add_argument('--canonical-test', default=str(DEFAULT_CANONICAL_TEST_PATH))
    p.add_argument('--planner', default=str(DEFAULT_PLANNER_PATH))
    p.add_argument('--step-index', default=str(DEFAULT_STEP_INDEX_PATH))
    p.add_argument('--aliases', default=str(DEFAULT_ALIASES_PATH))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_payload(
        canonical_test_path=Path(args.canonical_test),
        planner_path=Path(args.planner),
        step_index_path=Path(args.step_index),
        aliases_path=Path(args.aliases),
    )
    if args.format == 'json':
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.format == 'line':
        print(to_line(payload))
    else:
        print(to_markdown(payload))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
