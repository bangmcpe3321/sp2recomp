"""Exercise real mouse motion math and its Windows six-axis ABI bridge."""
from pathlib import Path
import subprocess,sys,tempfile
header=Path(sys.argv[1]);source=header.with_name('hle_hid.cpp').read_text()
sensor=source[source.index('uint64_t g_sixaxis_sampling'):source.index('void GetSixAxisSensorHandles')]
prefix=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include "mouse_gyro.h"
using nx::plat::MouseGyro;
using nx::plat::MouseGyroSample;
std::atomic<uint64_t> g_frame{0};
struct {int active=0,aim=0,timer=0;unsigned serial=0;float err_pitch=0,err_yaw=0,dist=0;} g_debug_aim;
template<class T> void st(uint64_t p,T v){std::memcpy((void*)p,&v,sizeof v);}
template<class T> T ld(uint64_t p){T v;std::memcpy(&v,(void*)p,sizeof v);return v;}
void log(const char*,...){}
MouseGyro device;
uint64_t now=1000000000;
namespace nx::plat { bool read_mouse_gyro(unsigned sensor,MouseGyroSample& out){out=device.sample(sensor,now);return true;} }
bool near(double x,double y){return std::abs(x-y)<1e-5;}
void check(const MouseGyroSample& s){
 for(int i=0;i<3;i++)for(int j=0;j<3;j++){
  double dot=0;for(int k=0;k<3;k++)dot+=s.direction[3*i+k]*s.direction[3*j+k];
  assert(near(dot,i==j?1:0));
 }
 double g=0;for(auto a:s.acceleration)g+=a*a;assert(near(g,1));
 for(auto v:s.velocity)assert(std::isfinite(v));
}
'''
tests=r'''
int main(){
 // Equal displacement has equal rotation at 30/60/120 Hz. Both sensors receive it.
 for(unsigned hz:{30,60,120}){
  MouseGyro g;g.capture(true,1000000000);MouseGyroSample s,t;
  for(unsigned k=1;k<=hz;k++){
   g.move(int(120/hz),-int(120/hz),0.15);auto ns=1000000000+1000000000ull*k/hz;
   s=g.sample(0,ns);t=g.sample(1,ns);check(s);
   assert(near(s.velocity[0],.05)&&near(s.velocity[1],.05));
   assert(near(s.angle[0],t.angle[0])&&near(s.angle[1],t.angle[1]));
  }
  assert(near(s.angle[0],.05)&&near(s.angle[1],.05));
  s=g.sample(0,2100000000);assert(s.velocity[0]==0&&s.velocity[1]==0);
  g.capture(false,2200000000);g.move(999,999,1);s=g.sample(0,2300000000);
  assert(near(s.angle[0],.05)&&s.velocity[0]==0);
  g.capture(true,2400000000);s=g.sample(0,2500000000);assert(s.velocity[0]==0);
  g.move(1000000,-1000000,.15);s=g.sample(0,2600000000);check(s);
 }
 // Compile and call the actual Windows HLE fill, verifying every sensor field's offset.
 device.capture(true,now);device.move(40,-20,.15);now+=20000000;
 alignas(8) unsigned char out[0x60];auto p=(uint64_t)out;
 fill_sixaxis_state(p,0);
 assert(ld<uint64_t>(p)==20000000&&ld<uint64_t>(p+8)==1);
 assert(near(ld<float>(p+0x28),3.0/360)&&near(ld<float>(p+0x2c),6.0/360));
 assert(near(ld<float>(p+0x1c),(3.0/360)/.02));
 assert(near(ld<float>(p+0x20),(6.0/360)/.02));
 assert(ld<uint32_t>(p+0x58)==1&&ld<uint32_t>(p+0x5c)==0);
 const float a[3]={ld<float>(p+0x10),ld<float>(p+0x14),ld<float>(p+0x18)};
 assert(near(a[0],-ld<float>(p+0x3c))&&near(a[1],-ld<float>(p+0x48))&&near(a[2],-ld<float>(p+0x54)));
 fill_sixaxis_state(p,1);assert(near(ld<float>(p+0x20),(6.0/360)/.02));
 now+=20000000;fill_sixaxis_state(p,0);assert(ld<float>(p+0x1c)==0&&ld<float>(p+0x20)==0);
 std::puts("PASS mouse gyro: frame independence, sensor reads, units, gravity, direction, focus and HLE ABI");
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-mouse-gyro-') as td:
 d=Path(td);cpp=d/'test.cpp';exe=d/'test';cpp.write_text(prefix+'\n#define _WIN32\n'+sensor+tests)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-I',str(header.parent),str(cpp),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
