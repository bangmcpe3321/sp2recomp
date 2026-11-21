"""Check a PlayerMake Vulkan capture using RenderDoc's Python module.

Put the matching RenderDoc pymodules directory on PYTHONPATH, then run:
    python tools/verify-playermake-capture.py path/to/playermake_capture.rdc
Run replay after the game exits, not concurrently with a live capture.
"""

import argparse

import renderdoc as rd


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def actions(items):
    for action in items:
        yield action
        yield from actions(action.children)


def verify(controller):
    draws = {
        action.eventId: action
        for action in actions(controller.GetRootActions())
        if action.flags & rd.ActionFlags.Drawcall
    }
    textures = {texture.resourceId: texture for texture in controller.GetTextures()}
    mask = None
    first_material = None
    for event in sorted(draws):
        controller.SetFrameEvent(event, True)
        pipeline = controller.GetPipelineState()
        reflection = pipeline.GetShaderReflection(rd.ShaderStage.Pixel)
        if not reflection:
            continue
        for binding in pipeline.GetReadOnlyResources(rd.ShaderStage.Pixel):
            resource = reflection.readOnlyResources[binding.access.index]
            if resource.name == "fp_t_tcb_2A":
                mask = binding.descriptor.resource
                first_material = event
                break
        if mask is not None:
            break
    require(mask in textures, "No PlayerMake lighting-mask binding found")
    texture = textures[mask]
    passes = 0
    producers = 0
    for usage in controller.GetUsage(mask):
        event = usage.eventId
        if event >= first_material or event not in draws:
            continue
        controller.SetFrameEvent(event, True)
        pipeline = controller.GetPipelineState()
        vulkan = controller.GetVulkanPipelineState()
        targets = {target.resource for target in pipeline.GetOutputTargets()}
        samples = {
            binding.descriptor.resource
            for binding in pipeline.GetReadOnlyResources(rd.ShaderStage.Pixel)
        }
        targets.discard(rd.ResourceId.Null())
        samples.discard(rd.ResourceId.Null())
        require(not targets.intersection(samples), f"Attachment/sampler alias at event {event}")
        viewport = pipeline.GetViewport(0)
        require(
            (abs(viewport.width), abs(viewport.height)) == (texture.width, texture.height),
            f"Mask extent mismatch at event {event}",
        )
        if vulkan.depthStencil.depthTestEnable and mask in targets:
            producers += 1
            require(vulkan.rasterizer.frontCCW, f"Producer winding flipped at event {event}")
        passes += 1
    require(producers >= 1 and passes >= 5, "Expected a mask producer and four filter passes")
    controller.SetFrameEvent(first_material, True)
    data = bytes(controller.GetTextureData(mask, rd.Subresource()))
    require(len(data) == texture.width * texture.height * 4, "Expected an RGBA8 lighting mask")
    lit = sum(red > 200 and green > 200 for red, green in zip(data[0::4], data[1::4]))
    require(lit > 1000, f"Lighting mask empty or missing its green channel: {lit} lit pixels")
    print(f"PASS: {passes} mask passes, distinct surfaces, matching extents, correct winding; {lit} lit pixels")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture")
    args = parser.parse_args()
    capture = rd.OpenCaptureFile()
    controller = None
    try:
        status = capture.OpenFile(args.capture, "", None)
        require(status == rd.ResultCode.Succeeded, f"Cannot open capture: {status}")
        status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
        require(status == rd.ResultCode.Succeeded, f"Cannot replay capture: {status}")
        verify(controller)
    finally:
        if controller is not None:
            controller.Shutdown()
        capture.Shutdown()


if __name__ == "__main__":
    main()
