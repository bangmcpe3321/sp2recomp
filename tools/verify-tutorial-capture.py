#!/usr/bin/env python3
"""Check a tutorial/Aim-step capture's HDR range and optional tonemap filtering.

Requires RenderDoc's Python module on PYTHONPATH. This checks the captured view,
not completion of the tutorial, other scenes, or all possible HDR lighting.
"""

import argparse
from collections import Counter
import math
from pathlib import Path

import renderdoc as rd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--max-hdr', type=float, default=1000.0,
                        help='Upper HDR bound for this tutorial view (default: 1000)')
    parser.add_argument('--save-frame', type=Path, help='Optionally save the final replay color target as PNG')
    parser.add_argument('--require-linear-lut', action='store_true',
                        help='Also require linear min/mag filtering on the tonemap 3D lookup')
    args = parser.parse_args()
    if not math.isfinite(args.max_hdr) or args.max_hdr <= 0:
        parser.error('--max-hdr must be finite and positive')

    capture = rd.OpenCaptureFile()
    controller = None
    try:
        result = capture.OpenFile(str(args.capture), '', None)
        if result != rd.ResultCode.Succeeded:
            raise RuntimeError(f'Cannot open capture: {result}')
        result, controller = capture.OpenCapture(rd.ReplayOptions(), None)
        if result != rd.ResultCode.Succeeded:
            raise RuntimeError(f'Cannot replay capture: {result}')

        def flatten(actions):
            for action in actions:
                yield action
                yield from flatten(action.children)

        draws = [a for a in flatten(controller.GetRootActions()) if a.flags & rd.ActionFlags.Drawcall]
        textures = {t.resourceId: t for t in controller.GetTextures()}
        candidates = {t.resourceId for t in textures.values()
                      if t.width >= 600 and t.height >= 300 and t.arraysize == 1
                      and 'R11G11B10' in t.format.Name()}
        counts = Counter(resource for a in draws for resource in set(a.outputs) if resource in candidates)
        if not counts:
            raise RuntimeError('No tutorial-sized R11G11B10 scene target found')
        scene = counts.most_common(1)[0][0]
        writer = next(a for a in reversed(draws) if scene in a.outputs)
        controller.SetFrameEvent(writer.eventId, True)
        low, high = controller.GetMinMax(scene, rd.Subresource(), rd.CompType.Typeless)
        minimum, maximum = list(low.floatValue[:3]), list(high.floatValue[:3])
        if not all(math.isfinite(v) and 0 <= v <= args.max_hdr for v in minimum + maximum):
            raise RuntimeError(f'HDR scene outside expected tutorial range: min={minimum}, max={maximum}')
        if max(maximum) <= 0.01:
            raise RuntimeError(f'HDR scene is black: max={maximum}')
        print(f'PASS: scene {scene}, event {writer.eventId}, min={minimum}, max={maximum}')

        if args.require_linear_lut:
            luts = {t.resourceId for t in textures.values()
                    if t.depth > 1 and t.arraysize == 1 and 'R11G11B10' in t.format.Name()}
            previous_outputs = None
            found = False
            for action in draws:
                outputs = tuple(action.outputs)
                first_in_pass = outputs != previous_outputs
                previous_outputs = outputs
                if not first_in_pass or action.eventId <= writer.eventId:
                    continue
                if not any(resource in textures and any(name in textures[resource].format.Name()
                           for name in ('R10G10B10A2', 'A2B10G10R10', 'A2R10G10B10'))
                           for resource in outputs):
                    continue
                controller.SetFrameEvent(action.eventId, True)
                used = list(controller.GetPipelineState().GetReadOnlyResources(rd.ShaderStage.Pixel))
                lookups = [d for d in used if d.descriptor.resource in luts]
                if not lookups or not any(d.descriptor.resource == scene for d in used):
                    continue
                for lookup in lookups:
                    filtering = lookup.sampler.filter
                    if filtering.minify != rd.FilterMode.Linear or filtering.magnify != rd.FilterMode.Linear:
                        raise RuntimeError(
                            f'Tonemap LUT {lookup.descriptor.resource} at event {action.eventId} '
                            f'is not linear: min={filtering.minify}, mag={filtering.magnify}')
                    print(f'PASS: tonemap event {action.eventId}, LUT {lookup.descriptor.resource}, linear min/mag')
                found = True
                break
            if not found:
                raise RuntimeError('No tonemap pass sampling both the scene and a 3D lookup was found')

        if args.save_frame:
            controller.SetFrameEvent(draws[-1].eventId, True)
            targets = controller.GetPipelineState().GetOutputTargets()
            if not targets or targets[0].resource == rd.ResourceId.Null():
                raise RuntimeError('Final draw has no color target to save')
            save = rd.TextureSave()
            save.resourceId = targets[0].resource
            save.destType = rd.FileType.PNG
            result = controller.SaveTexture(save, str(args.save_frame))
            if result != rd.ResultCode.Succeeded:
                raise RuntimeError(f'Cannot save replay frame: {result}')
    finally:
        if controller is not None:
            controller.Shutdown()
        capture.Shutdown()


if __name__ == '__main__':
    main()
