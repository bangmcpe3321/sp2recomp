# Windows GUI launcher

`sp2recomp-Launcher.exe` is a portable Windows launcher for the native PC
recompilation. Open it beside your game executable, or use the **sp2recomp
Launcher** desktop shortcut. The local installation is
`C:\sp2stage\sp2win\sp2recomp-Launcher.exe`.

The Play page provides Switch Pro Controller, mouse gyro and FPS overlay toggles.
Settings lets you choose the game folder and executable, start in fullscreen,
disable dynamic resolution, and change the memory limit. Settings save
automatically. The About page includes the in-game shortcuts and project link.

The current default build is `sp2-controller-gameplay.exe`. Automatic detection
checks that build, then `sp2-plaza-transition-safe.exe`, then `sp2.exe`; it does
not choose arbitrary diagnostic or rollback executables. You can choose another
build explicitly. Native Pro Controller and dynamic-resolution options require
a build with their runtime patches; the launcher does not add them to older builds.

**The 60 FPS experiment is on hold.** Every GUI launch explicitly sets
`NX_PLAZA_60FPS=0`, using the original game's scene timing. Native Switch Pro,
FPS overlay default on; mouse gyro defaults off (mouse aiming uses the right stick); fullscreen and disabled dynamic resolution
default off. The memory limit defaults to 13 GB and accepts values from 4 to 32 GB.

Before launching, the GUI checks for the selected executable,
`private\analysis\main.bin`, `private\extract\romfs`, and, when Switch Pro is
enabled, `SDL3.dll`. The game runs with its own folder as the working directory.
Inherited `NX_*` variables are cleared and replaced with the selected settings,
so diagnostic scripts, automatic tutorial input and timing experiments cannot
leak into a normal GUI session.

The launcher detects an existing game in the selected folder and prevents a
second launch. An independent session process also holds a per-folder lock,
captures both output streams and records the exit code. Closing the GUI leaves
the game and log capture running. Reopening the GUI recovers session status.
An exit code is reported as an ended session, without assuming a gameplay crash.

Settings and session records are stored under
`%LOCALAPPDATA%\sp2recomp\launcher`. The **Launch logs** button opens its `logs`
folder. The **Game folder** button opens the selected installation.

## Build and install

The C# / WPF launcher uses the installed .NET Framework compiler. It requires
Windows x64 with .NET Framework 4.8 and does not need the .NET SDK, WSL or a web
server. Its UI, supplied banner artwork and icon are embedded in the executable. No extracted game content is bundled.

From the repository root:

```powershell
.\tools\windows\build-launcher.ps1
.\tools\windows\build-launcher.ps1 -InstallDirectory C:\sp2stage\sp2win -DesktopShortcut
```

The default output is `build\windows-launcher\sp2recomp-Launcher.exe`.
Installation copies that executable into the existing game folder. The optional
switch creates the desktop shortcut. Updating a different existing launcher
retains it as a timestamped backup. Game builds and data remain separate.

## Verification

```powershell
.\tools\tests\windows\test-launcher.ps1 -Launcher .\build\windows-launcher\sp2recomp-Launcher.exe
```

The regression launches a temporary fixture executable through the production
session process. It checks saved settings, installation validation, explicit
normal timing and input options, paths containing spaces and `&`, concurrent
launch rejection, both output streams under pipe pressure, child environment,
working directory and recorded exit status. It does not run game data.

On November 24, 2026, the Windows build and regression passed. The installed GUI
was inspected visually; invalid memory feedback and restoring 13 GB worked.
Clicking **Play** launched the installed game and rendered the character
selection screen with the FPS overlay. This verifies launcher startup, not news
visibility or completion of gameplay.

## Editable inputs and session artwork

The Inputs page records keyboard or mouse button assignments per action, including
movement, face/shoulder buttons, plus/minus, stick clicks and D-pad. It supports
clear, cancellation, duplicate notices and restoring input defaults without
changing game/performance settings. Changes save automatically for the next
session. F1/F3/F11 remain fixed host shortcuts. Native controller mappings remain
unchanged. See [current controls](CONTROLS.md).

The local build embeds the user's supplied session artwork and displays its
illustrated strip in the Play banner with a contrast gradient. The original PNG
is retained unchanged; the launcher uses a cropped view to exclude letterboxing.
No game asset download is performed. `--render-preview <directory>` renders Home
and Inputs offscreen without showing windows, saving settings or launching games.

The updated runtime understands `NX_BIND_*` overrides supplied by the launcher.
Build it with `tools/patches/patch-launcher-inputs.py` and recompile
`platform_win.cpp`; the renderer and accepted performance configuration stay the
same. The input regression checks parser bounds, fallback, all defaults,
custom/disabled actions, focus gating and composition with controller input.
Launcher regressions cover saved settings/child environment and capture/clear/
reset behavior, plus the embedded image. No live game launch is part of these
checks. Game binaries, extracted content, saves, caches and keys remain external.
