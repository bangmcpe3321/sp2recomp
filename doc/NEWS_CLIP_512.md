# News screen flicker (part 1): the composite was clipped to a 512x512 square

Updated: 2026-11-13. Everything below is measured on this machine; the evidence is kept under
`/home/hexa/sp2port/keep_ca1` … `keep_ca5` and `private/frames/keep_ab_a`, `keep8`.

## What was wrong

There are two separate defects behind the news screen's flicker. This document covers the one with a hard
geometric signature; the other (frames that arrive nearly black with sparse, quantised content) is separate
and **not** addressed here.

On the affected frames the composite `6a00ffea80` — declared **1570x921** — held correct scene content in a
**perfect 512x512 origin-anchored square** and nothing else:

| measurement | value |
|---|---|
| non-black pixels | **262,144** = 512x512, zero remainder |
| rows 0..511 | exactly 512 non-black pixels each, x = 0..511, identical on every row |
| rows 512..920 | exactly 0 |
| both boundary edges | no exceptions |

A power-of-two, origin-anchored rectangle is not something a fragment shader, depth test, cull mode, blend
factor or barrier can produce; those give geometry-shaped or noise-shaped results. It is an extent
disagreement.

**The content was correct**, which is what made this a rendering bug rather than a missing-draw bug:

| test | result |
|---|---|
| clipped corner vs a **full** bright frame's same corner | **99.87%** identical |
| same, treating it as the whole scene **scaled** into 512x512 | 27.05% |
| chance between two independent images on this palette | 14.86% |
| every other frame's corner | 0.00% |

So it is a **crop at 1:1**. That single measurement rules out the viewport (a small viewport would scale the
scene) and leaves exactly two mechanisms: a small render area, or a small scissor.

## The cause

`begin_rendering` folds the render area by **minimum over the colour attachments and then over the depth**:

```
extent = min(extent, colour0 >> level)      (the colour loop)
extent = min(extent, depth   >> level)      (the depth branch)   <- this one
```

On the affected frames the **depth handle `6a00fff968` had resolved to a 512x512 incarnation** while colour0
was 1570x921, so the fold produced 512x512 and every draw into the composite was clipped. The instrument line
that named it (run `ca2`'s log — its *log* is genuine even though its archive turned out to hold another arm's
images):

```
CLEARAREA f=6489 tgt=6a00ffea80 img=1570x921 lvl=0 extent=512x512 AREA=1 SCISSOR=0 fresh=0 cleared=0
          loadop=0 layout=1 sc=0 0 1570 921 hs=1 vp=0 0 1570 921 hv=1 depth=6a00fff968 d=512x512 n=1
```

Colour target 1570x921, **depth 512x512**, resulting extent 512x512, and the guest's own **viewport and
scissor both full size** — so the guest believed the target was 1570x921 and the clip came entirely from the
port's fold. `AREA=1 SCISSOR=0` rules out the scissor.

## The fix

`tools/patches/patch-keep-colour-area.py`, env `NX_KEEP_COLOUR_AREA=1`, **off by default** so the shipped
path is byte-for-byte unchanged. When the depth attachment is smaller than the colour extent, the depth
attachment is **dropped for that pass** so the colour image renders whole, and it is logged (`KEEPCOLOUR ...`).

Vulkan requires `renderArea` to lie within every attachment, so a 1570x921 area with a 512x512 depth view is
invalid and both cannot be kept. Dropping is safe here specifically because the composite's draw has the depth
test disabled (`depth func 4 write 0 ... test 0` in the draw trace), so no pixel test depends on the attachment.

## The evidence

**Use only this A/B.** An earlier attempt at this table (runs `ca1`–`ca5`) was invalidated by the runner's audit
and is recorded below under "Invalidated runs" so its numbers are never counted again.

The valid A/B was run with one script (`sp2win/route-news-clip-ab.ps1`), in one session, against one verified
binary, with each arm proving its own state from the **child's own log** rather than from the wrapper's
environment:

| | control `ctl1` | fix `fix1` |
|---|---|---|
| switch | `NX_KEEP_COLOUR_AREA` **removed** from the child env | `NX_KEEP_COLOUR_AREA=1` |
| **proof of arm state** (`KEEPCOLOUR` lines in the child's log) | **0** | **40** |
| instrument liveness (`CLEARAREA f=`) | 257 | 4 |
| **strict 512x512 rectangles in 40 composites** | **3** (6488, 6501, 6509) | **0** |
| dump-set hash | `6e707d96…` | `d799222c…` (different — arms independent) |
| dumps written | 05:50 | 06:06 |
| FATAL / CRASH | 0 | 0 |

The control reproduced the defect **3 times in 40 frames with the fix provably off**, and the fix arm produced
**0 in 40 with the fix provably on**. Same binary (`140e110ee087bb3f8e76917b5b27d88d`, both copies matching
before and after), same route, same window, independent dump sets.

### Invalidated runs, and exactly why (kept so this cannot recur)

| run | claim made at the time | why it does not count |
|---|---|---|
| `ca1` | 2 rectangles | Genuine (own dumps, own log), but it is the **instrument-only** run, not a control against the fix. |
| `ca2` | 2 rectangles | **No images of its own.** Its archive step ran after the whole A/B, so `keep_ca2` holds `keep_ca4`'s dump set byte-for-byte. Its genuine contribution is the *log* — the `CLEARAREA` line below. |
| `ca3` | 0 rectangles | Same contamination: `keep_ca3` is also `keep_ca4`'s images. Its log is genuine but it contributes no pixels. |
| `ca4` | 0 rectangles | Holds the one genuine dump set of the three — but see `ca5`. |
| `ca5` | "control, 0 rectangles" | **Void.** It was meant to be the fix-off control, but the fix fired (40 `KEEPCOLOUR` lines): the earlier arm script set `NX_KEEP_COLOUR_AREA=1` in its own environment, and clearing the variable in the caller did not reach the child. The switch is `getenv(...) != nullptr`, so any non-null value — even an empty string — enables it. It was a second fix-on run compared against fix-on. |

**The two process rules that came out of this audit**, both now enforced by `route-news-clip-ab.ps1`:

1. **A control is only a control if the fix's own log line is absent.** The wrapper's environment is not
   evidence; only the child process's output is. `grep -c KEEPCOLOUR <log>` must be `0` before any rectangle
   count is believed.
2. **Each arm must be archived, and verified, against its own log's mtime.** An archive step that runs after a
   whole A/B copies only the last arm's frames into every directory, which is the same class of error as the
   stale-dump contamination earlier in this project.


## Three instrument designs that failed first (kept so they are not repeated)

1. **A frame window cannot see this.** `trace_pass()` has a hard `n++ >= 8000` budget — ~727 records/frame,
   so 11 frames — and the composite renders at in-pass index **~690**, i.e. last. `rtfix1.log` covers frame
   6499, which *is* a rectangle frame, but truncated 178 records in: **zero** composite records captured. A
   truncated log also looks exactly like "no attachment was 512x512".
2. **"A 512x512 attachment or viewport exists"** fires ~6x/frame on good frames: 512x512 appears in every
   frame as a colour-less depth-only pass, and all 297 recorded 512x512 viewports belong to depth-only passes
   or to `6a00fff368`, never to the news chain.
3. **Firing only on passes that CLEAR** fired **0 times in 45,000 watched passes** — a clean, confident,
   wrong result. The composite is a pass **pair** (a full-size CLEAR pass, then a LOAD pass that does the
   drawing), so the clip is in the LOAD pass and the CLEAR-only predicate skipped it. A zero that looks like
   a healthy system is the most dangerous outcome in this project.

## What this does NOT fix

`6a00fff968` is declared at **23 different sizes** across one run — 960x540, 977x550, 1024x1024, 3000x3000,
1920x1080, 512x512, 1x1, 1x0, … — and resolves to different ones on different frames. That is the resolution
/ incarnation path (`nvn_incarnation.cpp`), and it is where the real fix belongs. This patch stops the
clipping and proves, with a control, that the fold is what clipped the colour target; it does not explain why
the size was wrong.

Also unchanged: the **second** flicker signature — frames whose studio target holds only sparse, quantised
content (4,587–15,692 non-black pixels at discrete levels, 60–91% pairwise overlap, **no rectangle**). That is
a different defect and must not be folded into this one.
