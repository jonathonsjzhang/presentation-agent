from __future__ import annotations

import json
import re
from typing import Any

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of free-form model text.

    Order of attempts:
    1. The whole string is already valid JSON.
    2. The first fenced ```json ... ``` block.
    3. The first balanced { ... } span found by bracket matching.

    Raises ValueError if nothing parses, so the caller can retry.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model output")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    span = _first_balanced_object(text)
    if span is not None:
        try:
            parsed = json.loads(span)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError("no parseable JSON object found in model output")


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def validate(
    data: Any,
    schema: dict[str, Any],
    path: str = "$",
    *,
    _root_schema: dict[str, Any] | None = None,
) -> list[str]:
    """Minimal JSON-schema validator covering the subset this project uses.

    Supported keywords: type, required, properties, items, enum, const,
    minItems, maxItems, minLength, maxLength, minimum, maximum,
    additionalProperties, and local JSON-pointer $ref.
    Unknown keywords are ignored (lenient by design). Returns a list of human
    readable error strings; empty list means valid. No external dependency, so
    the harness stays pure-stdlib.
    """
    root_schema = _root_schema or schema
    errors: list[str] = []

    ref = schema.get("$ref")
    if isinstance(ref, str):
        try:
            resolved = _resolve_local_ref(root_schema, ref)
        except ValueError as exc:
            return [f"{path}: invalid schema reference {ref!r}: {exc}"]
        return validate(data, resolved, path, _root_schema=root_schema)

    if "const" in schema and data != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}, got {data!r}")

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']!r}, got {data!r}")

    expected_type = schema.get("type")
    if expected_type and not _type_ok(data, expected_type):
        errors.append(f"{path}: expected type {expected_type}, got {_type_name(data)}")
        return errors

    if expected_type == "object" or isinstance(data, dict):
        if isinstance(data, dict):
            for key in schema.get("required", []):
                if key not in data:
                    errors.append(f"{path}: missing required field '{key}'")
            properties = schema.get("properties", {})
            for key, subschema in properties.items():
                if key in data and isinstance(subschema, dict):
                    errors.extend(
                        validate(
                            data[key],
                            subschema,
                            f"{path}.{key}",
                            _root_schema=root_schema,
                        )
                    )
            additional = schema.get("additionalProperties", True)
            unknown_keys = [key for key in data if key not in properties]
            if additional is False:
                for key in unknown_keys:
                    errors.append(f"{path}: unexpected field '{key}'")
            elif isinstance(additional, dict):
                for key in unknown_keys:
                    errors.extend(
                        validate(
                            data[key],
                            additional,
                            f"{path}.{key}",
                            _root_schema=root_schema,
                        )
                    )

    if expected_type == "array" or isinstance(data, list):
        if isinstance(data, list):
            min_items = schema.get("minItems")
            max_items = schema.get("maxItems")
            if isinstance(min_items, int) and len(data) < min_items:
                errors.append(
                    f"{path}: must contain at least {min_items} item(s), got {len(data)}"
                )
            if isinstance(max_items, int) and len(data) > max_items:
                errors.append(
                    f"{path}: must contain at most {max_items} item(s), got {len(data)}"
                )
        item_schema = schema.get("items")
        if isinstance(data, list) and isinstance(item_schema, dict):
            for index, item in enumerate(data):
                errors.extend(
                    validate(
                        item,
                        item_schema,
                        f"{path}[{index}]",
                        _root_schema=root_schema,
                    )
                )

    if expected_type == "string" and isinstance(data, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(data) < min_length:
            errors.append(
                f"{path}: length must be at least {min_length}, got {len(data)}"
            )
        if isinstance(max_length, int) and len(data) > max_length:
            errors.append(
                f"{path}: length must be at most {max_length}, got {len(data)}"
            )

    if expected_type in ("integer", "number") and isinstance(data, (int, float)):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and data < minimum:
            errors.append(f"{path}: must be at least {minimum}, got {data}")
        if isinstance(maximum, (int, float)) and data > maximum:
            errors.append(f"{path}: must be at most {maximum}, got {data}")

    return errors


def _resolve_local_ref(root_schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError("only local '#/...' references are supported")
    current: Any = root_schema
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"path component {part!r} not found")
        current = current[part]
    if not isinstance(current, dict):
        raise ValueError("reference target must be a schema object")
    return current


def _type_ok(data: Any, expected: str | list[str]) -> bool:
    if isinstance(expected, list):
        return any(_type_ok(data, item) for item in expected)
    checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    check = checks.get(expected)
    return check(data) if check else True


def _type_name(data: Any) -> str:
    if isinstance(data, bool):
        return "boolean"
    if isinstance(data, dict):
        return "object"
    if isinstance(data, list):
        return "array"
    if isinstance(data, str):
        return "string"
    if isinstance(data, int):
        return "integer"
    if isinstance(data, float):
        return "number"
    if data is None:
        return "null"
    return type(data).__name__
