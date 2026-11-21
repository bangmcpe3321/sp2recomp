#!/usr/bin/env python3
"""Apply the tutorial lighting and six-axis fixes to the external sp2port tree.

Apply patch-playermake-descriptor-winding.py first. This patch preserves existing
POSE diagnostics and changes no generated game code or assets. Rebuild every
runtime translation unit afterward: the GpuImage layout changes.
"""

import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path,
                        default=Path(os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))))
    parser.add_argument('--check', action='store_true', help='Check applicability without writing')
    parser.add_argument('--restore', action='store_true', help='Reverse only this patch')
    args = parser.parse_args()
    patch = Path(__file__).with_name('tutorial-lighting-sixaxis.patch').resolve()
    header = args.root / 'runtime/src/nvn/nvn.h'
    if not header.is_file() or not (args.root / 'runtime/src/hle_hid.cpp').is_file():
        parser.error(f'Not a sp2port runtime tree: {args.root}')

    def run(reverse, check):
        command = ['git', 'apply']
        if reverse:
            command.append('--reverse')
        if check:
            command.append('--check')
        command.append(str(patch))
        return subprocess.run(command, cwd=args.root, capture_output=True, text=True)

    if run(not args.restore, True).returncode == 0:
        print('Already restored' if args.restore else 'Already applied')
        return
    if not args.restore and 'record_texture_descriptor' not in header.read_text():
        parser.error('Apply patch-playermake-descriptor-winding.py first')
    result = run(args.restore, True)
    if result.returncode:
        raise SystemExit('Patch preflight failed; no files changed.\n' + result.stderr)
    if args.check:
        print('Can restore' if args.restore else 'Can apply')
        return
    result = run(args.restore, False)
    if result.returncode:
        raise SystemExit(result.stderr)
    print('Restored' if args.restore else 'Applied; rebuild all runtime translation units (header layout changed)')


if __name__ == '__main__':
    main()
