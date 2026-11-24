# Pro Controller pitch and intro audio timing

The user reported reversed vertical aiming specifically with the physical Switch
Pro Controller. The first rate-only correction did not fix the user's aiming.
`tools/patches/patch-pro-gyro-pitch.py` now corrects accelerometer tilt as well as
the pitch sign before quaternion integration. Reflecting the acceleration's Y
axis requires the axial gyro signs (-X,+Y,-Z); initial gravity, integrated angle
and direction now agree. Horizontal aiming and mouse gyro retain their mapping.

The production motion regression checks a negative 90-degree guest pitch against
an independent rotation matrix, irregular packet resampling, calibration, shared
sensor history and gaps. The production HID/arbitration regression also passes
with the corrected sign across capture, focus and reconnect. Native worker
lifecycle tests pass. In-game direction still needs the user's confirmation.

```bash
python3 tools/patches/patch-pro-gyro-pitch.py --root "$HOME/sp2port"
python3 tools/tests/tutorial/test_controller_motion.py "$HOME/sp2port/runtime/src/controller_motion.h"
```

Rebuild `platform_win.cpp`, which includes the changed header. The installer also
supports `--check` and `--restore`; restoration requires rebuilding that unit.

The installed local build is
`C:\sp2stage\sp2win\sp2-pro-tilt-performance.exe`, also copied to the launcher's
default `sp2-controller-gameplay.exe`. SHA-256:
`12ccf4effa7dec1710617d5ea7508ae262e5b12932b762b3a1af08807d2e4456`.
It retains the [renderer and news repairs](RENDERER_CACHE_PERFORMANCE.md).
Its preceding build remains in a timestamped
`sp2-controller-gameplay-before-pro-tilt-*.exe` backup.

## Audio ahead during the tutorial intro

The reported screenshot shows 39.8 FPS. The native renderer advances 240 audio
samples per update, using a host-paced 200 Hz event and 48 kHz output. The
capture's audio queue stayed at zero to two 5 ms blocks, with no dropped blocks;
there is no evidence of growing queue latency. A frame-driven animation falling
behind real-time playback is consistent with the reported audio playing ahead.
The clean follow-up trace confirms one framework calculation per present: one
120-update window took 3.327 seconds instead of the intended 2 seconds. Other
windows approached 2.12 seconds. This remains a timing diagnosis, not a completed
audio-sync repair.

The preceding manual test overlapped CPU-heavy sanitizer compilation, which can
affect its FPS measurements. The pitch comparison was opened after all builds
and checks finished. It enables the existing simulation-rate trace to compare
actual presentation and framework calculation rates. Playback pitch and queue
contents have not been altered to hide the mismatch.

`tools/windows/start-performance-capture.ps1` accepts `-SimulationRateTrace`.
It uses `-NoNewWindow` to avoid a separate console: closing a console can bypass
the native game window's shutdown cache save. Close the game window normally to
save its frame CSV and pipeline cache. Stable frame rate, intro synchronization
and successful shutdown-cache persistence still need a clean manual comparison.
