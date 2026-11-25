#!/usr/bin/env python3
"""PC bindings: Space jump, Shift squid, left-click shoot, F confirm."""
from pathlib import Path
import argparse,os
CHANGES=[('// Keyboard: WASD / arrows move, Space A, Shift B (dash), J X, K Y, Q/E L/R, Z/C ZL/ZR, Enter +, Esc -.', '// Keyboard: WASD / arrows move, F A, Space B (jump), Shift/Z ZL, left click/C ZR, J X, K Y, Q/E L/R, Enter +, Esc -. // PATCH-PC-CONTROLS'), ('if (key(VK_SPACE)) p.buttons |= kA;', "if (key('F')) p.buttons |= kA; // PATCH-PC-CONTROLS: confirm / interact"), ('if (key(VK_SHIFT)) p.buttons |= kB;', 'if (key(VK_SPACE)) p.buttons |= kB; // PATCH-PC-CONTROLS: jump / back'), ("if (key('Z')) p.buttons |= kZL;", "if (key(VK_SHIFT) || key('Z')) p.buttons |= kZL; // PATCH-PC-CONTROLS: squid / swim"), ("if (key('C')) p.buttons |= kZR;", "if (key(VK_LBUTTON) || key('C')) p.buttons |= kZR; // PATCH-PC-CONTROLS: shoot")]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
 path=a.root/'runtime/src/platform_win.cpp';data=path.read_bytes();states=[]
 for old,new in CHANGES:
  left,right=old.encode(),new.encode()
  if data.count(right)==1:before=right;after=left if a.restore else right;states.append(True)
  elif data.count(left)==1:before=left;after=left if a.restore else right;states.append(False)
  else:raise SystemExit('PC controls source mismatch; no files changed')
  data=data.replace(before,after,1)
 if len(set(states))!=1:raise SystemExit('Partial PC controls patch; no files changed')
 if a.check:print('Preflight passed');return
 path.write_bytes(data);print('Restored' if a.restore else 'Applied; rebuild platform_win.cpp')
if __name__=='__main__':main()
