"""Compile the real 200 Hz mouse sensor and HLE bridge under ASan/UBSan."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

header=Path(sys.argv[1])
source=header.with_name('hle_hid.cpp').read_text()
sensor=source[source.index('uint64_t g_sixaxis_sampling'):source.index('void GetSixAxisSensorHandles')]
states=source[source.index('void GetSixAxisSensorStates'):source.index('\n}  // namespace',source.index('void GetSixAxisSensorStates'))]
prefix=r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <deque>
#include <mutex>
#include "mouse_gyro.h"
using nx::plat::MouseGyro;
using nx::plat::MouseGyroSample;
struct CPU { uint64_t x[32]{}; };
std::atomic<uint64_t> g_frame{0};
struct {int active=0,aim=0,timer=0;unsigned serial=0;float err_pitch=0,err_yaw=0,dist=0;} g_debug_aim;
template<class T> void st(uint64_t p,T v){std::memcpy((void*)p,&v,sizeof v);}
template<class T> T ld(uint64_t p){T v;std::memcpy(&v,(void*)p,sizeof v);return v;}
void log(const char*,...){}
bool sixaxis_on(){return true;}
MouseGyro device;
uint64_t now=1000000000;
unsigned stream_reads=0;
namespace nx::plat {
bool read_mouse_gyro(unsigned sensor,MouseGyroSample& out){out=device.sample(sensor,now);return true;}
unsigned read_mouse_gyro_states(unsigned sensor,MouseGyroSample* out,unsigned capacity){++stream_reads;return device.samples(sensor,now,out,capacity);}
}
bool near(double a,double b,double eps=1e-5){return std::abs(a-b)<eps;}
void check(const MouseGyroSample& s){
 assert(s.delta_ns==5000000&&s.sampling_number>0);
 for(int i=0;i<3;i++)for(int j=0;j<3;j++){
  double dot=0;for(int k=0;k<3;k++)dot+=s.direction[3*i+k]*s.direction[3*j+k];
  assert(near(dot,i==j?1:0));
 }
 double g=0;for(int i=0;i<3;i++){assert(near(s.acceleration[i],-s.direction[3*i+2]));g+=s.acceleration[i]*s.acceleration[i];}
 assert(near(g,1));for(float v:s.velocity)assert(std::isfinite(v));
}
// Independent Rodrigues reference: integrate emitted physical body rates and
// compare against published HID direction (transpose), after mixed-axis motion.
struct Reference {
 double r[9]={1,0,0,0,1,0,0,0,1}, angles[3]={};
 void consume(const MouseGyroSample& s) {
  constexpr double tau=6.2831853071795864769;
  double w[3];for(int i=0;i<3;i++){w[i]=double(s.velocity[i])*.005*tau;angles[i]+=double(s.velocity[i])*.005;}
  const double theta=std::hypot(w[0],w[1],w[2]);
  if(theta){
   const double x=w[0]/theta,y=w[1]/theta,z=w[2]/theta,c=std::cos(theta),t=1-c,ss=std::sin(theta);
   const double d[9]={c+x*x*t,x*y*t-z*ss,x*z*t+y*ss,y*x*t+z*ss,c+y*y*t,y*z*t-x*ss,z*x*t-y*ss,z*y*t+x*ss,c+z*z*t};
   double n[9]={};for(int i=0;i<3;i++)for(int j=0;j<3;j++)for(int k=0;k<3;k++)n[i*3+j]+=r[i*3+k]*d[k*3+j];
   for(int i=0;i<9;i++)r[i]=n[i];
  }
  for(int i=0;i<3;i++){assert(near(angles[i],s.angle[i],2e-5));for(int j=0;j<3;j++)assert(near(r[i*3+j],s.direction[j*3+i],2e-5));}
 }
};
'''
tests=r'''
int main(int argc,char**) {
 if(argc>1){
  alignas(8) unsigned char bytes[0x60*17];std::memset(bytes,0xA5,sizeof bytes);
  uint32_t handle[2]={0,0};CPU c;c.x[0]=(uint64_t)bytes;c.x[1]=16;c.x[2]=(uint64_t)handle;
  GetSixAxisSensorStates(c);assert(stream_reads==0&&c.x[0]==1);
  for(unsigned i=16*0x60;i<sizeof bytes;i++)assert(bytes[i]==0xA5);
  std::puts("PASS explicit six-axis mode bypasses mouse stream");return 0;
 }
 MouseGyroSample samples[16],again[16];
 // One event stream, read at different rendering rates and extra times per frame.
 std::array<float,9> final{};
 for(unsigned hz:{30u,60u,120u}){
  MouseGyro g;Reference reference;g.capture(true,1000000000);
  uint64_t consumed=g.sample(0,1000000000).sampling_number;
  for(unsigned ms=1;ms<=1000;ms++){
   const uint64_t t=1000000000ull+ms*1000000ull;
   if(ms%8==0)g.move(ms%24==0?3:-1,ms%40==0?-2:1,.15,t);
   if(ms*hz/1000 != (ms-1)*hz/1000 || ms==1000){
    unsigned n=g.samples(0,t,samples,16),m=g.samples(0,t+1,again,16);assert(n==m);
    for(unsigned i=0;i<n;i++)assert(samples[i].sampling_number==again[i].sampling_number);
    m=g.samples(1,t+2,again,16);assert(n==m);
    for(unsigned i=0;i<n;i++){check(samples[i]);assert(samples[i].sampling_number==again[i].sampling_number);for(unsigned k=0;k<9;k++)assert(samples[i].direction[k]==again[i].direction[k]);}
    for(unsigned i=n;i>0;i--)if(samples[i-1].sampling_number>consumed){reference.consume(samples[i-1]);consumed=samples[i-1].sampling_number;}
   }
  }
  // Flush the last input bucket. No new motion after this tick means exact zero rates.
  g.samples(0,2005000000ull,samples,16);for(int i=15;i>=0;i--)if(samples[i].sampling_number>consumed){reference.consume(samples[i]);consumed=samples[i].sampling_number;}
  if(hz==30)for(unsigned i=0;i<9;i++)final[i]=samples[0].direction[i];
  else for(unsigned i=0;i<9;i++)assert(near(final[i],samples[0].direction[i]));
  auto held=g.sample(0,2010000000ull);for(float v:held.velocity)assert(v==0);
  g.capture(false,2011000000ull);g.move(10000,-10000,.15,2012000000ull);
  held=g.sample(0,2030000000ull);for(unsigned i=0;i<9;i++)assert(near(final[i],held.direction[i]));for(float v:held.velocity)assert(v==0);
  g.capture(true,2031000000ull);held=g.sample(1,2040000000ull);for(float v:held.velocity)assert(v==0);
  // Large catch-up is bounded, preserves orientation, and expires obsolete rates.
  held=g.sample(0,1000000000000ull);check(held);for(unsigned i=0;i<9;i++)assert(near(final[i],held.direction[i]));
  for(float v:held.velocity)assert(v==0);
 }
 // Multiple reads in the same sensor tick cannot consume pending input.
 MouseGyro equal;equal.capture(true,2000000000ull);equal.move(5,-10,.15,2000000001ull);
 auto before=equal.sample(0,2000000002ull),repeat=equal.sample(0,2004000000ull);
 assert(before.sampling_number==repeat.sampling_number);
 auto moved=equal.sample(0,2005000000ull);assert(moved.sampling_number==before.sampling_number+1);
 assert(near(moved.velocity[0],(-1.5/360)/.005)&&near(moved.velocity[1],(-.75/360)/.005));
 assert(equal.sample(1,2005000000ull).velocity[0]==moved.velocity[0]);
 assert(equal.sample(0,2005000001ull).velocity[0]==moved.velocity[0]);
 auto idle=equal.sample(0,2010000000ull);for(float v:idle.velocity)assert(v==0);
 // No Euler pole or accumulated-angle wrap can invalidate the sensor basis.
 MouseGyro turns;turns.capture(true,3000000000ull);Reference whole_turns;
 for(unsigned k=1;k<=800;k++) {
  auto t=3000000000ull+uint64_t(k)*5000000;
  turns.move(k%3==0?5:0,-10,.15,t-1);
  auto s=turns.sample(0,t);check(s);whole_turns.consume(s);
 }
 auto finite=turns.sample(0,7000000000ull);
 turns.move(10,10,std::nan(""),7000000001ull);
 auto unchanged=turns.sample(0,7005000000ull);
 for(unsigned k=0;k<9;k++)assert(near(finite.direction[k],unchanged.direction[k]));
 // API limits fail safely.
 assert(equal.samples(2,2010000000ull,samples,16)==0);assert(equal.samples(0,2010000000ull,nullptr,16)==0);
 // Actual HLE GetStates returns the physical stream, including 3/4 samples per
 // 60 Hz frame, stable serials, newest-first ordering and safe output bounds.
 device.capture(true,now);device.move(40,-20,.15,now+1);now+=20000000;
 alignas(8) std::array<unsigned char,0x60*17> out;uint32_t handle[2]={0,0};CPU c;const uint64_t p=(uint64_t)out.data();
 auto read=[&](int count){out.fill(0xA5);c.x[0]=p;c.x[1]=uint32_t(count);c.x[2]=(uint64_t)handle;GetSixAxisSensorStates(c);};
 read(16);assert(c.x[0]==5);auto saved=out;
 for(unsigned i=0;i<5;i++){assert(ld<uint64_t>(p+0x60*i)==5000000);assert(ld<uint64_t>(p+0x60*i+8)==ld<uint64_t>(p+8)-i);assert(ld<uint32_t>(p+0x60*i+0x58)==1);}
 for(unsigned i=5*0x60;i<16*0x60;i++)assert(out[i]==0);for(unsigned i=16*0x60;i<out.size();i++)assert(out[i]==0xA5);
 read(16);assert(out==saved);handle[1]=1;read(16);assert(out==saved);
 auto serial=ld<uint64_t>(p+8);now+=16666667;read(16);assert(ld<uint64_t>(p+8)-serial==3);
 serial=ld<uint64_t>(p+8);now+=16666667;read(16);assert(ld<uint64_t>(p+8)-serial==3);
 serial=ld<uint64_t>(p+8);now+=16666667;read(16);assert(ld<uint64_t>(p+8)-serial==4);
 read(1);assert(c.x[0]==1);for(unsigned i=0x60;i<out.size();i++)assert(out[i]==0xA5);
 handle[1]=2;read(16);assert(c.x[0]==0);
 std::puts("PASS mouse gyro: coherent local-body quaternion/rates, 200 Hz stream, 30/60/120 Hz consumers, repeated/dual reads, pause, bounded catch-up and actual HLE ABI");
}
'''
env={k:v for k,v in os.environ.items() if not k.startswith('NX_')}
with tempfile.TemporaryDirectory(prefix='sp2-mouse-gyro-') as td:
 d=Path(td);cpp=d/'test.cpp';exe=d/'test';cpp.write_text(prefix+'\n#define _WIN32\n'+sensor+states+tests)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-I',str(header.parent),str(cpp),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,env=env)
 for mode in ('POSE','GRID','SEEK','WOBBLE'):
  subprocess.run([str(exe),'explicit'],check=True,env={**env,'NX_SIXAXIS_'+mode:'0.2:0.3' if mode=='POSE' else '1'})
