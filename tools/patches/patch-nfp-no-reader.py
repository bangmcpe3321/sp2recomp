#!/usr/bin/env python3
"""Return a valid NFP interface and the game's handled no-reader result."""
import argparse
import os
from pathlib import Path

ANCHOR = b'#include "ipc.h"\n'
INCLUDE = b'#include "nfp_service.h" // PATCH-NFP-NO-READER\n'
IPC_COPIES = [
    b'std::memcpy(&w[q + 1], ctx.out.data(), ctx.out.size());',
    b'std::memcpy(reinterpret_cast<void*>(o + 16), ctx.out.data(), ctx.out.size());',
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home()/'sp2port'))))
    p.add_argument('--check', action='store_true')
    p.add_argument('--restore', action='store_true')
    a = p.parse_args()
    source = a.root/'runtime/src/svc_misc.cpp'
    header = a.root/'runtime/src/nfp_service.h'
    data = source.read_bytes()
    if data.count(ANCHOR) != 1 or data.count(INCLUDE) > 1:
        raise SystemExit('NFP service source mismatch; no files changed')
    expected = (Path(__file__).resolve().parents[1]/'runtime/nfp_service.h').read_bytes()
    if header.exists() and header.read_bytes() != expected:
        raise SystemExit('NFP header differs; no files changed')
    result = data.replace(INCLUDE, b'', 1)
    if not a.restore:
        result = result.replace(ANCHOR, ANCHOR+INCLUDE, 1)
    ipc_path = a.root/'runtime/src/ipc.cpp'
    ipc = ipc_path.read_bytes()
    for old in IPC_COPIES:
        new = b'if (!ctx.out.empty()) '+old
        if ipc.count(new) == 1:
            ipc = ipc.replace(new, old if a.restore else new, 1)
        elif ipc.count(old) == 1:
            ipc = ipc.replace(old, old if a.restore else new, 1)
        else:
            raise SystemExit('IPC response-copy anchor mismatch; no files changed')
    if a.check:
        print('Preflight passed')
        return
    if not a.restore:
        header.write_bytes(expected)
    source.write_bytes(result)
    ipc_path.write_bytes(ipc)
    if a.restore and header.exists():
        header.unlink()
    print('Restored' if a.restore else 'Applied; rebuild svc_misc.cpp and ipc.cpp')


if __name__ == '__main__':
    main()
