"""Compile the production physical motion stream under ASan/UBSan.
Usage: python3 test_controller_motion.py /path/runtime/src/controller_motion.h
"""
from pathlib import Path
import subprocess
import sys
import tempfile

header = Path(sys.argv[1]).resolve()
addon_source = (header.parents[2]/'gen/main/code_421.cpp').read_text()
addon_start = addon_source.index('L_1397CA0:;')
addon_end = addon_source.index('L_1397D2C:;', addon_start)
addon_body = addon_source[addon_start:addon_end]
addon_test = r'''
namespace nx {
union V128 {uint32_t u32[4];uint64_t u64[2];float f32[4];};
inline V128 vzero(){return {};}
struct CPU {uint64_t x[32]{};V128 v[32]{};};
template<class T>T ld(uint64_t address){T value;std::memcpy(&value,reinterpret_cast<void*>(address),sizeof value);return value;}
template<class T>void st(uint64_t address,T value){std::memcpy(reinterpret_cast<void*>(address),&value,sizeof value);}
}
MouseGyroSample normal_addon(const MouseGyroSample& sample){
 alignas(16) unsigned char input[0x100]{},output[0x100]{};
 for(unsigned i=0;i<3;i++){
  std::memcpy(input+0x10+i*4,&sample.acceleration[i],4);
  std::memcpy(input+0x1c+i*4,&sample.velocity[i],4);
  std::memcpy(input+0x28+i*4,&sample.angle[i],4);
 }
 std::memcpy(input+0x34,sample.direction,36);
 nx::CPU c;c.x[19]=uint64_t(output);c.x[0]=0x48;c.x[5]=uint64_t(input);c.x[3]=uint64_t(output+0x28);
 c.v[4].f32[0]=sample.acceleration[0];c.v[3].f32[0]=sample.acceleration[1];
 std::memcpy(&c.x[1],&sample.acceleration[2],4);
 ADDON_BODY
 MouseGyroSample converted;
 for(unsigned i=0;i<3;i++){
  std::memcpy(&converted.acceleration[i],output+0x28+i*4,4);
  std::memcpy(&converted.velocity[i],output+0x34+i*4,4);
  std::memcpy(&converted.angle[i],output+0x40+i*4,4);
 }
 return converted;
}
'''.replace('ADDON_BODY', addon_body)
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
''' + addon_test + r'''
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
 // Physical positive-X pitch changes SDL gravity to (0,cos(theta),-sin(theta)).
 // Static tilt and integrated gyro must yield the same HID attitude: the game
 // fuses both, so negating rates alone leaves its accelerometer aiming reversed.
 ControllerMotion moving;moving.push_accel(ms,flat);moving.push_gyro(ms,pitch);
 for(int i=1;i<=100;i++){
  const double theta=(pi/2)*(i*.005);const float physical[3]={0,float(g*std::cos(theta)),float(-g*std::sin(theta))};
  moving.push_accel(ms+i*5*ms,physical);moving.push_gyro(ms+i*5*ms,pitch);
 }
 auto moving_sample=latest(moving);valid(moving_sample);
 for(int i=0;i<3;i++)assert(near(moving_sample.acceleration[i],-moving_sample.direction[i*3+2]));
 ControllerMotion settled;const float final_tilt[3]={0,g*.70710678f,-g*.70710678f};
 settled.push_accel(ms,final_tilt);settled.push_gyro(ms,zero);auto static_sample=latest(settled);
 for(int i=0;i<9;i++)assert(near(static_sample.direction[i],moving_sample.direction[i]));
 // Upside-down startup is finite and handles opposite-vector quaternion.
 m.reset();const float inverted[3]={0,-g,0};m.push_accel(ms,inverted);m.push_gyro(ms,zero);
 s=latest(m);valid(s);assert(near(s.direction[8],-1));
 // Bias calibration uses real elapsed time, not read count, and does not drift.
 m.reset();const float bias[3]={.004f,-.006f,.003f};time=ms;
 for(int i=0;i<500;i++,time+=5*ms){m.push_accel(time,flat);m.push_gyro(time,bias);}
 s=latest(m);assert(near(s.angle[0],0)&&near(s.angle[1],0)&&near(s.angle[2],0));
 assert(near(s.direction[0],1));
 // Correcting pitch retains yaw SDL +Y -> HID +Z; the proper half-turn also
 // reverses roll SDL +Z -> HID -Y instead of reflecting only one angular axis.
 for(int axis=1;axis<3;axis++){
  m.reset();float rate[3]={};rate[axis]=pi/2;
  m.push_accel(ms,flat);m.push_gyro(ms,rate);
  for(int i=1;i<=200;i++)m.push_gyro(ms+i*5*ms,rate);
  s=latest(m);valid(s);assert(near(s.angle[axis==1?2:1],axis==1?.25:-.25));
 }
 // Starting while moving cancels calibration; later gentle aiming stays live.
 m.reset();m.push_accel(ms,flat);m.push_gyro(ms,pitch);
 const float slow[3]={.04f,0,0};
 for(int i=1;i<=10;i++){m.push_accel(ms+i*5*ms,flat);m.push_gyro(ms+i*5*ms,slow);}
 s=latest(m);assert(s.velocity[0]>.006f);
 // Verify the actual generated normal-addon conversion, not an assumed camera
 // axis convention. Mouse up produces negative HID X and positive internal X.
 MouseGyro mouse;mouse.capture(true,ms);mouse.move(0,-20,.03,ms);
 auto mouse_up=mouse.sample(0,ms+5*ms);assert(mouse_up.velocity[0]<0);
 auto mouse_game=normal_addon(mouse_up);assert(mouse_game.velocity[0]>0);
 for(float sign:{-1.0f,1.0f}){
  ControllerMotion physical;float rate[3]={sign*.4f,0,0};
  physical.push_accel(ms,flat);physical.push_gyro(ms,rate);
  physical.push_gyro(ms+5*ms,rate);auto hid=latest(physical),game=normal_addon(hid);
  assert(near(hid.velocity[0],sign*.4/(2*pi)));
  assert(near(game.velocity[0],-sign*.4/(2*pi)));
  if(sign<0)assert(game.velocity[0]*mouse_game.velocity[0]>0);
 }
 // Combined pitch/roll/yaw: independent SDL Rodrigues gravity must agree with
 // the quaternion after the polar/axial maps, including nonzero initial tilt.
 const float w[3]={.7f,.2f,-.4f};
 const double length=std::hypot(w[0],w[1],w[2]);
 const double axis[3]={w[0]/length,w[1]/length,w[2]/length};
 const float initial_gravity[2][3]={{0,g,0},{-.3f*g,.8f*g,.51961524f*g}};
 for(const auto& initial:initial_gravity){
 ControllerMotion combined;combined.push_accel(ms,initial);combined.push_gyro(ms,w);
 for(int step=1;step<=200;step++){
  const double theta=length*step*.005,co=std::cos(theta),si=std::sin(theta);
  // R(axis,theta)^T*initial, independently of quaternion code.
  const double dot=axis[0]*initial[0]+axis[1]*initial[1]+axis[2]*initial[2];
  const double cross[3]={axis[1]*initial[2]-axis[2]*initial[1],
    axis[2]*initial[0]-axis[0]*initial[2],axis[0]*initial[1]-axis[1]*initial[0]};
  float gravity_sample[3];for(int i=0;i<3;i++)gravity_sample[i]=float(initial[i]*co+axis[i]*dot*(1-co)-cross[i]*si);
  combined.push_accel(ms+step*5*ms,gravity_sample);combined.push_gyro(ms+step*5*ms,w);
  auto coherent=latest(combined);valid(coherent);
  for(int i=0;i<3;i++)assert(near(coherent.acceleration[i],-coherent.direction[i*3+2]));
 }
 }
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
