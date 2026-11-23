"""Compile the production physical motion stream under ASan/UBSan.
Usage: python3 test_controller_motion.py /path/runtime/src/controller_motion.h
"""
from pathlib import Path
import subprocess
import sys
import tempfile

header = Path(sys.argv[1]).resolve()
source = r'''
#include "controller_motion.h"
#include <cassert>
#include <cstring>
#include <limits>
#include <cstdio>
using namespace nx::plat;
bool near(double a,double b,double e=1e-5){return std::abs(a-b)<e;}
MouseGyroSample latest(ControllerMotion& m){MouseGyroSample s;assert(m.read_states(0,&s,1)==1);return s;}
void valid(const MouseGyroSample& s){
 assert(s.delta_ns==5000000&&s.sampling_number);
 for(int i=0;i<3;i++)for(int j=0;j<3;j++){
  double d=0;for(int k=0;k<3;k++)d+=s.direction[i*3+k]*s.direction[j*3+k];
  assert(near(d,i==j?1:0));
 }
 // Determinant tests proper rotation, excluding accidental reflection maps.
 const float* a=s.direction;
 double det=a[0]*(a[4]*a[8]-a[5]*a[7])-a[1]*(a[3]*a[8]-a[5]*a[6])+a[2]*(a[3]*a[7]-a[4]*a[6]);
 assert(near(det,1));
}
int main(){
 constexpr uint64_t ms=1000000;
 constexpr float g=9.80665f,pi=3.14159265358979323846f;
 const float flat[3]={0,g,0},zero[3]={},pitch[3]={pi/2,0,0};
 ControllerMotion m;MouseGyroSample a[16]{},b[16]{};
 assert(m.read_states(0,a,16)==0);m.push_accel(ms,flat);m.push_gyro(ms,pitch);
 auto s=latest(m);assert(near(s.acceleration[2],-1));valid(s);
 // Constant pitch integrates exactly 90 degrees over a second, including
 // irregular 3/7 ms transport spacing. Independent Rodrigues X reference.
 uint64_t time=ms;
 for(int i=0;i<100;i++){
  time+=3*ms;m.push_accel(time,flat);m.push_gyro(time,pitch);
  time+=7*ms;m.push_accel(time,flat);m.push_gyro(time,pitch);
 }
 s=latest(m);valid(s);assert(near(s.velocity[0],.25));assert(near(s.angle[0],.25));
 const double expected[9]={1,0,0,0,0,1,0,-1,0};
 for(int i=0;i<9;i++)assert(near(s.direction[i],expected[i]));
 assert(m.read_states(0,a,16)==16&&m.read_states(1,b,16)==16);
 assert(std::memcmp(a,b,sizeof a)==0);assert(m.read_states(0,b,16)==16&&std::memcmp(a,b,sizeof a)==0);
 for(int i=1;i<16;i++)assert(a[i-1].sampling_number==a[i].sampling_number+1);
 // No integration across long stalls or duplicate/out-of-order timestamps.
 time+=2000*ms;m.push_gyro(time,pitch);s=latest(m);assert(near(s.angle[0],.25));
 assert(m.read_states(0,a,16)==1);assert(near(s.velocity[0],0));
 m.push_gyro(time,pitch);m.push_gyro(time-ms,pitch);assert(latest(m).sampling_number==s.sampling_number);
 const float bad[3]={std::numeric_limits<float>::quiet_NaN(),0,0};
 m.push_accel(time+ms,bad);m.push_gyro(time+ms,bad);assert(latest(m).sampling_number==s.sampling_number);
 m.reset();assert(m.read_states(0,a,16)==0);
 // Known 45 degree static pitch: R^T world gravity equals measured gravity.
 const float tilted[3]={0,g*.70710678f,g*.70710678f};
 m.push_accel(ms,tilted);m.push_gyro(ms,zero);s=latest(m);valid(s);
 for(int i=0;i<3;i++)assert(near(s.acceleration[i],-s.direction[i*3+2]));
 assert(near(s.direction[4],.70710678));assert(near(s.direction[5],-.70710678));
 // Upside-down startup is finite and handles opposite-vector quaternion.
 m.reset();const float inverted[3]={0,-g,0};m.push_accel(ms,inverted);m.push_gyro(ms,zero);
 s=latest(m);valid(s);assert(near(s.direction[8],-1));
 // Bias calibration uses real elapsed time, not read count, and does not drift.
 m.reset();const float bias[3]={.004f,-.006f,.003f};time=ms;
 for(int i=0;i<500;i++,time+=5*ms){m.push_accel(time,flat);m.push_gyro(time,bias);}
 s=latest(m);assert(near(s.angle[0],0)&&near(s.angle[1],0)&&near(s.angle[2],0));
 assert(near(s.direction[0],1));
 // Horizontal camera mapping: SDL +Y becomes HID +Z; vertical/pitch and
 // SDL +Z -> HID +Y retain their existing direction.
 for(int axis=1;axis<3;axis++){
  m.reset();float rate[3]={};rate[axis]=pi/2;
  m.push_accel(ms,flat);m.push_gyro(ms,rate);
  for(int i=1;i<=200;i++)m.push_gyro(ms+i*5*ms,rate);
  s=latest(m);valid(s);assert(near(s.angle[axis==1?2:1],.25));
 }
 // Starting while moving cancels calibration; later gentle aiming stays live.
 m.reset();m.push_accel(ms,flat);m.push_gyro(ms,pitch);
 const float slow[3]={.04f,0,0};
 for(int i=1;i<=10;i++){m.push_accel(ms+i*5*ms,flat);m.push_gyro(ms+i*5*ms,slow);}
 s=latest(m);assert(s.velocity[0]>.006f);
 assert(m.read_states(2,a,16)==0&&m.read_states(0,nullptr,16)==0&&m.read_states(0,a,0)==0);
 puts("controller motion: units, axes, Rodrigues, resampling, bias, gaps and shared history passed");
}
'''
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    cpp = root / "motion.cpp"
    cpp.write_text(source)
    exe = root / "motion"
    subprocess.run(["g++", "-std=c++20", "-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-I", str(header.parent), str(cpp), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
