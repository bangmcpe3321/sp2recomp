param([string]$LaunchScript=(Join-Path $PSScriptRoot '..\..\windows\start-performance-capture.ps1'))
$ErrorActionPreference='Stop'
$LaunchScript=(Resolve-Path -LiteralPath $LaunchScript).Path
$testRoot=Join-Path ([System.IO.Path]::GetTempPath()) ('sp2-capture-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
New-Item -ItemType File -Path (Join-Path $testRoot 'capture-test-stub.exe') | Out-Null
$global:Sp2CaptureLaunchTestRecords=@()
function Get-CimInstance { param($ClassName) return @() }
function Start-Process {
 param($FilePath,$WorkingDirectory,[switch]$NoNewWindow,$RedirectStandardError,$RedirectStandardOutput,[switch]$PassThru)
 $flags=@{};Get-ChildItem Env:NX_* | ForEach-Object {$flags[$_.Name]=$_.Value}
 $global:Sp2CaptureLaunchTestRecords+=@{Exe=$FilePath;Directory=$WorkingDirectory;NoNewWindow=$NoNewWindow.IsPresent;Flags=$flags}
 return [pscustomobject]@{Id=4242}
}
function Assert($condition,[string]$message){if(-not $condition){throw $message}}
try {
 $cases=@(
  @{Options=@{};Detailed=$false;Feedback=$false;Simulation=$false},
  @{Options=@{DetailedStats=$true};Detailed=$true;Feedback=$false;Simulation=$false},
  @{Options=@{PipelineFeedback=$true};Detailed=$false;Feedback=$true;Simulation=$false},
  @{Options=@{SimulationRateTrace=$true};Detailed=$false;Feedback=$false;Simulation=$true},
  @{Options=@{DetailedStats=$true;PipelineFeedback=$true;SimulationRateTrace=$true};Detailed=$true;Feedback=$true;Simulation=$true}
 )
 foreach($case in $cases){
  $env:NX_RENDER_STATS='1';$env:NX_PRESENT_STATS='1';$env:NX_REPLAY_PROFILE='1'
  $env:NX_PIPELINE_FEEDBACK='1';$env:NX_SIM_RATE_TRACE='1';$env:NX_INPUT_SCRIPT='stale-input.txt'
  $env:NX_NO_FRAME_LIMIT='1';$env:NX_PLAZA_60FPS='1';$env:NX_GPU_TIMESTAMPS='1'
  $options=$case.Options
  & $LaunchScript -GameDirectory $testRoot -Executable 'capture-test-stub.exe' @options | Out-Null
  $launch=$global:Sp2CaptureLaunchTestRecords[-1];$f=$launch.Flags
  $expected=if($case.Detailed){'1'}else{'0'}
  Assert ($f.NX_RENDER_STATS -eq $expected -and $f.NX_PRESENT_STATS -eq $expected) ("Detailed statistics must be explicit: expected=$expected got="+($f | ConvertTo-Json -Compress))
  Assert (($f.NX_PIPELINE_FEEDBACK -eq '1') -eq $case.Feedback) 'Pipeline feedback switch or stale environment leak'
  Assert (($f.NX_SIM_RATE_TRACE -eq '1') -eq $case.Simulation) 'Simulation trace switch or stale environment leak'
  Assert ($f.NX_FPS_OVERLAY -eq '1' -and $f.NX_FRAME_CSV.EndsWith('.csv')) 'Overlay and buffered CSV must remain enabled'
  Assert ($f.NX_GPU_TIMESTAMPS -eq '0' -and $f.NX_STALL_SAMPLER -eq '0') 'Heavy timestamp/stall diagnostics must remain off'
  Assert ($f.NX_PLAZA_60FPS -eq '0' -and $f.NX_DISABLE_DYNAMIC_RESOLUTION -eq '0') 'Original scene timing and dynamic resolution must remain'
  Assert (-not $f.ContainsKey('NX_INPUT_SCRIPT') -and -not $f.ContainsKey('NX_NO_FRAME_LIMIT') -and -not $f.ContainsKey('NX_REPLAY_PROFILE')) 'Stale input/pacing/profile overrides must be cleared'
  Assert ($launch.NoNewWindow -and $launch.Directory -eq $testRoot) 'Console and working-directory behavior changed'
 }
 Assert ($global:Sp2CaptureLaunchTestRecords.Count -eq 5) 'Each scenario must launch exactly once'
 Write-Output 'PASS actual capture launcher: quiet defaults, explicit diagnostic switches, clean inherited environment, overlay/CSV and original timing'
} finally {
 $resolved=[System.IO.Path]::GetFullPath($testRoot)
 $parent=[System.IO.Path]::GetDirectoryName($resolved).TrimEnd('\')
 if($parent -ne ([System.IO.Path]::GetTempPath()).TrimEnd('\')){throw 'Test cleanup target escaped temp directory'}
 Remove-Item -LiteralPath $resolved -Recurse -Force
}
