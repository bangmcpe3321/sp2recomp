# Renderer cache and news ending follow-up

The November 24 manual capture still contains loading pauses and dips when
shooting or hiding in ink. Its 1,359 first-use graphics pipelines took about
82 seconds in total across the session, including a 351-pipeline window taking
26.7 seconds. Compiling the asset shaders to SPIR-V does not create these
draw-specific Vulkan pipelines. A compatible driver cache was loaded, but the
session did not produce its shutdown CSV or update the cache file. Cache loading
alone therefore does not demonstrate that the latest pipeline results persisted.

Other slow windows created no pipelines. Their CPU replay took approximately
8–12 ms, followed by several milliseconds of GPU work. The repairs below address
CPU work and duplicate pipeline variants. Stable 60 FPS and the remaining
first-use compilation pauses are still open.

## Cache repairs

`tools/patches/patch-pipeline-effective-state.py` normalizes pipeline cache keys
to the state consumed by the current encoder. It discards unused vertex
attributes and streams, inactive attachment state, disabled blend factors and
unused diagnostic fields. Actual draw state, active formats, shader pointers,
depth and polygon behavior remain intact. The cache still has its 2,048-entry
bound and existing deferred retirement.

The production-source sanitizer regression compares the actual vertex input
encoder and integer SPIR-V transform. It maps 4,096 equivalent stale-binding
variants to one key while retaining distinct keys for consumed state. A further
hot-path repair removes shader-name string copies when pipeline-diff diagnostics
are off: 10,000 warmed cache hits allocate no diagnostic strings, compared with
20,000 allocations in the previous implementation.

`tools/patches/patch-image-held-front-cache.py` adds a bounded front cache for
descriptor-owned images. Entries point into stable map nodes and are cleared
before each frame's retirement pass. It preserves existing image ownership,
aliasing and expiration rules. The production-source regression returns identical
image identities and retirement results across 810,180 requests while reducing
map searches from 809,280 to 45,399. These are CPU regression measurements, not
an in-game FPS benchmark.

## Renderer compiler settings

The local comparison build compiles the 48 NVN renderer units at `-O2`, without
fast-math. Other objects retain their previous compiler settings. Before adding
the independent news correction, all 471 non-renderer linked objects were
byte-identical to the preceding build, including gameplay, input and clocks.

`tools/wsl/build-renderer-candidate.py` can reproduce an isolated renderer build
from an exact preceding object manifest or a baseline object directory. It
checks baseline object hashes and detects source/header changes during the
build. It records compiler commands, object hashes and the executable hash in
the new output directory. It does not replace the baseline objects or install
the candidate automatically.

```bash
python3 tools/patches/patch-pipeline-effective-state.py --root "$HOME/sp2port"
python3 tools/patches/patch-image-held-front-cache.py --root "$HOME/sp2port"
python3 tools/wsl/build-renderer-candidate.py --root "$HOME/sp2port" \
  --manifest /path/to/preceding/manifest.json --out /path/to/new-output --jobs 2
```

Both source helpers support `--check` and `--restore`. Restore requires rebuilding
the affected renderer units and relinking.

## Premature news ending

An older BGM fallback returned "finished" as soon as the news ending was armed.
Its separate callback counter could also advance more than once per displayed
frame. The original reservation explicitly divides the requested count by
`60.0`, independently of the broadcast's frame interval.

`tools/patches/patch-news-ending-reservation.py` uses monotonic elapsed time for
that reservation and keeps the ending predicate false until it elapses. The
usual 149-count reservation lasts `149/60` seconds. The injected handover now
uses a copied CPU context, preserving all caller registers and flags. Real BGM
event priority is retained; this repair does not manufacture an audio event or
change dialogue scheduling.

The sanitizer regression executes the actual generated ending predicate and
signature-pose procedure. It verifies the minimum delay, repeated polls, idle
idols, one handover, complete register preservation and native-event priority.
The three-file installer passes exact restoration and failed-preflight checks.

```bash
python3 tools/patches/patch-news-ending-reservation.py --root "$HOME/sp2port"
python3 tools/tests/tutorial/test_news_ending_reservation.py "$HOME/sp2port"
```

Rebuild `hle_audio.cpp`, `gen/main/code_213.cpp` and `gen/main/code_027.cpp` at
their existing settings. The helper supports `--check` and `--restore`.

## Installed comparison build

The local `C:\sp2stage\sp2win\sp2-renderer-news-performance.exe` combines these
repairs and is also installed as the launcher's default
`sp2-controller-gameplay.exe`. SHA-256:
`b49c39561dacfd1d6062b1dd19cffb15b73803e6c8678ad76464750c767007df`.
The preceding executable remains in a timestamped
`sp2-controller-gameplay-before-renderer-news-*.exe` backup.

The later [Pro pitch and audio timing follow-up](PRO_PITCH_AUDIO_TIMING.md)
records the currently installed executable and the remaining intro-sync issue.

The build launched with original plaza/news timing, dynamic resolution enabled,
real occlusion queries retained, and input injection off. News duration and
same-location ink-shooting/hiding FPS still need manual comparison. Normal window
closure should write the buffered frame CSV and save the pipeline cache; the
next capture will also check whether that shutdown path completes.
