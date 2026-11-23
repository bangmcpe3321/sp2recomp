#!/usr/bin/env python3
"""Check the SPIR-V execution model against an independently known shader stage.

Usage: python3 verify_spirv_stage.py file.spv --stage compute
Run spirv-val separately; this check catches a valid module translated as the wrong stage.
"""
import argparse
from pathlib import Path
import struct

MODELS = {'vertex': 0, 'hull': 1, 'domain': 2, 'geometry': 3, 'fragment': 4, 'compute': 5}

def verify(data, stage):
    if len(data) < 20 or len(data) % 4:
        raise ValueError('Invalid SPIR-V byte length')
    words = struct.unpack('<' + 'I' * (len(data) // 4), data)
    if words[0] != 0x07230203:
        raise ValueError('Invalid SPIR-V magic')
    at, models = 5, set()
    while at < len(words):
        count, opcode = words[at] >> 16, words[at] & 0xffff
        if count == 0 or at + count > len(words):
            raise ValueError('Instruction outside SPIR-V bounds')
        if opcode == 15:
            if count < 4:
                raise ValueError('Truncated OpEntryPoint')
            models.add(words[at + 1])
        at += count
    if models != {MODELS[stage]}:
        raise ValueError(f'Execution model {models} does not match {stage} ({MODELS[stage]})')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spirv', type=Path)
    parser.add_argument('--stage', choices=MODELS, required=True)
    args = parser.parse_args()
    try:
        verify(args.spirv.read_bytes(), args.stage)
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(f'Execution model matches {args.stage}.')

if __name__ == '__main__':
    main()
