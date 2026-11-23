#!/usr/bin/env python3
"""Patch the external Maxwell harness to recognize headerless compute and every SPH stage.

Usage: python3 wsl-patch-shader-stage-detection.py [SP2PORT directory]
Rebuild tools/maxwell/spirv_harness/SpirvHarness.csproj afterward.
"""
import os
from pathlib import Path
import sys
import time

OLD_COMPUTE = 'bool compute = BitConverter.ToUInt32(code, 0) == ComputeMagic;'
NEW_COMPUTE = '''// Older NVN compute binaries start directly at the instructions (no version header).
            // A zero program start plus an explicit 3-D local size distinguishes them from graphics SPH.
            bool compute = BitConverter.ToUInt32(code, 0) == ComputeMagic ||
                (start == 0 && BitConverter.ToUInt32(code, 0) != 0x12345678 &&
                 BitConverter.ToUInt32(ctrl, 0x748) > 0 && BitConverter.ToUInt32(ctrl, 0x74c) > 0 && BitConverter.ToUInt32(ctrl, 0x750) > 0);'''
OLD_STAGE = 'ShaderStage stage = compute ? ShaderStage.Compute : sphType == 5 ? ShaderStage.Fragment : ShaderStage.Vertex;'
NEW_STAGE = '''ShaderStage stage = compute ? ShaderStage.Compute : sphType switch
            {
                1 => ShaderStage.Vertex, 2 => ShaderStage.TessellationControl,
                3 => ShaderStage.TessellationEvaluation, 4 => ShaderStage.Geometry,
                5 => ShaderStage.Fragment, _ => throw new ArgumentException("Unknown SPH stage")
            };'''

def patch(text):
    if NEW_COMPUTE in text and NEW_STAGE in text:
        return text
    if text.count(OLD_COMPUTE) != 1 or text.count(OLD_STAGE) != 1:
        raise RuntimeError('Unrecognized harness detection code; no files changed.')
    return text.replace(OLD_COMPUTE, NEW_COMPUTE).replace(OLD_STAGE, NEW_STAGE)

def main():
    port = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))).resolve()
    source = port / 'tools/maxwell/spirv_harness/Program.cs'
    original = source.read_bytes()
    changed = patch(original.decode('utf-8')).encode('utf-8')
    if changed == original:
        print('Shader stage detection already patched.')
        return
    backup = port / 'private/shader-stage-detection-backups' / str(time.time_ns()) / 'Program.cs'
    backup.parent.mkdir(parents=True)
    backup.write_bytes(original)
    source.write_bytes(changed)
    print(f'Patched {source}; original saved to {backup}')
    print('Rebuild SpirvHarness.csproj before using the standard translator.')

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, UnicodeError) as error:
        raise SystemExit(str(error))
