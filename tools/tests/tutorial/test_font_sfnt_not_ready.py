#!/usr/bin/env python3
"""Execute actual fs_NewSfnt against sentinel/null and valid cached SFNT objects."""
from pathlib import Path
import re,subprocess,sys,tempfile
root=Path(sys.argv[1]).resolve();source=(root/'gen/sdk/code_035.cpp').read_text()
function=re.search(r'void sdk_001A2A1C\(nx::CPU& NX_RESTRICT c\) \{\n.*?\n\}',source,re.S).group(0)
prefix=r'''
#include <nx/cpu.h>
#include <array>
#include <cassert>
#include <iostream>
constexpr uint64_t NXB=0;
void sdk_002C30AC(nx::CPU& c){c.x[0]=0;}
'''
test=r'''
int main(){
 alignas(16) std::array<uint8_t,0x100> font{},face{},state{},sfnt{},head{},hhea{},maxp{},output{};
 alignas(16) std::array<uint8_t,0x540> glyph{};alignas(16) std::array<uint8_t,0x400> stack{};
 uint64_t slot=uint64_t(state.data());
 nx::st<uint64_t>(uint64_t(face.data())+8,uint64_t(glyph.data()));nx::st<uint8_t>(uint64_t(glyph.data())+0x1ec,1);
 nx::st<uint64_t>(uint64_t(face.data())+0x28,uint64_t(&slot));
 nx::st<uint64_t>(uint64_t(sfnt.data())+0x30,uint64_t(head.data()));nx::st<uint64_t>(uint64_t(sfnt.data())+0x38,uint64_t(hhea.data()));nx::st<uint64_t>(uint64_t(sfnt.data())+0x48,uint64_t(maxp.data()));
 nx::st<uint16_t>(uint64_t(head.data())+0x12,1000);nx::st<uint16_t>(uint64_t(head.data())+0x10,7);nx::st<uint16_t>(uint64_t(hhea.data())+0x22,19);nx::st<uint16_t>(uint64_t(maxp.data())+0x12,4);
 for(uint64_t pointer:std::array<uint64_t,3>{0,1,uint64_t(sfnt.data())}){
  font.fill(0);output.fill(0xa5);nx::st<uint64_t>(uint64_t(state.data())+0x38,pointer);
  nx::CPU c{};for(unsigned i=19;i<31;i++)c.x[i]=0xaaaa0000+i;auto saved=c;
  c.x[0]=uint64_t(font.data());c.x[1]=uint64_t(face.data());c.x[2]=uint64_t(output.data());c.x[31]=uint64_t(stack.data()+stack.size());uint64_t sp=c.x[31];
  sdk_001A2A1C(c);
  assert(c.x[19]==saved.x[19]&&c.x[20]==saved.x[20]&&c.x[29]==saved.x[29]&&c.x[30]==saved.x[30]&&c.x[31]==sp);
  if(pointer<=1){assert(c.x[0]==0x130);assert(nx::ld<uint32_t>(uint64_t(font.data())+0x48)==0x130);for(auto b:output)assert(b==0xa5);}
  else{assert(c.x[0]==0);assert(nx::ld<uint32_t>(uint64_t(font.data())+0x48)==0);assert(nx::ld<uint16_t>(uint64_t(output.data())+0x40)==1000);assert(nx::ld<uint16_t>(uint64_t(glyph.data())+0x200)==19);}
 }
 std::cout<<"PASS: actual SFNT lookup rejects 0/1, publishes caller-visible font status, preserves registers/output, and retains valid font behavior\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sfnt-test-') as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(prefix+function+test)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root/'runtime/include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
