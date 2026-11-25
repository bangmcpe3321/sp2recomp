# Stage performance and worker core identity

The first-stage manual capture on November 24, 2026 showed recurring frame-time
spikes while hiding in ink. The user's screenshot showed 45.5 FPS, a 22.0 ms
average and a 75.2 ms peak. Slow renderer windows often took 13–16 ms of CPU
replay, compared with approximately 6–7 ms in faster windows. Shader pipeline
creation was small in several slow windows, so compilation alone does not
explain the recurring dip. Stable 60 FPS has not been verified.

Two captured access violations occurred while drawing depth shadows through
`gsys::ModelUnitDrawArray::drawEachNode_<false,true,true>`. One read a model
uniform pointer equal to 9 and faulted at address `0x4a`; the previous run read
invalid uniform data in the same caller. These are distinct from the earlier
font and audio faults.

## Worker core repair

`tools/patches/patch-worker-core-identity.py` changes `runtime/src/hle_os.cpp`:

- `nn::os::SetThreadCoreMask` now updates the kernel thread's guest core.
- `nn::os::GetCurrentCoreNumber` reports that core instead of always returning 0.
- Synthetic current-thread tokens expose the US 1.0.0 SDK's handle field at
  `ThreadType + 0x1b8`; their allocation is enlarged to contain it.
- The synthetic thread ID counter is atomic.

The game's scratch allocator has separate cursors for cores 0, 1 and 2. Its
`gsys::ModelDrawObjStream` records draw data into this storage. Reporting core 0
for every worker defeats that separation and permits concurrent workers to
reuse the same cursor. Live startup logs from the repair candidate confirm
the requested masks and guest cores 0, 1 and 2. A stage retest is still needed
to establish whether this accounts for every captured shadow crash.

## Image lookup optimization

`tools/patches/patch-image-storage-lookup.py` changes `nvn_image.cpp`.
Snapshot fallback searches previously walked the complete weak image registry,
including expired entries for historical dynamic resolutions. `StorageKey`
orders the memory address first, so two tree lookups identify the matching
address range. Searches now visit only that range, preserving the original
iteration order, format rules, and freshest rendered image selection.

The regression compares the original scan with the new range on a registry
containing 80,000 entries, expired images, multiple shapes and formats, missing
addresses and `UINT64_MAX`. Results match while visiting at most five entries
for each tested address. This measures lookup work, not an in-game FPS gain.

## Apply, verify and restore

From the repository in WSL:

```bash
python3 tools/patches/patch-worker-core-identity.py --root "$HOME/sp2port"
python3 tools/patches/patch-image-storage-lookup.py --root "$HOME/sp2port"
python3 tools/verify-tutorial-runtime.py --root "$HOME/sp2port"
```

Rebuild `hle_os.cpp` and `nvn_image.cpp` and relink against the current gameplay
and native audio objects. Each helper supports `--check` and `--restore`;
restoration requires rebuilding those same units. Patch round-trip tests
confirmed byte-exact restoration, idempotence and no writes on a failed
preflight.

The local combined candidate is
`C:\sp2stage\sp2win\sp2-stage-performance.exe`, SHA-256
`6aeeab4d03b0396ccec84564fd4d9acc1c4ff0707eba2579cf6318edb9648849`.
The same build is installed as the GUI's default `sp2-controller-gameplay.exe`.
The later [gyro continuity follow-up](GYRO_STREAM_CONTINUITY.md) retains these
performance changes and records the current installed executable and hash.
The subsequent [upload-cache follow-up](UPLOAD_INVALIDATION_RANGE.md) retains
both repairs and records the latest installed build.
The earlier build is retained as a timestamped
`sp2-controller-gameplay-before-stage-fixes-*.exe`. The initial live worker-only
candidate is `sp2-worker-cores.exe`; it does not include the image optimization
or the subsequent atomic thread ID change. Updating the default executable
does not update an already-running test process.

All 37 runtime regression groups passed against the patched sources. Some
shader groups use structural assertions because `spirv-val` is unavailable.
Desktop control was unavailable during this follow-up: both computer-use tools
reported that their native pipe could not be found. The combined build therefore
still needs a manual first-stage ink-hide and shadow-crash retest.

The user subsequently reported no further crash during the worker-only run.
That process ran for approximately 15 minutes and produced a shutdown CSV.
The user later confirmed consistent vertical aiming in the combined gyro and
performance build. First-stage FPS measurements for that build remain open.
The user then reported 15–50 FPS, averaging approximately 30–40, in stage 1.
The upload-cache candidate is awaiting the next comparison; no stable-60 result
is claimed.

For an injection-free manual capture, close any running game and run:

```powershell
.\tools\windows\start-performance-capture.ps1 -Executable sp2-stage-performance.exe
```

The capture keeps the plaza 60 FPS experiment and forced fixed resolution off.
Compare standing and hiding in ink at the same first-stage location, after
initial asset loading. Logs go to the game's `diagnostics` folder. Close the
window normally to flush the frame CSV; the current recorder writes that CSV
only on normal shutdown, so a crash can leave only the text log.
