# Windows image allocation cache

Changing render-target dimensions repeatedly creates and retires Vulkan images.
A focused story/outpost profile sampled driver allocation creation and destruction
on the render thread. The latest closed run created more than 47,000 images.

`tools/patches/patch-image-memory-cache.py` adds a Windows-only cache for the
**memory allocations** of fully retired, destroyed images. Each image and view
is still newly created with its original format, dimensions, usage and undefined
initial layout. Image contents and texture state are never reused by this cache.
The existing shared-holder and completed-submit gates run before memory returns
to the cache. Native memory is matched by exact allocation size and memory type.

The cache holds at most 128 allocations and 128 MiB. FIFO eviction releases older
idle memory. Allocation failure releases idle memory and retries once; device
loss is propagated. Specialized allocations with `pNext` bypass the cache.
Non-Windows behavior is unchanged. Set `NX_IMAGE_MEMORY_CACHE=0` before startup
for a comparison with direct allocations. Cached idle bytes are additional to
the existing live-image byte counter and remain bounded by 128 MiB.

## Evidence

On November 25, 2026, the standalone Vulkan benchmark used the laptop's NVIDIA
GeForce RTX 3060. Four alternating rounds created, bound and destroyed 1,200
RGBA8 render targets, varying dimensions around 960x540:

| Mode | Driver allocations per round | Total time |
| --- | ---: | ---: |
| Direct | 1,200 | 553.1–568.8 ms |
| Cached | 7 | 2.7–3.8 ms |

The cached rounds retained about 17.2 MiB and included final cache release in
the reported time. This isolates allocation overhead; it does **not** measure
story-stage FPS, rendered GPU work or shader compilation. Stable 60 FPS remains
unverified until the same gameplay area is compared.

`tools/tests/windows/bench-image-memory.cpp` reproduces this benchmark. Compile
with Vulkan headers and `tools/runtime` on the include path; it dynamically loads
the installed Vulkan driver and needs no game assets.

The sanitizer regression uses the production cache. It checks active-allocation
exclusion, exact size/type matching, simultaneous ownership, byte/count limits,
FIFO eviction, oversized requests, allocation pressure, device loss, specialized
allocation bypass and 8,000 changing-shape allocation requests. Installer tests
cover LF/CRLF/mixed files, exact restoration, idempotence and partial-patch failure.
Existing image retirement tests cover shared holders and submit completion.

## Apply and restore

```bash
python3 tools/patches/patch-image-memory-cache.py --root "$HOME/sp2port" --check
python3 tools/patches/patch-image-memory-cache.py --root "$HOME/sp2port"
python3 tools/tests/tutorial/test_image_memory_cache.py "$HOME/sp2port"
```

Rebuild `nvn_image.cpp` and `nvn_frames.cpp`, then relink against the current
runtime objects. The helper copies the original cache header into the runtime.
Use `--restore` and rebuild those same units to remove the change. Runtime
source, executable, shader cache and game assets are not included here.
