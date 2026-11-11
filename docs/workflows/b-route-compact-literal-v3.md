# B-route compact literal v3

The explicit schema `newrouge.b-route-compact-literal.v3` changes only the visible spelling of data references. It does not activate a route, authorize a model request, change source evidence, or establish planning completion. The existing default schema and v1/v2 canonical spelling remain unchanged.

The owning API is `_b_route_compact_literal.dumps(value, schema=ATOM_SCHEMA)`, `loads(text)`, and `instruction(ATOM_SCHEMA)`. The existing complete-materials wire v2 can explicitly pass this compact schema; it still restores the entire original envelope and applies the original complete-material identities and verifier. Generation or historical callers keep their existing explicit policy.

| v3 data atom | Exact expansion before normal restoration |
| --- | --- |
| `S12` | `(None,12)`, referring to complete `strings[12]` |
| `D12` | `(False,12)`, referring to a fresh copy of `shared[12]` |
| `R12` | `(12,)`, restoring the one-key original object `{'$mvg_ref':12}` |
| `P12` | Exact visible string `phrases[12]` |
| `(C,piece1,...,pieceK)` | Concatenate complete restored string pieces in order, without separators |
| `(B,text)` | Standard padded base64 of the strict UTF-8 bytes of the complete restored visible text |
| `HN` | Exact string `sha256:` followed by the lowercase hexadecimal form of decimal integer N, padded to 64 digits |

The suffix is an exact nonnegative ASCII decimal integer, without leading zeroes except `0`. These names are parsed as a closed data grammar; they are never evaluated, imported, or resolved as Python variables. Calls, attributes, subscripts, operators, unknown names, forward or cyclic shared references, invalid ranges, and unused definitions are rejected. Ordinary strings such as `'R12'` remain strings. Boolean, integer and float JSON types remain distinct. A one-key `$mvg_ref` object with a child other than a nonnegative exact integer retains the existing singleton tuple spelling.

Every keyset, string, shared subtree and original field still travels in the same request. Key order, array order, string characters, escape interpretation, source text, and all contenders are preserved. The original ordered-JSON SHA and mandatory full canonical re-encoding remain enforced. The v3 reference atoms provide no additional trust or semantic review authority.

The visible phrase dictionary and ordered concatenations preserve exact substrings, including whitespace, escapes and newlines; they do not paraphrase or omit source. A phrase definition is either complete literal text or a concatenation of literal text and strictly earlier phrase references. The table is restored in dependency order; forward/cyclic references, base64 or nontext definitions, and duplicate or empty restored phrases are rejected. Factoring uses only already selected phrase definitions; it adds no auxiliary short dictionary. Every definition is completely visible in this request. There are no offset slices or external dictionaries. The base64 spelling is derived only when strict decoding and exact padded re-encoding succeed, and its complete UTF-8 plaintext can be assembled exactly from string fragments already present in the original packet. Otherwise the original base64 string remains literal. The codec does not interpret a business schema or legacy source envelope to infer such text.

The original global subtree sharing remains unchanged. The explicit v3 text forms are restored before those tables are decoded. Phrase references, string-only concatenations, UTF-8 encoding, complete phrase usage, original SHA and full canonical re-encoding are checked. v1/v2 gain none of these new syntax forms or fields. No projection, opaque compression or source summary is introduced. Capacity must be measured on the exact full runner wrapper with the original tokenizer and output reserve. A shorter literal is not evidence of a passing token budget. A failing preflight must remain a failure without dispatch or budget refund.

The H atom applies only to a full exact `sha256:` plus 64 lowercase hexadecimal digits. It changes the numeral spelling of the complete 256-bit digest; it does not encode natural source prose, shorten a digest, or replace original content by a digest. Decimal N must be canonical ASCII, unsigned, without leading zeroes except zero, and in `0..2**256-1`. The fixed 64-digit reconstruction retains every leading hexadecimal zero and the exact prefix. Bare hexadecimal strings, uppercase or partial digest text, surrounding prose and newlines retain their original string semantics. The host restores this representation; the model is instructed not to recompute cryptographic hashes. Legacy v1/v2 remain unchanged.
