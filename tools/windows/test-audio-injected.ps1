param([string]$GameDirectory='C:\sp2stage\sp2win')
$ErrorActionPreference='Stop'
$GameDirectory=(Resolve-Path -LiteralPath $GameDirectory).Path
$active=Get-CimInstance Win32_Process | Where-Object {$_.Name -like 'sp2*.exe' -and $_.Name -notlike 'sp2recomp-Launcher*'}
if($active){throw 'A game is already running; close it before starting the injected test.'}
$executable=Join-Path $GameDirectory 'sp2-controller-gameplay.exe'
if(!(Test-Path -LiteralPath $executable)){throw "Missing game build: $executable"}
foreach($item in @(Get-ChildItem Env:NX_*)){Remove-Item -LiteralPath ('Env:'+$item.Name)}
$parts=@('600:A','1000:A','1400:A','2400:A','2500:Right','2600:A','2700:Right','2800:A','3100:A')
for($frame=3400;$frame -le 6200;$frame+=200){$parts+="${frame}:A"}
for($frame=6300;$frame -le 10000;$frame+=60){$parts+="${frame}:A"}
$parts+=@('120:A','126:A','133:A','151:A','161:A','170:A','187:A','198:A','208:A','219:A','230:A','246:A','259:A','270:A','281:A','292:A','300:A','310:A','325:A','338:A','353:A','366:A','377:A','419:A','431:A','443:A','497:A','600:A','646:A','486:Right')
# PlayerMake confirmation defaults to No. Alternate direction/confirm pulses so
# a delayed page transition cannot trap the test between confirmation and legwear.
for($frame=550;$frame -le 1450;$frame+=150){$parts+="${frame}:Right";$parts+="$($frame+30):A"}
$env:NX_INPUT=$parts -join ','
$env:NX_TUT_AIM_SKIP='180';$env:NX_TUT_SHOT_SKIP='240';$env:NX_TUT_MOVE_SKIP='180'
$env:NX_ZLZR_HOLD='6000-8600'
$env:NX_DATA_ROOT='private';$env:NX_MEM_LIMIT_GB='13';$env:NX_FPS_OVERLAY='1';$env:NX_GPU_TIMESTAMPS='0'
$env:NX_SWITCH_PRO='1';$env:NX_SIXAXIS='1';$env:NX_MOUSE_GYRO='1'
$env:NX_PLAZA_60FPS='0';$env:NX_DISABLE_DYNAMIC_RESOLUTION='0'
$tag='audio-injected-'+(Get-Date -Format 'yyyyMMdd-HHmmss')
$env:NX_AUDIO_DUMP=Join-Path $GameDirectory ($tag+'.wav')
$env:NX_FRAME_CSV=Join-Path $GameDirectory ($tag+'.csv')
$env:NX_INPUT | Set-Content -LiteralPath (Join-Path $GameDirectory ($tag+'-input.txt'))
$test=Start-Process -FilePath $executable -WorkingDirectory $GameDirectory -WindowStyle Normal -RedirectStandardError (Join-Path $GameDirectory ($tag+'.log')) -RedirectStandardOutput (Join-Path $GameDirectory ($tag+'-stdout.log')) -PassThru
Write-Output "Input injection enabled. PID=$($test.Id) LOG=$GameDirectory\$tag.log"
