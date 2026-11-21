# Tutorial lighting and six-axis ABI fixes

This patch targets the external `sp2port` runtime, after the
[PlayerMake descriptor/winding patch](PLAYERMAKE_FIX.md). It contains no ROM
assets, generated game functions, scene-state skips, shader hashes used as
workarounds, or replacement lighting constants.

## What was failing

The tutorial's neon/posterized scene was not simply an R11G11B10 output-format
problem. A captured fragment produced approximately `2.8e18` and `1.3e25` in its
red and green channels **before** the render-target conversion. These values
came from six corrupt ambient-light coefficient vectors in the guest's uniform
data. Tracing the producer exposed several independent runtime contracts:

1. **CPU visibility of GPU results.** The game reads seven 8×8 RGBA32F lighting
   textures through mapped pool memory. Waiting for the GPU did not copy the
   image contents back to that memory. The runtime now stages supported
   pitch-linear color attachments through its existing fence-ordered writeback
   path. Row padding is preserved.
2. **Block-compressed render targets.** The game's cube encoder renders BC3
   blocks through a 16-byte RGBA32_UINT attachment view. The runtime discarded
   the compressed backing image before considering that view. On capable
   devices, it now creates block-texel-compatible images, checks attachment
   format support and uses block-grid attachment extents. Sampled views retain
   their compressed interpretation.
3. **Integer fragment interfaces.** Translated encoder outputs were float4
   values carrying raw integer block bits. Integer attachments require matching
   integer output interfaces. The shared SPIR-V interface transform now inserts
   bitcasts on fragment stores; it does not numerically convert float values to
   integers. Vertex-input handling keeps its existing behavior.
4. **Instance semantics.** Splitting a draw into 4,096-instance chunks changed
   `BaseInstance`, causing a shader that computes `InstanceIndex - BaseInstance`
   to repeat the first sample range. Such shaders now remain a single draw.
5. **Unit-point coverage.** A proven constant `(0,0,0,1)` position with point
   size 1 landed on pixel `(3,3)` instead of the guest's `(4,4)` in an 8×8 pass.
   Only straight-line shaders whose constant position and size can be proved
   have their viewport center aligned to the intended pixel center. Dynamic
   positions, aliases and unsupported control flow fail closed.
6. **Registered storage identity and ownership.** Direct-object registrations,
   not just copied descriptors, must freeze their storage metadata. In the
   failing run, a cube-copy pass sampled a changing 1×1 image, while registered
   snapshots pinned old dynamic-resolution allocations. Making all registration
   snapshots authoritative corrected the overexposure and allocation growth in
   the controlled test. The image cache retains current GPU-only contents while idle;
   reloadable images and render results superseded by a newer write to the same
   storage can age out through fence-aware retirement.
7. **Motion state ABI.** The 0x60-byte six-axis state had its `delta_time` and
   `sampling_number` fields reversed. The game saw a constant sample number and
   stopped processing motion. The patch also supplies newest-first per-sensor
   history, returns the written count and bounds-checks requests before touching
   guest memory. It does not implement a new physical gyro or mouse-to-gyro map.

## Apply or restore

Run in Linux/WSL, substituting the external runtime's location:

```sh
python3 tools/patches/patch-playermake-descriptor-winding.py --root ~/sp2port
python3 tools/patches/patch-tutorial-lighting-sixaxis.py --root ~/sp2port --check
python3 tools/patches/patch-tutorial-lighting-sixaxis.py --root ~/sp2port
```

**Rebuild every runtime translation unit**, not just timestamp-changed `.cpp`
files: `GpuImage` gains a field, and older build scripts do not track header
dependencies. Both helpers preflight the complete patch and are idempotent.
Existing `NX_SIXAXIS_POSE` diagnostics are not part of this patch.

To remove only this patch, leaving the PlayerMake patch in place:

```sh
python3 tools/patches/patch-tutorial-lighting-sixaxis.py --root ~/sp2port --restore
```

## Regression checks

The CPU checks compile helpers extracted from the **actual patched source** with
AddressSanitizer and UndefinedBehaviorSanitizer. They need `g++` with C++20, but
no GPU or game assets. The point test authors a small SPIR-V fixture and can
additionally check an existing local shader cache. If `spirv-val` is available
on `PATH` or through `SPIRV_VAL`, integer-interface variants are also validated.

```sh
python3 tools/verify-tutorial-runtime.py --root ~/sp2port
```

For a stationary tutorial RenderDoc capture, with RenderDoc's Python module on
`PYTHONPATH`:

```sh
python tools/verify-tutorial-capture.py tutorial_capture.rdc --save-frame tutorial.png
```

This is a narrow HDR regression check, not an image-quality score. It selects
the large R11G11B10 scene target with the most draws, rejects nonfinite/black or
extreme values, and optionally saves the final frame. The old broken capture
fails at `[65024, 65024, 34]`. Visual review is still required, including an
early PlayerMake frame to catch overexposure regressions.

### Measured Windows checks

- The final stationary tutorial capture's scene target measured RGB maxima
  `[9, 7.6875, 6.75]`, rather than the old capture's `[65024, 65024, 34]`.
  The README image comes from that capture, not generated artwork.
- A separate 225-second PlayerMake-to-tutorial run logged no allocation,
  device-loss or upload-ring failures. Its image-memory counter peaked at
  2,354 MB and ended at 2,205 MB; these are observations for that run, not a
  whole-game memory bound. The early PlayerMake frame retained colored hair,
  visible irises and textured clothes.
- Seven actual-source sanitizer tests passed, as did SPIR-V validation of the
  integer-interface fixtures and a local encoder variant. Patch apply/check/
  restore tests also preserved unrelated existing six-axis pose edits.

## Scope and remaining limitations

- Native compressed block attachment views require device support. The runtime
  probes the image and view-format capabilities; unsupported devices retain the
  previous fallback behavior rather than receiving an untested emulation path.
- CPU image writeback currently covers matching-format, single-level,
  single-layer, single-sample **pitch-linear color** images. General tiled,
  converted-format, array and mipmapped image readback is not implemented here.
- Unknown GPU write ordering is retained conservatively. The cache change is
  not a claim of general overlapping-image/memory alias coherence.
- Remaining banding/speckle and other scene-specific artifacts are not declared
  fixed by an HDR-range pass. The default six-axis source supplies no physical
  tilt input; automatic wobble is a diagnostic, not normal input support or
  proof of completing the tutorial.
- The external test build also contains a pre-existing logged `shot -> warp`
  scene redirect. This runtime patch neither adds nor removes it. Scene
  transitions in that build are not evidence of an unmodified tutorial clear.
- Whole-game rendering, software Vulkan drivers and concurrent live-game /
  RenderDoc-replay stress are not verified by these checks.
