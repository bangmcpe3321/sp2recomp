"""Compare actual grouped image retirement against the original per-frame map."""
from pathlib import Path
import importlib.util,subprocess,tempfile,sys

source=Path(sys.argv[1]).read_text()
def block(text,signature):
    start=text.index(signature);cur=text.index('{',start);depth=1;end=cur+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
patch=Path(__file__).resolve().parents[2]/'patches/patch-image-retirement-groups.py'
spec=importlib.util.spec_from_file_location('groups_patch',patch);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert source.count(module.NEW)==1
storage=block(source,'struct StorageKey {')+';'
expiry=block(source,'static bool cached_image_expired(')
prefix=r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <map>
#include <memory>
#include <new>
#include <tuple>
#include <vector>
bool measure=false;size_t allocations=0;
void* operator new(size_t size){if(measure)++allocations;if(auto p=std::malloc(size?size:1))return p;throw std::bad_alloc{};}
void operator delete(void* p)noexcept{std::free(p);}
void operator delete(void* p,size_t)noexcept{std::free(p);}
struct GpuImage {bool rendered=false;uint64_t rendered_at=0,id=0;};
struct HeldImage {std::shared_ptr<GpuImage> image;uint64_t used=0;};
'''+storage+'\n'+expiry+r'''
using Registry=std::map<StorageKey,HeldImage>;
std::vector<uint64_t> retired;
void retire_image(std::shared_ptr<GpuImage> image){assert(image);retired.push_back(image->id);}
'''
code=prefix
for name,body in [('reference',module.OLD),('grouped',module.NEW)]:
    code+='void '+name+'(Registry& held,uint64_t frame){\n'+body+'\n}\n'
code+=r'''
Registry fixture(){
 Registry result;
 for(uint64_t address=0;address<4096;++address){
  const uint64_t memory=address==0?0:address==4095?UINT64_MAX:address*4096;
  for(unsigned shape=0;shape<5;++shape){
   auto image=std::make_shared<GpuImage>();
   image->id=address*5+shape;image->rendered=shape!=0;
   // Includes CPU, unknown-order GPU, old/new/equal render orders.
   image->rendered_at=shape==1?0:shape==4?10:shape*5;
   StorageKey key{};key.memory=memory;key.width=1280+shape;key.height=720;
   result.emplace(key,HeldImage{image,address%4==0?100:address%4==1?99:address%4==2?102:UINT64_MAX});
  }
 }
 return result;
}
int main(){
 for(uint64_t frame:{uint64_t(0),uint64_t(99),uint64_t(100),uint64_t(101),uint64_t(102),uint64_t(103),uint64_t(104),UINT64_MAX}){
  auto before=fixture(),after=before;
  retired.clear();retired.reserve(before.size());
  measure=true;allocations=0;reference(before,frame);measure=false;
  const auto old_allocations=allocations;auto old_retired=retired;
  retired.clear();allocations=0;measure=true;grouped(after,frame);measure=false;
  assert(allocations==0 && old_allocations==4096);
  assert(old_retired==retired && before.size()==after.size());
  auto a=before.begin(),b=after.begin();
  for(;a!=before.end();++a,++b){assert(!(a->first<b->first) && !(b->first<a->first));assert(a->second.image.get()==b->second.image.get());assert(a->second.used==b->second.used);}
 }
 // Repeat on progressively reduced registries, checking retirement order too.
 auto before=fixture(),after=before;
 for(uint64_t frame=100;frame<120;++frame){
  retired.clear();reference(before,frame);auto expected=retired;
  retired.clear();grouped(after,frame);assert(expected==retired && before.size()==after.size());
 }
 std::cout<<"PASS grouped retirement: same surviving identities/order and retirements; 20480 images, zero/max addresses, 4096 temporary map allocations -> 0 per frame\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-image-retire-') as td:
    folder=Path(td);cpp=folder/'test.cpp';exe=folder/'test';cpp.write_text(code)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)

with tempfile.TemporaryDirectory(prefix='sp2-image-retire-install-') as td:
    root=Path(td);target=root/'runtime/src/nvn/nvn_image.cpp';target.parent.mkdir(parents=True)
    original=Path(sys.argv[1]).read_bytes();target.write_bytes(original)
    def run(*flags,ok=True):
        result=subprocess.run([sys.executable,str(patch),'--root',str(root),*flags],capture_output=True,text=True)
        assert (result.returncode==0)==ok,result.stdout+result.stderr
    run('--check');assert target.read_bytes()==original
    run();assert target.read_bytes()==original
    run('--restore');assert b'PATCH-IMAGE-RETIREMENT-GROUPS' not in target.read_bytes()
    run();assert target.read_bytes()==original
    broken=original.replace(b'const uint64_t memory = first->first.memory;',b'// anchor changed',1)
    target.write_bytes(broken);run(ok=False);assert target.read_bytes()==broken
    print('PASS grouped retirement installer preflight, idempotence, exact restore/reapply and failed-anchor safety')

# Both installers must compose in either restore order without changing unrelated
# bytes, including files with mixed line endings from Windows/WSL edits.
front_patch=patch.parent/'patch-image-held-front-cache.py'
normalized=Path(sys.argv[1]).read_bytes().replace(b'\r\n',b'\n')
variants=[normalized,normalized.replace(b'\n',b'\r\n'),
          b'// unrelated CRLF prefix\r\n'+normalized+b'// unrelated CRLF suffix\r\n']
for variant in variants:
    with tempfile.TemporaryDirectory(prefix='sp2-image-patch-compose-') as td:
        root=Path(td);target=root/'runtime/src/nvn/nvn_image.cpp';target.parent.mkdir(parents=True)
        target.write_bytes(variant)
        def apply(tool,*flags):
            result=subprocess.run([sys.executable,str(tool),'--root',str(root),*flags],capture_output=True,text=True)
            assert result.returncode==0,result.stdout+result.stderr
        for helper in [patch,front_patch]:
            apply(helper,'--check');assert target.read_bytes()==variant
            apply(helper);assert target.read_bytes()==variant
        for restore_order,apply_order in [([front_patch,patch],[patch,front_patch]),
                                           ([patch,front_patch],[front_patch,patch])]:
            for helper in restore_order:apply(helper,'--restore')
            baseline=target.read_bytes()
            assert b'PATCH-IMAGE-RETIREMENT-GROUPS' not in baseline
            assert b'PATCH-IMAGE-HELD-FRONT' not in baseline
            for helper in apply_order:apply(helper)
            assert target.read_bytes()==variant
print('PASS front-cache/group-retirement composition: both restore orders, LF, CRLF and mixed untouched newlines')
