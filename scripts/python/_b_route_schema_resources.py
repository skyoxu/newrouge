"""One offline schema registry, keyed by exact resource bytes.

Auxiliary input schemas do not extend the formal record identity registry.
Legacy formal records do not require auxiliary resources. Graph-bearing plans
reuse the local shared Flow graph resource when installed.
"""
from functools import lru_cache
from pathlib import Path

import _b_route_codec as codec

DIRECTORY = Path(__file__).resolve().parents[2] / "docs/planning/b-route/schemas"
FORMAL = ("common", "policy", "plan", "binding", "origins", "commit", "catalog")
AUXILIARY = ("flow-graph", "planning-candidate", "adoption-operation", "adoption-operation-v2")


def fail(code, expected, actual):
    raise codec.CodecError(codec.Diagnostic(code, codec.Stage.SCHEMA,
        expected=expected, actual=actual))


def resources(directory=None, *, auxiliary=False):
    directory = Path(directory or DIRECTORY)
    names = FORMAL + AUXILIARY if auxiliary else FORMAL
    try:
        contents = tuple((name, (directory / (name + ".schema.json")).read_bytes()) for name in names)
        if not auxiliary:
            try:
                graph = (directory / "flow-graph.schema.json").read_bytes()
            except FileNotFoundError:
                pass
            else:
                contents += (("flow-graph", graph),)
        return contents
    except OSError as error:
        fail(codec.ReasonCode.SCHEMA_RESOURCE_ERROR, "local offline schema resources", str(error))


def identity(directory=None, *, auxiliary=False):
    return {name: codec.raw_digest(raw) for name, raw in resources(directory, auxiliary=auxiliary)}


def validator(schema_id, directory=None, *, auxiliary=False):
    contents = resources(directory, auxiliary=auxiliary)
    # A warm resource cache must not hide a now-unavailable validation backend.
    # This also preserves the formal service's dependency failure contract.
    try:
        import jsonschema
        import referencing
    except ImportError:
        fail(codec.ReasonCode.DEPENDENCY_UNAVAILABLE,
             "jsonschema==4.26.0 and referencing==0.37.0", "dependency unavailable")
    return _validator(schema_id, contents, auxiliary)


@lru_cache(maxsize=48)
def _validator(schema_id, contents, auxiliary):
    try:
        from jsonschema import Draft202012Validator, validators
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError:
        fail(codec.ReasonCode.DEPENDENCY_UNAVAILABLE,
             "jsonschema==4.26.0 and referencing==0.37.0", "dependency unavailable")

    def reject(uri):
        fail(codec.ReasonCode.SCHEMA_RESOURCE_ERROR, "registered local resource", uri)

    registry, schemas, identifiers = Registry(retrieve=reject), {}, {}
    try:
        for name, raw in contents:
            document = codec.strict_json_loads(raw)
            Draft202012Validator.check_schema(document)
            key = document["$id"]
            if key in schemas:
                raise ValueError("duplicate resource")
            schemas[key] = document
            identifiers[name] = key
            registry = registry.with_resource(key, Resource.from_contents(document, default_specification=DRAFT202012))
        permitted = {key for name, key in identifiers.items()
                     if name != "common" and (auxiliary or name in FORMAL)}
        if schema_id not in permitted:
            fail(codec.ReasonCode.UNKNOWN_SCHEMA, "registered schema", schema_id)
        strict = validators.extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
            "integer", lambda _checker, value: type(value) is int))
        return strict(schemas[schema_id], registry=registry)
    except codec.CodecError:
        raise
    except Exception as error:
        fail(codec.ReasonCode.SCHEMA_RESOURCE_ERROR, "valid offline resources", type(error).__name__)


def validate(value, schema_id, directory=None, *, auxiliary=False):
    try:
        error = next(validator(schema_id, directory, auxiliary=auxiliary).iter_errors(value), None)
    except codec.CodecError:
        raise
    except Exception as error:
        fail(codec.ReasonCode.SCHEMA_RESOURCE_ERROR, "locally resolvable schema", type(error).__name__)
    if error is not None:
        pointer = "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in error.absolute_path)
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            codec.Stage.SCHEMA, expected={"json_pointer": pointer, "rule": error.validator}, actual=error.message))
