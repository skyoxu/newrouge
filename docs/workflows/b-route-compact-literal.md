# B-route compact data literal support

`scripts/python/_b_route_compact_literal.py` is an independent, standard-library-only
data codec. Its schema is `newrouge.b-route-compact-literal.v1`. It does not activate
a planning route or change the public v1 wire decoder. A future wire integration
must explicitly select and version its use.

## Public API

- `SCHEMA`: the exact schema identifier above.
- `INSTRUCTION`: English data-only decoding instructions for a consumer.
- `dumps(value: dict) -> str`: encode one complete JSON-compatible object.
- `loads(text: str) -> dict`: validate and restore one canonical packet into fresh
  containers. Invalid values or packets raise `ValueError`.

Only exact built-in `dict`, `list`, `str`, `int`, finite `float`, `bool` and `None`
are supported, with string object keys and a dictionary at the top level.
Subclasses, cycles, tuples, sets, bytes, complex values and nonfinite floats are
rejected. Shared input containers are allowed; decoding creates independent
containers for every occurrence. The input is never mutated or retained.
Strings and keys must be encodable as strict UTF-8: lone surrogate code points
are rejected. Ordinary Unicode, combining marks, non-BMP characters, controls,
newlines and literal marker-like strings are preserved character for character.
Integer versus float, booleans, null, negative floating zero, dictionary key order
and array order are preserved. Unknown nested fields are complete data.

## Canonical encoding

The packet has exactly these fields, in this order:

```text
{'schema_version':SCHEMA,'keysets':[[ordered keys],...],'value':encoded_object,'sha256':'sha256:...'}
```

This schematic uses placeholders. Actual packets are compact Python data
literals, recursively spelling dictionaries and lists without separator spaces
and scalar values using Python `repr`. They use `True`, `False` and `None` for
JSON booleans and null. Python source expressions are never an accepted format.

First, every original dictionary key is mapped through a reversible spelling
rule, regardless of the object's shape or business meaning:

| Original key | Encoded key |
| --- | --- |
| `$mvg_ref` | `r` |
| `$mvg_object` | `o` |
| `$mvg_lines` | `l` |
| `$mvg_source` | `s` |
| `r`, `o`, `l`, `s`, `@`, or any key starting with `~` | prepend one `~` |
| Every other key | unchanged |

Decoding removes one leading `~` before considering aliases. Thus literal alias
and record keys cannot collide with encoded control keys. Original marker names
are not interpreted as legacy envelopes or business instructions.

Next, count every ordered key tuple in preorder: each dictionary before its
children, dictionary children in insertion order, and arrays in array order.
Consider distinct tuples in first-encounter order. For each candidate, `index`
is the current length of the selected table. Select a tuple only if its count is
at least two and this exact compact-literal character-length calculation is
positive:

```text
count * (len(literal({key:None for key in keys}))
         - len(literal({'@':[index,[None for key in keys]]})))
      - len(literal(list(keys))) > 0
```

The table contains unique ordered string-key lists. Every dictionary with a
selected key tuple becomes `{'@':[index,[all values in original order]]}`.
All values are recursively encoded; ordinary dictionaries remain dictionaries.
Selection uses no tokenizer and makes no token-budget guarantee. Even table
ordering and use are part of the canonical representation.

The digest is SHA-256 of the **original** object serialized by
`json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)`,
without key sorting, then encoded as strict UTF-8. The stored digest has a
lowercase `sha256:` prefix. It covers original key order and all original values.
It detects corruption; it is not an authentication mechanism.

## Validation and boundaries

`loads` parses with `ast.parse` and constructs data only from a closed whitelist
of dictionary, list and JSON scalar AST nodes, with unary minus for numbers.
It never calls `eval`, `exec`, `compile`, imports from input, or executes input.
Duplicate dictionary keys are rejected before building a dictionary, including
equivalent escaped spellings. Calls, attributes, comprehensions, dictionary
unpacking and non-JSON literals are rejected.

It validates the closed packet fields and schema, table types and uniqueness,
canonical key spellings, reserved record shape, exact integer indices (excluding
booleans), index bounds, field counts and complete table usage. It restores the
complete object, verifies the original digest, and requires
`dumps(restored) == input_text`. This final check also rejects extra whitespace,
alternate quoting or numeric spellings, comments, reordered packet fields,
unused or suboptimal tables, and alternate representations with a valid digest.
Unknown or mixed packet versions are rejected. Version-like fields inside the
original object remain ordinary data.

Python runtime nesting, AST parsing, integer conversion and memory limits still
apply. The codec is not a resource-isolation sandbox for arbitrary hostile sizes.
Its canonical spelling follows the selected Python runtime's scalar `repr`.
There is no model call, network access, file access, ID allocation, business
projection or lifecycle management in the module.

## Focused verification

Run on Windows from the repository root:

```powershell
& 'C:\Program Files\Python312\python.exe' -I -S -B scripts/python/tests/test_b_route_compact_literal.py
```

Tests use embedded fixtures only. They verify complete nested round trips,
Unicode and exact types/order, marker collisions, deterministic selection,
fresh containers, digest behavior, strict rejection and non-execution.
They do not read run logs, dispatch models, measure request capacity, or establish
semantic acceptance. Earlier scratch capacity experiments are motivation only;
this independent codec needs a separate unchanged-wrapper capacity check before
any versioned wire integration. Structured measurement prompts are not a valid
substitute for the existing string-wrapper request.
