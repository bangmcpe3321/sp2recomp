"""Source-extracted cache-owned texture readiness and CPU refresh regression."""
from pathlib import Path
import argparse,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();r=a.source.resolve().parent
def function(source,signature):
 s=source.index(signature);o=source.index('{',s);depth=1;e=o+1
 while depth:
  depth+=(source[e]=='{')-(source[e]=='}');e+=1
 return source[s:e]
pipe=(r/'nvn_pipeline.cpp').read_text();sampler=(r/'nvn_sampler.cpp').read_text()
parts=[function(sampler,'uint64_t hash_memory('),function(sampler,'void check_linear_content('),function(pipe,'void check_atlas_content('),function(pipe,'bool sampled_ready(')]
prefix=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <mutex>
#include <vector>
namespace nx {
std::atomic<uint64_t> g_frame{10};
namespace nvn {
constexpr int VK_IMAGE_LAYOUT_GENERAL=1,VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL=2;
struct GpuImage { bool rendered=false,uploaded=true,alpha_from_r=false;int layout=2; };
struct Texture {
 std::shared_ptr<GpuImage> image;
 uint64_t memory=0,storage_size=0,hashed_submit=0,content_hash=0;
 uint32_t width=128,height=4,format=1,stride=128;
 bool watched=false;
 std::atomic<bool> dirty{false},has_writes{false};
 std::atomic<uint64_t> dirty_lo{UINT64_MAX},dirty_hi{0};
 void mark_dirty(uint64_t lo,uint64_t hi) { dirty=true;dirty_lo=lo;dirty_hi=hi; }
};
Texture* active=nullptr;GpuImage* cache_image=nullptr;uint64_t resolutions=0;
template<class T>T* get(uint64_t h) { return h?active:nullptr; }
GpuImage* image_of(uint64_t) { ++resolutions;return cache_image; }
void log(const char*,...) {}
namespace plat {
bool write_watch_add(uint64_t,uint64_t) { return false; }
bool write_watch_take(uint64_t,uint64_t*,uint64_t*) { return false; }
}
uint64_t g_not_ready[6]{};
'''
tests=r'''
}}
int main() {
 using namespace nx::nvn;
 std::vector<uint64_t> bytes(64,0x5555555555555555ull);
 Texture t;t.memory=(uint64_t)bytes.data();t.storage_size=bytes.size()*8;
 auto cache=std::make_shared<GpuImage>();active=&t;cache_image=cache.get();
 assert(!t.image);assert(cache.use_count()==1);
 // An immutable descriptor need not own the GPU allocation to be ready.
 assert(sampled_ready(1));assert(cache.use_count()==1);assert(!t.image);
 // Pitch-linear CPU changes are detected before gather_textures decides to keep a pass open.
 nx::g_frame=14;bytes[3]^=0x123400000000ull;
 assert(!sampled_ready(1));assert(t.dirty);assert(t.dirty_lo==0);assert(t.dirty_hi==UINT64_MAX);
 t.dirty=false;nx::g_frame=18;assert(sampled_ready(1));
 // Glyph alpha-from-red refresh also reads the cache-owned image, without t.image.
 cache->alpha_from_r=true;t.stride=0;nx::g_frame=20;
 assert(!sampled_ready(1));assert(t.dirty);t.dirty=false;
 assert(sampled_ready(1));
 reinterpret_cast<uint8_t*>(bytes.data())[61]^=0x12;nx::g_frame=21;
 assert(!sampled_ready(1));assert(t.dirty);t.dirty=false;
 // GPU-only contents remain authoritative and must not be overwritten from guest bytes.
 cache->rendered=true;cache->layout=VK_IMAGE_LAYOUT_GENERAL;nx::g_frame=25;bytes[4]^=1;
 assert(sampled_ready(1));assert(!t.dirty);
 t.has_writes=true;assert(!sampled_ready(1));t.has_writes=false;
 cache->layout=VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;assert(!sampled_ready(1));
 cache->rendered=false;cache->uploaded=false;cache->alpha_from_r=false;assert(!sampled_ready(1));
 cache->uploaded=true;assert(sampled_ready(1));
 cache_image=nullptr;assert(!sampled_ready(1));assert(!sampled_ready(0));
 assert(!t.image);assert(cache.use_count()==1);assert(resolutions>0);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-cache-ready-') as td:
 d=Path(td);cpp=d/'test.cpp';exe=d/'test';cpp.write_text(prefix+'\n'.join(parts)+tests)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
print('PASS cache-owned readiness, pitch/glyph CPU refresh before pass break, GPU-only authority and ownership')
