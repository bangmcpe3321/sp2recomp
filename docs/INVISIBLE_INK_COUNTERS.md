# False enemy-ink detection - November 23, 2026

The user confirmed that the corrected Windows build removes the tutorial's
slowdown/sticking on bare ground. The defect was in GPU query results: the
runtime returned an increasing report serial as a samples-passed count.
That false coverage reached the player's enemy-ink movement state.

Squid concealment in friendly ink is **not yet manually verified**. This fix
does not establish that every visible paint or model artifact is resolved.

## Evidence from the affected frame

The user captured `tutorial-ink_frame2281.rdc` while green hit effects surrounded
the Inkling's feet and the underlying ground appeared bare. Offline replay of
the actual floor, before character rendering, established:

- Thumbnail pixel (800,630) maps to HDR pixel (855,673), floor event 1307.
- The full 1600x1600 RG8 atlas is sampled at UV
  (0.306566894,0.867604852), layer 4: RG = (0,0).
- Both offset samples and the coarse 200x200 atlas also return zero coverage.
- Nearby floor pixels (850,650) and (800,660) give the same result.
- Paint exists elsewhere in both atlas channels. The observed zero color masks
  belong to intentional stencil/query passes; they were not overridden.

The complete guest consumer chain explains why fake counts matter:

1. `PaintDrawJob::drawTextureCamouflage_` brackets a stencil draw with
   `ResetCounter(1)` and `ReportCounter(1)`.
2. `QueryInfoBuffer::popResult` waits for the counter's timestamp at byte 8,
   then reads the actual samples count from byte 0.
3. `CamouflageChecker::calcResult` normalizes total/friend/enemy sample counts.
4. `PlayerStepPaint` smooths those coverage values and selects the enemy state
   when enemy coverage exceeds its threshold and the friend margin.
5. `Player::isStepPaint_OnEnemy` reads that state for ink-related behavior.

Returning `++reports` for all three counts therefore fabricated coverage,
regardless of which fragments survived the GPU's tests.

## Runtime change

The runtime now records `nvnCommandBufferResetCounter`. Opcode 39 is appended;
existing opcodes and the 128-byte command layout are unchanged.

Samples-passed reports use precise Vulkan occlusion queries around render-pass
segments. Reset/report boundaries close and reopen rendering with attachments
retained. Counts accumulate across passes and repeated reports until reset;
queries are not added separately to every draw. Existing zero-draw diagnostics
avoid nesting another occlusion query inside these queries.

Results become guest-visible only after the corresponding GPU fence completes.
A valid zero count remains zero. Its completion timestamp becomes nonzero so a
freshly zeroed result buffer can be consumed. This readiness rule also applies
when GPU timestamp queries are disabled or fail: a completed real sample count
is paired with the host completion time. Unsupported precision, failed sample
queries, or exhausted query capacity do not substitute invented coverage.

Timestamp reports of types 0/16 have a separate implementation using Vulkan
queries, timestamp-period conversion and wrap handling. These are **opt-in**:
`NX_GPU_TIMESTAMPS=1`. The default retains the earlier timing behavior while
keeping real samples-passed counts enabled. An explicit `NX_GPU_TIMESTAMPS`
value takes precedence over the legacy `NX_GPU_COUNTERS` alias.

GPU timestamp differences are measured on the GPU. Their initial alignment to
the host clock is approximate, based on the latest completed marker at first
fence retirement; it is not a calibrated CPU/GPU clock extension. Overlapping
counter/compute-writeback ranges remain unsupported and produce a bounded
warning rather than publishing an ambiguously ordered result.

## Validation and remaining performance work

The final Windows LLVM-MinGW build succeeds. All **26 CPU regression groups**
pass. New actual-source tests exercise:

- reset/report command recording and unchanged command ABI;
- legal query placement, ten draws sharing a pass query, multi-pass sums,
  repeated reports, reset and cross-command-buffer accumulation;
- fence-only publication and initially zero result buffers;
- genuine zero coverage with a nonzero readiness timestamp;
- failed sample/timestamp queries, allocation failures and bounded capacity;
- timestamp stages, periods, clock wrapping, opt-in defaults and flag precedence;
- counter/SSBO alias protection and whole-submit waits for asynchronous results.

The user reported that the earlier combined compiler-optimization/GPU-timing
candidate made the tutorial feel too fast around 60 FPS. It is not the normal
build. The confirmed ink test uses the earlier compiler settings and
`NX_GPU_TIMESTAMPS=0`. Opt-in private simulation diagnostics observed 120
framework calculations for 120 presents, with framework rate 1; this does not
by itself settle every report about animation or movement speed.

A separate runtime-only `-O2` candidate now retains the same legacy timing and
real ink queries, for a later comparison. Stable story-mode 60 FPS, remaining
stutters and squid concealment are still open checks. The capture run's FPS is
not a normal-play benchmark because RenderDoc capture adds work.

## Apply and restore

Apply after the published frame-stutter/overlay, mouse-gyro and motion-stream
follow-ups:

```sh
python3 tools/patches/patch-gpu-counter-queries.py --root "$HOME/sp2port"
python3 tools/verify-tutorial-runtime.py --root "$HOME/sp2port"
```

The helper supports `--check` and `--restore`. Rebuild the changed runtime
sources. The local incremental Windows builder does not track header changes;
a later edit to `nvn_counter_timestamps.h` requires rebuilding
`nvn_draw_state.cpp`. Patch application, repeated application and exact restore
were checked in an isolated fixture.

Game captures, shaders, private generated code and executables are not included
in this repository. The manual run used no scripted input or tutorial skips.
