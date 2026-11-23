#!/usr/bin/env python3
"""Apply reversible US 1.0.0 plaza FPS and dynamic resolution options.

No NSO/image bytes are modified. Validate the original NSO build ID, image
instructions and generated C++ anchors before changing the external runtime.
"""
import argparse
import os
from pathlib import Path

BUILD_ID = bytes.fromhex('F18FF3CFCBAD0884D72ABBEB6C540D6B' + '00' * 16)
INCLUDE = b'#include "sp2_gameplay_options.h" // PATCH-SP2-GAMEPLAY-OPTIONS\n'
SITES = (
    ('gen/main/code_006.cpp', 0x51C2C, bytes.fromhex('81010054'),
     b'    if (!c.zf) goto L_51C5C; // b.ne #0x51c5c\n',
     b'    if (nx::sp2::plaza_60fps_enabled() || !c.zf) goto L_51C5C; // PATCH-SP2-PLAZA-60FPS: b #0x51c5c\n'),
    ('gen/main/code_348.cpp', 0x1021FAC, bytes.fromhex('768f0f94'),
     b'    c.x[30] = NXB + 0x1021fb0ull; main_01405D84(c); // bl #0x1405d84\n',
     b'    if (!nx::sp2::dynamic_resolution_disabled()) { c.x[30] = NXB + 0x1021fb0ull; main_01405D84(c); } // PATCH-SP2-DYNAMIC-RESOLUTION: nop\n'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))))
    parser.add_argument('--nso', type=Path, help='Original, unmodified US 1.0.0 ExeFS/main NSO')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    expected_header = (Path(__file__).resolve().parent.parent / 'runtime/sp2_gameplay_options.h').read_bytes()
    header = root / 'runtime/src/sp2_gameplay_options.h'
    try:
        if not args.restore:
            if not args.nso:
                parser.error('--nso is required to verify the supported build ID')
            with args.nso.open('rb') as f:
                nso_header = f.read(0x60)
            if nso_header[:4] != b'NSO0' or nso_header[0x40:0x60] != BUILD_ID:
                raise ValueError('NSO build ID mismatch')
            with (root / 'private/analysis/main.bin').open('rb') as f:
                for _, address, instruction, _, _ in SITES:
                    f.seek(address)
                    if f.read(4) != instruction:
                        raise ValueError(f'Original image instruction mismatch at {address:#x}')
        changes = []
        states = []
        for relative, _, _, old, new in SITES:
            path = root / relative
            data = path.read_bytes()
            if data.count(old) == 1 and new not in data and INCLUDE not in data:
                states.append(False)
                result = INCLUDE + data.replace(old, new, 1)
            elif data.count(new) == 1 and old not in data and data.count(INCLUDE) == 1:
                states.append(True)
                result = data.replace(new, old, 1).replace(INCLUDE, b'', 1)
            else:
                raise ValueError(f'Generated source anchor mismatch: {relative}')
            if states[-1] == args.restore:
                changes.append((path, result))
        if len(set(states)) != 1:
            raise ValueError('Partial installation; no files changed')
        if header.exists() and header.read_bytes() != expected_header:
            raise ValueError('Options header differs; no files changed')
        if header.exists() != states[0]:
            raise ValueError('Options header/source state mismatch')
        if not changes:
            print('Already restored' if args.restore else 'Already applied')
            return
        if args.check:
            print('Can restore' if args.restore else 'Can apply: verified US 1.0.0 build and both instruction sites')
            return
        for path, data in changes:
            path.write_bytes(data)
        if args.restore:
            header.unlink()
        else:
            header.write_bytes(expected_header)
        print('Restored byte-exact source anchors' if args.restore else 'Applied; rebuild code_006.cpp and code_348.cpp. Both options default off.')
    except (OSError, ValueError) as error:
        raise SystemExit(f'Preflight failed: {error}')


if __name__ == '__main__':
    main()
