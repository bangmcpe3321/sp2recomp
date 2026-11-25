# Native Windows audio - November 24, 2026

The installed controller build now connects the game's AudioRenderer updates to
a host mixer and XAudio2. The previous default returned a dummy renderer handle,
discarded the update packets and signaled a timer event. Its log reported audio
frames even though it produced no PCM samples. Windows audio services were running.

The new implementation keeps the US 1.0.0 SDK's own packet serialization and
status handling. A host renderer supplies the virtual update method called by
`nn::audio::RequestUpdateAudioRenderer`. It decodes PCM8/16/24/32, float and mono
Nintendo DSP ADPCM, tracks playback and buffer completion, resamples voice rates
and pitch, applies volume/panning and voice biquads, routes submixes and outputs
stereo PCM16 at 48 kHz. Auxiliary send/return rings let the game's own effect code
process audio. Buffer-mixer effects are also supported.

This is scoped to the supplied US 1.0.0 SDK and its REV1-REV4 packet layout. The
live game uses REV2, 240 samples per update, 96 voice records, 30 mix buffers,
two active auxiliary effects and no splitters in the captured scene. Splitter
routing, standalone DSP reverb/delay effects, multichannel ADPCM and 32 kHz
renderer output are not implemented. Unsupported effects are counted in the log;
full audio fidelity across every game mode is not claimed.

XAudio2 now checks setup, start and submission results, reports HRESULT failures,
and returns rejected output blocks to the free list. The device opens on Windows'
default output. `NX_AUDIO_STUB_RENDERER=1` restores the former silent renderer for
comparison when launching directly. The normal GUI clears diagnostic variables.

## Observed crashes

An initial auxiliary-buffer candidate interpreted the four pointers as two info
pointers followed by two sample pointers. The SDK actually stores two consecutive
`(info, samples)` pairs. That candidate overwrote return metadata and crashed in
`WriteAuxReturnBuffer`. The pointer ordering was corrected. A regression now runs
the actual generated SDK `ReadAuxSendBuffer` and `WriteAuxReturnBuffer` functions
through 100 ring-buffer round trips, including wraparound.

A later candidate rendered audio for approximately 11 minutes before a UI font
thread crashed at host `0x146467704`, within generated `fs_NewSfnt`
(`sdk_001A2A1C`). The failing instruction loaded `[cached_sfnt + 0x30]` while
`cached_sfnt` contained the invalid value `1`, producing address `0x31`. The narrow
recovery returns the SDK's existing `0x130` font error and also writes the font
context status read by its caller. Tests execute the actual generated lookup for
values 0, 1 and a valid font, checking output and callee-saved registers. The cause
of the shared font cache's invalid pointer and long-run stability remain open.

## Apply and rebuild

```sh
python3 tools/patches/patch-sp2-native-audio.py --root "$HOME/sp2port"
python3 tools/patches/patch-windows-audio-output.py --root "$HOME/sp2port"
python3 tools/patches/patch-font-sfnt-not-ready.py --root "$HOME/sp2port"
python3 tools/verify-tutorial-runtime.py --root "$HOME/sp2port"
```

Rebuild `runtime/src/hle_audio.cpp`, `runtime/src/platform_win.cpp` and
`gen/sdk/code_035.cpp`, then relink. The helpers support `--check` and `--restore`.
Restore the audio-output helper before the native-audio helper, then rebuild.

The local build is installed as
`C:\sp2stage\sp2win\sp2-controller-gameplay.exe` and used by the GUI's Play button.
Native audio baseline SHA-256: `29e48fa83bdc46c82a542959e02b6fc371589c9ed0738e56095df8a7be08330b`.
The later [stage performance follow-up](STAGE_PERFORMANCE.md) retains this audio
implementation and records the current installed build and rollback.
The preceding build is retained as
`sp2-controller-gameplay-before-native-audio.exe`. Controller support is retained;
the normal launch uses original game timing with the plaza 60 FPS option off.

## Verification and manual testing

All 35 runtime regression groups passed. New tests cover formats and ADPCM
prediction/context, stereo gain and panning, resampling, loops, pause/stop,
sample/buffer feedback, submix routing, packet/address bounds, auxiliary rings and
the real SDK auxiliary calls. The font test covers the observed invalid-pointer
path. Some existing shader tests report structural assertions only because
`spirv-val` is unavailable.

The live renderer produced nonzero stereo PCM and a 10-second WAV capture. The
corrected auxiliary path delivered over 400 million samples to and from the
game's effect code before the separate font fault. The installed follow-up
reported XAudio2 ready and continued producing audio. Hearing and audio quality
still require the user's manual check; PCM capture alone does not prove the
selected Windows output is audible.

At the user's request, a separate
`tools/windows/test-audio-injected.ps1` starts an automated input test. The user
then requested injection off, and normal launch was restored. The regular GUI and
`launch-controller-gameplay.cmd` clear input scripts, tutorial skips and synthetic
motion variables. The injected script is a diagnostic helper, not a normal-play
default. Its confirmation navigation remains experimental.

No executable, WAV capture, audio packet, or game asset is distributed in this
repository. Protocol layouts were cross-checked against the game's generated SDK
and the [libnx audio definitions](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/services/audren.h).
