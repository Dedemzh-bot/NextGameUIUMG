"""Versioned, offline composition facts for reverse prototypes; no UE mutation."""
from __future__ import annotations

from jsonschema import Draft202012Validator


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1}
OPTIONAL_TEXT = {"anyOf": [TEXT, {"type": "null"}]}
STRINGS = {"type": "array", "items": TEXT, "uniqueItems": True}
RELATION = obj({
    "id": TEXT,
    "kind": {"enum": ["inheritance", "widget-instance", "named-slot-content", "named-slot-empty", "runtime-slot-content"]},
    "hostAsset": TEXT, "hostWidget": OPTIONAL_TEXT,
    "slotOwnerAsset": OPTIONAL_TEXT, "slotName": OPTIONAL_TEXT,
    "contentAsset": OPTIONAL_TEXT, "contentRoot": OPTIONAL_TEXT,
    "classProperty": OPTIONAL_TEXT,
    "status": {"enum": ["resolved", "unresolved"]},
    "unresolvedReason": {"type": "string"}, "evidenceIds": STRINGS,
})


def relation_inventory(source):
    """Validate declared relations without converting references into inheritance."""
    if source.get("version") == 1:
        return {}
    relations = source.get("compositionRelations")
    schema_errors = list(Draft202012Validator({"type": "array", "items": RELATION}).iter_errors(relations))
    if schema_errors:
        raise ValueError("Invalid compositionRelations: " + schema_errors[0].message)
    blocks = [source["screen"]]
    deps = source.get("dependencies", {})
    blocks.extend(deps.values() if isinstance(deps, dict) else deps)
    assets = {block["asset"]: block for block in blocks}
    if len(assets) != len(blocks):
        raise ValueError("Duplicate composition asset identity")
    for asset, block in assets.items():
        if "parentClass" not in block or (block.get("nodes") and not isinstance(block["parentClass"], str)):
            raise ValueError(f"{asset}: version 2 requires observed parentClass (null only for unread dependencies)")
        if isinstance(block["parentClass"], str) and not block["parentClass"].strip():
            raise ValueError(f"{asset}: parentClass cannot be an empty string")
    nodes = {asset: {node["name"]: node for node in block.get("nodes", [])} for asset, block in assets.items()}
    result, inherited, occupied, edges = {}, {}, set(), {}
    for relation in relations:
        identity = relation["id"]
        if identity in result:
            raise ValueError(f"Duplicate composition relation: {identity}")
        result[identity] = relation
        host, content = relation["hostAsset"], relation["contentAsset"]
        kind, widget = relation["kind"], relation["hostWidget"]
        if host not in assets or (content is not None and content not in assets):
            raise ValueError(f"{identity}: unknown host/content asset; include an unread dependency explicitly")
        if widget is not None and widget not in nodes[host]:
            raise ValueError(f"{identity}: unknown host widget")
        root = relation["contentRoot"]
        if root is not None and (content is None or root not in nodes[content]):
            raise ValueError(f"{identity}: unknown content root")
        if relation["status"] == "unresolved":
            if not relation["unresolvedReason"].strip():
                raise ValueError(f"{identity}: unresolved relationship needs a reason")
        elif not relation["evidenceIds"] or relation["unresolvedReason"].strip() or (content is None and kind != "named-slot-empty"):
            raise ValueError(f"{identity}: resolved relationship needs content and observation evidence, without an unresolved reason")
        if kind == "inheritance":
            if any(relation[key] is not None for key in ("hostWidget", "slotOwnerAsset", "slotName", "contentRoot", "classProperty")):
                raise ValueError(f"{identity}: inheritance is a class relationship, not a content/slot relationship")
            if host in inherited:
                raise ValueError(f"{identity}: duplicate parent-class relationship")
            inherited[host] = content
        elif kind == "widget-instance":
            if widget is None or any(relation[key] is not None for key in ("slotOwnerAsset", "slotName", "classProperty")):
                raise ValueError(f"{identity}: widget instance needs its host node and cannot masquerade as a NamedSlot")
        else:
            owner, slot = relation["slotOwnerAsset"], relation["slotName"]
            if owner not in assets or slot not in nodes[owner]:
                raise ValueError(f"{identity}: unknown NamedSlot owner or slot")
            slot_class = nodes[owner][slot].get("c", "").rsplit(".", 1)[-1]
            if slot_class != "NamedSlot":
                raise ValueError(f"{identity}: declared slot must be an observed NamedSlot")
            if relation["status"] == "resolved" and root is None and kind != "named-slot-empty":
                raise ValueError(f"{identity}: resolved slot content needs its observed content root")
            if kind in ("named-slot-content", "named-slot-empty") and relation["classProperty"] is not None:
                raise ValueError(f"{identity}: static NamedSlot content cannot carry a runtime class-property claim")
            if kind == "named-slot-empty" and (content is not None or root is not None):
                raise ValueError(f"{identity}: empty NamedSlot cannot have content")
            key = (host, widget, owner, slot)
            if key in occupied:
                raise ValueError(f"{identity}: multiple bindings for one host/slot; separate conditional variants into source revisions")
            occupied.add(key)
            if root is not None:
                native_parent = nodes[content][root].get("parent")
                if native_parent is not None and not (content == owner and native_parent == slot):
                    raise ValueError(f"{identity}: inserted content root has a conflicting native parent")
        # Class ownership can be checked globally. Slot content belongs to a
        # particular host instance and must not create asset-level edges.
        if kind in ("inheritance", "widget-instance") and content is not None and content != host:
            edges.setdefault(host, set()).add(content)
        elif kind in ("inheritance", "widget-instance") and content == host:
            raise ValueError(f"{identity}: self-referential class composition")

    def reaches_parent(child, ancestor):
        seen = set()
        while child is not None and child not in seen:
            if child == ancestor:
                return True
            seen.add(child)
            child = inherited.get(child)
        return False

    for relation in result.values():
        if relation["kind"] not in ("named-slot-content", "named-slot-empty", "runtime-slot-content"):
            continue
        host, widget, owner = relation["hostAsset"], relation["hostWidget"], relation["slotOwnerAsset"]
        if widget is None:
            if not reaches_parent(host, owner):
                raise ValueError(f"{relation['id']}: slot owner is not the host or an explicitly recorded ancestor")
        else:
            instances = [r for r in result.values() if r["kind"] == "widget-instance" and r["hostAsset"] == host and r["hostWidget"] == widget]
            if len(instances) != 1 or not reaches_parent(instances[0]["contentAsset"], owner):
                raise ValueError(f"{relation['id']}: named-slot host instance lacks a unique recorded class/owner relationship")

    declared_slots = {(r["hostAsset"], r["hostWidget"], r["slotOwnerAsset"], r["slotName"])
                      for r in result.values() if r["slotName"]}
    declared_instances = {(r["hostAsset"], r["hostWidget"]) for r in result.values() if r["kind"] == "widget-instance"}

    def required_slots(host, widget, source_asset):
        seen = set()
        while source_asset is not None and source_asset not in seen:
            seen.add(source_asset)
            for name, node in nodes[source_asset].items():
                if node.get("c", "").rsplit(".", 1)[-1] == "NamedSlot":
                    yield host, widget, source_asset, name
            source_asset = inherited.get(source_asset)

    # The declaration on the shared source is not a declaration for every
    # consumer. Require its effective binding in each concrete host context.
    expected_slots = set()
    for asset in assets:
        expected_slots.update(required_slots(asset, None, asset))
    for relation in result.values():
        if relation["kind"] == "widget-instance" and relation["contentAsset"] is not None:
            expected_slots.update(required_slots(relation["hostAsset"], relation["hostWidget"], relation["contentAsset"]))
    missing_slots = expected_slots - declared_slots
    if missing_slots:
        missing = sorted(missing_slots, key=lambda item: tuple(value or "" for value in item))[0]
        raise ValueError(f"NamedSlot binding omitted for host/instance/owner/slot {missing}; record inherited/default bindings explicitly with evidence")
    for asset, entries in nodes.items():
        parent_class = assets[asset].get("parentClass")
        if isinstance(parent_class, dict):
            parent_class = parent_class.get("refPath")
        if isinstance(parent_class, str) and parent_class.startswith("/Game/"):
            expected_parent = parent_class.split(".", 1)[0]
            if inherited.get(asset) != expected_parent:
                raise ValueError(f"{asset}: observed Blueprint parentClass lacks its matching inheritance relationship")
        elif asset in inherited:
            raise ValueError(f"{asset}: declared Blueprint inheritance has no matching observed parentClass")
        for name, node in entries.items():
            cls = node.get("c", "")
            if cls.startswith("/Game/") and (asset, name) not in declared_instances:
                raise ValueError(f"{asset}#{name}: custom Widget instance relationship omitted")
            if cls.startswith("/Game/"):
                instance_relations = [r for r in result.values() if r["kind"] == "widget-instance" and r["hostAsset"] == asset and r["hostWidget"] == name]
                if len(instance_relations) != 1 or instance_relations[0]["contentAsset"] != cls.split(".", 1)[0]:
                    raise ValueError(f"{asset}#{name}: instance relation differs from its observed Widget class")

    def reject_cycles(graph, label):
        done, active = set(), set()

        def visit(node):
            if node in active:
                raise ValueError(f"Cyclic {label}: {node}")
            if node in done:
                return
            active.add(node)
            for child in graph.get(node, ()):
                visit(child)
            active.remove(node)
            done.add(node)

        for node in graph:
            visit(node)

    reject_cycles(edges, "asset composition")
    graph = {}
    for asset, entries in nodes.items():
        for name, node in entries.items():
            if node.get("parent"):
                graph.setdefault((asset, node["parent"]), set()).add((asset, name))
    reject_cycles(graph, "native parent hierarchy")
    for relation in result.values():
        if relation["kind"] in ("named-slot-content", "runtime-slot-content") and relation["contentRoot"]:
            # Analyze each insertion in isolation; merging the shared source
            # trees for two host instances would invent a cross-instance cycle.
            scoped_graph = {key: set(children) for key, children in graph.items()}
            scoped_graph.setdefault((relation["slotOwnerAsset"], relation["slotName"]), set()).add((relation["contentAsset"], relation["contentRoot"]))
            reject_cycles(scoped_graph, "slot content in " + relation["id"])
    return result


def validate_reviews(ledger, relations, evidence_kinds, errors, elements):
    reviews = {review["relationId"]: review for review in ledger["compositionReviews"]}
    if len(reviews) != len(ledger["compositionReviews"]) or set(reviews) != set(relations):
        errors.append("composition review inventory differs from source relationships")
    for identity, relation in relations.items():
        prefix = identity + ": "
        if relation["status"] != "resolved":
            errors.append(prefix + "composition source unresolved")
        observed = evidence_kinds(relation["evidenceIds"], identity + "/source")
        required = {"source-readback", "source-code"} if relation["kind"] == "runtime-slot-content" else {"source-readback"}
        if not required <= observed:
            errors.append(prefix + "composition observation lacks readback/code evidence")
        if relation["kind"] == "named-slot-empty" and not observed & {"source-code", "user-decision"}:
            errors.append(prefix + "empty-slot classification needs code/scope evidence excluding a runtime provider")
        review = reviews.get(identity)
        if review is None:
            continue
        if review["decision"] == "unresolved" or not review["role"].strip() or not review["rationale"].strip():
            errors.append(prefix + "slot responsibility/use decision is unresolved")
        kinds = evidence_kinds(review["evidenceIds"], identity + "/use")
        if "figma-readback" not in kinds:
            errors.append(prefix + "composition use needs actual prototype readback")
        if review["decision"] == "propose-redesign" and "user-decision" not in kinds:
            errors.append(prefix + "changed composition needs an explicit design decision")
        cases = review["cases"]
        if not cases or len({case["id"] for case in cases}) != len(cases):
            errors.append(prefix + "composition needs unique rendered cases")
        if not any(case["visible"] for case in cases):
            errors.append(prefix + "composition needs a visible composed case; hidden-only evidence is insufficient")
        required_ids = {relation["hostAsset"] + "#@asset"}
        if relation["hostWidget"]:
            required_ids.add(relation["hostAsset"] + "#" + relation["hostWidget"])
        if relation["contentAsset"]:
            required_ids.add(relation["contentAsset"] + "#@asset")
        if relation["slotName"]:
            required_ids.add(relation["slotOwnerAsset"] + "#@asset")
            required_ids.add(relation["slotOwnerAsset"] + "#" + relation["slotName"])
        if relation["contentRoot"]:
            required_ids.add(relation["contentAsset"] + "#" + relation["contentRoot"])
        for case in cases:
            kinds = evidence_kinds(case["evidenceIds"], identity + "/" + case["id"])
            represented = set(case["representedIds"])
            if not {"figma-readback", "screenshot"} <= kinds or not case["visualReviewed"]:
                errors.append(prefix + "composition case lacks actual visual evidence/review")
            if represented - set(elements) or (case["visible"] and not required_ids <= represented):
                errors.append(prefix + "composition case has missing/unknown host, slot or content identities")
