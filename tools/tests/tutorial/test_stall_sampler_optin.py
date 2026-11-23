"""Verify real kernel startup retains watchdogs and starts high-frequency sampling only on request."""
from pathlib import Path
import subprocess,sys,tempfile,os
s=Path(sys.argv[1]).read_text()
def function(sig):
 start=s.index(sig);end=s.index('{',start)+1;depth=1
 while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]
code=r'''
#include <cstdlib>
#include <cassert>
#include <cstdint>
void watchdog(void*){} void stall_sampler(void*){}
unsigned watches=0,samplers=0;
namespace plat {void start_thread(void(*fn)(void*),void*,uint64_t size){assert(size==1ull<<20);if(fn==watchdog)watches++;else if(fn==stall_sampler)samplers++;else assert(false);}}
'''+function('static bool stall_sampler_requested()')+'\n'+function('void kernel_init()')+r'''
int main(int argc,char**argv){assert(argc==2);kernel_init();assert(watches==1);assert(samplers==unsigned(std::atoi(argv[1])));}
'''
with tempfile.TemporaryDirectory(prefix='sp2-stall-optin-') as td:
 d=Path(td);cpp=d/'t.cpp';exe=d/'t';cpp.write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-fsanitize=address,undefined',str(cpp),'-o',str(exe)],check=True)
 base=os.environ.copy()
 for key in ['NX_STALL_SAMPLER','NX_THREAD_DUMP_AT','NX_CPU_LOG','NX_NATIVE_LOG']:base.pop(key,None)
 for settings,expected in [({},0),({'NX_STALL_SAMPLER':'0'},0),({'NX_STALL_SAMPLER':'1'},1),({'NX_THREAD_DUMP_AT':'30'},1),({'NX_CPU_LOG':'1'},1),({'NX_NATIVE_LOG':'500'},1),({'NX_STALL_SAMPLER':'0','NX_CPU_LOG':'1'},0)]:
  subprocess.run([str(exe),str(expected)],env={**base,**settings},check=True)
print('PASS kernel startup: watchdog retained, default sampling off, explicit diagnostics on and off override')
