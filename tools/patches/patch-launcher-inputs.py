#!/usr/bin/env python3
"""Read saved launcher keyboard and mouse bindings."""
from pathlib import Path
import argparse,os
CHANGES=[('#include "mouse_capture_lock.h" // PATCH-MOUSE-CAPTURE-LOCK', '#include "mouse_capture_lock.h" // PATCH-MOUSE-CAPTURE-LOCK\n#include "pc_input_bindings.h" // PATCH-LAUNCHER-INPUTS'), ("    // Keyboard: WASD / arrows move, F A, Space B (jump), Shift/Z ZL, left click/C ZR, J X, K Y, Q/E L/R, Enter +, Esc -. // PATCH-PC-CONTROLS\n    if (key('A') || key(VK_LEFT)) p.lx = -kStickMax;\n    if (key('D') || key(VK_RIGHT)) p.lx = kStickMax;\n    if (key('W') || key(VK_UP)) p.ly = kStickMax;\n    if (key('S') || key(VK_DOWN)) p.ly = -kStickMax;\n    if (key('F')) p.buttons |= kA; // PATCH-PC-CONTROLS: confirm / interact\n    if (key(VK_SPACE)) p.buttons |= kB; // PATCH-PC-CONTROLS: jump / back\n    if (key('J')) p.buttons |= kX;\n    if (key('K')) p.buttons |= kY;\n    if (key('Q')) p.buttons |= kL;\n    if (key('E')) p.buttons |= kR;\n    if (key(VK_SHIFT) || key('Z')) p.buttons |= kZL; // PATCH-PC-CONTROLS: squid / swim\n    if (key(VK_LBUTTON) || key('C')) p.buttons |= kZR; // PATCH-PC-CONTROLS: shoot\n    if (key(VK_RETURN)) p.buttons |= kPlus;\n    if (key(VK_ESCAPE)) p.buttons |= kMinus;\n", '    // PATCH-LAUNCHER-INPUTS: configured keyboard/mouse bindings, still gated by window focus.\n    if (pc_inputs().pressed(PcAction::Left,key)) p.lx = -kStickMax;\n    if (pc_inputs().pressed(PcAction::Right,key)) p.lx = kStickMax;\n    if (pc_inputs().pressed(PcAction::Up,key)) p.ly = kStickMax;\n    if (pc_inputs().pressed(PcAction::Down,key)) p.ly = -kStickMax;\n    if (pc_inputs().pressed(PcAction::A,key)) p.buttons |= kA;\n    if (pc_inputs().pressed(PcAction::B,key)) p.buttons |= kB;\n    if (pc_inputs().pressed(PcAction::X,key)) p.buttons |= kX;\n    if (pc_inputs().pressed(PcAction::Y,key)) p.buttons |= kY;\n    if (pc_inputs().pressed(PcAction::L,key)) p.buttons |= kL;\n    if (pc_inputs().pressed(PcAction::R,key)) p.buttons |= kR;\n    if (pc_inputs().pressed(PcAction::ZL,key)) p.buttons |= kZL;\n    if (pc_inputs().pressed(PcAction::ZR,key)) p.buttons |= kZR;\n    if (pc_inputs().pressed(PcAction::Plus,key)) p.buttons |= kPlus;\n    if (pc_inputs().pressed(PcAction::Minus,key)) p.buttons |= kMinus;\n    if (pc_inputs().pressed(PcAction::StickL,key)) p.buttons |= kStickL;\n    if (pc_inputs().pressed(PcAction::StickR,key)) p.buttons |= kStickR;\n    if (pc_inputs().pressed(PcAction::DpadLeft,key)) p.buttons |= kLeft;\n    if (pc_inputs().pressed(PcAction::DpadUp,key)) p.buttons |= kUp;\n    if (pc_inputs().pressed(PcAction::DpadRight,key)) p.buttons |= kRight;\n    if (pc_inputs().pressed(PcAction::DpadDown,key)) p.buttons |= kDown;\n')]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
 path=a.root/'runtime/src/platform_win.cpp';data=path.read_bytes();states=[]
 for old,new in CHANGES:
  matches=[]
  for nl in (b'\n',b'\r\n'):
   left=old.encode().replace(b'\n',nl);right=new.encode().replace(b'\n',nl)
   if data.count(right)==1:matches.append((right,left if a.restore else right,True))
  if not matches:
   for nl in (b'\n',b'\r\n'):
    left=old.encode().replace(b'\n',nl);right=new.encode().replace(b'\n',nl)
    if data.count(left)!=1:continue
    if b'\n' not in left:
     at=data.index(left)+len(left);local=b'\r\n' if data[at:at+2]==b'\r\n' else b'\n'
     if nl!=local:continue
    matches.append((left,left if a.restore else right,False))
  matches=list(dict.fromkeys(matches))
  if len(matches)!=1:raise SystemExit('Launcher input source mismatch; no files changed')
  before,after,state=matches[0];states.append(state);data=data.replace(before,after,1)
 if len(set(states))!=1:raise SystemExit('Partial launcher input patch; no files changed')
 header=a.root/'runtime/src/pc_input_bindings.h';payload=(Path(__file__).resolve().parents[1]/'runtime/pc_input_bindings.h').read_bytes()
 if header.exists() and header.read_bytes()!=payload:raise SystemExit('Launcher input header differs; no files changed')
 if a.check:print('Preflight passed');return
 path.write_bytes(data)
 if not a.restore:header.write_bytes(payload)
 elif header.exists():header.unlink()
 print('Restored' if a.restore else 'Applied; rebuild platform_win.cpp')
if __name__=='__main__':main()
