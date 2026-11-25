# Gyro stream continuity

The November 24 follow-up repairs intermittent aiming after focus changes,
mouse capture and delayed controller packets. It preserves the earlier
horizontal direction correction. The user confirmed that vertical aiming
responds consistently in the installed follow-up.

The original controller backend numbered samples from 1 after each reset,
whereas the mouse backend used the host's 5 ms clock. sead's six-axis addon
computes new sample count from the signed difference between the latest sample
number and the previously consumed number. Returning from mouse to controller
could therefore look like older input. A controller packet delay also selected
the idle mouse stream automatically.

`tools/patches/patch-gyro-stream-continuity.py` changes four runtime sources:

- Controller samples use the same monotonic 5 ms numbering as mouse samples.
- Focus and mouse capture pause controller history, retaining orientation and
  learned bias. Disconnect still resets the physical device.
- A connected gyro remains selected during packet gaps. The HID API returns
  no new samples while awaiting fresh data, without manufactured fallback input.
- Gentle aiming cancels startup calibration; focus changes do not restart it.

Input remains gated by game focus. Right mouse or F1 capture explicitly selects
mouse gyro; releasing capture restores the controller. Injection remains off.

## Apply, verify and restore

Apply after the mouse motion and native Switch Pro patches:

```bash
python3 tools/patches/patch-gyro-stream-continuity.py --root "$HOME/sp2port"
python3 tools/verify-tutorial-runtime.py --root "$HOME/sp2port"
```

Rebuild `platform_win.cpp` and `hle_hid.cpp` and relink. Changing controller
headers also requires rebuilding `platform_win.cpp`. The helper supports
`--check` and `--restore`; restore this follow-up before the underlying Switch
Pro patch. It validates all four files before writing. Tests confirmed
byte-exact restoration, idempotence and no writes after failed preflight.

The regression exercises production arbitration and the HID bridge across
gentle pitch, packet delay, mouse capture, focus return and reconnect, including
dual-sensor consistency and output bounds. All 38 runtime regression groups
passed with exit code 0. Some shader groups use structural assertions because
`spirv-val` is unavailable.

## Local build and evidence

The installed `C:\sp2stage\sp2win\sp2-controller-gameplay.exe` combines this
repair with the [worker and texture lookup fixes](STAGE_PERFORMANCE.md).
The same build is `sp2-stage-gyro.exe`. SHA-256:
`f49b5dd0ebd757b12382ef9a070d3d75350333488c623437444ca21f1e3c898e`.
The later [upload-cache optimization](UPLOAD_INVALIDATION_RANGE.md) retains this
gyro repair and records the current installed executable and hash.
The previous build has a timestamped
`sp2-controller-gameplay-before-gyro-continuity-*.exe` backup.

A read-only process capture confirmed advancing native samples and pitch in
both directions. During approximately 17 seconds of focused samples, packet
age averaged 8.1 ms and peaked at 28.0 ms; mouse capture was off. The previous
capture contained only unfocused samples and could not assess vertical input.
The user then confirmed consistent vertical aiming in the new build.

The plaza 60 FPS experiment remains off. Sensor delivery and camera response
do not establish stable FPS in the first stage.
