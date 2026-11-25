# First-use shader transformation overhead

The user confirmed that synchronous command chunks made plaza, Tentakeel and
stage play much steadier. Remaining dips mostly occur on first-time areas or
effects. The verified chunking mode remains enabled in the local launcher.

The shader-transform candidate removes two sources of CPU allocator overhead:

- Integer interface, uniform-index clamping and unwritten-input rewrite passes
  reuse instruction scratch capacity rather than allocating a vector for every
  instruction. The rewrite order and generated instruction words are unchanged.
- Uniform-index clamping records result types only for IDs that occur as access
  chain indices. It previously allocated a tree node for nearly every function
  result, although it queried only the index IDs. The existing first-definition
  behavior, binding mask calculation and conservative rejection rules remain.

This affects first-use processing even for shaders the runtime has not seen
before. It does not depend on a learned disk cache and does not change shader
semantics, simulation timing, resolution or synchronization. It does not remove
driver pipeline compilation; an unseen pipeline can still stall its first draw.

## Evidence and limits

The regression compiles both original and optimized production passes. It checks
return values, complete output words and binding masks for all four affected
operations, with authored small/large/malformed instruction fixtures and an
optional local shader corpus. Allocation counts include the original map work
and scratch vectors. No game binaries or shaders are included in the repository.

On November 25, 2026, 216 local SPIR-V modules (24 largest and 192 distributed
samples, deduplicated) produced identical results across 932 transform cases.
The sanitizer corpus run reduced heap allocations from 4,883,976 to 106,691;
measured transform time was 4,562.7 to 3,266.6 ms. These timings include sanitizer
overhead and are not gameplay measurements.

The optimized Windows C++ benchmark used the same sample and alternated original
and optimized execution order to reduce warm-cache bias. It reduced allocations
from 4,883,581 to 106,296 and transformation time from 456.6 to 243.5 ms. The
platform-specific standard-library allocation totals differ slightly. This is
CPU transformation time, not an FPS or loading-time guarantee. The full 14,000+
shader inventory and every possible runtime variant were not exhaustively tested.

Run the production-source test with the private runtime root:

```bash
python3 tools/tests/tutorial/test_shader_first_use.py "$HOME/sp2port"
python3 tools/tests/tutorial/test_shader_first_use.py "$HOME/sp2port" --corpus /path/to/private/spirv
```

`--emit-cpp /path/to/benchmark.cpp` emits a standalone benchmark source instead of
running it. Compile at O2 and pass a text file containing one local shader path
per line. The benchmark checks exact outputs while collecting allocation/time
measurements. Existing integer shader tests remain part of full verification;
where `spirv-val` is unavailable they use structural assertions.

## Apply and rollback

Apply `tools/patches/patch-shader-first-use.py` to the external runtime. Rebuild
only `nvn_spirv_patch.cpp` and relink against the current synchronous-chunk objects.
The helper supports `--check` and `--restore`; its installer tests cover LF/CRLF
byte-exact restoration, idempotence and partial-patch refusal.

The new candidate still requires first-time-area/effect gameplay verification.
Preserve the confirmed synchronous-chunk baseline as a rollback.
