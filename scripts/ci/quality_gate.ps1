param(
  [string]$GodotBin = $env:GODOT_BIN,
  [switch]$WithExport = $false,
  [switch]$IncludeDemo = $false,
  [switch]$WithCoverage = $false,
  [int]$PerfP95Ms = 0,
  [string]$SecurityProfile = $null
)

$ErrorActionPreference = 'Stop'

function Run-Step($name, [ScriptBlock]$block) {
  Write-Host "=== [$name] ==="
  try { & $block; return $LASTEXITCODE } catch { Write-Error $_; return 1 }
}

function Resolve-SecurityProfile([string]$value) {
  $v = ('' + $value).Trim().ToLowerInvariant()
  if ($v -eq 'strict') { return 'strict' }
  return 'host-safe'
}

function Resolve-SecurityProfileMeta([string]$cliValue, [bool]$cliProvided) {
  if ($cliProvided) {
    $raw = $cliValue
    $source = 'cli'
  } elseif ($env:SECURITY_PROFILE) {
    $raw = $env:SECURITY_PROFILE
    $source = 'env'
  } else {
    $raw = 'host-safe'
    $source = 'default'
  }

  $resolved = Resolve-SecurityProfile $raw
  return @{
    value = $resolved
    source = $source
    raw = $raw
  }
}

function Write-QualityGateSummary(
  [hashtable]$profileMeta,
  [System.Collections.ArrayList]$steps,
  [int]$failCount,
  [string]$godotBin,
  [bool]$withExport,
  [int]$perfP95Ms
) {
  $date = Get-Date -Format 'yyyy-MM-dd'
  $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
  $outDir = Join-Path $repoRoot ("logs/ci/" + $date)
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null

  $summaryPath = Join-Path $outDir 'quality-gate-summary.json'
  $summary = [ordered]@{
    generated_at = (Get-Date).ToString('o')
    status = $(if ($failCount -gt 0) { 'fail' } else { 'pass' })
    fail_count = $failCount
    security_profile = [ordered]@{
      value = $profileMeta.value
      source = $profileMeta.source
      raw = $profileMeta.raw
    }
    inputs = [ordered]@{
      godot_bin = $godotBin
      with_export = $withExport
      perf_p95_ms = $perfP95Ms
    }
    steps = $steps
    artifacts = [ordered]@{
      ci_pipeline_summary = ("logs/ci/" + $date + "/ci-pipeline-summary.json")
    }
  }

  $json = ($summary | ConvertTo-Json -Depth 10) + [Environment]::NewLine
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($summaryPath, $json, $utf8NoBom)
  Write-Host ("QUALITY_GATE_SUMMARY status={0} security_profile={1} source={2} out={3}" -f $summary.status, $profileMeta.value, $profileMeta.source, $summaryPath)
}

$fail = 0
$profileMeta = Resolve-SecurityProfileMeta $SecurityProfile ($PSBoundParameters.ContainsKey('SecurityProfile'))
$SecurityProfile = $profileMeta.value
$stepResults = New-Object System.Collections.ArrayList

# Canonical entrypoint is Python (this wrapper stays for Windows convenience).
$c = Run-Step 'python quality_gates.py' {
  $env:SECURITY_PROFILE = $SecurityProfile
  py -3 "$PSScriptRoot/../python/quality_gates.py" all --godot-bin $GodotBin --solution 'Game.sln' --configuration 'Debug' --build-solutions --security-profile $SecurityProfile
}
$stepResults.Add([ordered]@{
  name = 'python quality_gates.py'
  required = $true
  status = $(if ($c -eq 0) { 'ok' } else { 'fail' })
  exit_code = $c
}) | Out-Null
if ($c -ne 0) { $fail++ }

# Export + EXE smoke (optional)
if ($WithExport) {
  $c = Run-Step 'Export Windows EXE' { & "$PSScriptRoot/export_windows.ps1" -GodotBin $GodotBin -Output 'build/NewRouge.exe' }
  $stepResults.Add([ordered]@{
    name = 'Export Windows EXE'
    required = $true
    status = $(if ($c -eq 0) { 'ok' } else { 'fail' })
    exit_code = $c
  }) | Out-Null
  if ($c -ne 0) { $fail++ }
  $c = Run-Step 'Smoke EXE' { & "$PSScriptRoot/smoke_exe.ps1" -ExePath 'build/NewRouge.exe' -TimeoutSec 5 }
  $stepResults.Add([ordered]@{
    name = 'Smoke EXE'
    required = $true
    status = $(if ($c -eq 0) { 'ok' } else { 'fail' })
    exit_code = $c
  }) | Out-Null
  if ($c -ne 0) { $fail++ }
} else {
  $stepResults.Add([ordered]@{
    name = 'Export Windows EXE'
    required = $false
    status = 'skipped'
    exit_code = $null
    reason = 'WithExport=false'
  }) | Out-Null
  $stepResults.Add([ordered]@{
    name = 'Smoke EXE'
    required = $false
    status = 'skipped'
    exit_code = $null
    reason = 'WithExport=false'
  }) | Out-Null
}

# Perf budget (optional)
if ($PerfP95Ms -gt 0) {
  $c = Run-Step "Perf budget <= $PerfP95Ms ms" { & "$PSScriptRoot/check_perf_budget.ps1" -MaxP95Ms $PerfP95Ms }
  $stepResults.Add([ordered]@{
    name = "Perf budget <= $PerfP95Ms ms"
    required = $true
    status = $(if ($c -eq 0) { 'ok' } else { 'fail' })
    exit_code = $c
  }) | Out-Null
  if ($c -ne 0) { $fail++ }
} else {
  $stepResults.Add([ordered]@{
    name = 'Perf budget'
    required = $false
    status = 'skipped'
    exit_code = $null
    reason = 'PerfP95Ms<=0'
  }) | Out-Null
}

Write-QualityGateSummary -profileMeta $profileMeta -steps $stepResults -failCount $fail -godotBin $GodotBin -withExport ([bool]$WithExport) -perfP95Ms $PerfP95Ms

if ($fail -gt 0) {
  Write-Host "QUALITY GATE: FAIL ($fail)"
  exit 1
}
Write-Host 'QUALITY GATE: PASS'
exit 0
