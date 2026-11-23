"""Run actual generated GetGlyph and cache lookup against missing/present nodes."""
import argparse
from pathlib import Path
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("source", type=Path, help="gen/main/code_417.cpp")
p.add_argument("--baseline", type=Path, help="unpatched source; must reproduce the null load")
a = p.parse_args()


def function(source, name):
    start = source.index("void " + name + "(")
    end = source.index("\n}\n", start) + 3
    return source[start:end]


PREFIX = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#define NX_RESTRICT
constexpr uint64_t NXB=0x7100000000ull;
namespace nx {
struct CPU { uint64_t x[32]{}; bool zf{},cf{},nf{},vf{}; };
template<class T> T ld(uint64_t a) { T v; std::memcpy(&v,(void*)a,sizeof v); return v; }
template<class T> void st(uint64_t a,T v) { std::memcpy((void*)a,&v,sizeof v); }
inline void subs64(CPU& c,uint64_t x,uint64_t y) { c.zf=x==y;c.cf=x>=y;c.nf=int64_t(x-y)<0;c.vf=((x^y)&(x^(x-y)))>>63; }
inline void subs32(CPU& c,uint32_t x,uint32_t y) { c.zf=x==y;c.cf=x>=y;c.nf=int32_t(x-y)<0;c.vf=((x^y)&(x^(x-y)))>>31; }
void log(const char*,...) {}
}
bool coverage=true;
void main_0136426C(nx::CPU& c) { nx::st<uint32_t>(c.x[1],0);c.x[0]=coverage; }
void main_013653C4(nx::CPU& c) { c.x[0]=coverage; }
void main_013654B8(nx::CPU& c) { c.x[0]=40; }
void main_01360274(nx::CPU&);
void main_0136591C(nx::CPU&);
'''

MAIN = r'''
alignas(16) uint8_t font[0x40],cache[0x1c00],node[0x60],stack[0x400],output[0x50];
void reset(int mode,int key) {
 std::memset(font,0,sizeof font);std::memset(cache,0,sizeof cache);std::memset(node,0,sizeof node);
 std::memset(output,0xa5,sizeof output);coverage=true;
 nx::st<uint64_t>((uint64_t)font+0x10,(uint64_t)cache);
 nx::st<uint32_t>((uint64_t)font+0x18,40);
 nx::st<uint8_t>((uint64_t)font+0x2f,mode);
 nx::st<uint32_t>((uint64_t)font+0x34,63);
 nx::st<uint64_t>((uint64_t)cache+0x20,0xfeed1234);
 nx::st<uint32_t>((uint64_t)cache+0x28,2048);nx::st<uint32_t>((uint64_t)cache+0x2c,1024);
 if(key>=0) {
  nx::st<uint64_t>((uint64_t)cache+0x30,(uint64_t)node);
  nx::st<uint64_t>((uint64_t)node+0x30,(uint64_t(40)<<48)|uint64_t(key));
  nx::st<uint8_t>((uint64_t)node+0x38,4);
  nx::st<uint16_t>((uint64_t)node+0x40,13);nx::st<uint16_t>((uint64_t)node+0x42,14);
  nx::st<uint16_t>((uint64_t)node+0x44,15);nx::st<uint16_t>((uint64_t)node+0x46,16);
  nx::st<uint16_t>((uint64_t)node+0x48,17);nx::st<uint16_t>((uint64_t)node+0x4a,18);
  nx::st<uint16_t>((uint64_t)node+0x4c,19);
 }
}
void run(int expected_advance,bool empty) {
 nx::CPU c;for(int i=19;i<=30;++i)c.x[i]=0x12340000+i;
 uint64_t before[32];std::memcpy(before,c.x,sizeof before);
 c.x[0]=(uint64_t)font;c.x[1]=(uint64_t)output+8;c.x[2]=65;c.x[31]=(uint64_t)stack+sizeof stack;
 uint64_t sp=c.x[31];main_013629FC(c);
 for(int i=19;i<=30;++i)assert(c.x[i]==before[i]);assert(c.x[31]==sp);
 for(int i=0;i<8;++i)assert(output[i]==0xa5);
 for(int i=8+0x29;i<(int)sizeof output;++i)assert(output[i]==0xa5);
 uint64_t out=(uint64_t)output+8;
 assert(nx::ld<uint64_t>(out)==0xfeed1234);
 assert(nx::ld<uint16_t>(out+0xc)==expected_advance);
 assert(nx::ld<uint16_t>(out+0x12)==2048&&nx::ld<uint16_t>(out+0x14)==1024);
 assert(nx::ld<uint16_t>(out+0x1a)==8&&nx::ld<uint16_t>(out+0x1c)==0);
 assert(nx::ld<uint64_t>(out+0x20)==(uint64_t)cache+0x1ba0);
 assert(nx::ld<uint8_t>(out+0x28)==0);
 if(empty) {
  for(int off:{8,10,14,16,22,24,30})assert(nx::ld<uint16_t>(out+off)==0);
 } else {
  assert(nx::ld<uint16_t>(out+8)==19&&nx::ld<uint16_t>(out+10)==16);
  assert(nx::ld<uint16_t>(out+14)==15&&nx::ld<uint16_t>(out+16)==18);
  assert(nx::ld<uint16_t>(out+22)==14&&nx::ld<uint16_t>(out+24)==14);
  assert((nx::ld<uint8_t>((uint64_t)node+0x38)&4)!=0);
 }
}
int main() {
 reset(1,-1);run(40,true); // Exact crash: supported char, missing SPACE cache node.
 reset(0,-1);run(40,true); // Same assumption in alternate glyph mode.
 reset(2,-1);run(0,true); // Missing default: requested char is not an advance.
 reset(1,-1);coverage=false;run(0,true);
 reset(1,65);run(18,false); // Cached original glyph remains byte-for-byte compatible.
 reset(1,32);run(40,false); // Existing SPACE still supplies bitmap and measured advance.
 reset(2,63);run(18,false); // Existing alternate/default glyph keeps its metrics.
 std::puts("PASS GetGlyph missing SPACE/default, measured advance, cached paths, ABI bounds and callee-saved registers");
}
'''.replace('#include_placeholder','')


def compile_and_run(source, directory, tag):
    body = "\n".join(function(source, n) for n in ["main_01360274", "main_0136591C", "main_013629FC"])
    cpp = directory / (tag + ".cpp")
    exe = directory / tag
    cpp.write_text("#include <initializer_list>\n" + PREFIX + body + MAIN)
    subprocess.run(["g++", "-std=c++20", "-O1", "-g", "-fsanitize=undefined", "-fno-sanitize-recover=all", str(cpp), "-o", str(exe)], check=True)
    return subprocess.run([str(exe)], capture_output=True, text=True)


with tempfile.TemporaryDirectory(prefix="sp2-font-fallback-") as td:
    directory = Path(td)
    if a.baseline:
        result = compile_and_run(a.baseline.read_text(), directory, "baseline")
        assert result.returncode != 0, "unpatched source did not reproduce the crash"
        print("PASS unpatched source reproduces missing SPACE null-load failure")
    result = compile_and_run(a.source.read_text(), directory, "fixed")
    print(result.stdout, end="")
    if result.returncode:
        raise SystemExit(result.stderr or result.returncode)
