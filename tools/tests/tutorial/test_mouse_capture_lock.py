from pathlib import Path
import subprocess,sys,tempfile,importlib.util
root=Path(sys.argv[1]);src=(root/'runtime/src/platform_win.cpp').read_text();header=root/'runtime/src/mouse_capture_lock.h'
key=src[src.index('            if (w == VK_F1 &&'):src.index('        case WM_SYSKEYDOWN:')];key=key[:key.rindex('            break;')]
buttons=src[src.index('        case WM_RBUTTONDOWN:'):src.index('        case WM_MOUSEMOVE:')]
focus=src[src.index('        case WM_KILLFOCUS:'):src.index('    return DefWindowProcW',src.index('        case WM_KILLFOCUS:'))];focus=focus[:focus.rfind('    }')]
code=r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
'''+ '#include "'+str(header)+'"\n'+r'''
using nx::plat::MouseCaptureLock;using LPARAM=int64_t;
constexpr int VK_F1=112,WM_RBUTTONDOWN=1,WM_RBUTTONUP=2,WM_KILLFOCUS=3,WM_ACTIVATE=4,WA_INACTIVE=0;
int h=7,foreground=7;bool mouse_enabled=true;bool controller_focus=false;
std::atomic<bool> g_mouse_capture{false};MouseCaptureLock g_mouse_lock;
unsigned changes=0;int GetForegroundWindow(){return foreground;}bool mouse_on(){return mouse_enabled;}
void mouse_set_capture(bool on){if(g_mouse_capture.exchange(on)!=on)changes++;}
void set_switch_pro_focus(bool on){controller_focus=on;}void fps_overlay_position(){}
unsigned LOWORD(uint64_t w){return unsigned(w)&65535;}
void key_event(int w,int64_t l=0){
'''+key+r'''
}
int event(unsigned msg,uint64_t w=0){switch(msg){
'''+buttons+focus+r'''
}return 99;}
int main(){
 assert(!g_mouse_capture);
 key_event(VK_F1);assert(g_mouse_capture); // latch on, no button held
 auto changed=changes;key_event(VK_F1,LPARAM(1)<<30);assert(g_mouse_capture && changes==changed); // key repeat ignored
 event(WM_RBUTTONDOWN);event(WM_RBUTTONUP);assert(g_mouse_capture); // no accidental unlock
 key_event(VK_F1);assert(!g_mouse_capture); // second press unlocks
 event(WM_RBUTTONDOWN);assert(g_mouse_capture);event(WM_RBUTTONUP);assert(!g_mouse_capture); // former hold remains
 event(WM_RBUTTONDOWN);key_event(VK_F1);event(WM_RBUTTONUP);assert(g_mouse_capture); // promote temporary hold to latch
 event(WM_KILLFOCUS);assert(!g_mouse_capture);event(WM_ACTIVATE,1);assert(!g_mouse_capture && controller_focus);
 event(WM_RBUTTONUP);assert(!g_mouse_capture);key_event(VK_F1);assert(g_mouse_capture); // no stale latch after focus loss
 event(WM_ACTIVATE,WA_INACTIVE);assert(!g_mouse_capture);key_event(VK_F1);assert(g_mouse_capture);
 event(WM_RBUTTONDOWN);key_event(VK_F1);assert(!g_mouse_capture);event(WM_RBUTTONUP);assert(!g_mouse_capture); // explicit F1 unlock wins
 foreground=8;key_event(VK_F1);event(WM_RBUTTONDOWN);assert(!g_mouse_capture);foreground=7;
 mouse_enabled=false;key_event(VK_F1);event(WM_RBUTTONDOWN);assert(!g_mouse_capture);mouse_enabled=true;
 for(unsigned i=0;i<10000;i++){key_event(VK_F1);assert(g_mouse_capture);event(WM_RBUTTONDOWN);event(WM_RBUTTONUP);assert(g_mouse_capture);event(WM_KILLFOCUS);assert(!g_mouse_capture);}
 puts("PASS actual mouse lock events: F1 latch/repeat, right-button release, temporary hold, explicit unlock, focus loss, disabled/background input, repeated cycles");
}
'''
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp);(path/'test.cpp').write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
 installer=Path(__file__).resolve().parents[2]/'patches/patch-mouse-capture-lock.py'
 spec=importlib.util.spec_from_file_location('mouse_capture_patch',installer);patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
 original=src
 for old,new in reversed(patch.CHANGES):assert original.count(new)==1;original=original.replace(new,old,1)
 fixture=path/'runtime/src/platform_win.cpp';fixture.parent.mkdir(parents=True)
 command=[sys.executable,str(installer),'--root',str(path)]
 for nl in [b'\n',b'\r\n']:
  raw=original.encode().replace(b'\n',nl);fixture.write_bytes(raw)
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);installed=fixture.read_bytes()
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);assert fixture.read_bytes()==installed
  subprocess.run(command+['--restore'],check=True,stdout=subprocess.DEVNULL);assert fixture.read_bytes()==raw
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
  old,new=patch.CHANGES[2];fixture.write_bytes(fixture.read_bytes().replace(new.encode(),old.encode()));partial=fixture.read_bytes()
  result=subprocess.run(command,capture_output=True);assert result.returncode!=0 and fixture.read_bytes()==partial
  # Reset for the next line-ending fixture.
  (path/'runtime/src/mouse_capture_lock.h').unlink()
 print('PASS mouse lock installer: exact LF/CRLF restore, idempotence and partial patch refusal')
