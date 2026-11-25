# Synchronous upload staging

A focused profile of the slow story/outpost area sampled GPU allocation creation
and destruction on the render thread. The Windows synchronous path's staging
policy consulted the asynchronous ring size, which is zero when asynchronous
submission is off. This forced normal texture uploads of at least 1 MB to create
standalone Vulkan staging buffers despite an available 256 MB upload buffer.

The repair adds capacity/usage accessors for the allocator actually in use.
Ordinary uploads fit its existing quarter-buffer/eighth-buffer policy; large
uploads and scene-loading bursts retain standalone staging. The policy handles
unsigned overflow conservatively. Fences, asynchronous allocation, timing,
resolution, upload contents and rendering are unchanged.

Apply tools/patches/patch-sync-upload-staging.py to the external runtime, then
rebuild nvn_vk.cpp and nvn_upload.cpp and relink. The helper supports --check and
--restore and preflights all three affected source files before writing.

The production-source sanitizer regression covers synchronous and asynchronous
capacity accounting, exact thresholds, overflow, forced staging, retained upload
bytes, alignment and submit reset. Installer checks cover LF, CRLF and mixed
files, exact restoration, partial/duplicate patches and failed preflight.
Run tools/tests/tutorial/test_sync_upload_staging.py with the runtime root.

The candidate still needs a same-location manual FPS comparison. This repair
removes unnecessary allocations; stable 60 FPS is not established.
