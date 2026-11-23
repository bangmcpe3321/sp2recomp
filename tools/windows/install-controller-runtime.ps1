param([Parameter(Mandatory=$true)][string]$GameDir)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($GameDir)
if(-not(Test-Path -LiteralPath $target -PathType Container)){throw 'GameDir must be an existing game directory.'}
$url='https://github.com/libsdl-org/SDL/releases/download/release-3.4.20/SDL3-3.4.20-win32-x64.zip'
$sha='368bed8b24e44ad9ea372990814f2343fcfb9e468abb7f8f4a3bc146c7304752'
$work=Join-Path ([IO.Path]::GetTempPath()) ('sp2-sdl3-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$archive=Join-Path $work 'SDL3.zip'
Invoke-WebRequest -Uri $url -OutFile $archive
if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha){throw 'SDL3 archive checksum mismatch; game files were not changed.'}
$unpacked=Join-Path $work 'unpacked'
Expand-Archive -LiteralPath $archive -DestinationPath $unpacked
$dll=Join-Path $unpacked 'SDL3.dll'
$license=Join-Path $unpacked 'LICENSE.txt'
if(-not(Test-Path -LiteralPath $dll) -or -not(Test-Path -LiteralPath $license)){throw 'SDL3 archive layout differs; game files were not changed.'}
$destination=Join-Path $target 'SDL3.dll'
if(Test-Path -LiteralPath $destination){
 if((Get-FileHash -LiteralPath $destination).Hash -ne (Get-FileHash -LiteralPath $dll).Hash){
  $backup=$destination+'.backup-'+(Get-Date -Format yyyyMMdd-HHmmss)
  Copy-Item -LiteralPath $destination -Destination $backup
 }
}
Copy-Item -LiteralPath $license -Destination (Join-Path $target 'SDL3-LICENSE.txt') -Force
Copy-Item -LiteralPath $dll -Destination $destination -Force
Write-Output "Installed verified SDL 3.4.20 runtime in $target"
Write-Output "Download and extraction evidence retained in $work"
