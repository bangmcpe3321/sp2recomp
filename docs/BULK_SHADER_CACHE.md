# Bulk private shader cache - November 24, 2026

The local game shader cache was populated from the extracted game assets in one
batch, instead of waiting for each stage to appear in a manual play session.
This is an offline shader-stage build, not a complete graphics-pipeline cache.

## Verified results

- Scanned 5,390 RomFS files, following Yaz0 compression and SARC members.
- Parsed BNSH, BAHS and embedded effect/model shader containers, plus six raw
  system-font/primitive shader records.
- Found 77,048 stage records, deduplicated to **14,379 unique code blocks**.
- All 216 previously captured runtime code blocks and control prefixes matched
  the corresponding extracted asset records exactly.
- Compiled **7,214 previously uncached stages**: 6,254 fragment, 959 vertex,
  and one geometry stage. Ten needed translator retry; none failed.
- All new stages passed `spirv-val --target-env vulkan1.2` and execution-model
  checks against the declared shader stage before installation.
- Existing cache files were preserved. Final cache: **14,415 SPIR-V files**.
- A final independent audit found no missing cache entry for any of the 14,379
  extracted stages or any of the **199 shader misses** from the affected
  story-mode run.

The deeper execution-model audit also found **15 pre-existing headerless
compute shaders cached incorrectly as vertex shaders**. Their original bytes
and hashes were retained; the corrected translator uses verified container and
control metadata. All 15 were recompiled as compute, validated, and replaced
with matching metadata. The prior files and complete metadata were backed up.
Thus this run translated 7,214 new stages plus 15 validated repairs (7,229 total).

The final audit checks every extracted stage's execution model and resource
metadata, not just file existence: all 14,379 passed, with zero audit errors.
The asset stage types are 4,801 vertex, 9,555 fragment, 15 compute and eight
geometry. The cache contains 14,415 files with corresponding metadata; 36 entries
outside the current extracted asset set were preserved.

Two apparent BAHS parse failures were incidental byte strings inside model
floating-point data: unaligned headers, implausible version and out-of-file size.
The three raw system shader blobs were handled separately. No actual discovered
shader-container parse failure remained after these checks.

## Local rerun and reports

On this machine, the private single-command workflow is:

```powershell
& C:/sp2stage/compile-all-shaders.ps1
```

It depends on the local asset dump, container parser, shader translator and
validator. It is a machine-specific helper, not a self-contained public tool.
Reports are in `C:/sp2stage/sp2win/private/all_asset_shaders/`, including
`summary.json`, `compile_summary.json`, `root_cache_audit.json`, and the translation
results. Game-derived code, shader files and captures are not distributed here.
The existing public [captured-miss workflow](../tools/wsl/wsl-translate-shaders.sh)
remains available for later runtime-only variants.

The standard captured-miss translator was also patched and rebuilt to recognize
headerless compute binaries and all SPH stage types. Apply the generic source
helper with `python3 tools/wsl/wsl-patch-shader-stage-detection.py "$HOME/sp2port"`,
then rebuild the external harness. `tools/wsl/verify_spirv_stage.py` independently
checks the generated execution model. A real-harness regression translated all
15 headerless compute cases plus vertex, fragment and geometry controls: all 18
passed Vulkan 1.2 validation with the expected stage; input bytes were unchanged.

Restart the game after cache changes: missing-shader records are process-cached.
The normal executable and simulation timing were unchanged for the cache retest.

## Rendering and performance limits

The affected run had black enemies/rings, and purple enemy-ink effects on
apparently clean hub ground after leaving a stage. A missing fragment shader is
omitted from the pipeline; a stencil/query draw can then pass samples without
its intended fragment discard test. Missing shader stages therefore can affect
both appearance and ink-detection counts, despite the corrected real GPU query
backend. This is a plausible cause; live confirmation of these symptoms after
cache completion is still required.

A new regression also confirms that an ordinary counter reset removes previous
scene samples, including millions of intervening samples. No normal transition
leak was demonstrated, and no forced reset or coverage override was added.

Compiling SPIR-V stages does not prebuild every Vulkan pipeline: shader pairs,
vertex layouts, attachment formats and other render-state combinations still
create pipelines on first use. Driver pipeline persistence remains enabled.
Stable story-mode 60 FPS and elimination of all stutter are not established by
this shader-cache build.
