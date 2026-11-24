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
ACCEL_OLD = '''        double mapped[3];map(values,mapped,1/gravity);
        const double norm'''
ACCEL_NEW = '''        double mapped[3];map(values,mapped,1/gravity);
        // PATCH-PRO-GYRO-PITCH-TILT: acceleration is a polar vector. Reflect
        // its Y axis; gyro is axial, so the corresponding signs above are
        // (-X,+Y,-Z). Initial gravity and subsequent rotation now agree.
        mapped[1]=-mapped[1];
        const double norm'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home()/'sp2port'))))
    p.add_argument('--check', action='store_true')
    p.add_argument('--restore', action='store_true')
    a = p.parse_args()
    path = a.root/'runtime/src/controller_motion.h'
    data = path.read_bytes()
    result = data
    for old, new in [(OLD, NEW), (ACCEL_OLD, ACCEL_NEW)]:
        old, new = old.encode(), new.encode()
        if result.count(new) == 1:
            result = result.replace(new, old if a.restore else new, 1)
        elif result.count(old) == 1:
            result = result.replace(old, old if a.restore else new, 1)
        else:
            raise SystemExit('Controller pitch anchor mismatch; no files changed')
    if a.check:
        print('Preflight passed')
        return
    path.write_bytes(result)
    print('Restored' if a.restore else 'Applied; rebuild platform_win.cpp')


if __name__ == '__main__':
    main()
