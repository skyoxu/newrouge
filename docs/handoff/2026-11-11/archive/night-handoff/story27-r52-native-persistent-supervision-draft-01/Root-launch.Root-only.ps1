param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ManifestSha256)
$ErrorActionPreference='Stop'
$nativeTask='C:\Users\Administrator\Documents\Codex\2026-11-05\task'
$nativeHome=Join-Path $nativeTask 'night-handoff/story27-r52-native-persistent-supervision-draft-01'
if ($PSScriptRoot -ne $nativeHome) { throw 'Exact Root launch entry required' }
Set-Location -LiteralPath $nativeTask
$nativePython='C:\Program Files\Python312\python.exe'
if ((Get-FileHash -LiteralPath $nativePython).Hash.ToLowerInvariant() -ne '4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a') { throw 'Fixed Python raw changed' }
$nativeManifest=Join-Path $nativeHome 'manifest.json'
if ((Get-FileHash -LiteralPath $nativeManifest).Hash.ToLowerInvariant() -ne $ManifestSha256) { throw 'Reviewed manifest changed' }
$nativeFrozen=Get-Content -LiteralPath $nativeManifest -Raw | ConvertFrom-Json
foreach ($nativeMember in $nativeFrozen.files.PSObject.Properties) {
    if ($nativeMember.Name.Contains('/') -or $nativeMember.Name.Contains('\')) { throw 'Simple frozen member only' }
    $nativePath=Join-Path $nativeHome $nativeMember.Name
    if ((Get-FileHash -LiteralPath $nativePath).Hash.ToLowerInvariant() -ne $nativeMember.Value.sha256) { throw 'Frozen supervisor control changed' }
}
$nativeWorker=Join-Path $nativeTask 'night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/run_review_prepare.Root-only.py'
$nativeWorkerManifest=Join-Path $nativeTask 'night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/manifest.json'
$nativeConfig=Join-Path $nativeTask 'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-seal-01/config.json'
if ((Get-FileHash -LiteralPath $nativeWorker).Hash.ToLowerInvariant() -ne '71e7f9241ae4485a525868060bff75db537fff15e1a6c2d4ce82f5c3fd4916c8' -or
    (Get-FileHash -LiteralPath $nativeWorkerManifest).Hash.ToLowerInvariant() -ne '88a551e4a57a09a621990758ae6355d0de70651824a36faabc01ec991810fa25' -or
    (Get-FileHash -LiteralPath $nativeConfig).Hash.ToLowerInvariant() -ne 'd6f1eec3a9e9bf7dc5b94608db02d069c4f84404625587bfe9ebd7e64658067d') { throw 'Actual sealed native worker inputs changed' }
$nativeLaunch=Join-Path $nativeTask 'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-Root-launch-01'
$nativeSuper=Join-Path $nativeTask 'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01'
$nativeOutput=Join-Path $nativeTask 'logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01'
foreach ($nativeExisting in @($nativeLaunch,$nativeSuper,$nativeOutput)) { if (Test-Path -LiteralPath $nativeExisting) { throw 'Existing/uncertain original namespace: never relaunch' } }
New-Item -ItemType Directory -Path $nativeLaunch | Out-Null
$nativeArguments=@('-X','dev','-I','-S','-B','night-handoff/story27-r52-native-persistent-supervision-draft-01/native_supervisor.Root-only.py','--manifest-sha256',$ManifestSha256)
$nativeIntent=[ordered]@{Utc=[DateTime]::UtcNow.ToString('o');Arguments=$nativeArguments;WorkerEntrySha256='71e7f9241ae4485a525868060bff75db537fff15e1a6c2d4ce82f5c3fd4916c8';ActualConfigSha256='d6f1eec3a9e9bf7dc5b94608db02d069c4f84404625587bfe9ebd7e64658067d';AboutToInvokeOriginalStartProcess=$true;AutomaticRetry=$false;NativePassClaimed=$false;ModelCallsAdded=0;FormalAcceptance=$false}
[IO.File]::WriteAllText((Join-Path $nativeLaunch 'intent.json'),($nativeIntent|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
$nativeAttempted=$false;$nativeReturned=$false;$nativePid=$null
try {
    $nativeAttempted=$true
    $nativeProcess=Start-Process -FilePath $nativePython -ArgumentList $nativeArguments -WorkingDirectory $nativeTask -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $nativeLaunch 'supervisor-stdout.bin') -RedirectStandardError (Join-Path $nativeLaunch 'supervisor-stderr.bin')
    $nativeReturned=$true;$nativePid=$nativeProcess.Id
    $nativeBirth=$null;$nativeBirthError=$null
    try { $nativeBirth=$nativeProcess.StartTime.ToUniversalTime().ToString('o') } catch { $nativeBirthError=$_.Exception.GetType().FullName }
    $nativeStarted=[ordered]@{Utc=[DateTime]::UtcNow.ToString('o');Launched=$true;SupervisorPid=$nativePid;BirthUtc=$nativeBirth;BirthError=$nativeBirthError;LaunchOnly=$true;NativePassClaimed=$false;AutomaticRetry=$false;FormalAcceptance=$false;ModelCallsAdded=0;PaidOrUnknown=80;GuardOccupancy=178;CampaignLimit=290;Released=0}
    [IO.File]::WriteAllText((Join-Path $nativeLaunch 'started.json'),($nativeStarted|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    $nativeStarted|ConvertTo-Json -Depth 8
} catch {
    $nativeFailure=[ordered]@{Utc=[DateTime]::UtcNow.ToString('o');OriginalLaunchAttempted=$nativeAttempted;OriginalProcessObjectReturned=$nativeReturned;OriginalReturnedPid=$nativePid;LaunchOutcomeMayBeUncertain=$nativeAttempted;Reason=$_.Exception.Message;AutomaticRetry=$false;NativePassClaimed=$false;FormalAcceptance=$false}
    [IO.File]::WriteAllText((Join-Path $nativeLaunch 'failure.json'),($nativeFailure|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    throw
}
