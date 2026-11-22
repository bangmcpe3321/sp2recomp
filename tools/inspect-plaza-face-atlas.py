"""Inspect the generated plaza body albedo in a RenderDoc capture.

Run only after the live game has exited. No shader/resource replacement is used.
Discovery uses material binding names and texture metadata, never fixed event/resource IDs.
The default inspects the first matching body atlas found while walking scene draws backwards;
--all inspects all matching atlases. A copy can occur before the captured frame, so copy use
is reported rather than required. Opaque coverage is a texture check, not whole-scene success.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path)
    p.add_argument('--out', type=Path, help='New output directory (default: <capture stem>_face_atlas)')
    p.add_argument('--json', type=Path, dest='json_path', help='Optional additional JSON report path')
    p.add_argument('--renderdoc-module-dir', type=Path,
                   default=None)
    p.add_argument('--all', action='store_true', help='Scan every draw to the primary scene target')
    p.add_argument('--min-opaque-fraction', type=float,
                   help='Fail if fewer than this fraction of atlas texels have alpha 255 (0..1)')
    a = p.parse_args()
    if a.min_opaque_fraction is not None and not 0 <= a.min_opaque_fraction <= 1:
        p.error('--min-opaque-fraction must be between 0 and 1')
    if not a.capture.is_file():
        p.error(f'Capture does not exist: {a.capture}')
    return a


def flatten(actions):
    for action in actions:
        yield action
        yield from flatten(action.children)


def alpha_statistics(raw, width, height):
    expected = width * height * 4
    if len(raw) != expected:
        raise RuntimeError(f'Expected tightly packed RGBA8 mip data ({expected} bytes); received {len(raw)}')
    pixels = width * height
    histogram = Counter(raw[3::4])
    return {
        'pixels': pixels,
        'nonzero_bytes': sum(b != 0 for b in raw),
        'alpha_histogram': {str(i): histogram.get(i, 0) for i in range(256)},
        'alpha_zero_fraction': histogram[0] / pixels,
        'alpha_opaque_fraction': histogram[255] / pixels,
        'alpha_at_least_128_fraction': sum(n for value, n in histogram.items() if value >= 128) / pixels,
        'channel_means': [sum(raw[c::4]) / pixels / 255 for c in range(4)],
        'most_common_rgba': [{'rgba': list(pixel), 'count': count}
                             for pixel, count in Counter(zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4])).most_common(8)],
    }


def inspect(a, rd):
    out = a.out or a.capture.with_name(a.capture.stem + '_face_atlas')
    out.mkdir(parents=True, exist_ok=False)
    report = {'capture': str(a.capture.resolve()), 'output': str(out.resolve()),
              'discovery': 'all scene draws' if a.all else 'first matching atlas from reverse scene draw order',
              'atlases': []}
    cap = rd.OpenCaptureFile()
    controller = None
    try:
        status = cap.OpenFile(str(a.capture), '', None)
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError(f'OpenFile failed: {status}')
        status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError(f'OpenCapture failed: {status}')
        draws = [action for action in flatten(controller.GetRootActions()) if action.flags & rd.ActionFlags.Drawcall]
        if not draws:
            raise RuntimeError('No draw calls found')
        textures = {texture.resourceId: texture for texture in controller.GetTextures()}
        hdr_targets = {resource for resource, texture in textures.items()
                       if texture.width >= 600 and texture.arraysize == 1 and
                       ('R11G11B10' in texture.format.Name() or 'R16G16B16A16_FLOAT' == texture.format.Name())}
        counts = Counter(resource for action in draws for resource in set(action.outputs) if resource in hdr_targets)
        if not counts:
            raise RuntimeError('No primary HDR scene target found')
        scene = counts.most_common(1)[0][0]
        scene_draws = [action for action in draws if scene in action.outputs]
        report['scene'] = {'resource': str(scene), 'width': textures[scene].width,
                           'height': textures[scene].height, 'draw_count': len(scene_draws)}
        non_body_shaders = set()
        seen_atlases = set()
        inspected = 0
        for action in reversed(scene_draws):
            controller.SetFrameEvent(action.eventId, False)
            pipeline = controller.GetPipelineState()
            shader = pipeline.GetShader(rd.ShaderStage.Pixel)
            inspected += 1
            if shader in non_body_shaders:
                continue
            reflection = pipeline.GetShaderReflection(rd.ShaderStage.Pixel)
            names = {binding.name for binding in reflection.readOnlyResources} if reflection else set()
            if not {'fp_t_tcb_8', 'fp_t_tcb_1E'}.issubset(names):
                non_body_shaders.add(shader)
                continue
            for binding in pipeline.GetReadOnlyResources(rd.ShaderStage.Pixel):
                if reflection.readOnlyResources[binding.access.index].name != 'fp_t_tcb_8':
                    continue
                descriptor = binding.descriptor
                texture = textures.get(descriptor.resource)
                if texture is None or (texture.width, texture.height, texture.mips, texture.arraysize) != (512, 256, 10, 1):
                    continue
                if texture.format.Name() != 'R8G8B8A8_UNORM' or descriptor.resource in seen_atlases:
                    continue
                seen_atlases.add(descriptor.resource)
                controller.SetFrameEvent(action.eventId, True)
                subresource = rd.Subresource()
                subresource.mip = descriptor.firstMip
                subresource.slice = descriptor.firstSlice
                raw = bytes(controller.GetTextureData(descriptor.resource, subresource))
                statistics = alpha_statistics(raw, max(1, texture.width >> descriptor.firstMip),
                                               max(1, texture.height >> descriptor.firstMip))
                usage = [{'event': use.eventId, 'usage': use.usage.name, 'usage_value': int(use.usage)}
                         for use in controller.GetUsage(descriptor.resource)]
                copies = [use for use in usage if use['usage_value'] in (int(rd.ResourceUsage.CopyDst),
                                                                        int(rd.ResourceUsage.Copy))]
                path = out / f'atlas_{len(report["atlases"])}.png'
                save = rd.TextureSave()
                save.resourceId = descriptor.resource
                save.destType = rd.FileType.PNG
                save.mip = descriptor.firstMip
                status = controller.SaveTexture(save, str(path))
                if status != rd.ResultCode.Succeeded:
                    raise RuntimeError(f'Atlas SaveTexture failed: {status}')
                item = {'material_event': action.eventId, 'index_count': action.numIndices,
                        'pixel_shader': str(shader), 'resource': str(descriptor.resource),
                        'format': texture.format.Name(), 'width': texture.width, 'height': texture.height,
                        'mips': texture.mips, 'sampled_mip': descriptor.firstMip,
                        'sampled_slice': descriptor.firstSlice, 'png': str(path.resolve()),
                        'usage': usage, 'copy_destination_usage': copies, **statistics}
                report['atlases'].append(item)
                (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(f"Atlas {descriptor.resource}, material {action.eventId}: "
                      f"opaque alpha {statistics['alpha_opaque_fraction']:.6%}, "
                      f"alpha >= 128 {statistics['alpha_at_least_128_fraction']:.6%}, "
                      f"copy destination uses {len(copies)}", flush=True)
            if report['atlases'] and not a.all:
                break
        report['scene_draws_inspected'] = inspected
        if not report['atlases']:
            raise RuntimeError('No body material with generated 512x256 RGBA8 ten-mip albedo was found')
        last = draws[-1]
        controller.SetFrameEvent(last.eventId, True)
        outputs = [target.resource for target in controller.GetPipelineState().GetOutputTargets()
                   if target.resource != rd.ResourceId.Null()]
        if not outputs:
            raise RuntimeError('Final draw has no color output')
        final_path = out / 'final.png'
        save = rd.TextureSave()
        save.resourceId = outputs[0]
        save.destType = rd.FileType.PNG
        status = controller.SaveTexture(save, str(final_path))
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError(f'Final SaveTexture failed: {status}')
        report['final'] = {'event': last.eventId, 'resource': str(outputs[0]), 'png': str(final_path.resolve())}
        passed = a.min_opaque_fraction is None or all(
            item['alpha_opaque_fraction'] >= a.min_opaque_fraction for item in report['atlases'])
        report['opaque_requirement'] = {'minimum_fraction': a.min_opaque_fraction, 'passed': passed}
        (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if a.json_path:
            a.json_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'Report: {out / "report.json"}', flush=True)
        return 0 if passed else 1
    finally:
        if controller is not None:
            controller.Shutdown()
        cap.Shutdown()


def main():
    a = arguments()
    if a.renderdoc_module_dir is not None:
        sys.path.insert(0, str(a.renderdoc_module_dir))
    import renderdoc as rd
    return inspect(a, rd)


if __name__ == '__main__':
    raise SystemExit(main())
