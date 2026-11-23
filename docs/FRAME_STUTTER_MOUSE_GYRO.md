# Frame stalls, FPS overlay and mouse gyro - November 23, 2026

The Windows runtime now includes a present-driven FPS overlay and captured mouse
motion through the six-axis API. This update also removes periodic diagnostic
work from normal play and corrects pipeline-key padding and cache persistence.
**Stable 60 FPS and the first-shot/scene-transition stalls are not declared fixed.**

## Mouse controls

Hold right mouse, or press F1 to toggle capture while the game has focus. Move the
mouse to aim through the emulated gyro. Focus loss releases the cursor. The mouse
no longer also sends right-stick input when gyro mode is enabled; physical
controller sticks remain available.

The first manual test confirmed vertical aiming, but reported excessive
sensitivity and reversed horizontal movement. The follow-up reverses the
horizontal mapping and lowers the default from 0.15 to **0.03 degrees per pixel**.
A later manual test found intermittent aiming even while capture remained active.
The motion-stream follow-up below addresses that separately; live recheck remains open.

While captured, press **[** to lower sensitivity by 20%, or **]** to raise it by
25%. These keys do not repeat while held. For a different startup value, set
`NX_MOUSE_GYRO_SENS` to a positive degrees-per-pixel value (maximum 10).
`NX_MOUSE_GYRO=0` restores the previous mouse-to-stick mapping. `NX_MOUSE=0`
disables mouse input. Six-axis must remain enabled; normal play uses
`NX_SIXAXIS=1` and no diagnostic pose/seek/grid/wobble settings.

Mouse motion now publishes a **200 Hz** stream with numbered 5 ms samples and a
16-sample history. Repeated reads return the same samples; both emulated sensors
see the same history. A 60 Hz reader receives the intervening 3/3/4 samples,
rather than consuming one displacement on whichever query arrives first.

The previous independent Euler angles also produced angular rates inconsistent
with the orientation matrix after mixed-axis motion. The stream integrates local
body rotations into one normalized quaternion and derives HID direction, gravity
and body rates coherently. Sead transposes HID direction, and the game's
`PlayerCtrlData200Hz::Data::integrate` integrates local rates with `q * dq`.
Tests independently reconstruct that rotation from the emitted rates, including
mixed-axis movement and full turns. Long-stall catch-up is bounded to 16 samples.

Six-axis velocity is in revolutions/second and integrated angle in revolutions;
see the [upstream motion implementation](https://git.dukantic.fr/dukantic/nxnative_patch/src/commit/76545a58a79058663865f1994a3947f2c799435f/dm/host/hle_hid.c).

## Overlay and timing

The overlay counts successful Vulkan presents, showing FPS, average frame time,
and peak/stalled-frame time. **F3** toggles it; `NX_FPS_OVERLAY=0` disables it.
It stays attached to the focused game window and follows fullscreen changes.
A black loading screen with no new presents therefore displays a stalled frame.

For a timing capture, set `NX_FRAME_CSV` to an output path. Up to 120,000 samples
are kept in memory and written when the window closes normally. There is no
per-frame file write. Columns are:

- `frame`, `interval_ms`: presented frame and wall time since the preceding present.
- `requested_interval`: the game's requested vblank interval (1 = 60 Hz pacing,
  2 = 30 Hz pacing on the runtime's 60 Hz clock).
- `pipeline_count`, `pipeline_ms`: synchronous pipeline creations and their CPU
  duration since the preceding recorded present. This is not a GPU execution timer.

```powershell
python tools/analyze-frame-times.py C:/captures/frames.csv --worst 10
```

The analyzer separates requested intervals, with average FPS, p50/p95/p99,
long-frame counts and pipeline costs. Older three-column captures remain readable.
Close using the window's close button so CSV and the driver cache are saved.
Forced termination cannot save the in-memory capture.

## Changes addressing stutter

- The detailed 5 ms all-thread stall sampler is now opt-in (`NX_STALL_SAMPLER=1`).
  Explicit `NX_CPU_LOG`, `NX_NATIVE_LOG` or `NX_THREAD_DUMP_AT` also enable it;
  `NX_STALL_SAMPLER=0` overrides those requests. The 1 Hz hang watchdog remains.
- Periodic present/thread/render summaries are opt-in (`NX_PRESENT_STATS=1`,
  `NX_RENDER_STATS=1`). Android affinity placement still runs with diagnostics off.
- Pipeline keys initialize the padding in the depth/stencil substructure. The
  reproduced LLVM build previously hashed different stack padding for identical
  render state. Semantic fields remain part of the key.
- The bounded graphics-pipeline cache now evicts the least recently used entry.
  Previously it used creation order: a repeatedly drawn pipeline could still be
  removed. The default limit remains 2048 (`NX_PIPE_CAP`); resource retirement
  keeps the existing in-flight-submit grace period. No unbounded-memory default
  or asynchronous pipeline creation is introduced.
- Driver cache headers must match the current device and driver UUID. Changed
  contents can replace a cache of the same size, and a compatible replacement can
  be smaller than a rejected file. A complete temporary file replaces the old
  cache only after successful writing and closing.
- Normal close serializes the cache under the GPU lock. Periodic serialization
  during gameplay is off by default; `NX_PIPELINE_CACHE_SAVE_INTERVAL` enables an
  optional diagnostic checkpoint interval.

Earlier logs contained approximately 420-441 ms periodic present stalls and
large windows of synchronous pipeline compilation. The user's manual run also
showed multi-second black transitions and a first-shot slowdown. The new CSV
captures compile costs per present to determine how much of those stalls is
compilation. Persistence and padding fixes do not eliminate first-use compilation.

A manual capture on November 23 (`gyro_manual_20261123_172952`, before LRU) recorded:

| Presented frame | Frame interval | Pipeline creation | Pipelines |
| --- | ---: | ---: | ---: |
| 3484 | 15,278.34 ms | 14,240.50 ms | 227 |
| 3496 | 12,968.31 ms | 12,107.83 ms | 177 |
| 3795 | 5,186.74 ms | 4,812.34 ms | 100 |
| 5913 | 1,404.77 ms | 1,310.10 ms | 56 |
| 7390 | 2,479.38 ms | 0.00 ms | 0 |

The run logged at least 1,000 pipeline evictions at its 2048-entry cap. Compilation
accounts for most of several large stalls, but not all of them. The LRU update
is intended to reduce repeated creation of hot entries; live improvement remains
to be measured. Normal close saved a 225,046,734-byte driver cache.

The observed plaza run changed its requested interval from 1 to 2 at frame 3023.
A previous interval-2 capture averaged 28.48 FPS, p95 37.27 ms, p99 67.39 ms, with
a 1099 ms longest frame. An interval-1 diagnostic segment averaged 54.23 FPS,
p95 25.20 ms. These are separate historical runs, **not a before/after benchmark**.
The runtime preserves the requested interval because game step timing is coupled
to it; forcing presentation to 60 alone risks changing game speed.

## Apply and verify

Apply after the existing plaza/news rendering and draw-diagnostic patches:

```sh
python3 tools/patches/patch-frame-stutter-overlay.py --root "$HOME/sp2port"
python3 tools/patches/patch-mouse-gyro.py --root "$HOME/sp2port"
python3 tools/patches/patch-motion-stream-stall-diagnostics.py --root "$HOME/sp2port"
python3 tools/verify-tutorial-runtime.py --root "$HOME/sp2port"
```

Rebuild the changed runtime sources, including both `platform_win.cpp` and
`hle_hid.cpp` when changing the new `mouse_gyro.h`; the local incremental builder
does not track header dependencies. All helpers support `--check` and `--restore`. Restore the motion-stream
follow-up before mouse gyro, then restore the underlying stutter/overlay patch.

Validation: the Windows LLVM-MinGW build succeeds. The 26 CPU regression groups
include frame statistics disabled/enabled paths, cache compatibility and failed
writes, every semantic pipeline-key byte, bounded CSV capture with compile costs,
overlay counters/stalls, bounded LRU hot-entry retention, collisions and deferred
retirement, actual Windows mouse-message processing, gyro samples
consumed at 30/60/120 Hz, repeat reads, both sensors, release/recapture, independent
rate-to-orientation integration, bounded catch-up, finite orientation/gravity and
the actual Windows six-axis ABI bridge. Patch application, idempotence and
byte-for-byte restoration were checked in an isolated fixture.

No game assets, translated shaders, executable or private driver cache is included
in this repository. The samples-passed counter defect and confirmed false enemy-ink slowdown fix
are documented [separately](INVISIBLE_INK_COUNTERS.md). Manual first-shot and
plaza performance verification remains open; the available checks establish specific fixes, not complete playability.
