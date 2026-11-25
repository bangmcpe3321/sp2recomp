"""Exercise the actual coherent upload-memory selector with device-type mocks."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(sys.argv[1]);src=(root/'runtime/src/nvn/nvn_caps.cpp').read_text();start=src.index('uint32_t upload_memory_type(');at=src.index('{',start);end=at+1;depth=1
while depth:depth+=(src[end]=='{')-(src[end]=='}');end+=1
body=src[start:end]
code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
using VkMemoryPropertyFlags=uint32_t;
constexpr uint32_t VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT=1,VK_MEMORY_PROPERTY_HOST_COHERENT_BIT=2,VK_MEMORY_PROPERTY_HOST_CACHED_BIT=4;
struct VkPhysicalDeviceMemoryProperties {uint32_t memoryTypeCount=0;struct {uint32_t propertyFlags=0;}memoryTypes[32];} properties;
unsigned queries=0,logs=0;int vk_physical(){return 1;}
void p_vkGetPhysicalDeviceMemoryProperties(int,VkPhysicalDeviceMemoryProperties* p){queries++;*p=properties;}
void log(const char*,...){++logs;}
uint32_t memory_type(uint32_t bits,VkMemoryPropertyFlags flags){
 for(uint32_t i=0;i<properties.memoryTypeCount;i++)if((bits>>i&1)&&(properties.memoryTypes[i].propertyFlags&flags)==flags)return i;
 return 0;
}
'''+body+r'''
int main(){
 properties.memoryTypeCount=6;
 properties.memoryTypes[0].propertyFlags=0;
 properties.memoryTypes[1].propertyFlags=1; // noncoherent cannot be selected
 properties.memoryTypes[2].propertyFlags=7; // coherent cached, lower index
 properties.memoryTypes[3].propertyFlags=3; // coherent uncached
 properties.memoryTypes[4].propertyFlags=7; // coherent cached
 properties.memoryTypes[5].propertyFlags=5; // cached but noncoherent cannot be selected
 unsetenv("NX_RING_CACHED");assert(upload_memory_type(0x38)==3 && queries==0);
 setenv("NX_RING_CACHED","0",1);assert(upload_memory_type(0x38)==3 && queries==0);
 setenv("NX_RING_CACHED","1",1);assert(upload_memory_type(0x38)==4 && queries==1 && logs==1);
 assert(upload_memory_type(0x3F)==2); // first compatible cached type, not first host-visible
 assert(upload_memory_type(0x28)==3); // cached types disallowed by resource bits: coherent fallback
 properties.memoryTypes[4].propertyFlags=5;assert(upload_memory_type(0x38)==3); // noncoherent cached rejected
 properties.memoryTypes[4].propertyFlags=7;
 // Compare the production policy against an independent full property/bit-mask scan.
 for(unsigned mask=1;mask<64;mask++){
  if(!(mask&0x1C))continue; // require at least one coherent resource-compatible type
  unsigned expected=32;
  for(unsigned i=0;i<6;i++)if((mask&(1u<<i))&&((properties.memoryTypes[i].propertyFlags&7)==7)){expected=i;break;}
  if(expected==32)for(unsigned i=0;i<6;i++)if((mask&(1u<<i))&&((properties.memoryTypes[i].propertyFlags&3)==3)){expected=i;break;}
  assert(upload_memory_type(mask)==expected);
 }
 puts("PASS actual upload memory selection: cached/coherent preference, resource bits, first-compatible order, noncoherent rejection, fallback and opt-out");
}
'''
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp);(path/'test.cpp').write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
