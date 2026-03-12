from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

REDACTED = "REDACTED"

SENSITIVE_ATTRS = {
    "account",
    "lastAccount",
    "masterClientID",
    "port",
    "verifiedAppPortRangeStart",
    "verifiedAppPortRangeEnd",
    "portOfVerifiedAppShutdown",
    "host",
    "username",
    "userName",
    "password",
    "passwd",
    "token",
    "secret",
    "clientId",
    "ClientId",
}

SENSITIVE_TAGS = {
    "account",
    "username",
    "userName",
    "password",
    "passwd",
    "sigtext",
}

ACCOUNT_ID_RE = re.compile(r"\bU\d{5,}\b")


@dataclass
class Stats:
    redacted_attrs: int = 0
    redacted_tags: int = 0
    replaced_account_ids: int = 0


def _replace_account_ids(value: str, stats: Stats) -> str:
    if not value:
        return value
    out, n = ACCOUNT_ID_RE.subn("U********", value)
    stats.replaced_account_ids += n
    return out


def sanitize_tree(root: ET.Element) -> Stats:
    stats = Stats()

    for elem in root.iter():
        # Attribute-level redaction.
        for attr_name, attr_val in list(elem.attrib.items()):
            if attr_name in SENSITIVE_ATTRS and str(attr_val).strip():
                elem.set(attr_name, REDACTED)
                stats.redacted_attrs += 1
            else:
                replaced = _replace_account_ids(attr_val, stats)
                if replaced != attr_val:
                    elem.set(attr_name, replaced)

        # Tag text redaction for known sensitive tags.
        if elem.tag in SENSITIVE_TAGS:
            if elem.text and elem.text.strip():
                elem.text = REDACTED
                stats.redacted_tags += 1
        elif elem.text:
            elem.text = _replace_account_ids(elem.text, stats)

        if elem.tail:
            elem.tail = _replace_account_ids(elem.tail, stats)

    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Sanitize IBKR/TWS decrypted settings XML")
    ap.add_argument("--input", required=True, help="Input XML path")
    ap.add_argument("--output", required=True, help="Output XML path")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.exists():
        raise SystemExit(f"input not found: {in_path}")

    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(in_path, parser=parser)
    root = tree.getroot()

    stats = sanitize_tree(root)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)

    print(
        "SANITIZE_OK "
        f"input={in_path} output={out_path} "
        f"redacted_attrs={stats.redacted_attrs} "
        f"redacted_tags={stats.redacted_tags} "
        f"account_ids_masked={stats.replaced_account_ids}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
