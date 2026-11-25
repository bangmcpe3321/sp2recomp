# Local synchronous command-chunk candidate

The latest upload-prefix run still had inconsistent FPS. For captured uncapped
frames with 300-800 draws and no pipeline creation, median replay was 9.86 ms,
fence waiting 5.94 ms and total frame interval 18.22 ms. These broad bins are not
a matched-scene FPS comparison. The same run also had long pipeline-compilation
stalls; command chunking does not eliminate compilation work.

The opt-in candidate queues completed portions of replay while the CPU records
later portions. It reuses existing command-part barriers, pass boundaries and
binding reinitialization. Every queued part is waited before the guest submit
returns. Compute write-backs and counters are published after completion.
The synchronous upload buffer, descriptors, guest simulation pacing, resolution
and normal presentation path remain in use. Presentation restores its original
command buffer, separate from the replay slot buffers. Image retirement keeps
its original synchronous aging points.

Enable `NX_SYNC_CHUNKS=1` and `NX_SUBMIT_CHUNK_DRAWS=150` before startup, or use
`tools/windows/start-performance-capture.ps1 -SynchronousChunks`. The runtime mode remains opt-in and does not override explicit asynchronous or
pipelined modes. After the user confirmed steadier plaza, Tentakeel and stage
play, the local GUI and capture launcher now enable it by default. For a rollback
comparison with the same executable, pass `-SynchronousChunks:$false` to the
PowerShell capture launcher.

## Verification

Production-source sanitizer tests exercise early ordered parts, threshold/pass
handling, the part limit, complete fence retirement, write-back/counter ordering,
failed submission, the debug/no-chunk path and the separate presentation buffer.
Installer tests cover multi-file preflight, LF/CRLF exact restore and idempotence.
The Windows launch mock verifies explicit opt-in and clearing of inherited flags.

The RTX 3060 standalone Vulkan transfer benchmark modeled eight command parts
with 2 ms of CPU work between parts. Serial recording/queuing took 39.8-41.5 ms;
early queuing took 23.7-24.3 ms. All output words matched after the full completion
fence. The source is `tools/tests/windows/bench-sync-chunks.cpp`. This tests the
overlap mechanism, not game FPS, draw correctness or new shader-cache coverage.

Apply `tools/patches/patch-synchronous-chunks.py` to the private runtime, rebuild
`nvn_vk.cpp` and `nvn_frames.cpp`, and relink. The patch supports `--check` and
`--restore`. No game assets or shader binaries are included.

Gameplay rendering, ink queries and same-area frame pacing require manual
verification in addition to these source regressions.

## User validation and launcher persistence

The user reported that plaza, Tentakeel and stage play are much steadier, with
some remaining dips mostly when entering an area or seeing an effect for the
first time. The local GUI launcher now retains the tested 150-draw chunk mode.
Its real child-process test verified the environment, inherited-flag cleanup,
saved settings, duplicate-launch guard, pipe draining and exit status. The quiet
capture launcher also defaults to this mode and retains an explicit opt-out.

The completed capture shows lower fence-wait times and near-60-FPS median pacing
in some uncapped draw ranges; captures cover different routes and do not prove a
matched-scene FPS percentage gain. First-use pipeline creation remains visible.
This follow-up preserves the improvement; it does not claim all first-use stalls
or all scenes are fixed.
