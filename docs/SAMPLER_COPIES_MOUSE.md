# Copied samplers, mouse deltas, and diagnostic overhead

This follow-up targets the external `sp2port` runtime. It does **not** claim to
finish tutorial input, restore missing green paint, or fix every rendering
artifact. It contains two source-file changes and no generated game code.

## Sampler values must survive copies

The game's sampler cache copies a 0x60-byte opaque sampler into a different
address before registering it with a sampler pool. Tracking initialized samplers
only by their original address dropped these registrations. A missing slot then
fell back to the runtime's default point-filtered sampler, even when the builder
requested linear or trilinear filtering.

Initialized opaque samplers now carry a canonical, pointer-free value payload.
Registration, getters, and comparison read that payload, including after a copy
overwrites an address that previously held another initialized sampler. Pool
slots retain their own values and existing replay history. Reinitializing or
finalizing the original does not change a copied sampler or a registered slot.
Requested point filtering remains point filtering; this is not a global linear
filter override.

In the earlier tutorial capture, the first tonemap pass sampled its smooth 8³
color LUT with point filtering, producing coarse color steps. A fresh capture
visually confirmed to contain the tutorial now passes the actual combined
sampler check: linear minification and magnification reach the color LUT at
tonemap event 5622. The scene's HDR maximum was `[5.5, 4.5, 3.9375]`.
This verifies the filtering contract, **not** missing paint, aiming completion,
or every tutorial color. A separate filtering control reduced posterization
but left floor streaks and dark patches. The fresh run also remained at the
aiming prompt despite receiving the scripted vertical-stick inputs.

Current-build ink tracing also confirms that the full-resolution and coarse
paint atlases contain nonzero data in layer 4, and the floor binds both with
linear filtering. At the three ground pixels inspected, the material samples
zero paint and produces gray before tonemapping. A replay-only diagnostic of
all 12 paint-sampling material shaders did not establish visible floor coverage;
the few green candidate pixels were supplied by separate draw passes. This
narrows the investigation, but does not establish whether paint coordinates,
visibility, or another pass is responsible. No production paint data or shader
colors were changed by these diagnostics.

## Mouse motion must be incremental

The Windows mouse handler accumulated displacement from an old cursor position
without updating that position after ordinary messages. Successive moves and
even duplicate stationary messages therefore added too much right-stick input.
It now updates the last position after consuming each delta, before the existing
recenter logic. Capture activation, sensitivity, and the right-stick mapping are
otherwise unchanged. This does not add mouse-to-gyro support or prove an
automated aiming sequence completes the tutorial.

## Keep optional sampler tracing bounded

With `NX_NVN_STATES=1`, printing every sampler initialization caused synchronous
log writes on a hot path. A recorded line took 289 ms to write. Matching-route
tests ran around 2–4 FPS with the verbose trace and typically 20–33 FPS in heavier
parts with it disabled; lighter parts reached roughly 50–58 FPS. These are local
observations, not a frame-rate guarantee.

The trace now records its first 64 states, reports the budget, then samples once
per 4,096 calls. Normal tracing-off behavior remains quiet. Replay, fence, and
presentation costs still limit performance in heavier parts.

## Apply and verify

```sh
python3 tools/patches/patch-sampler-copies-mouse.py --root ~/sp2port --check
python3 tools/patches/patch-sampler-copies-mouse.py --root ~/sp2port
```

Rebuild `nvn_sampler_objects.cpp` and `platform_win.cpp`, then relink. Unlike the
earlier tutorial patch, this patch does not change a header layout. The helper
preflights the whole change and supports idempotent `--check` and `--restore`.
The older PlayerMake and tutorial-lighting patches remain separate.

The maintained runtime checks now include nine source-extracted sanitizer tests:

```sh
python3 tools/verify-tutorial-runtime.py --root ~/sp2port
```

Sampler tests cover 0x60-byte bounds, deterministic values, copied registrations,
getters, comparison, overwrite/reinitialization/finalization, replay history,
point-filter preservation, and quiet/bounded tracing. Mouse tests cover relative
moves, duplicate messages, recentering, inactive capture, and the first message.
Both regressions fail against their earlier implementations. Patch-package
checks also verify exact application, read-only checks, idempotence, restoration,
and unsupported-source rejection without partial writes.

For a RenderDoc capture containing the scene and its tonemap pass:

```sh
python tools/verify-tutorial-capture.py capture.rdc --require-linear-lut
```

The optional flag checks the actual combined sampler, not just shader or texture
metadata. It does not identify the game scene or score image quality: inspect the
saved frame and verify paint, geometry, input, and remaining artifacts separately.
