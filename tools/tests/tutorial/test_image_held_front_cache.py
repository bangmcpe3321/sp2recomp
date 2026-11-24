#!/usr/bin/env python3
"""Compare production descriptor-image caching with its original map path."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).read_text()
patch = Path(__file__).resolve().parents[2] / 'patches/patch-image-held-front-cache.py'
spec = importlib.util.spec_from_file_location('image_front_patch', patch)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
start = source.index('struct StorageKey {')
key = source[start:source.index('std::map<StorageKey,', start)]
start = source.index('static bool cached_image_expired(')
body = source[start:source.index('void transition(', start)]
baseline = body
for old, new in [(module.OLD, module.NEW), (module.PRUNE, module.PRUNE_NEW), (module.LOOKUP, module.LOOKUP_NEW)]:
    assert baseline.count(new) == 1
    baseline = baseline.replace(new, old)

common = r'''
struct GpuImage { bool rendered=false; uint64_t rendered_at=0, id=0; };
struct Texture {
 uint64_t memory=0; uint32_t format=37,width=1280,height=720,depth=1,levels=1,target=1,samples=1;
 std::atomic<uint32_t> pool_swizzle{0}; bool descriptor_copy=true;
 std::shared_ptr<GpuImage> image;
};
std::atomic<uint64_t> g_frame{0};
std::map<uint64_t,Texture> textures;
uint64_t next_id=0, retired=0, lookups=0;
template<class T> T* get(uint64_t guest) {
 auto it=textures.find(guest);return it==textures.end()?nullptr:&it->second;
}
GpuImage* image_of_impl(uint64_t guest) {
 auto* t=get<Texture>(guest);if(!t)return nullptr;
 if(!t->image){t->image=std::make_shared<GpuImage>();t->image->id=++next_id;}
 return t->image.get();
}
void retire_image(std::shared_ptr<GpuImage> image){assert(image);++retired;}
'''
scenario = r'''
std::vector<uint64_t> run() {
 std::vector<uint64_t> results;
 for(uint64_t i=0;i<2048;i++)textures[i].memory=0x50000000+i*4096;
 for(uint64_t frame=0;frame<90;frame++){
  g_frame=frame;
  for(uint64_t n=0;n<9000;n++){
   // Hot groups, replacements, hash collisions and empty object lookups.
   uint64_t guest=(n%1000<940)?(n%20+frame/12*20):(1000+n%1048);
   if(n%997==0)guest=9999;
   auto* result=image_of(guest);results.push_back(result?result->id:0);
  }
  auto& t=textures[0];
  if(frame%9==0){t.width=640+frame;t.height=360+frame; t.format=frame%2?1:37; t.pool_swizzle=frame;}
  // A different guest descriptor over identical storage must share the same image.
  auto& alias=textures[2048+frame];auto& origin=textures[1];
  alias.memory=origin.memory;
  results.push_back(image_of(1)->id);results.push_back(image_of(2048+frame)->id);
  assert(results[results.size()-2]==results.back());
 }
 results.push_back(next_id);results.push_back(retired);
 return results;
}
'''
code = '''#include <atomic>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <tuple>
#include <vector>
'''
for name, implementation in [('reference', baseline), ('optimized', body)]:
    implementation = implementation.replace('held.find(key)', '(++lookups, held.find(key))')
    code += f'namespace {name} {{\n' + key + common + implementation + scenario + '\n}\n'
code += r'''
int main(){
 auto old=reference::run(),fast=optimized::run();
 assert(old==fast);
 assert(optimized::lookups*4 < reference::lookups);
 std::cout << "PASS: identical image identities, aliasing and retirement across " << old.size()-2
           << " requests; map lookups " << reference::lookups << " -> " << optimized::lookups << "\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-held-front-') as directory:
    path = Path(directory)
    (path/'test.cpp').write_text(code)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
