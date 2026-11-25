# Local upload-prefix reuse candidate

The November 25 foreground slow-scene call-stack sample captured 951 stacks.
153 included `dedup_upload`; 156 included texture gathering. A frequent bulk
copy returned to `dedup_upload + 0x1b8`. Disassembly of the exact linked object
identified that call as `memcpy`. The CPU replay cost in the completed uncapped
capture was about 13 ms, versus about 4.5 ms of submit fence waiting, for the
filtered recent frames with at least 500 draws and no pipeline creation.
These are sampled/filtered observations, not a claim about every story frame.

The old upload cache required exact source and padded sizes. A smaller draw
request therefore copied the buffer again even when a valid larger copy of that
same source address already existed within the same submit.

`patch-upload-prefix-reuse.py` permits reuse only when the retained source and
allocation cover the request and its upload offset satisfies alignment. A request
with zero padding may reuse an equal-source-length copy with sufficient padding.
A larger payload cannot replace required zero bytes. Existing inline/compute
invalidation and per-submit reset remain responsible for source validity.
The current `nvn_dedup.cpp` build also includes the earlier bounded invalidation
search, which the previous executable's inherited dedup object did not contain.

The regression compares production behavior with the original exact-size policy
across 15,903 size/padding/alignment combinations. It verifies identical copied
bytes and zeros, source mutations, reset, front-cache collisions and the disabled
cache path. A synthetic repeated multi-draw pattern copied 3,456,000 bytes with
the old policy and 4,096 with prefix reuse. That pattern measures potential copy
savings, not gameplay FPS.

The isolated candidate recompiles only `nvn_dedup.cpp` at O2 and retains the recent
frame-cost recorder. Timing, resolution, input, GPU synchronization and plaza cap
are unchanged. Same-location gameplay comparison is required before claiming an
FPS gain.

Apply `tools/patches/patch-upload-prefix-reuse.py` to the private runtime; rebuild
`nvn_dedup.cpp` and relink. Use `--restore` and rebuild the same unit to remove it.
The helper supports `--check` and refuses duplicate/mismatched anchors.
