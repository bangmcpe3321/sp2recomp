#!/usr/bin/env python3
"""Keep F1 mouse lock independent of temporary right-button capture."""
from pathlib import Path
import argparse,os
CHANGES=[('#include "mouse_gyro.h"', '#include "mouse_gyro.h"\n#include "mouse_capture_lock.h" // PATCH-MOUSE-CAPTURE-LOCK'), ('std::atomic<bool> g_mouse_capture{false};', 'std::atomic<bool> g_mouse_capture{false};\nMouseCaptureLock g_mouse_lock; // PATCH-MOUSE-CAPTURE-LOCK: window thread only'), ('mouse_set_capture(!g_mouse_capture.load());', 'mouse_set_capture(g_mouse_lock.toggle()); // PATCH-MOUSE-CAPTURE-LOCK'), ('        case WM_RBUTTONDOWN:\n            if (GetForegroundWindow() == h && mouse_on()) {\n                mouse_set_capture(true);', '        case WM_RBUTTONDOWN:\n            if (GetForegroundWindow() == h && mouse_on()) {\n                mouse_set_capture(g_mouse_lock.button(true)); // PATCH-MOUSE-CAPTURE-LOCK'), ('        case WM_RBUTTONUP:\n            if (g_mouse_capture.load()) {\n                mouse_set_capture(false);', '        case WM_RBUTTONUP:\n            if (g_mouse_capture.load()) {\n                mouse_set_capture(g_mouse_lock.button(false)); // PATCH-MOUSE-CAPTURE-LOCK'), ('if (g_mouse_capture.load()) mouse_set_capture(false);  // never leave the cursor hidden behind another window', 'mouse_set_capture(g_mouse_lock.release()); // PATCH-MOUSE-CAPTURE-LOCK: release cursor on focus loss'), ('if (LOWORD(w) == WA_INACTIVE && g_mouse_capture.load()) mouse_set_capture(false);', 'if (LOWORD(w) == WA_INACTIVE) mouse_set_capture(g_mouse_lock.release()); // PATCH-MOUSE-CAPTURE-LOCK')]
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
  if len(matches)!=1:raise SystemExit('Mouse lock source mismatch; no files changed')
  before,after,state=matches[0];states.append(state);data=data.replace(before,after,1)
 if len(set(states))!=1:raise SystemExit('Partial mouse lock patch; no files changed')
 header=a.root/'runtime/src/mouse_capture_lock.h';payload=(Path(__file__).resolve().parents[1]/'runtime/mouse_capture_lock.h').read_bytes()
 if header.exists() and header.read_bytes()!=payload:raise SystemExit('Mouse lock header differs; no files changed')
 if a.check:print('Preflight passed');return
 path.write_bytes(data)
 if not a.restore:header.write_bytes(payload)
 elif header.exists():header.unlink()
 print('Restored' if a.restore else 'Applied; rebuild platform_win.cpp')
if __name__=='__main__':main()
