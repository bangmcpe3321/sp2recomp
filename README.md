# sp2recomp

**English** · [Tiếng Việt](README_vi.md)

A native PC **recompilation of Splatoon 2** (USA) for Windows with Vulkan.
The original game's AArch64 code is recompiled to x86-64 and connected to a PC
runtime for graphics, input and platform services.

The recompilation is in development. This repository contains runtime patches,
build and verification tools, and research notes supporting the port. The sections
below record verified behavior, current limitations and the original executable's
structure.

## Current state

### Renderer cache and news ending follow-up - November 24, 2026

The latest candidate reuses equivalent graphics pipelines, avoids repeated image
tree lookups and diagnostic allocations, and optimizes the renderer while keeping
gameplay timing unchanged. It also corrects an old fallback that finished the
news ending before its reserved delay. Source regressions and the Windows build
pass; loading pauses and ink-related FPS dips still need manual comparison.
See [changes, evidence and rollback](docs/RENDERER_CACHE_PERFORMANCE.md).

The following build corrects physical Pro Controller vertical aiming. Tutorial
intro audio can still run ahead when animation falls below its intended rate;
the clean manual comparison remains open. See [pitch and audio timing](docs/PRO_PITCH_AUDIO_TIMING.md).

### Native Switch Pro input and gameplay options - November 24, 2026

The Windows runtime now reads native Switch Pro Controller buttons, sticks and
physical gyro through SDL3 HIDAPI. A connected Bluetooth controller supplied a
verified 200 Hz motion stream; in-game aiming still needs a manual check.

Two separate options implement the supplied US 1.0.0 patches: plaza 60 FPS and
disabled dynamic resolution. Build ID and original instructions match; both
options default off and have reversible source helpers and separate launchers.
Octo Expansion credits are outside this US 1.0.0 patch's scope, and stable 60 FPS
is not claimed. All 32 runtime regression groups pass. See
[behavior, validation and rollback](docs/CONTROLLER_GAMEPLAY_OPTIONS.md).

A manual comparison found that copying the 60 FPS branch patch hid the news
studio. An interval-only follow-up then ran the scene too fast. The current option
executes scene initialization and changes calculation mode together with the
vblank interval; normal-speed play awaits manual recheck. Physical gyro horizontal aiming was also corrected
from the user's test feedback.

### Bulk shader-cache build - November 24, 2026

The local cache now covers all **14,379 shader stages extracted from the game
assets**, including all 199 misses from the affected story-mode run. The batch
compiled and validated 7,214 new stages and repaired 15 older compute stages
that had been incorrectly cached as vertex shaders.
See [counts, verification and limitations](docs/BULK_SHADER_CACHE.md). Black
materials and post-stage ink behavior are awaiting manual retest; this does not
precompile every Vulkan pipeline or establish stable 60 FPS.


### Plaza transition safety follow-up - November 23, 2026

A missing font fallback no longer causes the observed null glyph read. Resource
waits also retain live rendering data until submission completion, instead of
releasing it after two seconds. See [the crash evidence, patches and limits](docs/PLAZA_TRANSITION_SAFETY.md)
and [28 regression groups](tools/verify-tutorial-runtime.py). Live transition
verification remains open.


### False enemy-ink detection fixed - November 23, 2026

Standing on bare tutorial ground no longer triggers the reported enemy-ink
slowdown in the confirmed manual test. The runtime had returned a report serial
as a GPU samples-passed count; those fabricated counts fed the player's ink
coverage. It now records counter resets and publishes real GPU counts with a
valid completion timestamp.

See [the captured evidence, fix and remaining checks](docs/INVISIBLE_INK_COUNTERS.md),
the [apply/restore helper](tools/patches/patch-gpu-counter-queries.py), and
[26 runtime regressions](tools/verify-tutorial-runtime.py). Squid concealment,
stable story-mode 60 FPS and remaining stutters still need verification. GPU
timestamp changes are opt-in; the normal build retains the earlier timing.


### Mouse gyro, FPS overlay and stutter follow-up - November 23, 2026

Windows mouse movement now feeds the emulated gyro while holding right mouse or
using F1 capture. The latest adjustment corrects reported reversed horizontal
aiming and lowers sensitivity to 0.03 degrees/pixel; use **[ / ]** while captured
to adjust it. **F3** toggles the FPS overlay. A follow-up replaces query-driven
motion with coherent 200 Hz samples to address intermittent aiming; manual
verification remains open.

Periodic rendering summaries and driver-cache checkpoints are disabled during
normal play. Pipeline keys ignore padding, driver caches persist correctly, and cache
eviction now retains recently used pipelines. Optional per-frame capture records
compilation costs. **Stable 60 FPS and first-shot/transition
stalls remain unverified.** See [controls, evidence and patch instructions](docs/FRAME_STUTTER_MOUSE_GYRO.md)
and [26 runtime checks](tools/verify-tutorial-runtime.py).



### Plaza/news rendering follow-up — November 23, 2026

Valid black textures now retain their contents, restoring shading across the
square and news studio. Cache-owned glyph atlases refresh correctly, and a scalar
sine precision fix removes the measured area-light stippling. Native Vulkan no
longer applies the extra Metal depth tolerance that let the face overwrite nearby
eyebrows. See [evidence, scope and application](docs/PLAZA_NEWS_RENDERING.md), the
[apply/restore helper](tools/patches/patch-plaza-news-rendering.py), and
[15 runtime sanitizer checks](tools/verify-tutorial-runtime.py).

Disabled draw diagnostics also skip their former per-draw environment scans and
trace formatting. See the [measured CPU optimization and FPS observations](docs/DRAW_DIAGNOSTICS_PERFORMANCE.md).

Black story-mode trees, balloons and crates were traced separately to missing
shader-cache stages. The local cache has been rebuilt and validated; game-derived
shader files are not distributed here.

![News rendering after the texture-content and precision fixes](docs/images/news-rendering-verified.png)


### Plaza Inkling faces — November 22, 2026

Copied texture descriptors were also being dropped by texture-to-texture copies,
leaving generated body atlases unfilled. Retaining both copy operands with the
command list restores solid Inkling faces and skin in the café scene. See the
[measured fix and limitations](docs/PLAZA_FACE_TEXTURE_COPIES.md),
[apply/restore helper](tools/patches/patch-plaza-texture-copy-descriptors.py), and
[ten runtime sanitizer checks](tools/verify-tutorial-runtime.py).

![Verified plaza Inkling faces](docs/images/plaza-faces-verified.png)

### Sampler-copy and mouse-input follow-up — November 22, 2026

Further tracing found that copied sampler objects were silently dropped, leaving
nearest filtering where the game requested linear or trilinear filtering. The
runtime now preserves sampler values through copies and registration, including
copies over an already initialized object. Requested point filtering is preserved.
A reproduced mouse-delta accumulation error is also corrected, and verbose
sampler-state logging is bounded instead of flushing a line on every initialization.

These are specific runtime fixes, **not** a claim that tutorial aim automation,
missing ink, or all remaining floor/color artifacts are fixed. See the
[evidence and limitations](docs/SAMPLER_COPIES_MOUSE.md), the
[apply/restore helper](tools/patches/patch-sampler-copies-mouse.py), and the
[ten runtime sanitizer checks](tools/verify-tutorial-runtime.py).

### Tutorial lighting update — November 21, 2026

The Windows runtime now renders the tutorial's textured world without the former
neon/black lighting failure. The fixes cover GPU-to-CPU lighting readback,
compressed-cube attachment views, integer shader interfaces, instance semantics,
unit-point coverage, and registered texture identity and lifetime. The six-axis
state layout/history is also corrected so the game can process supplied motion
samples. PlayerMake's colored hair, visible irises and textured clothes were
checked again with this build.

![Tutorial scene after the runtime lighting fixes](docs/images/tutorial-lighting-verified.png)

*Actual Windows runtime output, with the tutorial's aiming instructions visible.
Remaining banding/speckle is not declared fixed. This is not proof of completing
the tutorial. That November 21 build did not add mouse-to-gyro input; see the
November 23 update above for mouse mapping and the November 24 update for native
Switch Pro physical gyro.*

See [the fixes, measured checks and limitations](docs/TUTORIAL_LIGHTING.md), the
[apply/restore helper](tools/patches/patch-tutorial-lighting-sixaxis.py),
[runtime sanitizer regressions](tools/verify-tutorial-runtime.py), and the
[HDR capture check](tools/verify-tutorial-capture.py). Apply this patch after the
PlayerMake patch below; both target the separate `sp2port` runtime.

### PlayerMake rendering update — November 21, 2026

The verified isolated Windows runs now render the Inklings' eyes, skin, hair,
textured clothes and shoes. Two runtime fixes were required: preserve copied
texture descriptors' own storage identity instead of following a reinitialized
texture object, and stop flipping front-face winding just because a depth
attachment is present. The empty fragment shaders were not the cause.

![PlayerMake after the descriptor and winding fixes](docs/images/playermake-verified.png)

*Late-frame replay from the isolated run: sampled live frames 300–6,300 remained
correct. A separate run without RenderDoc or atlas-refresh overrides stayed
correct through frame 3,000. One earlier concurrent-replay run went dark; that
stress case remains unresolved. Those PlayerMake-only checks did not verify
tutorial or plaza rendering.*

See [the measured fix and verification](docs/PLAYERMAKE_FIX.md), the
[apply/restore helper](tools/patches/patch-playermake-descriptor-winding.py), and the
[capture regression check](tools/verify-playermake-capture.py). The patch targets
the separate `sp2port` runtime; this repository does not contain game assets or
the generated game executable. Older screenshots and findings below are historical.

### Historical route observations

The route notes below describe earlier builds. The verified café face result above
supersedes the old missing-skin diagnosis; free-roaming plaza rendering has not
been reverified by this fix.

The recompiled port runs the game's own code on Vulkan on Windows. The title screen renders at
1920×1080. PlayerMake character creation completes with legible text, the intro cutscene plays,
and the first-launch controller tutorial runs: the controller page renders whole (the Pro
Controller diagram, the Joy-Con photo, the banner shapes, the button prompts), the guide
sentences read correctly, and the aim and ZR steps pass. The tutorial then reaches the Move page:
its controller diagram, "Move with L!" banner and hand prompt render, and the 3D room behind them
now renders too — a central 960×540 viewport, measured at ~98% non-black pixels and luma 85. A
temporary `SCENECHG` log in `main_00620ED0` makes the tutorial and UI/page state sequences
visible. Motion aiming reads a swept six-axis state (`NX_SIXAXIS_WOBBLE=1`), and a scripted input
sweep walks the steps forward.

The 9-state tutorial manager requests `5 → 6` after the first warp; an idempotent patch
redirects that one request to warp state 7. The 21-state UI/page manager's `4 → 5` request is
not a null-state dead end. Its state-5 entry stays null in the old table, but the page's virtual
scene-change handler constructs a new page manager and loads the title's Off the Hook news
scene. A live capture of the actual `4 → 5` transition is below: the central 960×540 TV
viewport shows the news studio and the two hosts, Pearl and Marina. The earlier `4 → 7` redirect
is a diagnostic detour that skips the news: it reaches the PlayerMake gear-selection screen
(`7 → 1 → 2 → 9`), whose state-9 entry is null, and stalls there.

The news now ends, and the plaza loads behind it. The news' own BGM handover is driven through
the game's code path by [patch-newsend-bgm-handover.py](tools/patches/patch-newsend-bgm-handover.py),
so the pose sequence completes and the scene goes `5 → 7 → 1 → 2`: the Turbun Shell reward, then
`SeqMgrPlaza::stateProgress`, i.e. Inkopolis Square. The last story transition is
`Cmn::BgmConductor::xlinkCalc`, the plaza's own track restarting. The 3D world behind the plaza UI
still does not draw (see [The plaza](#the-plaza)), so the square is only visible through the
first NPC page's camera. About one boot in three stalls in the UI job manager at the
character→tutorial transition (see Open).

![The title screen at 1920×1080](docs/images/title-1920x1080.png)

*The title screen, rendered at the full 1920×1080 output size. The title appears around frame
6750 on this build; the route keeps the `ZL+ZR` chord held past that point.*

![The Off the Hook news scene reached through the actual 4 → 5 transition](docs/images/news-4to5.png)

*The actual `4 → 5` UI/page transition loads the title's Off the Hook news scene. The central
960×540 viewport shows the news studio with Pearl and Marina; the old 21-state table still
reports its state-5 entry as null because the transition creates a new page manager. The
surrounding UI is still mis-scaled (the separate UI-layout issue), but the news scene itself
renders. The `4 → 7` detour skips this scene and reaches the gear-selection screen instead.*

![Inkopolis Square behind the first NPC's gear page](docs/images/plaza-gear-page.png)

*The plaza after the news: `5 → 7 → 1 → 2` reaches `SeqMgrPlaza::stateProgress` and the HUD
(level, cash, coins) comes up. The first NPC the route walks into opens the gear page
(`stateShowGearNpc`: weapon, headgear, clothes, shoes), and that page's camera renders the
square's sky behind it — clouds over a haze, in the lower-right area next to the card. The
lower two thirds of the frame are 100% non-black with 63–77 distinct colours per sampled
region, which is a rendered sky, not a flat fill. The `B` prompt backs out of the page.*

![Inkopolis Square at rest in the plaza](docs/images/plaza-progress.png)

*The same plaza at rest, in `cProgress` with the NPC page closed and the camera turned: the
NPC/action markers and the HUD draw, but no stage geometry and no sky (98% of pixels black).
This is an earlier-build observation, described under "The plaza" below.*

![The tutorial aim step, passed](docs/images/tutorial-aim-legible.png)

*The aim step. The guide bands read "Aim at the [balloon] balloon!" and "Target the [balloon]
balloon with the [reticle] reticle!"; `Just like that!` is the game's answer once the swept
six-axis state brings the reticle onto the balloon. The bands are drawn by
`TutorialGuideMsgPage` with the CPU-written size-100 BlitzBold glyph atlas, which the port now
re-uploads when its bytes change.*

![The first-launch controller tutorial, "Shoot with ZR"](docs/images/tutorial-zr-step.png)

*The next step: "Shoot with [ZR]!" with "Tilt the controller to aim!" underneath; the Joy-Con's
ZR is lit orange and the prompt badge reads ZR.*

![The tutorial Move step](docs/images/tutorial-move-step.png)

*The Move page. The Pro Controller diagram highlights the left stick, and the "Move with L!"
banner and hand prompt are drawn; the room behind them is now rendered as a central 960×540
viewport (~98% non-black, luma 85), rather than black. The page is a timed step:
`main_00A00BDC` advances the tutorial manager from page 6 to page 8 when the global counter
`[+0x44c]` reaches `0x12c0`, about 3,100 frames after the page starts. An earlier forced skip
took the `main_00A00300` actor-flag path at `L_A00350`, which calls `main_00620ED0(this, 7)` —
the quit-to-title path; the `SCENECHG` log showed `6 -> 7` and the title reappeared. The skip is
now disabled ([tools/patches/patch-move-skip-disable.py](tools/patches/patch-move-skip-disable.py)),
so the timeline transition runs.*

![PlayerMake gear selection reached through the UI state redirect](docs/images/ui-gear-state9.png)

*The state-9 evidence frame from the first full planted-route run: the PlayerMake gear-selection
screen (four gear cards on the Switch tablet), reached through `4 -> 7 -> 1 -> 2 -> 9`. This is not
the plaza. State 9's entry is null, so the UI stops here; the image confirms that redirecting the
missing shot state to state 7 is a detour into the PlayerMake UI, not the plaza handoff.*

![PlayerMake character creation, eye colour step](docs/images/boot-playermake-en.png)

*Historical PlayerMake eye-colour capture ("Pick an eye color!"). Text is legible
because the port stores the CPU-written R8 glyph atlas as packed rows instead of
untiling it. The missing-model defect shown here is superseded by the verified
descriptor/winding update above.*

![Character confirmation](docs/images/boot-confirm-text.png)

*The confirmation page, captured before the language fix (`この設定でオッケー？`); the small
bottom-left hint is still garbled — a second, smaller atlas.*

Six fixes took the port from a boot fatal to this point:

- **Dropped tail call.** `Cui::Page::findPartsControl` (`0x20BD74`) ends in
  `b 0x20CF60`, a tail call into `Control::List::searchAs<PartsCtrl>`. The recompiler emitted
  the two instructions before it and no call, so the function returned
  `page->controls + 0x38` — a list pointer — to callers that expect a `PartsCtrl*`;
  `Cui::CustomizePartsSet::onInitialize` then called `(*ctrl)[0]` through it and died with
  `call to 50c12201b8` (heap) at boot. A scan of every generated function in every module for a
  final `b` to another function with no emitted call found **this as the only case in the whole
  game**. Patch: [tools/patches/patch-tailcall-20bd74.py](tools/patches/patch-tailcall-20bd74.py).
- **The glyph atlas is CPU-written.** The 2048×2048 R8 atlas is created with `stride 0` (the
  builder treats it as tiled), swizzle (R,1,1,1) and `alpha_from_r`, but the game fills it from
  the CPU, so its guest memory is packed `width`-byte rows. Untiling it produced streak noise
  (the `NX_DUMP_ALPHA` dump of the uploaded atlas showed no glyph shapes); treating stride 0 as
  `row_stride = width` and widening R8 → RGBA8 `(255,255,255,R)` made the labels legible.
  Patch: [tools/patches/patch-alpha-atlas.py](tools/patches/patch-alpha-atlas.py).
- **The glyph atlas was uploaded only once.** The size-100 BlitzBold atlas is also written by the
  CPU through mapped memory, but the font engine never reports that range to
  `nvnMemoryPoolFlushMappedRange` (the 32 KB+ flushes the port sees belong to other pools), so the
  image kept the letters of whatever face or size had filled those cells first — clean glyphs,
  wrong text. The port hashes one sampled byte in 61 of each sampled R8-read-as-alpha image once a
  frame and re-uploads the whole image when the hash changes; the tutorial's guide sentences now
  read correctly and the upload cost is paid only on the frames the font engine rasterises glyphs
  (`NX_ATLAS_REFRESH=0` disables). Patch: [tools/patches/patch-atlas-refresh.py](tools/patches/patch-atlas-refresh.py).
- **The reported language was byte-swapped.** `nn::settings::LanguageCode` is a `char[8]`,
  but the port wrote each tag as a number with its first character in the high byte, so
  `"en-US"` landed in memory as `"SU-ne"`. The game matched no language and fell back to
  Japanese (`/Message/CommonMsg_JPja.szs`), even though `nn::oe::GetDesiredLanguage` already
  answered `en-US` (that path `memcpy`s the tag). The codes are now derived from their string
  literals at compile time and the game loads `/Message/CommonMsg_USen.szs`.
  Patch: [tools/patches/patch-language-code.py](tools/patches/patch-language-code.py).
- **A null font face on the intro→title transition.** `nn::font::FSS_set_scale` checks the
  face pointer, calls `get_scale_inputs` (which can release and rebuild the face) and then
  reloads the pointer and reads `[face+0x20]` without checking it again. When the face is null
  at that point the game died at data address `0x20`. The patch honours FSS's own null-face
  error (`0x131`) instead, so the caller falls back to the unscaled glyph instead of crashing.
  Patch: [tools/patches/patch-fss-null-face.py](tools/patches/patch-fss-null-face.py).
- **Whole-target clears erased UI panels.** NVN clips a clear to the bound scissor. The port
  ignored the scissor (behind `NX_CLEARS_SCISSOR=1`) and cleared the whole attachment instead, so
  a clear meant for one UI panel wiped the rest of the UI image. On the first-launch tutorial
  this removed the Pro Controller diagram and other layout parts, leaving only the photo, banners
  and arrows. Honouring the scissor by default restores the whole page. `NX_CLEARS_SCISSOR=0`
  restores the old behaviour for bisecting (the port once saw a course break with scissored
  clears, docs/nvn/DEBUG.md #52).
  Patch: [tools/patches/patch-clears-scissor-default.py](tools/patches/patch-clears-scissor-default.py).

### The plaza

**November 22 update:** the café scene now renders the square and intact Inkling
faces in isolated runs with and without RenderDoc. See the
[texture-copy fix](docs/PLAZA_FACE_TEXTURE_COPIES.md). The following measurements
are historical; they do not describe the newly verified café scene. Free-roaming
plaza rendering still needs a separate check.

After the news, `SeqMgrPlaza` runs `5 cNews → 7 cGetTurbunShell → 1 cPreProgress → 2 cProgress`.
The Turbun Shell reward is the pop-up at frames 10000–15000 of the plaza run; `cProgress` is
Inkopolis Square, HUD up, with NPC/action markers on screen. The state names are the
string table at `main.bin+0x282e0d9` (`cReady, cPreProgress, cProgress, cFirstDemo, cTitle,
cNews, cIntro, cGetTurbunShell, cFirstTurbunShell, cNpc, …`), and the delegate table is at
`main.bin+0x2fbb578`.

One thing in the square does render, which is useful for separating what works from what does
not. Standing in front of an NPC and pressing `A` calls `SeqMgrPlaza::requestLookAtNpc`(`0x97CC2C`) → `changeStateTo(9)` = `cNpc`; that spawns `Game::SeqPlazaNpc` and opens
`stateShowGearNpc` (`main_00988E6C`). Inside that page the stage's sky draws behind the gear
card: fully populated, saturated clouds over a haze (100% non-black, 63–77 distinct colours per
sampled region). `B` there calls `changeStateTo(1, true)` into `stateShowStatusNpc`, whose back
button calls `outGearOrder` and returns `SeqMgrPlaza` to `cProgress`. With the page closed the
square is black again, while the `Lp::UI` markers and the HUD still draw (98% of pixels black).

The difference is not the route and not the moment the page closed. Entering `cProgress` and
never opening an NPC page leaves the square black; opening one, closing it with `B` and turning
the camera leaves it black as well — the same frames are byte-identical whichever way
`cProgress` is reached (frames 37500 and 42500 of the `plazab` run). The page camera is what
gives the stage's draws a usable state.

What the log rules out:

- **Missing NVN commands.** None of the stage draws need one. The runtime rejects nothing in
  this run (`0 unknown` submits, `nvnCommandBufferSetAlphaRef` is the newest command the game
  first calls, and every other unimplemented NVN call — indirect draws, buffer copies,
  transform feedback, debug groups — is never made).- **Missing pipelines.** The 60-frame report shows `0 no pipeline` throughout; the stage's 637
  pipelines and 13 ASTC textures are built right after `2 → 9` (3.5 s of compile). Draws that
  reach the replay without a *program* do not draw: `no program` goes from 0 to ~3–5 million
  over the run, and the 512-entry pipeline cache thrashes from the title onward. This is a
  consequence of the cache cap, not a missing shader.
- **The viewport's clears.** The last clear statistics show `96812 scissored`, of which only 13
  left their pass and cleared a whole target — the plaza's clears are scissored to the
  960×540 composite viewport, so the square's own pass is not being wiped from outside.

So the open question is inside the stage pass itself. The next step is a pass trace of one
plaza frame (`NX_TRACE_PASSES_FROM_FRAME`, [patch-pass-frame.py](tools/patches/patch-pass-frame.py)):
which target the stage draws into, whether the pass is created there at all, and whether its
draws arrive after the composite viewport has been blitted.

### Memory, input and the tutorial

- **Six-axis sensor HLE.** `GetSixAxisSensorHandles` used to leave the output untouched, and it
  returned 0 where the API returns the number of handles written. `sead::NinJoyNpadDevice::calc`
  stores that value as its sensor count, so the game concluded the controller had no sensor and
  never called `StartSixAxisSensor` or `GetSixAxisSensorStates`. With the count returned, the game
  starts sensor 0 and reads 16 states every frame; the HLE reports a controller held level
  (identity direction, gravity on -Z, 1/60 s delta). `NX_SIXAXIS_WOBBLE=1`
  ([patch-sixaxis-wobble.py](tools/patches/patch-sixaxis-wobble.py)) adds a slow pitch/yaw sweep
  for the tutorial's "Tilt the controller to aim!" step. Patch:
  [tools/patches/patch-sixaxis.py](tools/patches/patch-sixaxis.py).
- **R11G11B10F stored natively.** NVN format `0x3f` was always widened to RGBA16F off Android,
  doubling every HDR load/store/sample (636 MB of 1020 MB live images at the title on a 6 GB
  laptop GPU, and it ran out of device memory at the tutorial). The port now uses
  `B10G11R11_UFLOAT_PACK32` when the device can render, blend, filter and copy it, halving
  those images (`NX_R11G11B10_EMULATE=1` restores the old behaviour). At the tutorial the live
  set went from 5.6 GB to 1.2-1.7 GB with no failed allocations. Patch:
  [tools/patches/patch-r11-native.py](tools/patches/patch-r11-native.py).
- **Image accounting.** A live `VkDeviceMemory` histogram by NVN format is logged with the
  60-frame report, which is how the R11G11B10F and D32F sets were sized. Patch:
  [tools/patches/patch-imgstats.py](tools/patches/patch-imgstats.py).
- **Pipelines.** The pipeline cache is capped (`NX_PIPE_CAP`, default 2048) with deferred
  destruction; the tutorial's UI reaches about 2100 live pipelines, so the cap is a band-aid
  rather than a fix, and pipeline memory is a large part of the 6 GB budget.

Open:

- **Free-roaming plaza rendering.** The November 22 fix verifies the café camera,
  the square behind it and NPC faces. Earlier `cProgress` routes produced a black
  scene; those routes have not yet been repeated with the latest runtime. See the
  [verified scope](docs/PLAZA_FACE_TEXTURE_COPIES.md).
- **UI job stall at the character→tutorial transition.** About one boot in three the game stops
  advancing at frame ~2933–2942 with no render thread activity: the main thread waits in
  `Lp::UI::Impl::JobMgr::endRun` on a light event while a UI job worker is still inside
  `nn::font::TextureCache::CalculateKerning` → `FSS_set_scale`, so the job never completes.
  Re-running the same script usually passes. The stack is in the font code path whose atlas is
  handled by the atlas-refresh fix above, so the face/glyph-cache handling is the first suspect.
- **Font layout loop.** A `FSS_set_scale` layout can keep the UI job worker inside the glyph
  loop for minutes. The temporary 512-glyph cap
  ([tools/patches/patch-fss-loop-cap.py](tools/patches/patch-fss-loop-cap.py)) returns `0x131`
  after the cap, which keeps the job manager alive; the face removal and atlas handling are the
  real fix and remain open.
- **Characters (PlayerMake verified in isolated runs).** The descriptor/winding fix
  restores the visible character materials; see the update above. Concurrent-replay
  stress stability and character rendering in other scenes remain unverified.
- **Device memory.** On the 6 GB laptop GPU the load still briefly peaks above the R11G11B10F
  savings: several runs log `vkAllocateMemory failed (-2)` around the character customisation
  load (live images 2.6 GB at frame 233) and either recover or stall. The live set fell to
  1.2–1.7 GB once the tutorial is up, so the peak, not the steady state, is the problem.
- **Loading is slow.** The "now loading" screen with the ink spinner runs at 0.8–6 fps because
  the game's own texture registration and decompression work runs as recompiled guest code;
  once loading finishes the title screen runs at 33–58 fps.

## Start here

| What you want | Where to go |
|---|---|
| What is known, what is not, and in what order to read | [STATUS.md](doc/STATUS.md) |
| **Where the platform layer actually is — 51/51 provider map** | **[PLATFORM_LAYER_FOUND.md](doc/PLATFORM_LAYER_FOUND.md)** |
| How far the port gets on screen right now | [RECOMP_BOOT_TO_UI.md](doc/RECOMP_BOOT_TO_UI.md) |
| The decoded startup chain | [BOOT_CALLGRAPH.md](doc/BOOT_CALLGRAPH.md) |
| The whole `main` module in one document | [ENGINE_REFERENCE.md](doc/ENGINE_REFERENCE.md) |

### Porting

- Scope and target: [PORTING.md](doc/PORTING.md), [BOOT_MILESTONE.md](doc/BOOT_MILESTONE.md), [BOOT_ENGINE_ORDER.md](doc/BOOT_ENGINE_ORDER.md)
- Worklist and platform contract: [PORT_WORKLIST.md](doc/PORT_WORKLIST.md), [PLATFORM_IMPLEMENTATION_SPEC.md](doc/PLATFORM_IMPLEMENTATION_SPEC.md), [PLATFORM_REFERENCE.md](doc/PLATFORM_REFERENCE.md)
- Where the platform layer lives: [PLATFORM_LAYER_LOCATION.md](doc/PLATFORM_LAYER_LOCATION.md)
- Graphics path: [GRAPHICS_NVN.md](doc/GRAPHICS_NVN.md), [GRAPHICS_SCOPE.md](doc/GRAPHICS_SCOPE.md)

### Background and coverage

- Engine and middleware: [ENGINE_RECONSTRUCTION.md](doc/ENGINE_RECONSTRUCTION.md), [SEAD_COVERAGE.md](doc/SEAD_COVERAGE.md), [NNWARE_COVERAGE.md](doc/NNWARE_COVERAGE.md), [AGL_COVERAGE.md](doc/AGL_COVERAGE.md)
- `sdk` module: [SDK_ANALYSIS.md](doc/SDK_ANALYSIS.md), [SDK_REFERENCE.md](doc/SDK_REFERENCE.md)
- Layout verification: [VERIFICATION.md](doc/VERIFICATION.md), [VTABLE_VERIFICATION.md](doc/VTABLE_VERIFICATION.md)
- Static-analysis tool history: [DECOMPILATION_UNBLOCKED.md](doc/DECOMPILATION_UNBLOCKED.md), [DECOMPILED_BODIES.md](doc/DECOMPILED_BODIES.md)
- Wider ecosystem survey: [ECOSYSTEM.md](doc/ECOSYSTEM.md), [subsystem-map.txt](subsystem-map.txt)

## In this document

[Status](#status) · [Target](#target) · [NSO container layout](#nso-container-layout) ·
[Architecture observations](#architecture-observations) · [Memory map](#memory-map) ·
[Subsystem decomposition](#subsystem-decomposition) · [Content pipeline](#content-pipeline) ·
[Toolchain](#toolchain) · [Reproduction](#reproduction) · [Limitations](#limitations) ·
[Legal](#legal) · [License](#license)

---

## Status

| Area | State |
|---|---|
| Target identification | Done |
| Container/format handling | Done |
| Memory map | Done |
| Function/symbol inventory | Done (113,150 functions) |
| Subsystem decomposition | Done (55 namespaces) |
| Engine & middleware identification | Done |
| **Recompiled PC port** | Boots to the in-game UI: `RootTask::prepare_`, display loop, PlayerMake character creation, the title screen at 1920×1080, and the first-launch tutorial - [RECOMP_BOOT_TO_UI.md](doc/RECOMP_BOOT_TO_UI.md). The tutorial advances past aim/ZR with legible guide text, and the Move page's central 960×540 3D room renders. The tutorial→plaza boundary is under test: an idempotent patch redirects the tutorial's `5 → 6` to warp state 7, and the 21-state UI/page manager's real `4 → 5` handoff loads the Off the Hook news scene (the old table's state-5 entry is null because the transition creates a new page manager). The earlier `4 → 7` detour reached the gear-selection screen and stalled at null state 9; it is a diagnostic, not the plaza path. The plaza café scene and intact NPC faces are verified with the texture-copy fix; free-roaming rendering remains unverified. The news scene and its two hosts render in the central 960×540 viewport. About one boot in three stalls at the character→tutorial UI job transition. |

Everything below is static analysis of the shipped binary unless a section says
otherwise; runtime findings from the port are labelled as such. Behaviour is only
claimed where it has been observed or verified against the original instructions.

---

## Target

| Property | Value |
|---|---|
| Module | `exefs/main` (23,717,627 bytes) |
| Container | **NSO0** (not an ELF on disk) |
| Architecture | AArch64, 64-bit little-endian |
| Title ID | `01003bc0000a0000` |
| ACID | `Is Retail: 1` |
| Build ID | `F18FF3CFCBAD0884D72ABBEB6C540D6B00000000000000000000000000000000` |
| Main thread stack | `0x100000` |
| Main thread priority | 44 (ACID allowed range 28–59) |
| ExeFS siblings | `main.npdm`, `rtld`, `sdk`, `subsdk0`–`subsdk3` |
| Image base (as loaded) | `0x7100000000` |

### Confirmation that this is Splatoon 2

Resource names recovered from `.rodata` are conclusive:

```
WeaponInfo_%s.byml      GearInfo_%s.byml        UdemaeGrade.byml
TankInfo.byml           SkillInfo.byml          BrandInfo.byml
BottomInfo.byml         HairInfo.byml           PaintResTex.byml
PlayerRank.byml         EnemyInfo.byml          DamageRateInfo.byml
MapInfo.byml            NpcInfo.byml            ActorDb.byml
WorldHotaruTalkInfo.byml                        WorldHotaruFreeTalkInfo.byml
```

The map that shipped as **MakoMart** carries the internal codename **Blitz** —
`Map/Blitz.mutre.szs` — independently corroborated by a `BlitzViewer` symbol
namespace in the binary.

---

## NSO container layout

`main` is an NSO0 container: the sections are LZ4-compressed and packed
back-to-back on disk, but each section's *memory* offset is page-aligned. That
gap is the single most important detail when reconstructing the image.

| Section | Memory range | Size |
|---|---|---|
| `.text` | `0x0000000` – `0x1415068` | 21,045,608 |
| `.rodata` | `0x1416000` – `0x2d624b3` | 26,526,899 |
| `.rwdata` | `0x2d63000` – `0x2fdb1b0` | 2,589,104 |
| `.bss` | `0x2fdc000` – `0x3699e50` | 7,065,504 |

### MOD0

The module header `MOD0` sits at **`.text+0x8`**. Per the
[SwitchBrew MOD specification](https://switchbrew.org/wiki/MOD) it is a
replacement for `PT_DYNAMIC` and **contains no entry point**:

| Offset | Field | This build |
|---|---|---|
| 0x0 | Signature `"MOD0"` | `4d4f4430` |
| 0x4 | `DynamicOffset` | `0x2f9a468` |
| 0x8 | `BssStartOffset` | `0x2fdbff8` |
| 0xC | `BssEndOffset` | `0x3698f98` |
| 0x10 | `ExceptionInfoStartOffset` | `0x2921ec0` |
| 0x14 | `ExceptionInfoEndOffset` | `0x2a00eac` |
| 0x18 | `ModuleOffset` (runtime-generated, ≈ `.bss` base) | `0x2fdbff8` |

> **Correction.** An earlier revision of this README derived an "entry VA" from
> `entryTarget + entryOffset` using offsets `0x10`/`0x14`. Those fields are
> exception-handling metadata. There is no entry point in MOD0; the module is
> entered through the dynamic section. See
> [BOOT_MILESTONE.md](doc/BOOT_MILESTONE.md) for the real boot chain.

The dynamic section (VA `0x2f9a470`) carries the boot-relevant pointers:

```
DT_INIT          = 0x24
DT_FINI          = 0x160
DT_INIT_ARRAY    = 0x2fd7f90      1604 static constructors
DT_INIT_ARRAYSZ  = 0x3220
```

### A note on a NSO header field

The 32-bit field at NSO header offset `0x40` is **reserved**. It is not a `.bss`
address, and it must not be read as one — in this container it holds the `.data`
section's compressed size. Treating it as an address produces a `.bss` that
overlaps `.rwdata`. `.bss` follows the last initialised section in memory.

---

## Architecture observations

`.text` holds 5,264,410 instructions. Instruction census:

| Encoding | Count | Meaning |
|---|---|---|
| `STP x29,x30,[sp,#-N]!` | 7,316 | function prologues (lower bound on functions) |
| `STP x29,x30,[sp,#N]` | 60,453 | saved-frame stores |
| `B` (`0x14......`) | 114,236 | unconditional branches |
| `PACIBSP` / `AUTIBSP` | **0** | no pointer authentication |
| `BTI c` | **0** | no branch target identification |

The first instruction at VA `0x100` is `stp x29,x30,[sp,#-0x10]!`, a textbook
prologue confirming `.text` begins with code.

> **Inference.** Pointer authentication and BTI are the mitigations introduced by
> Nintendo's later SDKs. Their complete absence is consistent with a build from
> the 2017 launch-era toolchain. This is an inference from instruction absence,
> not a build-string observation.

---

## Memory map

As reconstructed by an analysis load of the module (18 blocks):

```
.text          7100000000   21,045,608  r-x
.plt           7101412168       12,032  r-x
.rodata        7101416000           72  r--
.rela.dyn      7101416048    6,121,056  r--   dynamic relocations
.rela.plt      71019ec6a8       18,048  r--
.hash          71019f0d28    1,110,904  r--
.gnu.hash      7101b000a0    1,238,848  r--
.dynsym        7101c2e7e0    3,518,952  r--   148,138 symbols
.dynstr        7101f899c8    8,828,579  r--   8.8 MB of names
.rodata.1      71027f506b    5,690,440  r--
.data          7102d63000    2,323,568  rw-
.dynamic       7102f9a470          400  rw-
.data.1        7102f9a600           80  rw-
.got.plt       7102f9a650        6,040  rw-
.got           7102f9bde8      246,184  rw-
.init_array    7102fd7f90       12,832  rw-
.bss           7102fdc000    7,065,504  rw-
```

**The module is not stripped.** The embedded ELF dynamic symbol table survives:
3.5 MB of `.dynsym` and 8.8 MB of `.dynstr`. This is the single most valuable
property of this target — analysis starts from 113,150 real function names rather
than `FUN_xxxxxxxx`.

---

## Subsystem decomposition

113,150 functions across 55 top-level namespaces.

| Namespace | Functions | Interpretation |
|---|---:|---|
| `Game` | 28,439 | core gameplay |
| `nn` | 15,953 | NintendoSDK |
| `Lp` | 10,672 | game framework layer |
| `Cmn` | 4,447 | shared game code |
| `sead` | 4,022 | first-party C++ library |
| `agl` | 2,852 | graphics |
| `aal` | 2,264 | SDK applet/UI |
| `gsys` | 2,099 | game system layer |
| `Cui` | 1,815 | SDK UI components |
| `eui` | 803 | SDK extended UI |
| `Lobby` | 792 | online lobby |
| `enl` | 717 | — |
| `Cnet` | 590 | network |
| `Match` | 555 | matchmaking |
| `xlink2` | 548 | audio/effect middleware |
| `Shop` | 509 | in-game shop |
| `pead` | 490 | sound |
| `UICheck` | 413 | UI validation |
| `MiniGame` | 184 | — |
| `PlayerMake` | 132 | character creation |
| `Cstm` | 121 | customization |
| `DbgSetting` | 120 | debug settings |
| `PlayerViewer` | 86 | debug viewer |

Plus 33,692 `_Z`-mangled functions (operators, thunks, templates) and 327 plain-C
functions.

### Internal tooling present in the retail build

Debug and test harnesses survive in the shipping binary:

```
DbgSetting 120   PlayerViewer 86   UdgwTest 66      NisdTest 33
EnemyObjViewer 28   ScheduleViewer 27   YmgcTest 25   JintTest 21
GearUnsetupTest 20  BlitzViewer 9   GndColTest 7      MrmtTest 3
```

### Engine and middleware

| Component | Evidence |
|---|---|
| **sead** | `sead::CalculateTask` (calculate/draw task graph), `ExpHeap`, `CriticalSection`, `SafeStringBase`, `Matrix34f`, `TreeNode`, `Path::getExt` |
| **agl** | 2,852 functions, 6,024 `.rodata` hits |
| **Radiance** | `Etc/BRDFFitting/ggx_ltc.byml` (GGX LTC BRDF fitting) |
| **NintendoWare / Nw4f** | 35 `.rodata` hits |
| `nn::nex` | Nintendo networking |
| `nn::bcat` | DeliveryCache (background content delivery) |
| `nn::aoc` | add-on content |
| `nn::nfp` | Amiibo (`Cmn::Def::isSupportedAmiibo`) |
| libcurl | 24 functions / 36 symbols — HTTP |
| **wslay** | 53 functions — WebSocket |
| zlib | 49 functions / 63 symbols |
| libc++ (`std::__1`) | 292 functions |
| `__nnmusl` | Nintendo's musl-derived libc |

The libcurl + wslay + `Cnet`/`Match`/`Lobby`/`Shop` combination is consistent with
a live-service architecture.

---

## Content pipeline

Resource paths recovered from `.rodata`:

```
Model/%s.Nin_NX_NVN.szs      NX NVN (NVIDIA) model container
Map/%s.szs                   Map/Blitz.mutre.szs
Env/%s.szs                   Etc/LightCtrl/%s.byml
Nin_NX_NVN.release.szs       Etc/BRDFFitting/ggx_ltc.byml
HapTexture.bfres             PanelTexture.bfres        IconTexture.bfres
```

One string leaks the internal build toolchain:

```
File = %%AGL_ROOT%%/tools/bat/convertTempTexture.bat, NoWindow = True,
WindowStyle = Hidden, WaitEnd = True, Arg = %%AGL_ROOT%%/tools/temporary/temp_proj_light.bfres
```

`.mutre` is a distinct map variant format from `.szs`.

---

## Toolchain

### Prerequisites

- **Ghidra 12.1.2** (the extension below matches this version)
- **JDK 21+** — `JAVA_HOME` must point at the JDK root
- **[SwitchLoader](https://github.com/Adubbz/Ghidra-Switch-Loader)** — Ghidra
  loader for Nintendo Switch formats. Provides both NSO loading and the ELF
  `.dynsym` recovery used here.
- **hactool** — to extract the ExeFS from the XCI and decompress NSO sections
- **Node.js 18+** for the scripts in `tools/`
- **Python 3** via Ghidra's PyGhidra if you want the scripted inventory export

### Environment

```powershell
$env:GHIDRA_INSTALL_DIR = 'C:\path\to\ghidra_12.1.2_PUBLIC'
$env:JAVA_HOME          = 'C:\Program Files\Java\jdk-21.0.12'
```

Install SwitchLoader through Ghidra's *File → Install Extensions…*, then restart
Ghidra. Do not place the same extension in both the Ghidra install and the user
extension directory — Ghidra aborts with
`Multiple modules collided with same name`.

### Extract the target

```powershell
hactool -t xci --exefsdir=exefs "Splatoon 2 USA.xci"
hactool -t nso exefs/main --uncompressed=main.decompressed
```

Keys are required for the XCI but **are not part of this repository** and must
never be committed.

---

## Reproduction

### 1. Export the symbol inventory

PyGhidra must be started explicitly, otherwise Python scripts fail with
*"Ghidra was not started with PyGhidra"*:

```powershell
& "$env:GHIDRA_INSTALL_DIR\support\pyghidraRun.bat" -H `
    "<project-dir>" Sp2 `
    -import "exefs\main" `
    -noanalysis `
    -scriptPath "<repo>\tools\ghidra" `
    -postScript ExportInventory.py "<repo>\inventory.txt" `
    -deleteProject
```

Expected:

```
ExportInventory wrote inventory.txt (functions=113150 symbols=148138 strings=146621)
```

An import-only pass (`-noanalysis`) is deliberate: the ELF symbol table gives the
function names without paying for analysis. Function *sizes* from this pass are
placeholders and must not be interpreted as code sizes.

### 2. Analyse the inventory

```bash
node tools/static/analyze-inventory.mjs inventory.txt
node tools/static/namespace-report.mjs   inventory.txt
node tools/static/subsystem-map.mjs      inventory.txt subsystem-map.txt
node tools/static/symbol-census.mjs      main.decompressed
node tools/static/check-prologue.mjs     main.decompressed
```

### 3. Container tooling

`tools/nso/nso2elf.mjs` rebuilds a loadable ELF64 from a decompressed NSO. It
exists for analysis engines without NSO support; Ghidra with SwitchLoader does
not need it.

```bash
node tools/nso/nso2elf.mjs main.decompressed main.elf
node tools/nso/validate-elf.mjs main.elf      # structural self-check
node tools/nso/mod0-exports.mjs main.decompressed
```

`validate-elf.mjs` checks the ELF header, the `p_vaddr ≡ p_offset (mod align)`
segment rule, segment/section overlap, and `.bss` placement. It was written after
four real layout bugs were found by hand.

---

## Limitations

These are genuine, unresolved gaps. Do not read the tables above as a complete
account of the binary.

1. **No function bodies were decompiled.** The inventory is symbol-level only.
   Consequently **no claim about runtime behaviour is made anywhere in this
   repository.**

2. **Full auto-analysis does not complete.** Ghidra's headless analyzer wedges
   reproducibly. 22 functions recurse through computed jumps whose targets fall
   outside the image; the log then advances only ~99 bytes per 3 minutes:

   ```
   WARN Decompiling 710090ab30: Unable to read bytes at ram:23504cd0fec
   ```

   This is the decompiler following a computed jump, not a defect in the
   reconstructed image. Running analysis in the **Ghidra GUI**, which can be
   driven incrementally, is the recommended way past it.

3. **REA cannot drive this target on Windows.** The REA 6.5.0 Ghidra adapter
   admits only x86/x86-64 PE and explicitly selected raw 6502 images:

   > "Windows Ghidra P0 accepts native x86 and x86-64 PE applications and DLLs,
   > and explicitly selected raw 6502 images"

   Both an ELF and a headerless `--architecture arm64` attempt are rejected with
   `target_format_unsupported`. Hopper is macOS-only and IDA was unregistered.
   The Ghidra installation itself does ship AArch64, so this is an adapter
   restriction, not a missing processor module.

4. **MOD0 export-table parsing is unresolved.** Two candidate field layouts gave
   contradictory results (one negative offset, one past EOF), so no function
   names in this repository are derived from the MOD0 table. The names come from
   the ELF `.dynsym` via SwitchLoader.

5. **Namespace attribution is by symbol prefix only.** A namespace label
   describes where a symbol is declared, not what the code does.

---

## Legal

This repository contains **no game code, no game data, and no cryptographic
keys** — only analysis notes and original tooling. Splatoon 2 and Nintendo
Switch are trademarks of Nintendo. No affiliation or endorsement is claimed.
Intended for interoperability research and preservation; use your own legally
obtained copy of the game.

## Contributors

- [Azlekayn](https://github.com/azlekayn) — extended the Splatoon 2
  reverse-engineering work into the [Inksplash2](https://github.com/azlekayn/Inksplash2)
  Linux and Steam Deck port, contributing runtime and recompiler fixes, PC input and
  scripted-input tooling, boot and tutorial-flow testing, Vulkan rendering
  investigations, and network-stack research.

## License

Original tooling and notes in this repository are released under the MIT License.
See [LICENSE](LICENSE).
