from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _detect_eol(data: bytes) -> str:
    # Prefer CRLF if present anywhere.
    if b"\r\n" in data:
        return "\r\n"
    return "\n"


def _update_broker_port(text: str, new_port: int, eol: str) -> tuple[str, bool]:
    lines = text.splitlines()
    out: list[str] = []
    in_broker = False
    changed = False
    saw_port = False

    for i, raw in enumerate(lines):
        line = raw
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            # leaving broker section
            if in_broker and not saw_port:
                out.append(f"port = {new_port}")
                changed = True
                saw_port = True
            in_broker = (stripped == "[broker]")
            out.append(line)
            continue

        if in_broker and stripped.startswith("port") and "=" in stripped:
            # Preserve inline comment if present
            before_comment, *rest = line.split("#", 1)
            comment = ("#" + rest[0]) if rest else ""
            prefix = before_comment.split("=", 1)[0].rstrip()
            new_line = f"{prefix} = {new_port}".rstrip()
            if comment:
                new_line = f"{new_line} {comment.strip()}"
            if new_line != line:
                changed = True
            out.append(new_line)
            saw_port = True
            continue

        out.append(line)

    if in_broker and not saw_port:
        out.append(f"port = {new_port}")
        changed = True

    return (eol.join(out) + (eol if text.endswith(eol) else "")), changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="set_broker_port")
    ap.add_argument("--profile", default="paper")
    ap.add_argument("--port", type=int, required=True)
    args = ap.parse_args(argv)

    p = ROOT / "config" / f"{args.profile}.toml"
    if not p.exists():
        print(f"SET_BROKER_PORT FAIL missing={p}")
        return 2

    data = p.read_bytes()
    eol = _detect_eol(data)
    text = data.decode("utf-8", errors="replace")
    new_text, changed = _update_broker_port(text, args.port, eol)

    if changed:
        p.write_text(new_text, encoding="utf-8", newline="")
        print(f"SET_BROKER_PORT OK profile={args.profile} port={args.port}")
    else:
        print(f"SET_BROKER_PORT OK (nochange) profile={args.profile} port={args.port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
