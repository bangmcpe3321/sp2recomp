#!/usr/bin/env python3
"""Reuse valid copied buffer prefixes without changing padding or invalidation."""
from pathlib import Path
import argparse,os
OLD='    if (e && e->size == size && e->padded == padded && e->upload.offset % align == 0) {'
NEW='    // PATCH-UPLOAD-PREFIX-REUSE: a smaller draw can read an existing copied prefix.\n    // Preserve zero padding: a larger source payload cannot stand in for bytes\n    // that this request requires to be zero. No new assumptions about guest writes.\n    const bool compatible = e && e->size >= size && e->padded >= padded &&\n                            (padded == size || e->size == size);\n    if (compatible && e->upload.offset % align == 0) {'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
 path=a.root/'runtime/src/nvn/nvn_dedup.cpp';data=path.read_bytes();choices=[]
 for nl in (b'\n',b'\r\n'):
  right=NEW.encode().replace(b'\n',nl)
  if data.count(right)==1:choices.append((right,OLD.encode() if a.restore else right))
 if not choices and data.count(OLD.encode())==1:
  end=data.index(OLD.encode())+len(OLD.encode());nl=b'\r\n' if data[end:end+2]==b'\r\n' else b'\n'
  choices=[(OLD.encode(),OLD.encode() if a.restore else NEW.encode().replace(b'\n',nl))]
 if len(choices)!=1:raise SystemExit('Upload prefix source mismatch; no files changed')
 before,after=choices[0];rest=data.replace(before,b'',1)
 if b'PATCH-UPLOAD-PREFIX-REUSE' in rest or OLD.encode() in rest:raise SystemExit('Duplicate prefix patch; no files changed')
 if a.check:print('Preflight passed');return
 path.write_bytes(data.replace(before,after,1));print('Restored' if a.restore else 'Applied; rebuild nvn_dedup.cpp')
if __name__=='__main__':main()
