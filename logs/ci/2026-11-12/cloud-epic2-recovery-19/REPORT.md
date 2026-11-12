# Cloud Epic2 continuation19: authorized subscription runtime recovery

The coordinator explicitly confirms the two logical review calls belong to the user's continuing Epic2 authorization and use existing ChatGPT/Codex subscription access, not a separate OpenAI API payment. No further dollar-budget approval is required. The fixed plan and lifetime limit2 remain the intended next invocation; no actual business call was consumed this turn.

## Actual supported recovery and observations

The inherited CODEX_HOME is read-only and lacks models_cache.json. Rather than repeat the known SQLite initialization failure there, create a private isolated writable CODEX_HOME at /workspace/newrouge-tools/codex-runtime-epic2-20261112. Copy only the existing official auth/config files with private permissions, leave original unchanged, and retain all inherited proxy/CA/network settings. No credentials, token bodies, sessions or raw account response are committed or exposed.

Official `codex login status` exits0 and reports ChatGPT. This is local login metadata, not online authentication qualification. Official `codex debug models` exits0 and outputs the same exact catalog as the retained bundled catalog; it creates no models_cache.json and proves no successful remote refresh. Do not invent a cache or label bundled data as fresh server metadata.

A bounded official App Server metadata-only process initializes successfully in the isolated directory: original SQLite/read-only blocker is resolved. RPCs are initialize, model/list, config/read and account/read(refreshToken:false). Model/list returns default gpt-6.1-sol and bundled metadata; stderr explicitly reports Failed to refresh models/HTTP401 Unauthorized. Account type is chatgpt/planType unknown; effective model/provider/reasoning/service_tier values are null. No thread/start or turn/start is sent. The returned list is not current online admission or quota proof, and no official cache is generated.

One supported account/read(refreshToken:true) attempt returns without RPC error but leaves auth bytes unchanged from the inherited record. It does not establish renewed online credentials or create a cache. One subsequent independent non-business account/rateLimits/read check returns RPC -32603 with HTTP401 and no rate-limit observation. All processes exit and owned pipe threads stop. This is a concrete online authentication blocker, not a payment authorization, Story/skill, model-capacity or product-code failure.

No further online retries are made. No manual OAuth/token exchange, alternate network route, API-key switch, metadata fabrication or model call is attempted. Private raw metadata/status captures remain outside Git in the isolated runtime; public evidence includes only categorical state/error codes and nonsecret model/config fields.

## State and next boundary

All83 current source pins match the prepared epoch. The genuine current two-node prepare and66079/68307 literal full-RPC bounds remain intact; actual predecessor output is still absent. No call-limit, intent, execution, proof or new business operation was created. Original catalog, NativeV15Origin03 receipt and operation bytes match. Both authorized business calls remain unused. Historical unknowns/STOP/ledgers remain untouched; Separately billed API business calls, fiscal actions, unknown replay/release and business model turns are0; metadata RPC attempts are recorded above.

The necessary next action is to restore effective ChatGPT authentication for the official CLI subprocess in this managed cloud runtime through the platform/official login flow. Do not request password/token/API-key text, new payment or extra quota. Only after successful official online metadata/subscription access should the same source-pinned deterministic plan run with model-request-budget2, high/default speed, no automatic unknown replay. The current source is unchanged; no full tests/reprepare/old driver were repeated to explore this environment failure.

Actual2.8 semantic review/proof and compensation commit/recovery remain pending online auth. Existing2.9/2.10 evidence remains in its original scope, and no additional independent implementation gap is evidenced to justify unrelated work. No Epic3-5, main merge, Fast, full regression, Aliyun, S2/monitoring or network-policy change.
