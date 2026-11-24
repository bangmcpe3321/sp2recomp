# Runtime status

Updated November 24, 2026 (Asia/Bangkok). This file separates implemented changes
from behavior that the user has verified in game.

## Current priorities

1. Correct physical Pro Controller vertical aiming, including accelerometer tilt.
2. Resolve tutorial intro audio playing ahead of animation.
3. Reduce loading pauses and FPS dips when shooting or hiding in ink; verify
   story-mode frame times and normal shutdown cache persistence.

## Current build

The installed executable is `C:\sp2stage\sp2win\sp2-controller-gameplay.exe`.
The preceding manual candidate is `sp2-pro-pitch-performance.exe`, SHA-256
`bb621ba59f8dc7c877d895ff043cf0dd228f0e5aaffc971cb5a2dd85e71d8fae`.
That candidate corrected angular velocity but **the user still reported reversed
vertical aiming**. It is not a confirmed gyro fix.

The follow-up corrects accelerometer tilt together with gyro rotation. It is
built, installed and launched as `sp2-pro-tilt-performance.exe`, SHA-256
`12ccf4effa7dec1710617d5ea7508ae262e5b12932b762b3a1af08807d2e4456`.
Its visible game window is responding (PID 12964; capture `201306`). In-game
vertical direction still needs confirmation. Normal runs retain original
plaza/news timing, dynamic resolution, real occlusion queries and manual input.
No tutorial automation is enabled.

## Implemented and tested

| Area | Change | Evidence / limit |
| --- | --- | --- |
| Pipeline cache | Key equivalent draw state by shader-consumed inputs; preserve the 2,048-entry limit and deferred retirement | 4,096 equivalent variants share one key; consumed state stays distinct |
| Draw hot path | Avoid shader-name diagnostic string copies on ordinary cache hits | 10,000 warmed hits allocate zero diagnostic strings; old comparison allocated 20,000 |
| Descriptor images | Bounded front cache cleared before frame retirement | 810,180 requests preserve image identity/aliasing/retirement; map searches decrease from 809,280 to 45,399 |
| Renderer compiler | Build 48 NVN units at `-O2`, without fast-math | All 471 other objects were byte-identical before the separate news correction; no stable-60 result claimed |
| News ending | Honor the original count/60 reservation and preserve all caller registers in the fallback handover | Actual generated predicate/pose sanitizer tests pass; minimum usual reservation is 149/60 seconds; manual duration retest remains open |
| Native controller | SDL3 Switch Pro buttons, sticks and sensor stream | Bluetooth hardware stream verified; current vertical direction remains under correction |
| Gyro continuity | Shared monotonic sample numbering, focus/capture handoff and no idle mouse fallback during controller packet gaps | Production HID/arbitration tests pass; earlier user confirmed consistent vertical responsiveness |
| Pro pitch follow-up | Match accelerometer tilt to corrected gyro pitch before attitude integration | New test compares moving physical tilt, integrated attitude and settled gravity; motion and HID handoff regressions pass; in-game retest pending |

The complete local suite passed **41 regression groups** before the latest
accelerometer follow-up. The follow-up's motion and HID/arbitration tests pass;
it has not yet had a complete-suite rerun. Do not interpret source tests as
proof of in-game FPS or audio synchronization.

## Unresolved issues

### Tutorial intro audio ahead

The user reported audio playing ahead during the initial tutorial portrait
scene at about 39.8 FPS, and reported that it remains ahead in the next test.
Native audio advances 240 samples per update at 200 Hz and outputs at 48 kHz.
The captured output queue was zero to two 5 ms blocks with no dropped blocks.

The clean simulation trace records one calculation per present. One 120-update
window took 3.327 seconds instead of 2 seconds; others approached 2.12 seconds.
This confirms that visual simulation can fall behind real-time audio. **Audio
sync is not fixed.** No queue flushing, pitch adjustment or unvalidated time
stretch has been added. The remaining repair needs a deliberate simulation/audio
clock solution alongside the frame-time work.

### Loading and ink-related FPS dips

One manual session created about 1,359 Vulkan pipelines, spending about 82
seconds compiling across the session. A 351-pipeline window took 26.7 seconds.
Offline asset SPIR-V compilation does not pre-create every draw-specific Vulkan
pipeline. The driver cache loaded successfully. Two earlier sessions did not
write their shutdown CSV or update the cache file. The later normal closure of
the `200654` capture did produce a 224,806-byte CSV and updated the cache at
20:10:11 Bangkok time; its log ends with `window closed`.

Other slow windows created no pipelines, with approximately 8–14 ms of CPU
replay plus several milliseconds of GPU work. Shooting/hiding dips and stable
60 FPS remain unresolved. A previous test overlapped CPU-heavy regression
compilation; later manual comparisons run after builds and tests finish.

The manual capture launcher now avoids an extra console window, whose closure
can bypass the native game window's cache-save path. The latest normal closure
verifies that save path completed. The next launch still needs a loading-time
comparison.

### Earlier rendering reports

The user previously confirmed the white-brightness and eyebrow issues improved,
and confirmed the bare-ground invisible-ink slowdown disappeared after the real
occlusion-query repair. Black story enemies/rings, post-stage invisible purple
ink and friendly-ink model concealment do not yet have a clear final verification
in the retained reports.

## Local evidence and rollback

- Build manifests: `/home/hexa/sp2port/obj-win-*-performance-20261124/manifest.json`.
- Manual logs and shutdown CSVs: `C:\sp2stage\sp2win\diagnostics`.
- Full suite result: `C:\sp2stage\verify-renderer-news-performance-20261124.log`.
- Previous default executables: timestamped `sp2-controller-gameplay-before-*.exe`
  files beside the game. Restore one only while the game is closed.
- Source helpers support `--check` and `--restore`; rebuild affected units after
  restoring source.

Published code and notes include commits `4f1d1d7` (renderer/news) and `ced711b`
(first Pro pitch attempt and audio diagnosis). The complete tilt correction is
the current follow-up; the earlier pitch attempt must not be described as verified.
