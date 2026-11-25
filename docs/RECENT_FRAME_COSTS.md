# Recent frame-cost diagnostics

The November 25 long gameplay run stopped recording after its first 120,000
presents. Its roughly 60 FPS early sample therefore did not describe the later
Tentakeel and first-stage screenshots showing 24-38 FPS and stalls.

The local diagnostic follow-up retains the latest 120,000 samples in a circular
buffer. It writes chronological CSV only when the window closes normally. Capture
is still opt-in via `NX_FRAME_CSV`; there is no per-frame file output or logging.

Alongside frame interval and pipeline creation time, each row records replay CPU
time, queue encoding time, fence waiting, total replay-submit time, and draw count.
Multiple submissions between presents accumulate; the accumulator resets at each
present. These costs cover replay submissions, not guest simulation or the entire
present operation. A fence wait is host waiting time, not an independent GPU
busy-time measurement. Pipeline compilation is part of replay time and must not
be added to it again.

`tools/patches/patch-recent-frame-costs.py` applies the local diagnostic change.
Rebuild `nvn_vk.cpp` and relink. `--restore` removes it. The recorder regression
checks disabled capture, multiple submissions, reset, two complete buffer wraps,
bounded memory, ordered recent CSV output and no file opens during capture.

`tools/windows/read-frame-capture.py` snapshots either the original 40-byte samples
or the new 80-byte samples from a live Windows process. It only requests read/query
access, retries concurrent buffer changes and reorders the ring by its cursor.
It does not suspend, write to, or send input to the game.
