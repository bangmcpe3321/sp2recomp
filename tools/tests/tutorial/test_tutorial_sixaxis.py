"""Compile the actual six-axis HLE functions in an isolated CPU/memory harness."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).read_text()
sensor = source[source.index('uint64_t g_sixaxis_sampling'):source.index('void GetSixAxisSensorHandles')]
states = source[source.index('void GetSixAxisSensorStates'):source.index('\n}  // namespace', source.index('void GetSixAxisSensorStates'))]
prefix = r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <mutex>
#include <cstdio>
struct CPU { uint64_t x[32]{}; };
template<class T> T ld(uint64_t p) { T v; std::memcpy(&v, (void*)p, sizeof v); return v; }
template<class T> void st(uint64_t p, T v) { std::memcpy((void*)p, &v, sizeof v); }
template<class... T> void log(const char*, T...) {}
std::atomic<uint64_t> g_frame{0};
struct { int active=0, aim=0, timer=0; unsigned serial=0; float err_pitch=0,err_yaw=0,dist=0; } g_debug_aim;
bool enabled=true;
bool sixaxis_on() { return enabled; }
'''
tests = r'''
int main() {
  CPU c;
  c.x[0]=0; c.x[1]=uint32_t(-1); GetSixAxisSensorStates(c); assert(c.x[0]==0);
  c.x[0]=0; c.x[1]=0; GetSixAxisSensorStates(c); assert(c.x[0]==0);
  alignas(8) std::array<uint8_t,0x60*17> out;
  uint32_t handle[2]={0,0};
  const uint64_t p=(uint64_t)out.data();
  auto read=[&](int n) { c.x[0]=p;c.x[1]=uint32_t(n);c.x[2]=(uint64_t)handle;GetSixAxisSensorStates(c); };
  for (uint64_t sample=1; sample<=40; ++sample) {
    out.fill(0xA5); read(16);
    assert(c.x[0]==std::min<uint64_t>(sample,16));
    for (unsigned i=0; i<c.x[0]; ++i) {
      assert(ld<uint64_t>(p+i*0x60)==16666667);
      assert(ld<uint64_t>(p+i*0x60+8)==sample-i);
      assert(ld<uint32_t>(p+i*0x60+0x58)==1);
      assert(ld<float>(p+i*0x60+0x34)==1);
      assert(ld<float>(p+i*0x60+0x44)==1);
      assert(ld<float>(p+i*0x60+0x54)==1);
    }
    for (size_t i=c.x[0]*0x60; i<16*0x60; ++i) assert(out[i]==0);
    for (size_t i=16*0x60;i<out.size();++i) assert(out[i]==0xA5);
  }
  handle[1]=1; read(16); assert(c.x[0]==1 && ld<uint64_t>(p+8)==1);
  handle[1]=0; read(1); assert(c.x[0]==1 && ld<uint64_t>(p+8)==41);
  read(1000000); assert(c.x[0]==16 && ld<uint64_t>(p+8)==42);
  enabled=false; out.fill(0xA5); read(16); assert(c.x[0]==0);
  for (size_t i=0;i<16*0x60;++i) assert(out[i]==0);
  assert(out[16*0x60]==0xA5);
  enabled=true; handle[1]=2; read(16); assert(c.x[0]==0);
  handle[1]=0; handle[0]=1; read(16); assert(c.x[0]==0);
  std::puts("PASS: six-axis ABI offsets, increasing per-sensor samples, newest-first history, return counts and bounds");
}
'''
temporary = tempfile.TemporaryDirectory(prefix='sp2-sixaxis-')
work = Path(temporary.name)
cpp = work / 'test.cpp'
cpp.write_text(prefix + sensor + states + tests)
binary = work / 'test'
subprocess.run(['g++', '-std=c++20', '-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-pthread', str(cpp), '-o', str(binary)], check=True)
subprocess.run([str(binary)], check=True)
