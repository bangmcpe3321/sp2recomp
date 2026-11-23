# Plaza transition safety - November 23, 2026

After the confirmed false enemy-ink fix, a manual run crashed while entering the
plaza. These changes address the observed font null read and an independent
resource-lifetime hazard. The next manual transition still needs verification.

## Missing font fallback

The exact crashed executable resolves host offset `0x14255c564` to generated
`ScalableFont::GetGlyph`, guest `main+0x1362abc`, reading `[NULL+0x4c]`.
The requested character exists in the font face and measures 40 pixels, but its
SPACE fallback is absent from the separate glyph cache. Initialization already
checks for failed fallback registration; the later read assumed it existed.

The narrow recovery returns a fully initialized transparent glyph, preserving
measured advance and the normal texture descriptors. Cached characters and
cached fallbacks retain their existing behavior. It does not mutate the cache
from the UI reader. Bounded `FSSGLYPH missing fallback` messages retain evidence
for investigating why registration or retention failed. A character with no
cached fallback can remain invisible; this recovery prevents the null crash,
not a claim that all font-cache failures are solved.

Apply with `tools/patches/patch-scalable-font-missing-fallback.py` using the
`SP2PORT` environment variable. The helper supports `--restore`. Rebuild
`gen/main/code_417.cpp`; generated game code itself is not distributed here.

## Submission waits

The same log reported a CPU wait returning after two seconds while submit 3706
was still replaying. Existing invalidate/finalize operations could then reuse
or free memory still being read by rendering. This is a separate proven unsafe
behavior; its causal relationship to the missing glyph is unestablished.

Resource waits now require actual completion. Two-second intervals only emit
progress diagnostics. Submission tickets advance the completed prefix in order,
even when callers finish out of order. An impossible reentrant wait for the
current replay fails explicitly rather than freeing live resources.

`SyncWait` respects its nanosecond timeout and NVN results (already signaled 0,
condition satisfied 1, timeout 2, failed 3). One deadline covers replay, fence
capture and GPU completion. Polling uses a nonblocking GPU-lock attempt and
retires only slots whose Vulkan fences are already signaled. Fence jobs retain
their own state if a guest sync object is finalized or reused.

Apply `tools/patches/patch-submit-wait-safety.py` after the GPU-counter patch;
`--check` and `--restore` are supported. Rebuild the changed runtime sources.

## Validation

The Windows build succeeds. The GetGlyph test executes the actual generated
function and tree lookup, including missing SPACE/default nodes, normal cached
paths, preserved advance, output bounds and registers. The wait regression
checks out-of-order completion, a delayed submission still blocking after
2.1 seconds, finite deadlines, spurious wakeups and reentrant deadline handling.
The wait patch passed idempotent application and byte-for-byte restoration.
All 28 maintained CPU regression groups pass; these tests do not establish live
plaza stability, stable 60 FPS or squid concealment in friendly ink.
