# Upload-cache invalidation search

The first-stage follow-up preserves the confirmed vertical gyro repair and the
worker-core crash repair. The user reported approximately 30–40 FPS, ranging
from 15 to 50 FPS, in the preceding combined build. Stable 60 FPS remains open.

The renderer reuses copied vertex and uniform data within each submit. Inline
uniform writes must invalidate every overlapping copy. The previous invalidation
walk scanned backwards through cached addresses up to 64 MB away, including
unrelated small blocks. Process sampling identified upload reuse and invalidation
among the renderer's CPU work.

`tools/patches/patch-upload-invalidation-range.py` tracks the largest copied
range in the current submit. A cached entry farther before an update than that
size cannot overlap it. The invalidator now uses tree bounds for that candidate
range, then checks exact byte overlap. The largest size only grows until submit
reset, so replacing a large copy with a smaller one cannot hide an overlap.
Front-cache invalidation and upload alignment/padding behavior are preserved.

The regression exercises the production cache with real copied bytes and inline
changes, overlapping ranges, ranges merely touching the boundary, empty writes,
shorter replacements, padding and front-cache collisions. Its 4,096-update
fixture examines 4,096 candidate ranges, while preserving the expected copied
contents. Irregular update positions are compared with a complete reference
scan. This measures search work and does not establish an FPS gain.

## Apply and restore

```bash
python3 tools/patches/patch-upload-invalidation-range.py --root "$HOME/sp2port"
python3 tools/verify-tutorial-runtime.py --root "$HOME/sp2port"
```

Rebuild `runtime/src/nvn/nvn_dedup.cpp` and relink. The helper supports `--check`
and `--restore`. All 39 runtime regression groups passed with exit code 0. Some
shader groups use structural assertions because `spirv-val` is unavailable.

The installed `C:\sp2stage\sp2win\sp2-controller-gameplay.exe` includes this
optimization, [gyro continuity](GYRO_STREAM_CONTINUITY.md), and the
[worker core and image lookup repairs](STAGE_PERFORMANCE.md). The same local
build is `sp2-stage-upload.exe`, SHA-256
`8035cec630c8a4c02e6ab3cf7356bcfe2ff15a7f28c5041463fe17523a3953fe`.
The previous build is retained in a timestamped
`sp2-controller-gameplay-before-upload-search-*.exe` backup.

This build was launched with injection off and original plaza/news timing.
When render statistics are enabled, its log includes upload invalidation counts
and examined cached ranges. First-stage FPS and repeated ink-hide dips still
need comparison in this build. Original plaza/news timing targets 30 FPS.
