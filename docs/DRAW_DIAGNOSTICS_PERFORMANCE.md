# Disabled draw diagnostics and Windows FPS observations

The normal renderer still performed an environment scan and formatted a trace
summary on every draw with draw tracing disabled. A native Windows sample pinned
151 CRT environment-query hits to `NX_TRACE_DRAWS_DEBUG`, versus seven to
`NX_CLEAR_AREA`, over its short sampling window.

The draw hook now returns after its independent huge-draw, cube, studio and frame
signature checks when draw tracing and trace debugging are disabled. Summary
formatting occurs only for selected traced draws. Debug enablement and the
clear-area handle are read once. Enabled trace filters, trace budgets and the
independent diagnostic hooks retain their behavior. Rendering and input are unchanged.

The source-extracted sanitizer regression checks disabled, enabled, filtered and
budget-limited traces and the independent hooks. An unsanitized CPU microbenchmark
of one million hook calls measured 174.6 ms before and 4.4 ms after, with per-draw
environment queries and summary formatting removed. These are CPU-hook timings,
not a whole-game FPS multiplier.

## Windows run observations on November 23, 2026

The laptop initially reported discharging, with the RTX 3060 Laptop GPU at 450 MHz
core and 810 MHz memory. Its news-scene samples were approximately 10 FPS. After
the user connected the charger, memory speed rose to 6001 MHz and that same
running process measured approximately 24–29 FPS. This comparison predates the
new diagnostics optimization and identifies the power constraint separately.

The optimized executable was then started visibly without RenderDoc, frame dumps,
automatic inputs or renderer diagnostic overrides. Sampled windows varied with
the scene: roughly 33–40 FPS in one portion and 48–56 FPS later, with temporary
lower readings during scene changes. This is not a controlled before/after scene
benchmark or a guarantee of 60 FPS. The normal launchers select this build; older
executables remain available locally as rollbacks.

## Apply and check

Apply after the [plaza/news rendering patch](PLAZA_NEWS_RENDERING.md):

```sh
python3 tools/patches/patch-draw-diagnostics-fastpath.py --root /path/to/sp2port --check
python3 tools/patches/patch-draw-diagnostics-fastpath.py --root /path/to/sp2port
python3 tools/verify-tutorial-runtime.py --root /path/to/sp2port
```

Rebuild `nvn_draw.cpp` and `nvn_draw_trace.cpp` and relink. `--restore` reverses
only this optimization. The full runtime sanitizer suite now has 15 groups.
