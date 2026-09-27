"""JSON-strict field types for addon-produced result models (issue #580).

The bridge is the seam between two typed producers: GDScript (the addon) and
these Pydantic models (the server). GDScript's typed producers emit real JSON
booleans/numbers/strings — so when a ``bool`` field arrives as the string
``"yes"``, or an ``int`` field as ``1.0``, that is *shape drift* and must fail
loudly (surfacing as INTERNAL_ERROR via the #567 middleware), not coerce into
a plausible value the agent then acts on. Lax mode silently coerces exactly
that class (``bool("yes") → True``, ``int(1.0) → 1``), which is why targeted
strictness exists.

Use these aliases on **result-model fields the addon produces with a typed
GDScript value**. Deliberate exceptions (stay lax — do not convert):
- ``Any``-typed Variant fields (``value``/``expected``/``default``/``before``/
  ``after``/``snapshot`` …) — the #564 JSON-safe Variant shapes, where a
  string/bool/int is a legitimate *value*;
- request-side coercion (``ArgumentCoercionMiddleware`` repairs stringified
  JSON arguments) — that path is deliberately forgiving on input;
- ``dry_run``/``confirm``-style *tool arguments* — those are client-supplied
  and repaired upstream.

The name pins the intent: these types are strict about the **JSON kinds** the
addon sends (bool ↔ bool, string ↔ string, integer ↔ integer, number ↔ number),
while still allowing the one widening the addon genuinely produces — a
GDScript ``int`` landing in a ``float`` field (JSON has no int/float split).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field

# Strict bool: only real JSON booleans — "yes"/"1"/ints are drift.
JSONBool = Annotated[bool, Field(strict=True)]

# Strict string: only real JSON strings. (Lax already rejects ints for str in
# pydantic 2.13, but the explicit form keeps the intent readable and guards
# against future laxity changes.)
JSONStr = Annotated[str, Field(strict=True)]

# Strict int: only JSON integers — floats (even 1.0) are drift.
JSONInt = Annotated[int, Field(strict=True)]


def _accept_json_number(value: object) -> object:
    """A JSON number (int or float) — reject strings/bools/None outright."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected a JSON number (int or float), got {type(value).__name__}")
    return value


# Strict float: real JSON numbers, including integer widening (a GDScript int
# in a float field is a legitimate number; a string or bool is not).
JSONFloat = Annotated[float, BeforeValidator(_accept_json_number)]

__all__ = ["JSONBool", "JSONInt", "JSONStr", "JSONFloat"]