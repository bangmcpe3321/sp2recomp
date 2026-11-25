"""Exercise the production cache with a strict allocation ownership model."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(sys.argv[1]);folder=root/'runtime/src/nvn'
header=folder/'image_memory_cache.h'
frames=(folder/'nvn_frames.cpp').read_text();image=(folder/'nvn_image.cpp').read_text()
# Existing retirement tests cover submit serials/shared holders. Cache return must
# stay after those gates and after all views and the VkImage are destroyed.
region=frames[frames.index('void free_retired_images('):frames.index('Texture::~Texture()')]
assert region.index('e.first > completed') < region.index('img.use_count() > long(h->second)') < region.index('forget_image_views(*img)') < region.index('p_vkDestroyImage(vk_device(), img->image, nullptr)') < region.index('release_image_memory(img->memory)')
assert image.count('image_memory_cache().allocate(ai, &img->memory)')==2
code=r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <map>
#include <set>
#include <vector>
using VkDeviceMemory=uint64_t;
using VkResult=int;
constexpr VkResult VK_SUCCESS=0,VK_ERROR_OUT_OF_DEVICE_MEMORY=-2,VK_ERROR_DEVICE_LOST=-4;
struct VkMemoryAllocateInfo { const void* pNext=nullptr;uint64_t allocationSize=0;uint32_t memoryTypeIndex=0; };
namespace nx::nvn {int vk_device(){return 1;}}
namespace nx::vk {
std::map<uint64_t,VkMemoryAllocateInfo> live;
std::set<uint64_t> bound;
uint64_t next=0,allocations=0,frees=0;int failures=0;bool lost=false;
int p_vkAllocateMemory(int,const VkMemoryAllocateInfo* ai,void*,VkDeviceMemory* out){
 ++allocations;if(lost)return VK_ERROR_DEVICE_LOST;if(failures){--failures;return VK_ERROR_OUT_OF_DEVICE_MEMORY;}
 *out=++next;assert(live.emplace(*out,*ai).second);return VK_SUCCESS;
}
void p_vkFreeMemory(int,VkDeviceMemory m,void*){assert(!bound.count(m));assert(live.erase(m)==1);++frees;}
}
'''+ '#include "'+str(header)+'"\n'+r'''
using namespace nx::nvn;using namespace nx::vk;
VkDeviceMemory alloc(ImageMemoryCache& c,uint64_t bytes,uint32_t type=2){
 VkMemoryAllocateInfo ai{nullptr,bytes,type};VkDeviceMemory m=0;
 assert(c.allocate(ai,&m)==VK_SUCCESS);return m;
}
int main(){
 ImageMemoryCache cache(128,3);
 auto a=alloc(cache,32);bound.insert(a);
 // In-flight/live allocations are never eligible for reuse.
 auto b=alloc(cache,32);assert(a!=b);
 bound.erase(a);cache.retire(a);assert(cache.cached_bytes()==32);
 auto reused=alloc(cache,32);assert(reused==a);assert(cache.cached_count()==0);
 auto otherType=alloc(cache,32,3);assert(otherType!=a);
 cache.retire(b);cache.retire(a);cache.retire(otherType);
 assert(cache.cached_count()==3 && cache.cached_bytes()==96);
 auto differentSize=alloc(cache,33);assert(differentSize!=a && differentSize!=b);
 cache.retire(differentSize);assert(!live.count(b)); // oldest evicted at entry cap
 assert(cache.cached_count()==3 && cache.cached_bytes()==97);
 auto large=alloc(cache,90);cache.retire(large);
 assert(cache.cached_bytes()<=128 && cache.cached_count()==2);
 auto oversized=alloc(cache,129);cache.retire(oversized);assert(!live.count(oversized));
 auto extreme=alloc(cache,UINT64_MAX);cache.retire(extreme);assert(!live.count(extreme));
 cache.drain();assert(live.empty());
 // Allocation pressure drains only idle allocations and retries once.
 auto pending=alloc(cache,11);bound.insert(pending);
 auto idle=alloc(cache,12);cache.retire(idle);
 failures=1;auto afterPressure=alloc(cache,13);
 assert(!live.count(idle) && live.count(pending) && cache.cached_count()==0);
 bound.erase(pending);cache.retire(pending);cache.retire(afterPressure);
 auto before=allocations;lost=true;VkMemoryAllocateInfo ai{nullptr,14,2};VkDeviceMemory failed=0;
 assert(cache.allocate(ai,&failed)==VK_ERROR_DEVICE_LOST);assert(allocations==before+1);lost=false;
 assert(cache.cached_count()==2);cache.drain();assert(live.empty());
 // No cache / unknown allocation / specialized pNext preserve native behavior.
 ImageMemoryCache disabled(0,0);auto direct=alloc(disabled,32);disabled.retire(direct);assert(live.empty());
 int extension=1;ai={&extension,10,2};assert(cache.allocate(ai,&failed)==VK_SUCCESS);
 cache.retire(failed);assert(live.empty() && cache.cached_count()==0);
 ImageMemoryCache noEntries(100,0);direct=alloc(noEntries,32);noEntries.retire(direct);assert(live.empty());
 // Repeated changing image shapes whose requirements round to the same size
 // retain live allocations until retirement, then reuse memory without content/state sharing.
 ImageMemoryCache churn(128,8);auto initial=allocations;
 for(unsigned frame=0;frame<2000;frame++){
  std::vector<uint64_t> inFlight;
  for(unsigned slot=0;slot<4;slot++){auto m=alloc(churn,16+(slot%2)*16);bound.insert(m);inFlight.push_back(m);}
  assert(std::set<uint64_t>(inFlight.begin(),inFlight.end()).size()==4);
  for(auto m:inFlight){bound.erase(m);churn.retire(m);}
  assert(churn.cached_bytes()==96);
 }
 assert(allocations-initial==4);churn.drain();assert(live.empty());
 std::puts("PASS: allocation identity, live ownership, exact requirements, limits, pressure, device loss, bypass, and 8000 churn allocations");
}
'''
with tempfile.TemporaryDirectory() as tmp:
 source=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';source.write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)

# Installer round-trip with real source anchors, all files preflight before write.
import importlib.util
installer=Path(__file__).resolve().parents[2]/'patches/patch-image-memory-cache.py'
spec=importlib.util.spec_from_file_location('image_memory_patch',installer);patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
with tempfile.TemporaryDirectory() as tmp:
 fixture=Path(tmp);target=fixture/'runtime/src/nvn';target.mkdir(parents=True)
 names=list(patch.CHANGES)
 for name in names:(fixture/name).write_bytes((root/name).read_bytes())
 (target/'image_memory_cache.h').write_bytes(header.read_bytes())
 command=[sys.executable,str(installer),'--root',str(fixture)]
 subprocess.run(command+['--restore'],check=True,stdout=subprocess.DEVNULL)
 original={name:(fixture/name).read_bytes() for name in names}
 for mode in ['lf','crlf','mixed']:
  expected={}
  for name,raw in original.items():
   raw=raw.replace(b'\r\n',b'\n')
   if mode=='crlf':raw=raw.replace(b'\n',b'\r\n')
   if mode=='mixed':raw=raw.replace(b'\n',b'\r\n',3)
   (fixture/name).write_bytes(raw);expected[name]=raw
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
  installed={name:(fixture/name).read_bytes() for name in names}
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
  assert installed=={name:(fixture/name).read_bytes() for name in names}
  subprocess.run(command+['--restore'],check=True,stdout=subprocess.DEVNULL)
  assert expected=={name:(fixture/name).read_bytes() for name in names},mode
 subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
 # Corrupt only one consumer to prove partial patches do not write other files.
 name='runtime/src/nvn/nvn_frames.cpp';data=(fixture/name).read_bytes()
 old,new=patch.CHANGES[name][0];(fixture/name).write_bytes(data.replace(new.encode(),old.encode()))
 snapshot={name:(fixture/name).read_bytes() for name in names}
 result=subprocess.run(command,capture_output=True);assert result.returncode!=0
 assert snapshot=={name:(fixture/name).read_bytes() for name in names}
print('PASS: installer LF/CRLF/mixed round-trip, idempotence and partial-patch preflight')
