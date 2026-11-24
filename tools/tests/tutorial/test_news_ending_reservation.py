#!/usr/bin/env python3
"""Exercise the actual BGM fallback, generated predicate and signature pose."""
from pathlib import Path
import importlib.util
import re
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
tools = Path(__file__).resolve().parents[2]
patch_path = tools/'patches/patch-news-ending-reservation.py'
spec = importlib.util.spec_from_file_location('news_patch', patch_path)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


def function(source, signature):
    begin = source.index(signature)
    end = source.index('{', begin)+1
    depth = 1
    while depth:
        depth += (source[end]=='{')-(source[end]=='}')
        end += 1
    return source[begin:end]


audio = (root/'runtime/src/hle_audio.cpp').read_text()
begin = audio.index('namespace {', audio.index('// NEWSEND-BGM:'))
end = audio.index('\n}  // namespace nx', begin)
audio = audio[begin:end]
predicate = function((root/'gen/main/code_213.cpp').read_text(), 'void main_009DF970(')
pose = function((root/'gen/main/code_020.cpp').read_text(), 'void main_000F3618(')
conductor = (root/'gen/main/code_027.cpp').read_text()
handover = function(conductor, '    { // NEWSEND-BGM handover')
prefix = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#define NX_RESTRICT
constexpr uint64_t NXB=0x7100000000ull;
uint64_t fake_now=10000000000ull;
namespace nx {
struct CPU { uint64_t x[32]{};uint64_t vector[64]{};bool zf=false,nf=false,vf=false,cf=false; };
std::map<uint64_t,uint64_t> memory;
template<class T>T ld(uint64_t a){return T(memory[a]);}
template<class T>void st(uint64_t a,T value){memory[a]=uint64_t(value);}
void subs32(CPU& c,uint32_t a,uint32_t b){c.zf=a==b;c.nf=int32_t(a-b)<0;c.vf=false;c.cf=a>=b;}
void call(CPU& c,uint64_t){c.x[0]=0x555000;}
void log(const char*,...){}
namespace plat {uint64_t monotonic_ns(){return fake_now;}}
'''
stubs = r'''
}
constexpr uint64_t plaza=0x400000,pose_self=0x100000,pose_state=0x110000,proc=0x200000,param=0x300000;
unsigned handovers=0, cleared=0;
void main_009DF970(nx::CPU&);
void main_009DF0B4(nx::CPU& c){++handovers;for(auto& x:c.x)x=~x;for(auto& v:c.vector)v=~v;c.zf=!c.zf;c.nf=!c.nf;}
void main_009DF154(nx::CPU& c){assert(c.x[0]==plaza);for(auto& x:c.x)x=0;for(auto& v:c.vector)v=0;c.cf=!c.cf;c.vf=!c.vf;}
'''
callees = set(re.findall(r'(main_[0-9A-F]+)\(c\)', pose))
custom = {
    'main_00A9AB9C':'c.x[0]=0;',
    'main_009D4B90':'c.x[0]=plaza;main_009DF970(c);',
    'main_00777680':'c.x[0]=1;',
    'main_001E5244':'++cleared;',
}
stubs += '\n'.join('void '+name+'(nx::CPU& c){'+custom.get(name,'')+'}' for name in sorted(callees))
test = r'''
void handover_hook(nx::CPU& c) HANDOVER
uint64_t finished(){nx::CPU c;c.x[0]=plaza;main_009DF970(c);return c.x[0];}
uint64_t signature_pose(){
 nx::CPU c;c.x[0]=pose_self;c.x[1]=proc;c.x[2]=param;c.x[31]=0x800000;
 main_000F3618(c);assert(c.x[31]==0x800000);return c.x[0];
}
int main(){
 using namespace nx;
 memory[plaza+0x410]=1;memory[plaza+0x350]=0x410000;
 memory[0x410020]=7;memory[plaza+0x358]=7;
 memory[pose_self+0x18]=pose_state;memory[pose_state]=1;memory[pose_state+4]=1;
 memory[proc+0x10]=0x600000;memory[proc+0x28]=0x610000;memory[proc+0x30]=0x620000;
 memory[param+0x780]=0x550000;memory[0x5500c8]=0x1234;memory[0x555000]=500;
 hle_audio_news_bgm_arm(plaza,149);
 assert(hle_audio_news_bgm_available()&&hle_audio_news_bgm_pending(plaza));
 for(int i=0;i<10000;++i){assert(!finished());assert(!hle_audio_news_bgm_elapsed(plaza));}
 // An idle/looping idol must not let SignaturePose end before the reserved region.
 assert(!signature_pose()&&!cleared);
 assert(!hle_audio_news_bgm_take(plaza));
 fake_now+=2483333333ull;assert(!finished());assert(!signature_pose());
 fake_now+=1;assert(finished());assert(signature_pose()==1&&cleared==1);
 CPU caller;for(unsigned i=0;i<32;++i)caller.x[i]=0x123000+i;
 for(unsigned i=0;i<64;++i)caller.vector[i]=0x456000+i;
 caller.zf=caller.cf=true;CPU saved=caller;
 handover_hook(caller);assert(handovers==1);
 assert(!std::memcmp(caller.x,saved.x,sizeof caller.x));
 assert(!std::memcmp(caller.vector,saved.vector,sizeof caller.vector));
 assert(caller.zf==saved.zf&&caller.nf==saved.nf&&caller.cf==saved.cf&&caller.vf==saved.vf);
 assert(memory[plaza+0x3f0]==2);handover_hook(caller);assert(handovers==1);
 assert(finished()); // completed fallback remains available to all later polls
 fake_now+=10000000000ull;hle_audio_news_bgm_arm(plaza,60);
 assert(!finished());fake_now-=1;assert(!finished());fake_now+=1000000001ull;assert(finished());
 assert(!hle_audio_news_bgm_elapsed(plaza+1)&&!hle_audio_news_bgm_pending(plaza+1));
 // No inferred native BGM event: only the explicit event API disables fallback.
 hle_audio_note_bgm_play_event();assert(!hle_audio_news_bgm_available());
 memory[0x410020]=7;assert(!finished());memory[0x410020]=8;assert(finished());
 std::cout<<"PASS: actual news predicate and pose respect149/60s reservation, repeated polls do not advance it, one handover preserves all registers, native event wins\n";
}
'''.replace('HANDOVER',handover)

with tempfile.TemporaryDirectory(prefix='sp2-news-reservation-') as tmp:
    directory = Path(tmp)
    cpp, exe = directory/'test.cpp', directory/'test'
    cpp.write_text(prefix+audio+stubs+'\n'+predicate+'\n'+pose+'\n'+test)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
    fixture = directory/'fixture'
    originals = {}
    for name in patch.CHANGES:
        data=(root/name).read_bytes();originals[name]=data
        target=fixture/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    def apply(*flags,ok=True):
        result=subprocess.run([sys.executable,str(patch_path),'--root',str(fixture),*flags],capture_output=True,text=True)
        assert (result.returncode==0)==ok,result.stdout+result.stderr
    apply('--check');apply()
    assert all((fixture/p).read_bytes()==data for p,data in originals.items())
    apply('--restore');apply()
    assert all((fixture/p).read_bytes()==data for p,data in originals.items())
    path=fixture/'gen/main/code_027.cpp';path.write_bytes(path.read_bytes().replace(b'hand over missing anchor',b''))
    path.write_bytes(path.read_bytes().replace(b'nx::CPU handover_ = c;',b'nx::CPU unknown_context = c;'))
    broken={p:(fixture/p).read_bytes() for p in originals}
    apply('--restore',ok=False)
    assert all((fixture/p).read_bytes()==data for p,data in broken.items())
    print('PASS news reservation patch preflight, idempotence, exact restore and multi-file failure safety')
