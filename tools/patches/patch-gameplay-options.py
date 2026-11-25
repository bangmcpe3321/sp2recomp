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
ORIGINAL_BRANCH = b'    if (!c.zf) goto L_51C5C; // b.ne #0x51c5c\n'
LEGACY_BRANCH = b'    if (nx::sp2::plaza_60fps_enabled() || !c.zf) goto L_51C5C; // PATCH-SP2-PLAZA-60FPS: b #0x51c5c\n'
OLD_SETTER = b'    c.x[1] = uint32_t(0x2ull); // mov w1, #2\n    c.x[30] = NXB + 0x51c5cull; main_00E67D58(c); // bl #0xe67d58\n'
INTERVAL_ONLY = b'    c.x[1] = nx::sp2::plaza_60fps_enabled() ? 1u : 2u; // PATCH-SP2-PLAZA-60FPS: retain renderer setup, change vblank interval\n    c.x[30] = NXB + 0x51c5cull; main_00E67D58(c); // bl #0xe67d58\n'
OLD_FLAG = b'    c.x[9] = uint32_t(uint32_t(uint32_t(c.x[9]) | uint32_t(0x1ull))); // orr w9, w9, #1\n'
FLAG_SETUP = OLD_FLAG + b'''    { uint64_t a = c.x[8] + 0x550ull; nx::st<uint32_t>(a, uint32_t(uint32_t(c.x[9]))); } // str w9, [x8, #0x550]
    c.x[8] = uint64_t(NXB + 0x2f9d000ull); // adrp x8, #0x2f9d000
    { uint64_t a = c.x[8] + 0x2a8ull; c.x[8] = uint64_t(nx::ld<uint64_t>(a)); } // ldr x8, [x8, #0x2a8]
    { uint64_t a = c.x[8]; c.x[0] = uint64_t(nx::ld<uint64_t>(a)); } // ldr x0, [x8]
'''
COUPLED_FLAG = b'    c.x[9] = nx::sp2::plaza_60fps_enabled() ? uint32_t(c.x[9]) & ~1u : uint32_t(c.x[9]) | 1u; // PATCH-SP2-FRAME-MODE: match full/half-rate calculation to vblank interval\n'
COUPLED_VERSION = FLAG_SETUP.replace(OLD_FLAG, COUPLED_FLAG) + INTERVAL_ONLY
SITES = (
    ('gen/main/code_006.cpp', 0x51C54, bytes.fromhex('e1031f32'),
     FLAG_SETUP + OLD_SETTER,
     FLAG_SETUP + OLD_SETTER + b'    // PATCH-SP2-PLAZA-NATIVE-ENTRY: loading and news retain native timing; gameplay switches at stateEnterProgress.\n'),
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
    legacy_header = expected_header.split(b'// PATCH-SP2-NEWS-TIMING\n')[0]
    header = root / 'runtime/src/sp2_gameplay_options.h'
    try:
        if args.restore:
            for relative in ('gen/main/code_204.cpp', 'gen/main/code_206.cpp'):
                path = root / relative
                if path.is_file() and b'PATCH-SP2-NEWS-LIFECYCLE' in path.read_bytes():
                    raise ValueError('Restore patch-plaza-news-timing.py first; its hooks require the timing header')
        if not args.restore:
            if not args.nso:
                parser.error('--nso is required to verify the supported build ID')
            with args.nso.open('rb') as f:
                nso_header = f.read(0x60)
            if nso_header[:4] != b'NSO0' or nso_header[0x40:0x60] != BUILD_ID:
                raise ValueError('NSO build ID mismatch')
            with (root / 'private/analysis/main.bin').open('rb') as f:
                f.seek(0x51C2C)
                if f.read(4) != bytes.fromhex('81010054'):
                    raise ValueError('Original scene branch mismatch at 0x51c2c')
                for _, address, instruction, _, _ in SITES:
                    f.seek(address)
                    if f.read(4) != instruction:
                        raise ValueError(f'Original image instruction mismatch at {address:#x}')
        changes = []
        states = []
        for relative, _, _, old, new in SITES:
            path = root / relative
            data = path.read_bytes()
            if relative == SITES[0][0]:
                if data.count(COUPLED_VERSION) == 1 and data.count(ORIGINAL_BRANCH) == 1 and data.count(INCLUDE) == 1:
                    states.append(True)
                    normalized = data.replace(COUPLED_VERSION, old, 1)
                    result = normalized.replace(INCLUDE, b'', 1) if args.restore else normalized.replace(old, new, 1)
                    changes.append((path, result))
                    continue
                if data.count(FLAG_SETUP + INTERVAL_ONLY) == 1 and data.count(ORIGINAL_BRANCH) == 1 and data.count(INCLUDE) == 1:
                    states.append(True)
                    normalized = data.replace(INTERVAL_ONLY, OLD_SETTER, 1)
                    if normalized.count(old) != 1:
                        raise ValueError('Interval-only upgrade anchor mismatch')
                    result = normalized.replace(INCLUDE, b'', 1) if args.restore else normalized.replace(old, new, 1)
                    changes.append((path, result))
                    continue
                if data.count(LEGACY_BRANCH) == 1 and ORIGINAL_BRANCH not in data and data.count(old) == 1 and data.count(INCLUDE) == 1:
                    states.append(True)
                    result = data.replace(LEGACY_BRANCH, ORIGINAL_BRANCH, 1)
                    result = result.replace(INCLUDE, b'', 1) if args.restore else result.replace(old, new, 1)
                    changes.append((path, result))
                    continue
                if data.count(ORIGINAL_BRANCH) != 1 or LEGACY_BRANCH in data:
                    raise ValueError('Scene branch mismatch; no files changed')
            if data.count(old) == 1 and new not in data and INCLUDE not in data:
                states.append(False)
                result = INCLUDE + data.replace(old, new, 1)
            elif data.count(new) == 1 and data.count(old) == new.count(old) and data.count(INCLUDE) == 1:
                states.append(True)
                result = data.replace(new, old, 1).replace(INCLUDE, b'', 1)
            else:
                raise ValueError(f'Generated source anchor mismatch: {relative}')
            if states[-1] == args.restore:
                changes.append((path, result))
        if len(set(states)) != 1:
            raise ValueError('Partial installation; no files changed')
        if header.exists() and header.read_bytes() not in (expected_header, legacy_header):
            raise ValueError('Options header differs; no files changed')
        if header.exists() != states[0]:
            raise ValueError('Options header/source state mismatch')
        if not changes:
            if not args.restore and header.read_bytes() == legacy_header:
                if not args.check: header.write_bytes(expected_header)
                print('Can upgrade header' if args.check else 'Upgraded timing header; rebuild affected guest units')
                return
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
