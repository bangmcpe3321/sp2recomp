#!/usr/bin/env python3
"""Round-trip native audio through this SDK's actual auxiliary-buffer functions."""
from pathlib import Path
import ast,re,subprocess,sys,tempfile
root=Path(sys.argv[1]).resolve()
fixture_file=Path(__file__).with_name('test_sp2_audio.py')
tree=ast.parse(fixture_file.read_text())
source=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SOURCE' for t in n.targets))
fixture=source[source.index('struct Fixture {'):source.index('int main(){')]
prefix='''#include "sp2_audio_renderer.h"
#include <nx/cpu.h>
#include <cassert>
#include <iostream>
using nx::CPU;
using namespace nx::sp2::audio;
constexpr uint64_t NXB=0;
void sdk_002C24CC(CPU&){} // CPU memory is coherent; these SDK calls flush data caches.
void sdk_00159A58(CPU&);void sdk_00159C00(CPU&);
void sdk_002C910C(CPU& c){sdk_00159A58(c);}
void sdk_002BC67C(CPU& c){sdk_00159C00(c);}
'''
bodies={}
for path in (root/'gen/sdk').glob('code_*.cpp'):
    text=path.read_text()
    for name in ('sdk_00159A58','sdk_00159C00','sdk_0015B040','sdk_0015B060'):
        match=re.search(r'void '+name+r'\(nx::CPU& NX_RESTRICT c\) \{\n(.*?)\n\}',text,re.S)
        if match:bodies[name]=match.group(0)
if len(bodies)!=4:raise SystemExit('Missing SDK auxiliary routine')
test=r'''
int main(){
 Fixture f(1,1,1,1);for(unsigned i=0;i<1000;i++)put<int16_t>(f.memory,2*i,1000);f.wave(0,0,1000,2000,true);
 Sections sections(f.packet);size_t e=sections.data[5].data()-f.packet.data();
 auto address=[&](size_t offset){return uint64_t(f.memory.data()+offset);};
 put<uint8_t>(f.packet,e,2);put<uint8_t>(f.packet,e+2,1);put<uint32_t>(f.packet,e+0x50,1);put<uint32_t>(f.packet,e+0x58,720);
 // These four fields are also loaded by the unmodified SDK ReadAuxSendBuffer/WriteAuxReturnBuffer below.
 put<uint64_t>(f.packet,e+0x60,address(0x2000));put<uint64_t>(f.packet,e+0x68,address(0x3000));put<uint64_t>(f.packet,e+0x70,address(0x2100));put<uint64_t>(f.packet,e+0x78,address(0x4000));
 auto read=[&](uint64_t a,size_t size)->const uint8_t*{uint64_t base=address(0);if(a>=base&&a-base<=f.memory.size()&&size<=f.memory.size()-(a-base))return reinterpret_cast<const uint8_t*>(a);return f.read()(a,size);};
 auto write=[&](uint64_t a,size_t size)->uint8_t*{return const_cast<uint8_t*>(read(a,size));};
 Renderer renderer(read,write);std::array<uint8_t,0xc0> effect{};std::memcpy(effect.data(),f.packet.data()+e,0xc0);uint64_t aux=uint64_t(effect.data());
 alignas(16) std::array<uint8_t,4096> stack{};std::array<int32_t,240> data{};
 uint64_t auxType=uint64_t(&aux);
 for(unsigned frame=0;frame<100;frame++){
  renderer.update(f.packet,true);if(frame)assert(renderer.pcm[0]==2000);f.accepted();
  CPU c{};c.x[31]=uint64_t(stack.data()+stack.size());c.x[0]=auxType;c.x[1]=uint64_t(data.data());c.x[2]=240;
  sdk_0015B040(c);assert(c.x[0]==240);for(auto sample:data)assert(sample==1000);
  for(auto& sample:data)sample*=2;
  c=CPU{};c.x[31]=uint64_t(stack.data()+stack.size());c.x[0]=auxType;c.x[1]=uint64_t(data.data());c.x[2]=240;
  sdk_0015B060(c);assert(c.x[0]==240);
 }
 assert(renderer.auxSent==24000&&renderer.auxReturned==23760);
 std::cout<<"PASS: native -> real SDK ReadAuxSendBuffer -> guest effect -> real SDK WriteAuxReturnBuffer -> native output, including ring wrap\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-sdk-aux-test-') as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(prefix+'\n'.join(bodies.values())+fixture+test)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root/'runtime/src'),'-I',str(root/'runtime/include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
