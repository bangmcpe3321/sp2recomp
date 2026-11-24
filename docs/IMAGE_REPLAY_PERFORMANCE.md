# Image replay work and warm pipeline cache

The user confirmed that loading improved after the same build was closed normally
and restarted, while shooting and hiding in ink still caused FPS dips. In the
initial paired snapshot, 658 matching pipeline recipes/shader hashes all hit the
saved driver cache on restart. Their combined host creation time fell from
40,495 ms to 1,181 ms. New content still requires first-use compilation, and
resource loading also accounts for pauses independently of pipeline creation.

The next renderer follow-up removes two sources of repeated image-cache work:

- `tools/patches/patch-sampled-image-reuse.py` returns the resolved image from
  the existing readiness check and uses that same pointer for pass-write and
  pending-clear checks. Previously each texture binding resolved the image again
  immediately after checking it. The original one-argument readiness API remains
  available. Dirty glyph/linear content is still detected before the pass-break
  decision, and missing images retain their existing behavior.
- `tools/patches/patch-image-retirement-groups.py` walks contiguous storage-address
  groups in the existing held-image map. It computes the latest write before
  expiring each group, preserving the retirement rule without constructing a
  temporary address map every frame. Front-cache pointers are cleared before
  retiring nodes as before.

The actual-source readiness/gather regression checks that each binding resolves
one image, including dirty and queued-write cases, pending clears, previously
written pass targets, missing images and dummy textures. The retirement regression
compares survivor identities and retirement order against the original algorithm
for 20,480 images across 4,096 storage addresses, including frame wrap, unknown
write ordering and `UINT64_MAX`. The optimized traversal makes no temporary map
allocations. These checks establish equivalence and removed work; they do not
measure an in-game FPS gain.

```bash
python3 tools/patches/patch-sampled-image-reuse.py --root "$HOME/sp2port"
python3 tools/patches/patch-image-retirement-groups.py --root "$HOME/sp2port"
python3 tools/tests/tutorial/test_cache_texture_readiness.py "$HOME/sp2port/runtime/src/nvn/nvn_pipeline.cpp"
python3 tools/tests/tutorial/test_image_retirement_groups.py "$HOME/sp2port/runtime/src/nvn/nvn_image.cpp"
```

Rebuild `nvn_pipeline.cpp`, `nvn_sets.cpp` and `nvn_image.cpp` at the candidate's
existing settings, then relink. Both helpers support `--check` and `--restore`.
The readiness helper preflights all three source files before writing. Restore
requires rebuilding the same affected units. These changes retain the inventory
NFP repair, real ink occlusion queries, game timing and controller code.

Same-location manual ink-shooting/hiding frame-time comparisons remain necessary;
stable 60 FPS is not established.
