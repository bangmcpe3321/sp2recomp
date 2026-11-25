#!/usr/bin/env python3
"""Test production motion arbitration and HID delivery across mouse capture, gaps and reconnects."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(sys.argv[1])
platform=(root/'runtime/src/platform_win.cpp').read_text()
first=platform.index('bool read_mouse_gyro(unsigned sensor,')
last=platform.index('// Re-centre the cursor',first)
arbitration=platform[first:last]
hid=(root/'runtime/src/hle_hid.cpp').read_text()
sensor=hid[hid.index('uint64_t g_sixaxis_sampling'):hid.index('void GetSixAxisSensorHandles')]
first=hid.index('void GetSixAxisSensorStates')
states=hid[first:hid.index('\n}  // namespace',first)]
source=r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <mutex>
#include "controller_motion.h"
using nx::plat::MouseGyroSample;
struct CPU {uint64_t x[32]{};};
template<class T>T ld(uint64_t p){T v;std::memcpy(&v,(void*)p,sizeof v);return v;}
template<class T>void st(uint64_t p,T v){std::memcpy((void*)p,&v,sizeof v);}
void log(const char*,...){}
bool sixaxis_on(){return true;}
std::atomic<uint64_t> g_frame{0};
struct {int active=0,aim=0,timer=0;unsigned serial=0;float err_pitch=0,err_yaw=0,dist=0;}g_debug_aim;
namespace nx::plat {
uint64_t now=1000000000000ull;
std::atomic<bool> g_mouse_capture{false};
std::mutex g_mouse_motion_mutex;
MouseGyro g_mouse_motion;
ControllerMotion native;
bool selected=true,fresh=true,focused=true,mouse_enabled=true;
int g_window=1;
int GetForegroundWindow(){return focused?1:2;}
uint64_t monotonic_ns(){return now;}
bool mouse_gyro_on(){return mouse_enabled;}
bool switch_pro_motion_selected(){return selected;}
unsigned read_switch_pro_motion(unsigned sensor,MouseGyroSample* out,unsigned capacity){
 return fresh&&focused?native.read_states(sensor,out,capacity):0;
}
'''+arbitration+r'''
}
'''+sensor+states+r'''
int main(){
 using namespace nx::plat;
 const float flat[3]={0,9.80665f,0},slow[3]={.04f,0,0};
 auto packets=[&](unsigned n){for(unsigned i=0;i<n;i++){native.push_accel(now,flat);native.push_gyro(now,slow);now+=5000000;}};
 alignas(8)std::array<unsigned char,0x60*17> output{};uint32_t handle[2]={0,0};CPU c{};
 auto read=[&]{output.fill(0xa5);c.x[0]=uint64_t(output.data());c.x[1]=16;c.x[2]=uint64_t(handle);GetSixAxisSensorStates(c);
  for(unsigned i=16*0x60;i<output.size();i++)assert(output[i]==0xa5);
  return c.x[0];};
 auto serial=[&]{return ld<uint64_t>(uint64_t(output.data()+8));};
 auto pitch=[&]{return ld<float>(uint64_t(output.data()+0x1c));};
 packets(10);assert(read()==10&&pitch()>.006);uint64_t before=serial();
 assert(before>100000); // Shared monotonic clock, not a controller-local counter starting at 1.
 auto saved=output;assert(read()==10&&output==saved);handle[1]=1;assert(read()==10&&output==saved);handle[1]=0;
 // A connected controller with delayed packets stays selected. No idle mouse or fabricated HID fallback.
 fresh=false;now+=150000000;assert(read()==0);for(unsigned i=0;i<16*0x60;i++)assert(output[i]==0);
 MouseGyroSample sample;assert(!read_mouse_gyro(0,sample));
 fresh=true;packets(4);assert(read()>0&&serial()>before&&pitch()>.006);
 // Switch to real mouse capture, then back to native. sead's signed 32-bit sample delta must stay positive.
 before=serial();g_mouse_capture=true;g_mouse_motion.capture(true,now);g_mouse_motion.move(0,-20,.15,now+1);now+=20000000;
 assert(read()>0&&int32_t(uint32_t(serial()-before))>0);before=serial();
 native.pause();g_mouse_capture=false;now+=10000000;packets(4);
 assert(read()>0&&int32_t(uint32_t(serial()-before))>0&&pitch()>.006);
 // Focus handoff does not restart stationary calibration or numbering.
 before=serial();native.pause();focused=false;now+=10000000;assert(read()==0);
 focused=true;packets(4);assert(read()>0&&serial()>before&&pitch()>.006);
 // New physical device / reconnect resets orientation but not the external sample clock.
 before=serial();native.reset();now+=100000000;packets(4);
 assert(read()>0&&serial()>before&&pitch()>.006);
 puts("PASS: gentle vertical aiming, packet-gap ownership, no synthetic fallback, shared sensor clock, mouse/focus/reconnect handoff and HID bounds");
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-gyro-continuity-') as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(source)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I',str(root/'runtime/src'),'-D_WIN32',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
