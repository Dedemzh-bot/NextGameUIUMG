"""Offline source-inventory and declared state-coverage gate. No Editor/network writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1}
STRINGS = {"type": "array", "items": TEXT, "uniqueItems": True}
BOOL = {"type": "boolean"}
HASH = {"type": "string", "pattern": "^[a-fA-F0-9]{64}$"}
EVIDENCE = obj({"id": TEXT, "path": TEXT, "sha256": HASH, "kind": {
    "enum": ["source-code", "user-decision", "source-readback", "figma-readback", "screenshot"]}})
CASE = obj({"id": TEXT, "condition": TEXT, "visible": BOOL, "visualReviewed": BOOL,
            "fileKey": TEXT, "screenId": TEXT, "nodeId": TEXT,
            "evidenceIds": STRINGS, "representedIds": STRINGS})
ELEMENT = obj({"id": TEXT, "asset": TEXT, "widget": TEXT, "class": TEXT,
               "sourceVisibility": TEXT, "sourceHidden": BOOL, "sourceUnread": BOOL, "interactive": BOOL,
               "classification": {"enum": ["unknown", "static", "active", "conditional", "inactive", "template"]},
               "rationale": {"type": "string"}, "evidenceIds": STRINGS,
               "relatedIds": STRINGS, "requiredCases": STRINGS,
               "cases": {"type": "array", "items": CASE}})
SCHEMA = obj({"kind": {"const": "nextgame-reverse-state-ledger"}, "version": {"const": 1},
              "pageId": TEXT, "revision": TEXT,
              "source": obj({"path": TEXT, "sha256": HASH}),
              "limits": STRINGS, "evidence": {"type": "array", "items": EVIDENCE},
              "elements": {"type": "array", "minItems": 1, "items": ELEMENT}})


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def resolve(base, path):
    value = Path(path)
    return value.resolve() if value.is_absolute() else (base / value).resolve()


def inventory(source):
    if source.get("kind") != "nextgame-umg-reverse-prototype" or source.get("version") != 1:
        raise ValueError("Unsupported normalized source: require nextgame-umg-reverse-prototype version 1")
    blocks = [source["screen"]]
    deps = source.get("dependencies", {})
    blocks.extend(deps.values() if isinstance(deps, dict) else deps)
    result = {}
    for block in blocks:
        asset = block["asset"]
        if not block.get("nodes"):
            # An audit marker, never a claimed WidgetTree node.
            identity = asset + "#@unexpanded"
            if identity in result:
                raise ValueError(f"Duplicate asset: {asset}")
            result[identity] = {"id": identity, "asset": asset, "widget": "@unexpanded",
                                "class": "__unexpanded_asset__", "sourceVisibility": "Unknown",
                                "sourceHidden": False, "sourceUnread": True, "interactive": False}
            continue
        nodes = {n["name"]: n for n in block["nodes"]}
        if len(nodes) != len(block["nodes"]):
            raise ValueError(f"Duplicate source names in asset: {asset}")
        for name, node in nodes.items():
            identity = asset + "#" + name
            if identity in result:
                raise ValueError(f"Duplicate asset-qualified ID: {identity}")
            hidden, current, seen = False, name, set()
            while current:
                if current in seen or current not in nodes:
                    raise ValueError(f"Invalid source hierarchy: {identity}")
                seen.add(current)
                ancestor = nodes[current]
                hidden |= ancestor.get("visibility") in ("Hidden", "Collapsed") or ancestor.get("visible") is False
                current = ancestor.get("parent")
            cls = node.get("c", "Unknown")
            interactive = name.startswith("Btn") or any(s in cls.lower() for s in ("button", "checkbox", "slider", "editabletext", "combobox"))
            result[identity] = {"id": identity, "asset": asset, "widget": name, "class": cls,
                                "sourceVisibility": node.get("visibility", "Unknown"),
                                "sourceHidden": hidden, "sourceUnread": bool(node.get("unread", False)),
                                "interactive": interactive}
    return result


def prepare(args):
    source_path = args.source.resolve()
    source = read(source_path)
    nodes = inventory(source)
    elements = [dict(n, classification="unknown", rationale="", evidenceIds=[], relatedIds=[],
                     requiredCases=[], cases=[]) for n in nodes.values()]
    ledger = {"kind": "nextgame-reverse-state-ledger", "version": 1, "pageId": args.page_id,
              "revision": args.revision, "source": {"path": str(source_path), "sha256": digest(source_path)},
              "limits": list(dict.fromkeys(source.get("limits", []))), "evidence": [], "elements": elements}
    Draft202012Validator(SCHEMA).validate(ledger)
    write_new(args.out, ledger)
    return {"status": "prepared-pending-analysis", "nodes": len(elements),
            "interactiveCandidates": sum(n["interactive"] for n in elements),
            "hiddenCandidates": sum(n["sourceHidden"] for n in elements), "output": str(args.out)}


def validate(path):
    path = path.resolve()
    errors = []
    try:
        ledger = read(path)
        errors.extend("schema:" + "/".join(map(str, e.absolute_path)) + ": " + e.message
                      for e in Draft202012Validator(SCHEMA).iter_errors(ledger))
        if errors:
            return {"ledger": str(path), "status": "incomplete", "errors": errors}
        source_path = resolve(path.parent, ledger["source"]["path"])
        if digest(source_path).lower() != ledger["source"]["sha256"].lower():
            errors.append("source hash is stale")
        source = read(source_path)
        nodes = inventory(source)
        elements = {n["id"]: n for n in ledger["elements"]}
        if len(elements) != len(ledger["elements"]):
            errors.append("duplicate element IDs")
        if set(elements) != set(nodes):
            errors.append("source inventory mismatch: omitted or fabricated IDs")
        evidence = {e["id"]: e for e in ledger["evidence"]}
        if len(evidence) != len(ledger["evidence"]):
            errors.append("duplicate evidence IDs")
        for ev in evidence.values():
            file = resolve(path.parent, ev["path"])
            if not file.is_file() or digest(file).lower() != ev["sha256"].lower():
                errors.append(f"missing/stale evidence: {ev['id']}")

        def evidence_kinds(ids, owner):
            for identity in ids:
                if identity not in evidence:
                    errors.append(f"{owner}: missing evidence ID {identity}")
            return {evidence[i]["kind"] for i in ids if i in evidence}

        for identity, node in elements.items():
            prefix = identity + ": "
            if identity not in nodes:
                continue
            original = nodes[identity]
            # interactive may be enriched to true after binding analysis, never downgraded.
            for field, expected in original.items():
                if field == "interactive" and not expected:
                    continue
                if node[field] != expected:
                    errors.append(prefix + "source fact changed: " + field)
            classification = node["classification"]
            if node["sourceUnread"]:
                errors.append(prefix + "source dependency unread; refresh source evidence before coverage can complete")
            if classification == "unknown" or not node["rationale"].strip():
                errors.append(prefix + "classification/rationale unresolved")
            kinds = evidence_kinds(node["evidenceIds"], identity)
            if classification != "unknown" and not kinds:
                errors.append(prefix + "classification needs evidence")
            if classification == "inactive" and not kinds & {"source-code", "user-decision"}:
                errors.append(prefix + "inactive needs explicit business-scope evidence")
            if classification == "conditional" and not kinds & {"source-code", "user-decision"}:
                errors.append(prefix + "conditional needs behavior evidence")
            if node["interactive"] and classification == "static":
                errors.append(prefix + "interactive control cannot be static")
            if node["sourceHidden"] and classification not in ("conditional", "inactive", "template", "unknown"):
                errors.append(prefix + "hidden source needs explicit conditional/inactive/template resolution")
            if set(node["relatedIds"]) - set(elements):
                errors.append(prefix + "unknown related content")
            required = set(node["requiredCases"])
            if classification == "conditional":
                required |= {"normal", "hidden"}
            if classification == "active" and node["interactive"]:
                required.add("normal")
            cases = {c["id"]: c for c in node["cases"]}
            if len(cases) != len(node["cases"]):
                errors.append(prefix + "duplicate cases")
            if required - set(cases):
                errors.append(prefix + "missing cases: " + ", ".join(sorted(required - set(cases))))
            for case in cases.values():
                ckinds = evidence_kinds(case["evidenceIds"], identity + "/" + case["id"])
                if not {"figma-readback", "screenshot"} <= ckinds or not case["visualReviewed"]:
                    errors.append(prefix + case["id"] + " lacks readback/screenshot/visual review")
                if case["id"] == "normal" and not case["visible"]:
                    errors.append(prefix + "normal case must be effectively visible")
                if case["id"] == "hidden" and case["visible"]:
                    errors.append(prefix + "hidden case is visible")
                represented = set(case["representedIds"])
                if represented - set(elements):
                    errors.append(prefix + "case has unknown represented IDs")
                if case["visible"] and not {identity, *node["relatedIds"]} <= represented:
                    errors.append(prefix + "visible case omits control or related content")
        return {"ledger": str(path), "ledgerSHA256": digest(path), "pageId": ledger["pageId"],
                "revision": ledger["revision"], "status": "incomplete" if errors else "coverage-complete",
                "scope": "declared source inventory and evidence-bound state coverage; not runtime or user acceptance",
                "limits": ledger["limits"], "elementCount": len(elements), "errors": errors}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ledger": str(path), "status": "incomplete", "errors": [f"input error: {exc}"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--source", type=Path, required=True)
    prepare_parser.add_argument("--page-id", required=True)
    prepare_parser.add_argument("--revision", required=True)
    prepare_parser.add_argument("--out", type=Path, required=True)
    for name in ("validate", "batch"):
        command = sub.add_parser(name)
        command.add_argument("ledgers", type=Path, nargs="+" if name == "batch" else 1)
        command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(json.dumps(prepare(args), ensure_ascii=False))
            return 0
        reports = [validate(p) for p in args.ledgers]
        duplicate_pages = len({r.get("pageId") for r in reports}) != len(reports)
        complete = all(r["status"] == "coverage-complete" for r in reports) and not duplicate_pages
        result = reports[0] if args.command == "validate" else {
            "kind": "nextgame-reverse-page-index", "version": 1,
            "status": "coverage-complete" if complete else "incomplete", "pages": reports,
            "errors": ["duplicate/unknown page IDs; select one explicit revision per page"] if duplicate_pages else []}
        write_new(args.out, result)
        print(json.dumps({"status": result["status"], "pages": len(reports),
                          "issueCount": sum(len(r["errors"]) for r in reports), "output": str(args.out)}, ensure_ascii=False))
        return 0 if complete else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
