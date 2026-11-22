#!/usr/bin/env python3
"""Preserve copied NVN texture descriptors through texture-copy command replay.

Requires the PlayerMake descriptor-identity patch and its RecordedTexture API.
Rebuild runtime/src/nvn/nvn_copy.cpp after applying this incremental patch.
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
    patch = Path(__file__).with_name('plaza-texture-copy-descriptors.patch').resolve()
    source = args.root / 'runtime/src/nvn/nvn_copy.cpp'
    header = args.root / 'runtime/src/nvn/nvn.h'
    if not source.is_file() or not header.is_file():
        parser.error(f'Not a supported sp2port runtime tree: {args.root}')
    if 'record_texture_descriptor' not in header.read_text():
        parser.error('Apply the PlayerMake descriptor-identity patch first')

    def run(reverse, check):
        command = ['git', '-c', 'core.autocrlf=false', 'apply']
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
    print('Restored' if args.restore else 'Applied; rebuild runtime/src/nvn/nvn_copy.cpp')


if __name__ == '__main__':
    main()
