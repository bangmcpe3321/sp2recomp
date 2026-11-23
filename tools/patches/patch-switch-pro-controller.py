#!/usr/bin/env python3
"""Add Windows Switch Pro HIDAPI buttons, sticks and 200 Hz physical gyro.
Apply after the mouse motion stream patch; rebuild platform_win.cpp.
Install SDL3.dll beside the executable using the Windows installer.
"""
import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))))
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    patch = Path(__file__).with_name('switch-pro-controller.patch').resolve()
    source = args.root / 'runtime/src/platform_win.cpp'
    if not source.is_file() or not (args.root / 'runtime/src/mouse_gyro.h').is_file():
        parser.error('Apply the existing mouse motion stream patch first')

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
    print('Restored' if args.restore else 'Applied; rebuild platform_win.cpp')


if __name__ == '__main__':
    main()
