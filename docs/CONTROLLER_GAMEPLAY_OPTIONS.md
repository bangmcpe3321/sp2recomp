# Native Switch Pro input and US 1.0.0 gameplay options

The Windows runtime supports native Nintendo Switch Pro Controller buttons,
sticks, accelerometer and gyro through SDL 3.4.20 HIDAPI. Separate startup
options implement the two supplied theboy181 US 1.0.0 patches in generated C++.
The FPS and resolution options default off.

## Patch compatibility and behavior

The original US 1.0.0 NSO has build ID
`F18FF3CFCBAD0884D72ABBEB6C540D6B00000000000000000000000000000000`.
Both supplied patch files identify this build (one omits trailing zero bytes).
Their `offset_shift 0x100` accounts for the NSO header when producing patches;
the addresses below are the corresponding flat-image/code offsets.

| Option | Original instruction | Replacement | Generated implementation |
| --- | --- | --- | --- |
| `NX_PLAZA_60FPS=1` | `0x51C2C`: `81010054`, `b.ne +0x30` | `0C000014`, `b +0x30` | In `Cmn::SceneBase::sceneEnter`, skip the interval-2 setter block even for mode 3. |
| `NX_DISABLE_DYNAMIC_RESOLUTION=1` | `0x1021FAC`: `768F0F94`, `bl agl::fctr::GPUStressChecker::calc` | `1F2003D5`, `nop` | Skip this GPU stress/scaling update call in `gsys::SystemTask::invokeCalcFrame_`, preserving the guest LR. |

This changes the guest's scene transition decision, rather than overriding only
host presentation. It removes that scene's request for 30 Hz pacing while
retaining the game's remaining timing code. Reaching a sustained 60 FPS still
depends on CPU/GPU work and pipeline compilation; no stable-60 benchmark is
claimed. Disabling the scaling update retains the configured render resolution
and can increase GPU load compared with automatic scaling.

The provided `US_1.0.0.pchtxt` contains only the plaza branch patch. US 1.0.0
predates Octo Expansion. **Octo Expansion credits are not covered or verified**;
support needs the corresponding later executable/build and patch sites.

Only the exact string `1` enables either gameplay option. Unset, `0`, and invalid
values retain the original instruction behavior. Options are latched on first
use and log their state once; restart to change them.

## Controller behavior

The backend selects Nintendo vendor `057e`, product `2009`, preserving Nintendo
button labels and converting SDL stick axes to the game's HID axes. A bounded
worker drains physical sensor events, resamples irregular device timestamps to
200 Hz, and publishes one coherent 16-sample history to both emulated sensors.
Angular velocity uses revolutions/second; acceleration uses gravity units. A
normalized quaternion keeps emitted orientation and angular rates consistent.
Stationary startup estimates sensor bias; movement cancels startup calibration.

Focus loss, mouse capture, disconnect, and long transport stalls prevent stale
motion from reaching the game. Reconnect resets history and calibration. Holding
right mouse or F1 capture selects mouse gyro; releasing it restores physical
gyro. Sticks/buttons remain usable while mouse aiming. XInput is the fallback
when no native Pro Controller is selected. `NX_SWITCH_PRO=0` disables this backend.

`SDL3.dll` loads only from beside the executable and its Windows system
dependencies. Missing SDL logs one message and leaves XInput available. The
installer pins the official SDL 3.4.20 archive checksum, retains its license,
and backs up a different existing DLL before replacement.

## Apply, build and launch

Apply after the existing mouse motion stream patch:

```sh
python3 tools/patches/patch-switch-pro-controller.py --root "$HOME/sp2port"
python3 tools/patches/patch-gameplay-options.py --root "$HOME/sp2port" \
  --nso /path/to/original/exefs/main
python3 tools/verify-tutorial-runtime.py --root "$HOME/sp2port"
```

The gameplay helper verifies NSO build ID, both original image instructions and
both generated source anchors before writing. It does not modify the NSO, flat
image or game assets. Rebuild `platform_win.cpp`, `code_006.cpp`, and `code_348.cpp`;
changing any controller header also requires rebuilding `platform_win.cpp` because
the local incremental builder does not track header dependencies.

Install SDL beside the executable:

```powershell
powershell -File tools/windows/install-controller-runtime.ps1 -GameDir C:/sp2stage/sp2win
```

With the private candidate executable named `sp2-controller-gameplay.exe`:

- `launch-controller-gameplay.cmd`: native input, original FPS/resolution behavior.
- `launch-60fps-fixed-resolution.cmd`: native input with both gameplay options on.

For independent options, set the appropriate environment variable and use the
first launcher. F3 toggles the existing present-driven FPS overlay. The local
candidate is installed separately from the existing normal launch executable.

To roll back, use the original launcher or the first new launcher with both
gameplay variables unset/zero. Source helpers support `--check` and `--restore`:

```sh
python3 tools/patches/patch-gameplay-options.py --root "$HOME/sp2port" --restore
python3 tools/patches/patch-switch-pro-controller.py --root "$HOME/sp2port" --restore
```

Rebuild after source restoration. The controller patch must be restored before
restoring the underlying mouse motion stream. Original source bytes were checked
after apply/idempotence/restore in isolated fixtures.

## Validation on November 24, 2026

The Windows candidate compiled 85 runtime units at O2 and two changed guest units
at O1, reusing 520 current guest objects and retaining earlier graphics/font/wait
fixes. Candidate SHA-256:
`9e6384cb1a78915865a48c84098e782d604bfd4c953635d6c6f8b87c0b562e81`.

The connected Bluetooth Nintendo Switch Pro Controller produced 300 gyro and
300 accelerometer events in approximately 1.5 seconds through the production
backend. Both emulated sensors returned the same 16 numbered 5 ms samples. Focus
exclusion/resume and worker shutdown passed in that physical-device probe.

CPU sanitizer tests cover Nintendo button chords/full signed stick range,
physical motion units/axes, independent reference rotations, irregular sampling,
bias, stalls, shared histories, actual worker reconnect/identity filtering,
old packets after focus regain, and missing-DLL/disabled fallback. Gameplay tests
exercise the full generated scene-enter function against the original branch
semantics, all option combinations, NOP/LR preservation, and rejected build or
source mismatches. In-game physical aiming and plaza performance still need a
manual play check; the device probe does not establish tutorial completion.

All 32 runtime regression groups passed. A candidate game launch also logged the
native controller connection and both gameplay options enabled, without an
observed startup crash. This startup check does not establish plaza performance.

No executable, SDL DLL, game image, shaders, or private cache is committed here.
