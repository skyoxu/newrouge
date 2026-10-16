"""Request-local sharing of JSON source values with exact original spelling."""
import json
import re

from _mvg_lossless_context import digest, lossless_context, restore_lossless_context, wire

SCHEMA = "newrouge.mvg-structured-context.v1"
RESERVED = {"$mvg_json_text", "$mvg_json_literal"}


def _object(pairs):
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("mvg_json_duplicate_key")
    return dict(pairs)


def _reject_constant(value):
    raise ValueError("mvg_json_nonfinite_number")


def render_json_text(view):
    fmt = view["format"]
    body = json.dumps(view["value"], ensure_ascii=fmt["ensure_ascii"], indent=fmt["indent"],
                      separators=tuple(fmt["separators"]), allow_nan=False)
    return fmt["prefix"] + body.replace("\n", fmt["newline"]) + fmt["suffix"]


def json_text_view(text):
    """Use a structured view only when its serializer reproduces every character."""
    if not isinstance(text, str):
        return None
    match = re.fullmatch(r"(\ufeff?[ \t\r\n]*)([\s\S]*?)([ \t\r\n]*)", text)
    prefix, body, suffix = match.groups()
    if not body.startswith(("{", "[")):
        return None
    try:
        value = json.loads(body, object_pairs_hook=_object, parse_constant=_reject_constant)
        newline = "\r\n" if "\r\n" in body else "\n"
        normalized = body.replace(newline, "\n")
        indent_match = re.search(r"\n([ \t]+)\S", normalized)
        indent = indent_match[1] if indent_match else 0 if "\n" in normalized else None
        if isinstance(indent, str) and set(indent) == {" "}:
            indent = len(indent)
        for ascii_only in (False, True):
            for separators in ((",", ": "), (",", ":"), (", ", ": ")):
                view = {"format": {"prefix": prefix, "suffix": suffix, "newline": newline,
                    "indent": indent, "ensure_ascii": ascii_only, "separators": list(separators)},
                    "value": value}
                if render_json_text(view) == text:
                    return view
    except (ValueError, TypeError, OverflowError, RecursionError):
        pass
    return None


def _transform(value):
    if isinstance(value, dict):
        if set(value) & RESERVED:
            return {"$mvg_json_literal": [[key, _transform(child)] for key, child in value.items()]}
        return {key: _transform(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_transform(child) for child in value]
    if isinstance(value, str) and len(value) >= 128:
        view = json_text_view(value)
        if view is not None:
            return {"$mvg_json_text": {"format": view["format"], "value": _transform(view["value"])}}
    return value


def _restore(value):
    if isinstance(value, dict):
        if set(value) == {"$mvg_json_literal"}:
            return {key: _restore(child) for key, child in value["$mvg_json_literal"]}
        if set(value) == {"$mvg_json_text"}:
            view = value["$mvg_json_text"]
            return render_json_text({"format": view["format"], "value": _restore(view["value"])})
        if set(value) & RESERVED:
            raise ValueError("mvg_structured_reserved_key_invalid")
        return {key: _restore(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_restore(child) for child in value]
    return value


def structured_context(value):
    transformed = _transform(value)
    if wire(_restore(transformed)) != wire(value):
        raise ValueError("mvg_structured_roundtrip_mismatch")
    return {"schema_version": SCHEMA, "content_sha256": digest(value), "encoded": lossless_context(transformed)}


def restore_structured_context(encoded):
    if (not isinstance(encoded, dict) or set(encoded) != {"schema_version", "content_sha256", "encoded"}
            or encoded["schema_version"] != SCHEMA):
        raise ValueError("mvg_structured_schema_invalid")
    try:
        value = _restore(restore_lossless_context(encoded["encoded"]))
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("mvg_structured_content_invalid") from exc
    if digest(value) != encoded["content_sha256"] or wire(structured_context(value)) != wire(encoded):
        raise ValueError("mvg_structured_content_changed")
    return value


def resolve_json_pointer(text, pointer):
    """Locate an existing JSON value in the original source, never a paraphrase."""
    if not isinstance(pointer, str) or not re.fullmatch(r"(?:/(?:[^~/]|~[01])*)*", pointer):
        raise ValueError("mvg_json_citation_pointer_invalid")
    try:
        json.loads(text.removeprefix("\ufeff"), object_pairs_hook=_object, parse_constant=_reject_constant)
    except ValueError as exc:
        raise ValueError("mvg_json_citation_source_invalid") from exc
    decoder = json.JSONDecoder()
    start = len(text) - len(text.lstrip("\ufeff \t\r\n"))
    components = [] if not pointer else [p.replace("~1", "/").replace("~0", "~") for p in pointer[1:].split("/")]

    def skip(offset):
        while offset < len(text) and text[offset] in " \t\r\n":
            offset += 1
        return offset

    def locate(offset, path):
        value, end = decoder.raw_decode(text, offset)
        if not path:
            return offset, end
        key, rest = path[0], path[1:]
        if isinstance(value, dict):
            cursor = skip(offset + 1)
            while cursor < end - 1:
                field, after_key = decoder.raw_decode(text, cursor)
                child = skip(skip(after_key) + 1)
                _, after_child = decoder.raw_decode(text, child)
                if field == key:
                    return locate(child, rest)
                cursor = skip(after_child)
                if cursor < end and text[cursor] == ",":
                    cursor = skip(cursor + 1)
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            target = int(key)
            if target < len(value):
                cursor = skip(offset + 1)
                for _ in range(target):
                    _, after_child = decoder.raw_decode(text, cursor)
                    cursor = skip(skip(after_child) + 1)
                return locate(cursor, rest)
        raise ValueError("mvg_json_citation_pointer_missing")

    begin, end = locate(start, components)
    return {"json_pointer": pointer, "start": begin, "end": end, "text": text[begin:end]}
