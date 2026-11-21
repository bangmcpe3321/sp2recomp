# PlayerMake: descriptor identity and front-face winding

## Measured defects

The black faces, missing eyes, broken clothes and hair were not caused by the
empty fragment shader. Those draws include intentional depth/prepass work;
the real character material shaders execute.

Two independent runtime defects prevented their lighting mask from working:

1. **Copied texture descriptors lost their storage identity.** A copied descriptor
   can still describe surface A after its named `NVNtexture` has been reinitialized
   for surface B. `SetRenderTargets` and texture-pool registration resolved the copy
   to that mutable object, discarding the copy's memory address and dimensions.
   A measured capture consequently read and wrote the same image in blur passes
   that should ping-pong, with a viewport smaller than the sampled image.
2. **A depth attachment automatically inverted front-face winding.** The mask's
   fullscreen producer was back-face culled. Depth attachment presence does not
   determine triangle winding. Removing the depth-dependent inversion lets the
   producer draw while preserving the existing explicit `NX_FLIP_WINDING` override
   and 2D/inert-depth culling exceptions.

Disabling winding inversion alone on the old executable still rendered broken
models. Preserving descriptor identity alone also left them broken. Both changes
were required in the live A/B tests.

## Implementation

- Decode the copy's own storage fields at command recording and pool registration,
  including format, dimensions, mip/layer layout, flags, swizzle and block height.
- Keep immutable metadata alive with its recorded command list. Pool entries that
  came from copies select that immutable snapshot, not the later named object.
- Share GPU images by exact storage identity. Historical command lists retain
  metadata rather than pinning a GPU allocation for every prior resolution.
  Inactive descriptor-cache images retire through the existing fence-aware image
  graveyard. Broad pool-snapshot fallback heuristics remain only for legacy,
  non-copy registrations.
- Use the guest front-face state without an automatic depth-dependent flip.

No shader translation, static texture bytes, global no-cull mode, or white lighting
mask substitution is part of this fix. Temporary feedback tracing was removed.

## Regression check

The executable runtime lives in the separate `sp2port` tree. Apply the exact tested
source change from this repository with:

```sh
python3 tools/patches/patch-playermake-descriptor-winding.py --root /path/to/sp2port --check
python3 tools/patches/patch-playermake-descriptor-winding.py --root /path/to/sp2port
```

`SP2PORT` can supply the root instead; `--restore` reverses this patch. Preflight
rejects unsupported source layouts instead of making partial substitutions. The
patch includes no generated guest code, executable or game assets. Rebuild all
runtime translation units after applying it: `nvn.h` changes structure layout,
and older incremental build scripts do not track header dependencies. Do not
reuse stale runtime object files.

Capture PlayerMake with no scripted A presses: this installation starts on that
screen. Use a RenderDoc launcher matching the installed capture layer, and finish
the live run before opening a replay on the same GPU.

With RenderDoc's Python module available on `PYTHONPATH`:

```text
python tools/verify-playermake-capture.py path/to/playermake_capture.rdc
```

The check discovers the material's `fp_t_tcb_2A` lighting mask without fixed event
or resource IDs. It checks the producer and four filter passes for distinct
attachment/sampler images, matching viewport/texture dimensions, producer winding,
and nonempty red/green lighting coverage. Visually inspect eyes, skin, hair,
clothes, shoes and background as well: this is not a whole-game graphics test.

## Verification on November 21, 2026

- Default-winding build: isolated 145-second capture run, correctly rendered
  sampled frames 300 through 6,300, including a capture at frame 4,800.
- Late capture: 1920x1080 mask, distinct ping-pong images, producer front-CCW,
  and 251,897 mask pixels with both red and green above 200/255.
- Separate 75-second run without RenderDoc or `NX_ATLAS_REFRESH`: sampled frames
  300 through 3,000 remained correctly rendered.
- Those two runs logged no image-allocation failure, device-lost message,
  upload-ring overflow or upload-buffer-full message.
- The maintained replay check passes the late capture and rejects the earlier
  descriptor-only capture with `Producer winding flipped at event 809`.

Local evidence is in `C:\sp2stage\playermake_matched_20261121_185048` and
`C:\sp2stage\playermake_live_launch_defaults_20261121_185542`.

**Unresolved stress observation:** an earlier run became dark at frame 4,800
while a separate RenderDoc replay ran concurrently on the same GPU. The isolated
rerun did not reproduce it. The cause is not established; do not treat these
results as proof of stability under concurrent replay/load, every resolution
transition, or scenes beyond PlayerMake.
