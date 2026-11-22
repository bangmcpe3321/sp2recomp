#!/usr/bin/env python3
"""Apply copied-sampler state and Windows relative-mouse fixes to sp2port.

This is an incremental patch; it does not replace the PlayerMake or tutorial
lighting patches. Rebuild the two affected runtime translation units afterward.
No shader hashes, forced filters, scene skips or gyro emulation are included.
"""

import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path,
                        default=Path(os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))))
    parser.add_argument('--check', action='store_true', help='Check without modifying files')
    parser.add_argument('--restore', action='store_true', help='Reverse only this patch')
    args = parser.parse_args()
    patch = Path(__file__).with_name('sampler-copies-mouse.patch').resolve()
    for name in ('runtime/src/nvn/nvn_sampler_objects.cpp', 'runtime/src/platform_win.cpp'):
        if not (args.root / name).is_file():
            parser.error(f'Not a supported sp2port runtime tree: {args.root}')

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
    result = run(args.restore, True)
    if result.returncode:
        raise SystemExit('Patch preflight failed; no files changed.\n' + result.stderr)
    if args.check:
        print('Can restore' if args.restore else 'Can apply')
        return
    result = run(args.restore, False)
    if result.returncode:
        raise SystemExit(result.stderr)
    print('Restored' if args.restore else 'Applied; rebuild the two affected runtime sources')


if __name__ == '__main__':
    main()
