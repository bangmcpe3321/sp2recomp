#!/usr/bin/env python3
"""Correct physical Switch Pro pitch before coherent motion integration."""
import argparse
import os
from pathlib import Path

OLD = '''        // Match the game camera horizontal direction; apply before quaternion
        // integration so rate, angle and orientation remain one coherent stream.
        raw[2]=-raw[2];'''
NEW = '''        // PATCH-PRO-GYRO-PITCH: match the game's physical camera directions.
        // Apply both signs before integration so rate, angle and orientation
        // remain one coherent stream. Mouse motion has its own mapping.
        raw[0]=-raw[0];
        raw[2]=-raw[2];'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home()/'sp2port'))))
    p.add_argument('--check', action='store_true')
    p.add_argument('--restore', action='store_true')
    a = p.parse_args()
    path = a.root/'runtime/src/controller_motion.h'
    data = path.read_bytes()
    old, new = OLD.encode(), NEW.encode()
    if data.count(new) == 1:
        result = data.replace(new, old if a.restore else new, 1)
    elif data.count(old) == 1:
        result = data.replace(old, old if a.restore else new, 1)
    else:
        raise SystemExit('Controller pitch anchor mismatch; no files changed')
    if a.check:
        print('Preflight passed')
        return
    path.write_bytes(result)
    print('Restored' if a.restore else 'Applied; rebuild platform_win.cpp')


if __name__ == '__main__':
    main()
