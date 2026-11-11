"""One exact, request-local 3B delivery; no semantic projection or model execution."""
import json

import _b_route_codec as codec
import _b_route_compact_literal as compact
from _mvg_evidence_transport import MODEL_ENCODING, ENCODING_INSTRUCTION, lossless_context, restore_lossless_context

SCHEMA = "newrouge.b-route-complete-materials-wire.v1"
CURRENT_SCHEMA = "newrouge.b-route-complete-materials-wire.v2"
DELIVERIES = (SCHEMA, CURRENT_SCHEMA)
INSTRUCTION = ("The complete materials below use one request-local lossless envelope. "
    "Restore every original field, JSON type, order and string before using it. Nested legacy encoded core "
    "or virtual-file values retain their OWN local envelope namespaces; literal reference-like keys remain data. "
    + ENCODING_INSTRUCTION.strip())


def text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def encode(materials, delivery=SCHEMA):
    if delivery not in DELIVERIES:
        raise ValueError("b_route_wire_version_invalid")
    if type(materials) is not dict:
        raise ValueError("b_route_wire_materials_not_object")
    encoded = lossless_context(materials)
    if text(restore_lossless_context(encoded)) != text(materials):
        raise ValueError("b_route_wire_roundtrip_changed")
    return {"schema_version": delivery, "materials_identity": codec.canonical_digest(materials),
        "materials_bytes_sha256": codec.raw_digest(text(materials).encode("utf-8")), "encoded": encoded}


def decode(envelope, delivery=SCHEMA):
    if (type(envelope) is not dict or set(envelope) != {
            "schema_version", "materials_identity", "materials_bytes_sha256", "encoded"}
            or delivery not in DELIVERIES or envelope["schema_version"] != delivery or type(envelope["encoded"]) is not dict
            or envelope["encoded"].get("schema_version") != MODEL_ENCODING):
        raise ValueError("b_route_wire_version_or_shape_invalid")
    value = restore_lossless_context(envelope["encoded"])
    if (type(value) is not dict or codec.canonical_digest(value) != envelope["materials_identity"]
            or codec.raw_digest(text(value).encode("utf-8")) != envelope["materials_bytes_sha256"]):
        raise ValueError("b_route_wire_materials_changed")
    return value


def read_prompt(prompt, delivery=None):
    if type(prompt) is not str or "\n" not in prompt:
        raise ValueError("b_route_wire_prompt_invalid")
    body = prompt.split("\n", 1)[1]
    value = compact.loads(body) if delivery == CURRENT_SCHEMA else codec.strict_json_loads(body)
    if delivery is None:
        if not isinstance(value, dict) or value.get("schema_version") in DELIVERIES or "encoded" in value or "wire_delivery" in value:
            raise ValueError("b_route_wire_mixed_delivery")
        return value
    if delivery not in DELIVERIES:
        raise ValueError("b_route_wire_version_invalid")
    return decode(value, delivery)


def render(instruction, materials, delivery=None):
    if delivery is None:
        return instruction + "\n" + text(materials)
    if delivery not in DELIVERIES:
        raise ValueError("b_route_wire_version_invalid")
    if delivery == CURRENT_SCHEMA:
        return (instruction + " " + compact.INSTRUCTION +
            " After restoring the compact packet, decode its complete B-route envelope. " + INSTRUCTION +
            "\n" + compact.dumps(encode(materials, delivery)))
    return instruction + " " + INSTRUCTION + "\n" + text(encode(materials))
