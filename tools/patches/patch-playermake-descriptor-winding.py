#!/usr/bin/env python3
"""Apply the tested PlayerMake descriptor/winding fix to the external sp2port tree.

Usage: python3 patch-playermake-descriptor-winding.py [--root PATH] [--check] [--restore]
SP2PORT overrides the default /home/hexa/sp2port. The patch changes only runtime
NVN sources; it does not stage files, modify generated game code, or include ROMs.
Unsupported/partially patched source layouts fail the preflight without writes.
"""

import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("SP2PORT", "/home/hexa/sp2port")))
    parser.add_argument("--check", action="store_true", help="Check applicability without writing")
    parser.add_argument("--restore", action="store_true", help="Reverse only this patch")
    args = parser.parse_args()
    patch = Path(__file__).with_name("playermake-descriptor-winding.patch").resolve()
    require_root = args.root / "runtime/src/nvn/nvn.h"
    if not require_root.is_file():
        parser.error(f"Not a sp2port runtime tree: {args.root}")

    def run(reverse, check):
        command = ["git", "apply"]
        if reverse:
            command.append("--reverse")
        if check:
            command.append("--check")
        command.append(str(patch))
        return subprocess.run(command, cwd=args.root, capture_output=True, text=True)

    # First recognize the requested end state, so re-running is harmless.
    if run(not args.restore, True).returncode == 0:
        print("Already restored" if args.restore else "Already applied")
        return
    result = run(args.restore, True)
    if result.returncode:
        raise SystemExit("Patch preflight failed; no files changed.\n" + result.stderr)
    if args.check:
        print("Can restore" if args.restore else "Can apply")
        return
    result = run(args.restore, False)
    if result.returncode:
        raise SystemExit(result.stderr)
    print("Restored" if args.restore else "Applied; rebuild all runtime translation units (header layout changed)")


if __name__ == "__main__":
    main()
