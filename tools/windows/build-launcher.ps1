param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '../../build/windows-launcher'),
    [string]$InstallDirectory,
    [switch]$DesktopShortcut
)
$ErrorActionPreference = 'Stop'
$sourceDirectory = Join-Path $PSScriptRoot 'launcher'
$frameworkDirectory = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319'
$compiler = Join-Path $frameworkDirectory 'csc.exe'
if (!(Test-Path -LiteralPath $compiler)) { throw 'Install .NET Framework 4.8 to build the Windows launcher.' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$output = Join-Path $OutputDirectory 'sp2recomp-Launcher.exe'
$references = @('System.dll', 'System.Core.dll', 'System.Xml.dll', 'System.Runtime.Serialization.dll', 'System.Windows.Forms.dll', 'System.Xaml.dll')
$arguments = @('/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/warn:4', "/out:$output", "/win32manifest:$sourceDirectory/launcher.manifest", "/win32icon:$sourceDirectory/assets/launcher-icon.ico", "/resource:$sourceDirectory/assets/launcher-icon.png,LauncherIcon.png", "/resource:$sourceDirectory/MainWindow.xaml,MainWindow.xaml", "/resource:$sourceDirectory/assets/session-art.png,SessionArt.png")
foreach ($reference in $references) { $arguments += "/reference:$frameworkDirectory/$reference" }
foreach ($reference in @('WindowsBase.dll', 'PresentationCore.dll', 'PresentationFramework.dll')) { $arguments += "/reference:$frameworkDirectory/WPF/$reference" }
$arguments += @((Join-Path $sourceDirectory 'Launcher.cs'), (Join-Path $sourceDirectory 'LauncherTests.cs'), (Join-Path $sourceDirectory 'InputOptions.cs'))
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
Write-Output "Built: $output"
if ($InstallDirectory) {
    if (!(Test-Path -LiteralPath $InstallDirectory -PathType Container)) { throw "Game folder missing: $InstallDirectory" }
    $installed = Join-Path $InstallDirectory 'sp2recomp-Launcher.exe'
    $same = (Test-Path -LiteralPath $installed) -and ((Get-FileHash -LiteralPath $installed).Hash -eq (Get-FileHash -LiteralPath $output).Hash)
    if (!$same) {
        $backup = $null
        if (Test-Path -LiteralPath $installed) {
            $backup = $installed + '.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 6)
            Move-Item -LiteralPath $installed -Destination $backup
        }
        try { Copy-Item -LiteralPath $output -Destination $installed }
        catch {
            if ($backup -and !(Test-Path -LiteralPath $installed)) { Move-Item -LiteralPath $backup -Destination $installed }
            throw
        }
    }
    Write-Output "Installed: $installed"
    if ($DesktopShortcut) {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'sp2recomp Launcher.lnk'))
        $shortcut.TargetPath = $installed
        $shortcut.WorkingDirectory = (Resolve-Path -LiteralPath $InstallDirectory).Path
        $shortcut.Description = 'Launch the Splatoon 2 PC recompilation'
        $shortcut.IconLocation = $installed + ',0'
        $shortcut.Save()
        Write-Output 'Created desktop shortcut: sp2recomp Launcher'
    }
}
