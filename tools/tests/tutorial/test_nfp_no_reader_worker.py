#!/usr/bin/env python3
"""Prove DeviceNotFound reaches the game's real NFP worker completion path."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
source = (root/'gen/main/code_391.cpp').read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start)+1
    depth = 1
    while depth:
        depth += (source[end]=='{')-(source[end]=='}')
        end += 1
    return source[start:end]


handler = function(source, 'void main_01218AE8(')
worker = function(source, 'void main_012185F4(')
prefix = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#define NX_RESTRICT
constexpr uint64_t NXB=0x7100000000ull;
constexpr uint64_t self=0x500000,handle=0x550000,stack=0x800000;
unsigned stops=0,initializes=0,lists=0,sleeps=0;
namespace nx {
struct CPU {uint64_t x[32]{};bool zf=false,nf=false,vf=false,cf=false;};
std::map<uint64_t,uint64_t> memory;
template<class T>T ld(uint64_t a){return T(memory[a]);}
template<class T>void st(uint64_t a,T v){memory[a]=uint64_t(v);}
void subs32(CPU& c,uint32_t a,uint32_t b){
 uint32_t value=a-b;c.zf=value==0;c.nf=value>>31;c.cf=a>=b;
 c.vf=((a^b)&(a^value))>>31;
}
void subs64(CPU& c,uint64_t a,uint64_t b){
 uint64_t value=a-b;c.zf=value==0;c.nf=value>>63;c.cf=a>=b;
 c.vf=((a^b)&(a^value))>>63;
}
void call(CPU&,uint64_t){assert(!"unexpected indirect call without a reader");}
}
void main_01414358(nx::CPU& c){assert(c.x[0]==handle);++stops;}
void main_01414368(nx::CPU& c){c.x[0]=1;} // software NFP state: initialized
void main_01414378(nx::CPU&){assert(!"device-state query without a reader");}
void main_01414388(nx::CPU&){++initializes;}
void main_01414398(nx::CPU& c){
 // The service must return a genuine absence error, never a fake device handle.
 ++lists;assert(c.x[2]==9);nx::st<uint32_t>(c.x[1],0);c.x[0]=0x8073;
}
void main_012CDF50(nx::CPU& c){assert(c.x[0]==100);assert(++sleeps<3);}
'''
defined = {'main_01414358','main_01414368','main_01414378','main_01414388',
           'main_01414398','main_012CDF50','main_01218AE8'}
callees = set(re.findall(r'(main_[0-9A-F]+)\(c\)',worker)) - defined
prefix += '\n'.join('void '+name+'(nx::CPU&){assert(!"unexpected NFP reader operation");}' for name in sorted(callees))
test = r'''
nx::CPU prepare(uint32_t phase,uint32_t result){
 nx::memory.clear();stops=initializes=lists=sleeps=0;
 nx::CPU c;for(unsigned i=0;i<32;++i)c.x[i]=0x12340000+i;
 c.x[0]=self;c.x[31]=stack;
 nx::memory[self+0x370]=phase;nx::memory[self+0x380]=77;
 nx::memory[self+0x388]=88;nx::memory[self+0x390]=result;
 nx::memory[self+0x6a8]=handle;
 return c;
}
void preserved(const nx::CPU& c,const nx::CPU& saved){
 for(unsigned i=19;i<=30;++i)assert(c.x[i]==saved.x[i]);
 assert(c.x[31]==saved.x[31]);
}
int main(){
 // Actual error handler accepts DeviceNotFound from every phase and leaves the
 // normal no-reader completion code; active detection is stopped only if needed.
 for(uint32_t phase=0;phase<7;++phase){
  auto c=prepare(phase,0x8073);const auto saved=c;
  main_01218AE8(c);preserved(c,saved);
  assert(nx::memory[self+0x390]==0x8073);
  assert(nx::memory[self+0x380]==0&&nx::memory[self+0x388]==2);
  assert(nx::memory[self+0x339]==1&&stops==unsigned(phase>=2));
 }
 // Neighboring error values must not accidentally take the no-reader path.
 // In this game NfcDisabled is an explicit unavailable/error completion (3).
 auto c=prepare(1,0xa073);auto saved=c;main_01218AE8(c);preserved(c,saved);
 assert(nx::memory[self+0x339]==1&&nx::memory[self+0x388]==3);
 c=prepare(1,0x1234);saved=c;main_01218AE8(c);preserved(c,saved);
 assert(nx::memory[self+0x339]==0&&nx::memory[self+0x388]==88);
 assert(nx::memory[self+0x370]==0&&nx::memory[self+0x390]==0x1234);
 // The generated worker itself terminates after ListDevices' absence result.
 // This rules out changing the AV into an endless zero-device success poll.
 c=prepare(1,0);saved=c;
 const uint64_t table=NXB+0x29175a0;
 nx::memory[table+4]=uint32_t((NXB+0x121871c)-table);
 main_012185F4(c);preserved(c,saved);
 assert(lists==1&&initializes==0&&stops==0&&sleeps==1);
 assert(nx::memory[self+0x339]==1&&nx::memory[self+0x388]==2);
 assert(nx::memory[self+0x390]==0x8073);
 std::cout<<"PASS: actual NFP worker exits once with no-reader result0x8073, active cleanup is conditional, NfcDisabled stays distinct, callee-saved registers/SP restored\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-nfp-no-reader-') as tmp:
    directory=Path(tmp)
    cpp,exe=directory/'test.cpp',directory/'test'
    cpp.write_text(prefix+'\n'+handler+'\n'+worker+'\n'+test)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
