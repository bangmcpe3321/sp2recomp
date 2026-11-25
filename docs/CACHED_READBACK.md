# Coherent cached upload and read-back memory

The shared Vulkan upload buffer also holds GPU compute output read back to guest
memory. The original default selects the first HOST_VISIBLE | HOST_COHERENT
memory type. On this RTX 3060 that is type 3, without HOST_CACHED. Comparing its
GPU-written words on the CPU is substantially slower than reading cached memory.

The runtime already supports `NX_RING_CACHED=1`. It prefers memory with all three
HOST_VISIBLE, HOST_COHERENT and HOST_CACHED properties while respecting the
buffer's resource compatibility bits. It falls back to the original coherent
choice if none exists. Coherence remains required, so this mode does not require
new flush/invalidate operations or alter fence/write-back ordering.

The local GUI and quiet capture launcher now request this mode. The confirmed
synchronous-chunk settings remain enabled. No runtime/game executable change was
needed. For an isolated rollback comparison using the same executable:

```powershell
.\tools\windows\start-performance-capture.ps1 -CachedReadback:$false
```

## Real-device evidence

On November 25, 2026, the RTX 3060 benchmark alternated uncached coherent type 3
and cached coherent type 4. Each round performed sixteen 2 MiB small-block uploads,
GPU round trips and 8-byte CPU comparisons after the completion fence. Every word
matched and each round produced the same checksum.

| Coherent host memory | CPU comparison of 32 MiB | GPU round-trip time | Total |
| --- | ---: | ---: | ---: |
| Uncached type 3 | 499.9–519.3 ms | 14.6–15.9 ms | 518.9–538.3 ms |
| Cached type 4 | 3.3–4.0 ms | 14.0–14.8 ms | 19.2–21.1 ms |

These are synthetic buffer costs, not a gameplay FPS guarantee. The size and
frequency of actual compute read-backs vary by scene. New shader/pipeline or
texture work can still stall. The source is `tools/tests/windows/bench-host-cached.cpp`;
it dynamically loads Vulkan, contains no game data and verifies transferred bytes.

Production-source sanitizer tests cover resource bits, required coherence,
cached preference, first-compatible ordering, fallback and opt-out. Eight capture
launcher scenarios test inherited-state cleanup and rollback. The actual GUI
child-process test verifies the requested environment and retained chunk settings.
The previous runtime's 50 regression groups passed before this launcher-only
change. Gameplay stage FPS still needs a same-area comparison.

Driver memory capabilities vary. Retain the explicit opt-out for comparisons.
