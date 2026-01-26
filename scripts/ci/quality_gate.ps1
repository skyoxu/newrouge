param(
  [string]$GodotBin = $env:GODOT_BIN,
  [switch]$WithExport = $false,
  [switch]$IncludeDemo = $false,
  [switch]$WithCoverage = $false,
  [int]$PerfP95Ms = 0
)

$ErrorActionPreference = 'Stop'

function Run-Step($name, [ScriptBlock]$block) {
  Write-Host "=== [$name] ==="
  try { & $block; return $LASTEXITCODE } catch { Write-Error $_; return 1 }
}

$fail = 0

# Canonical entrypoint is Python (this wrapper stays for Windows convenience).
$c = Run-Step 'python quality_gates.py' {
  py -3 "$PSScriptRoot/../python/quality_gates.py" all --godot-bin $GodotBin --solution 'Game.sln' --configuration 'Debug' --build-solutions
}
if ($c -ne 0) { $fail++ }

# Export + EXE smoke (optional)
if ($WithExport) {
  $c = Run-Step 'Export Windows EXE' { & "$PSScriptRoot/export_windows.ps1" -GodotBin $GodotBin -Output 'build/NewRouge.exe' }
  if ($c -ne 0) { $fail++ }
  $c = Run-Step 'Smoke EXE' { & "$PSScriptRoot/smoke_exe.ps1" -ExePath 'build/NewRouge.exe' -TimeoutSec 5 }
  if ($c -ne 0) { $fail++ }
}

# Perf budget (optional)
if ($PerfP95Ms -gt 0) {
  $c = Run-Step "Perf budget <= $PerfP95Ms ms" { & "$PSScriptRoot/check_perf_budget.ps1" -MaxP95Ms $PerfP95Ms }
  if ($c -ne 0) { $fail++ }
}

if ($fail -gt 0) {
  Write-Host "QUALITY GATE: FAIL ($fail)"
  exit 1
}
Write-Host 'QUALITY GATE: PASS'
exit 0
