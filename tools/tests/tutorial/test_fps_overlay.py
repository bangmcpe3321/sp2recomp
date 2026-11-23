"""Source-extracted FPS overlay metrics; no GPU or Windows desktop required."""
import argparse,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();s=a.source.read_text()
def function(signature):
 start=s.index(signature);op=s.index('{',start);depth=1;end=op+1
 while depth:
  depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]
start=s.index('struct FpsCounters {');end=s.index('static FpsCounters',start);counter=s[start:end]
tick=function('static void fps_overlay_tick()')
prefix=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <string>
using HWND=uintptr_t;
constexpr bool FALSE=false;
FpsCounters_PLACEHOLDER
static FpsCounters g_fps_counters;
static wchar_t g_fps_text[128]{};
static HWND g_fps_window=1;
uint64_t clock_now=1000000000;
unsigned paints=0,positions=0;
uint64_t monotonic_ns() { return clock_now; }
void fps_overlay_position() { positions++; }
bool IsWindowVisible(HWND) { return true; }
void InvalidateRect(HWND,void*,bool) { paints++; }
'''.replace('FpsCounters_PLACEHOLDER',counter)
tests=r'''
int main() {
 static_assert(std::atomic<uint64_t>::is_always_lock_free);
 fps_overlay_tick();assert(paints==1 && positions==1);
 // Displayed FPS uses completed presents and elapsed wall time, independent of simulation.
 for(uint64_t k=1;k<=60;k++)g_fps_counters.presented(1000000000+16666667*k);
 clock_now=2000000020;fps_overlay_tick();
 assert(std::wstring(g_fps_text).find(L"60.0 FPS")!=std::wstring::npos);
 assert(std::wstring(g_fps_text).find(L"16.7 ms")!=std::wstring::npos);
 assert(std::wstring(g_fps_text).find(L"peak 16.7 ms")!=std::wstring::npos);
 // Stalls are shown even when no new frame arrives; no division by zero.
 clock_now+=1000000000;fps_overlay_tick();
 assert(std::wstring(g_fps_text).find(L"0.0 FPS")!=std::wstring::npos);
 assert(std::wstring(g_fps_text).find(L"1000 ms")!=std::wstring::npos);
 // A long frame remains visible as the peak rather than being hidden by a later short frame.
 g_fps_counters.presented(clock_now+10000000);g_fps_counters.presented(clock_now+20000000);
 clock_now+=250000000;fps_overlay_tick();
 assert(std::wstring(g_fps_text).find(L"8.0 FPS")!=std::wstring::npos);
 assert(std::wstring(g_fps_text).find(L"125.0 ms")!=std::wstring::npos);
 assert(std::wstring(g_fps_text).find(L"peak 1010.0 ms")!=std::wstring::npos);
 assert(g_fps_counters.frames.load()==62);
 // A backwards or repeated timestamp cannot underflow into a fake enormous peak.
 FpsCounters independent;independent.presented(100);independent.presented(90);independent.presented(90);
 assert(independent.frames.load()==3 && independent.peak_ns.load()==0);
 independent.presented(190);assert(independent.peak_ns.load()==100);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-fps-overlay-') as td:
 d=Path(td);cpp=d/'test.cpp';exe=d/'test';cpp.write_text(prefix+'\n'+tick+tests)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
print('PASS FPS/mean/peak frame metrics, no-frame stalls, zero/reversed timestamps and lock-free present counters')
