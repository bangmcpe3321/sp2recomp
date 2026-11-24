# Quiet gameplay capture

The detailed capture launcher previously enabled synchronous renderer and present
statistics in every manual run. Those statistics write and flush multiple lines
on the presenting thread. In the `204630` capture, 12 non-compiling 60 Hz frames
at 300-frame boundaries had a median of 185.01 ms (range 170.42–221.59 ms),
versus 17.40 ms for other non-compiling frames.

The same executable was launched with these statistics disabled. A read-only
snapshot of its existing buffered recorder found 14 comparable boundary frames:
median 17.47 ms, maximum 25.99 ms. Other non-compiling frames had a 17.21 ms
median. The user confirmed this run was much smoother. The comparison establishes
that the periodic diagnostics added substantial hitches; it is not a controlled
same-route benchmark or evidence of stable 60 FPS in every scene.

The launcher now defaults to quiet recording. It retains the FPS overlay and
bounded frame CSV, which is written on normal shutdown. Render/present summaries
require `-DetailedStats`; pipeline feedback and simulation traces remain
separate explicit switches. Inherited diagnostics, scripted input and unpaced
settings are cleared before every launch.

```powershell
.\tools\windows\start-performance-capture.ps1
# Diagnostic-only capture; synchronous summaries can affect frame times:
.\tools\windows\start-performance-capture.ps1 -DetailedStats -PipelineFeedback
```

The mocked Windows regression executes the actual launcher in five option
combinations without starting a game. It verifies quiet defaults, explicit
switches, cleanup of inherited overrides, original scene timing, and continued
overlay/CSV recording:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\tests\windows\test-performance-capture.ps1
```

## Remaining story performance

The user subsequently reported sustained 30–40 FPS in story stages and Tentakeel
Outpost. This is separate from the resolved 300-frame logging hitch. First-use
pipeline creation and non-compilation loading pauses also remain. A targeted
CPU/GPU sample at a slow location is needed before choosing the next rendering
or simulation optimization. No timer, simulation-rate or visual-quality changes
are included in this launcher repair.
