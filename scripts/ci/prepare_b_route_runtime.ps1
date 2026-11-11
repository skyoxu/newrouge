param(
    [string]$EvidenceDirectory = 'logs/ci/b-route-runtime-environment'
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:RUNNER_TEMP) -or [string]::IsNullOrWhiteSpace($env:GITHUB_ENV)) {
    throw 'B-route CI preparation requires RUNNER_TEMP and GITHUB_ENV.'
}

# The interpreter, packages and encoding cache belong only to this runner job.
# Do not activate the venv or change PATH/the Python used by other hard gates.
$ciPrivateRoot = Join-Path $env:RUNNER_TEMP 'nr-br-runtime'
if (Test-Path -LiteralPath $ciPrivateRoot) {
    throw 'B-route private environment already exists; refusing implicit reuse.'
}
New-Item -ItemType Directory -Path $ciPrivateRoot | Out-Null
$ciEnvironmentRoot = Join-Path $ciPrivateRoot 'venv'
$ciCacheRoot = Join-Path $ciPrivateRoot 'encodings'
$ciTestTemp = Join-Path $ciPrivateRoot 'tests'
New-Item -ItemType Directory -Path $ciCacheRoot, $ciTestTemp | Out-Null
New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
$ciEvidenceRoot = (Resolve-Path -LiteralPath $EvidenceDirectory).Path

python -m venv $ciEnvironmentRoot
if ($LASTEXITCODE -ne 0) { throw "Private venv creation failed: $LASTEXITCODE" }
$ciPython = Join-Path $ciEnvironmentRoot 'Scripts/python.exe'
& $ciPython -m pip --isolated install --no-input --index-url https://pypi.org/simple --disable-pip-version-check --report (Join-Path $ciEvidenceRoot 'install-report.json') 'jsonschema==4.26.0' 'tiktoken==0.14.0' 2>&1 | Tee-Object -FilePath (Join-Path $ciEvidenceRoot 'install.log')
if ($LASTEXITCODE -ne 0) { throw "Private dependency installation failed: $LASTEXITCODE" }

$ciPriorCache = $env:TIKTOKEN_CACHE_DIR
try {
    $env:TIKTOKEN_CACHE_DIR = $ciCacheRoot
    @'
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tiktoken

encodings = {}
for name in ('cl100k_base', 'o200k_base'):
    encoding = tiktoken.get_encoding(name)
    tokens = encoding.encode('B-route complete input / \u4e2d\u6587')
    if not tokens:
        raise RuntimeError('Tokenizer prewarm returned no tokens: ' + name)
    encodings[name] = {'vocabulary_size': encoding.n_vocab, 'probe_token_count': len(tokens)}
cache = Path(os.environ['TIKTOKEN_CACHE_DIR'])
result = {
    'execution_scope': 'CI dependency preparation; no model calls',
    'python': sys.executable,
    'python_version': sys.version,
    'packages': {name: importlib.metadata.version(name) for name in ('jsonschema', 'tiktoken')},
    'encodings': encodings,
    'cache_files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted(cache.iterdir()) if path.is_file()},
}
print(json.dumps(result, ensure_ascii=False, indent=2))
'@ | & $ciPython -B - 2>&1 | Tee-Object -FilePath (Join-Path $ciEvidenceRoot 'encodings.json')
    if ($LASTEXITCODE -ne 0) { throw "Tokenizer prewarm failed: $LASTEXITCODE" }
} finally {
    $env:TIKTOKEN_CACHE_DIR = $ciPriorCache
}

# Only the explicit runtime gate maps these private paths into its child env.
"BR_PYTHON=$ciPython" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
"BR_TIKTOKEN_CACHE_DIR=$ciCacheRoot" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
"BR_TEST_TEMP=$ciTestTemp" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
