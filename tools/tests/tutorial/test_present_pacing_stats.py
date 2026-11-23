"""Exercise actual present pacing with optional diagnostic statistics (Linux/WSL)."""
from pathlib import Path
import argparse, os, subprocess, tempfile
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();source=a.source.read_text()
def function(signature):
 start=source.index(signature);opening=source.index('{',start);depth=1;end=opening+1
 while depth:
  depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]
code=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
struct WaitSite { const char* name;std::atomic<uint64_t> calls{0},blocked{0},ns{0},frame_ns{0}; };
WaitSite g_wait_sites[4]={{"sync wait"},{"queue finish"},{"pool invalidate"},{"pool finalize"}};
std::vector<std::string> lines;
void log(const char* f,...) { char b[1024];va_list a;va_start(a,f);std::vsnprintf(b,sizeof b,f,a);va_end(a);lines.emplace_back(b); }
namespace plat {
uint64_t clock_ns=1000000000ull,sleeps=0,slept=0;
uint64_t monotonic_ns() {return clock_ns;}
void sleep_ns(int64_t ns) {assert(ns>0);clock_ns+=uint64_t(ns);slept+=uint64_t(ns);sleeps++;}
}
'''+function('void log_wait_sites(')+'\n'+function('void pace_present(')+r'''
int main(int argc,char** argv) {
 assert(argc==2);std::string scenario=argv[1];constexpr uint64_t period=16666667;
 if (scenario=="unpaced") { for(int i=0;i<1200;i++)pace_present(1);assert(plat::sleeps==0&&lines.empty());return 0; }
 g_wait_sites[0].calls=17;g_wait_sites[0].blocked=3;g_wait_sites[0].ns=2500000;g_wait_sites[0].frame_ns=123;
 uint64_t start=plat::clock_ns;
 // A 5ms CPU workload remains spaced by 60Hz deadlines over an entire stats window.
 for (int i=0;i<600;i++) {pace_present(1);if(i!=599)plat::clock_ns+=5000000;}
 assert(plat::clock_ns==start+599*period);assert(plat::sleeps==599);
 bool enabled=scenario=="enabled";
 if(enabled) {
  assert(lines.size()==2);assert(lines[0].find("0 of the last 600")!=std::string::npos);
  assert(lines[1].find("sync wait 17 calls, 3 blocked 2.5 ms")!=std::string::npos);
  assert(g_wait_sites[0].calls==0&&g_wait_sites[0].blocked==0&&g_wait_sites[0].ns==0);
 } else {assert(lines.empty());assert(g_wait_sites[0].calls==17);}
 assert(g_wait_sites[0].frame_ns==123); // Per-frame wait accounting belongs to the guest probe.
 // An unpaced interval neither sleeps nor consumes a future pacing deadline.
 uint64_t before=plat::clock_ns;pace_present(0);assert(plat::clock_ns==before);
 pace_present(2);assert(plat::clock_ns==before+period);
 // Interval changes preserve the guest's requested 30Hz period on the following frame.
 before=plat::clock_ns;pace_present(2);assert(plat::clock_ns==before+2*period);
 // A late frame is not snapped to an extra vsync or followed by catch-up bursts.
 plat::clock_ns+=100000000;before=plat::clock_ns;pace_present(1);assert(plat::clock_ns==before);
 pace_present(1);assert(plat::clock_ns==before+period);
 // The next 600-present window reports its own interval distribution.
 if(enabled) {
  for(int i=0;i<596;i++)pace_present(2);
  assert(lines.size()==4);assert(lines[2].find("598 of the last 600")!=std::string::npos);
 }
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-present-stats-') as td:
 d=Path(td);cpp=d/'test.cpp';exe=d/'test';cpp.write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
 for scenario,stats,unpaced in [('disabled',None,None),('disabled','0',None),('enabled','1',None),('unpaced','1','1')]:
  env=os.environ.copy();env.pop('NX_PRESENT_STATS',None);env.pop('NX_NO_FRAME_LIMIT',None)
  if stats is not None:env['NX_PRESENT_STATS']=stats
  if unpaced is not None:env['NX_NO_FRAME_LIMIT']=unpaced
  subprocess.run([str(exe),scenario],env=env,check=True)
print('PASS actual pacing deadlines, late frames, interval changes, disabled statistics and opt-in wait counts')
