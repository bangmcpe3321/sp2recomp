#!/usr/bin/env python3
"""Keep news at native timing and enable plaza 60 FPS on gameplay entry."""
import argparse
import os
from pathlib import Path

INCLUDE = b'#include "sp2_gameplay_options.h" // PATCH-SP2-NEWS-LIFECYCLE\n'
HOOKS = (
    ('gen/main/code_204.cpp', b'void main_0097985C(nx::CPU& NX_RESTRICT c) {\n',
     b'    nx::sp2::set_plaza_timing(c, NXB, main_00E67D58, true); // PATCH-SP2-NEWS-LIFECYCLE: plaza gameplay\n'),
    ('gen/main/code_206.cpp', b'void main_0098E008(nx::CPU& NX_RESTRICT c) {\n',
     b'    nx::sp2::set_plaza_timing(c, NXB, main_00E67D58, false); // PATCH-SP2-NEWS-LIFECYCLE: native news broadcast\n'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))))
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    try:
        header = args.root / 'runtime/src/sp2_gameplay_options.h'
        if not args.restore and b'inline void set_plaza_timing(' not in header.read_bytes():
            raise ValueError('Apply the updated gameplay-options helper first')
        changes, states = [], []
        for relative, function, hook in HOOKS:
            path = args.root / relative
            data = path.read_bytes()
            if data.count(function) != 1:
                raise ValueError(f'Function anchor mismatch: {relative}')
            if data.count(function + hook) == 1 and data.count(INCLUDE) == 1:
                states.append(True)
                result = data.replace(hook, b'', 1).replace(INCLUDE, b'', 1)
            elif hook not in data and INCLUDE not in data:
                states.append(False)
                result = INCLUDE + data.replace(function, function + hook, 1)
            else:
                raise ValueError(f'Lifecycle anchor mismatch: {relative}')
            if states[-1] == args.restore: changes.append((path, result))
        if len(set(states)) != 1: raise ValueError('Partial lifecycle patch')
        if not changes:
            print('Already restored' if args.restore else 'Already applied')
            return
        if args.check:
            print('Can restore' if args.restore else 'Can apply')
            return
        for path, data in changes: path.write_bytes(data)
        print('Restored' if args.restore else 'Applied; rebuild code_204.cpp, code_206.cpp and other timing-header users')
    except (OSError, ValueError) as error:
        raise SystemExit(f'Preflight failed; no files changed: {error}')


if __name__ == '__main__':
    main()
