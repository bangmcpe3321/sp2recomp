"""Exercise actual draw-trace selection and disabled hot-path work (Linux/WSL)."""
from pathlib import Path
import argparse,os,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--baseline',type=Path);p.add_argument('--benchmark',action='store_true',help='Measure without sanitizer overhead');a=p.parse_args()

def prefix(path):
 s=path.read_text();start=s.index('void trace_draw(');end=s.index('        // PATCH-TRACE-FRAME: dump the guest side',start)
 # The selected trace body is heavy GPU inspection. Keep its actual entry condition,
 # summary formatting and budget update, substituting an emission counter for the dump.
 body=s[start:end]+'        traced++; selected++;\n    }\n}\n'
 return body.replace('std::getenv(', 'checked::getenv(').replace('std::snprintf(', 'checked::snprintf(')

stub=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <cstdint>
namespace checked {
uint64_t lookups=0,formats=0;
const char* getenv(const char* n) { lookups++;return std::getenv(n); }
int snprintf(char* b,size_t n,const char* f,...) { formats++;va_list a;va_start(a,f);int r=std::vsnprintf(b,n,f,a);va_end(a);return r; }
}
namespace nx { std::atomic<uint64_t> g_frame{50}; }
using namespace nx;
struct Targets { uint64_t colors[1]={0x123};uint32_t color_count=1; };
struct Cmd { int i[4]={12,12,0,1}; };
struct ShaderInfo { std::string hash; };
using TexBindings=std::vector<int>;
struct { uint64_t done=0; } g_stats;
uint64_t cube=0,studio=0,signature=0,selected=0,huge=0,checks=0;
void log(const char* f,...) { if(std::strstr(f,"huge draw"))huge++;if(std::strstr(f,"trace check"))checks++; }
void trace_cube_draw(const Targets&,const ShaderInfo*,const ShaderInfo*,const TexBindings&,const std::vector<uint64_t>&) { cube++; }
void studio_shaders_draw(const Targets&,const ShaderInfo*,const ShaderInfo*) { studio++; }
void frame_sig_draw(const Targets&,bool,uint32_t,uint32_t,const ShaderInfo*,const TexBindings&,const std::vector<uint64_t>&) { signature++; }
'''
tail=r'''
int main(int argc,char** argv) {
 Targets t;Cmd cmd;ShaderInfo vs{"vs"},fs{"fs"};TexBindings b;std::vector<uint64_t> h;
 bool baseline=argc>2;std::string mode=argv[1];uint64_t n=mode=="off"?1000000:100;
 auto begin=std::chrono::steady_clock::now();uint64_t cold=0;
 for(uint64_t i=0;i<n;i++) {
  g_stats.done=i;
  if(mode=="huge")cmd.i[0]=1<<19;
  trace_draw(t,0,true,cmd,&vs,&fs,b,h);
  if(!i)cold=checked::lookups;
 }
 double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
 assert(cube==n&&studio==n&&signature==n);
 if(mode=="off") { assert(!selected&&!checks);if(!baseline){assert(checked::lookups==cold);assert(!checked::formats);} }
 if(mode=="debug"){assert(!selected&&checks==12);if(!baseline)assert(!checked::formats);}
 if(mode=="on"){assert(selected==2);if(!baseline)assert(checked::formats==2);}
 if(mode=="mismatch"){assert(!selected);if(!baseline)assert(!checked::formats);}
 if(mode=="huge"){assert(huge==40&&!selected);if(!baseline){assert(!checked::formats);assert(checked::lookups==cold);} }
 std::printf("%s %.3f ms lookups=%llu formats=%llu selected=%llu hooks=%llu\n",mode.c_str(),ms,(unsigned long long)checked::lookups,(unsigned long long)checked::formats,(unsigned long long)selected,(unsigned long long)cube);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-trace-fastpath-') as td:
 d=Path(td)
 for source,baseline in [(a.source,False)]+([(a.baseline,True)] if a.baseline else []):
  cpp=d/'test.cpp';exe=d/'test';cpp.write_text(stub+prefix(source)+tail)
  flags=[] if a.benchmark else ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
  subprocess.run(['g++','-std=c++20','-O1','-g',*flags,str(cpp),'-o',str(exe)],check=True)
  for mode in (['off'] if baseline else ['off','debug','on','mismatch','huge']):
   env={k:v for k,v in os.environ.items() if not k.startswith('NX_TRACE')}
   if mode=='debug':env['NX_TRACE_DRAWS_DEBUG']='1'
   if mode in ['on','mismatch']:env.update(NX_TRACE_DRAWS='3',NX_TRACE_COUNT='2',NX_TRACE_TARGET='123' if mode=='on' else '124',NX_TRACE_FS_HASH='fs')
   subprocess.run([str(exe),mode]+(['baseline'] if baseline else []),env=env,check=True)
print('PASS disabled-path work, trace selection/budgets, debug-only mode, independent hooks and huge-draw warnings')
