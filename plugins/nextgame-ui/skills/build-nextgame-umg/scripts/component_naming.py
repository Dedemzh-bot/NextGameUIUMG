"""Creation-only WidgetTree naming checks shared by build and art planning.

Do not apply these checks to unchanged observed names or use them to rename
program bindings. Revision identity belongs to the task, not the component.
"""
from __future__ import annotations

import re


NAMING_POLICY = "component-creation-naming/2026-11-04"
# Match a revision-shaped segment at a PascalCase or underscore boundary.
# Ordinary numeric suffixes (Player2, Slot01) and embedded model identifiers
# (R2D2) are not revision segments. Semantic intent still needs human review.
_ITERATION_TOKEN = re.compile(
    r"(?:^|_)(?:[RrVv]|[Rr]ev(?:ision)?|[Vv]ersion)[0-9]+(?=$|_|[A-Z](?![0-9]))"
    r"|(?<=[a-z0-9])(?:R|V|Rev(?:ision)?|Version)[0-9]+(?=$|_|[A-Z](?![0-9]))"
)


def iteration_token(name: object) -> str | None:
    """Return a reserved revision segment, without inferring from digits alone."""
    if not isinstance(name, str):
        return None
    match = _ITERATION_TOKEN.search(name)
    return match.group(0).lstrip("_") if match else None
