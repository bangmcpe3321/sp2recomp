param([string]$GameDirectory='C:\sp2stage\sp2win', [string]$Executable='sp2-controller-gameplay.exe', [switch]$ReplayProfile, [switch]$SimulationRateTrace, [switch]$PipelineFeedback, [switch]$DetailedStats)
$ErrorActionPreference='Stop'
$GameDirectory=(Resolve-Path -LiteralPath $GameDirectory).Path
$active=Get-CimInstance Win32_Process | Where-Object {$_.Name -like 'sp2*.exe' -and $_.Name -notlike 'sp2recomp-Launcher*'}
if($active){throw 'A game is running; leaving it alone.'}
$exe=Join-Path $GameDirectory $Executable
if(!(Test-Path -LiteralPath $exe)){throw "Missing executable: $exe"}
foreach($item in @(Get-ChildItem Env:NX_*)){Remove-Item -LiteralPath ('Env:'+$item.Name)}
$captureDirectory=Join-Path $GameDirectory 'diagnostics'
New-Item -ItemType Directory -Path $captureDirectory -Force | Out-Null
$prefix=Join-Path $captureDirectory ('stage-performance-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
$env:NX_DATA_ROOT='private';$env:NX_MEM_LIMIT_GB='13';$env:NX_FPS_OVERLAY='1'
$env:NX_GPU_TIMESTAMPS='0';$env:NX_PLAZA_60FPS='0';$env:NX_DISABLE_DYNAMIC_RESOLUTION='0'
$env:NX_SWITCH_PRO='1';$env:NX_SIXAXIS='1';$env:NX_MOUSE_GYRO='1'
$env:NX_FRAME_CSV=$prefix+'.csv';$env:NX_RENDER_STATS='0';$env:NX_PRESENT_STATS='0';$env:NX_STALL_SAMPLER='0'
# Synchronous statistics can add visible periodic hitches; opt in only to diagnose.
if($DetailedStats){$env:NX_RENDER_STATS='1';$env:NX_PRESENT_STATS='1'}
if($ReplayProfile){$env:NX_REPLAY_PROFILE='1'}
if($SimulationRateTrace){$env:NX_SIM_RATE_TRACE='1'}
if($PipelineFeedback){$env:NX_PIPELINE_FEEDBACK='1'}
# Reuse the diagnostic host's console instead of creating an extra console window.
# Closing a console can terminate the process before the game's WM_CLOSE saves caches.
$process=Start-Process -FilePath $exe -WorkingDirectory $GameDirectory -NoNewWindow -RedirectStandardError ($prefix+'.log') -RedirectStandardOutput ($prefix+'-stdout.log') -PassThru
Write-Output "PID=$($process.Id) LOG=$prefix.log CSV=$prefix.csv"
Write-Output 'Input injection is off. Reproduce the first-stage ink-hide dip; close normally to save frame times.'
