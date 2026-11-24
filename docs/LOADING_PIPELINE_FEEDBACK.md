# Loading stalls and pipeline-cache feedback

A completed manual capture contains a 9,215 ms frame in which creating 139
graphics pipelines took 8,626 ms, and a 5,437 ms frame in which creating 85 took
4,862 ms. A 120-present loading window took about 14 seconds. This explains a
large portion of the reported long stalls, but separate multi-second waits had
little or no recorded graphics compilation.

The 8,064-frame capture created 438 graphics pipelines, spending 22,578 ms in
creation. It did not evict pipelines from the application LRU. Its compatible
234,273,404-byte driver cache loaded successfully, and normal shutdown updated
that file even though its size stayed the same. Loading the file does not prove
that an individual creation request hit the driver's application pipeline cache.

`tools/patches/patch-pipeline-creation-feedback.py` adds optional Vulkan 1.3
creation feedback. Enable `NX_PIPELINE_FEEDBACK=1`, or pass `-PipelineFeedback`
to the manual Windows capture helper. Each `PIPE_FEEDBACK` record includes:

- Host and driver creation time, result and valid-feedback status.
- Application cache hit (`1`), miss (`0`) or unknown feedback (`-1`).
- Graphics/compute stage feedback and hashes of the actual post-transform
  SPIR-V passed to Vulkan.
- A pointer-free recipe fingerprint for cross-run comparison. It is a diagnostic
  signature, not a complete serialization of the Vulkan creation inputs.

The option defaults off, preserves existing extension chains and creation flags,
requires Vulkan 1.3, and logs at most 8,192 creation requests. Invalid feedback
and failed calls remain unknown rather than being labeled cache misses.

Compute pipeline creation was absent from the previous frame CSV totals. It is
now included in the existing lifetime and timing-window counters. This prevents
an unmeasured compute compilation from appearing as "no pipeline work".

The production helper regression tests disabled/malformed options, unsupported
devices, supported devices, preserved graphics/compute extension chains, invalid
feedback and failures under sanitizers. Existing pipeline key and hot-allocation
regressions also pass. The installer supports `--check` and `--restore`, with
exact restoration and no writes on a failed preflight.

```bash
python3 tools/patches/patch-pipeline-creation-feedback.py --root "$HOME/sp2port"
python3 tools/tests/tutorial/test_pipeline_creation_feedback.py "$HOME/sp2port/runtime/src/nvn/nvn_pipeline.cpp"
```

Rebuild `runtime/src/nvn/nvn_pipeline.cpp` at the candidate's existing compiler
settings and relink. This instrumentation does not remove the loading stall;
the next manual capture will distinguish cache misses, costly cache hits and
other waits before choosing the performance repair.
