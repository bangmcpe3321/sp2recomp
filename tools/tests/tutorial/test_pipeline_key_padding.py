"""Actual-source graphics pipeline cache keys ignore padding while retaining state (Linux/WSL)."""
from pathlib import Path
import argparse,subprocess,tempfile,sys
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();r=a.source.parent
cpp=a.source.read_text();header=(r/'nvn_pipeline.h').read_text();types=(r/'nvn.h').read_text()
def block(s,signature):
 start=s.index(signature);cur=s.index('{',start);depth=1;end=cur+1
 while depth:
  depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]
structures='\n'.join(block(types,'struct '+name+' {')+';' for name in ['VertexAttrib','VertexStream','BlendTarget','ColorStateInfo','ChannelMaskInfo','DepthStencilInfo','PolygonInfo'])
structures+='\n'+block(header,'struct PipelineKey {')+';'
structures+='\n'+block(header,'template <size_t N>\nstruct ByteKey {')+';'
helper=block(cpp,'static ByteKey<sizeof(PipelineKey)> pipeline_cache_key(')
body=block(cpp,'VkPipeline graphics_pipeline(')
vertex_begin=body.index('    std::vector<VkVertexInputAttributeDescription> attrs;')
vertex_end=body.index('    VkPipelineVertexInputStateCreateInfo vi{',vertex_begin)
vertex_encoder='auto vertex_description(const PipelineKey& key) {\n'+body[vertex_begin:vertex_end]+'    return std::pair{attrs,binds};\n}'
spirv=(r/'nvn_spirv_patch.cpp').read_text()
integer_helpers=spirv[spirv.index('enum : uint32_t {'):spirv.index('uint32_t integer_format_kind(')]
# That region ends the anonymous namespace before enum helpers. Re-open a
# namespace around exactly the production input-transform implementation.
integer_helpers='namespace {\n'+integer_helpers
integer_helpers+='\n'+block(spirv,'static bool patch_integer_io(')+'\n'+block(spirv,'bool patch_int_inputs(')
assert 'const Key k = pipeline_cache_key(key);' in body
assert 'cache.find(k)' in body and 'cache.insert(k,p,' in body
assert 'std::memcpy(k.b, &key' not in body
hit_path=body[:body.index('    // PATCH-PIPE-DIFF-BEGIN:')]
assert 'const std::string vs_h' not in hit_path
hit_path+='    cache.insert(k,1,[](VkPipeline){}); return 1;\n}'
baseline_hit=hit_path.replace('VkPipeline graphics_pipeline(', 'VkPipeline baseline_graphics_pipeline(',1)
baseline_hit=baseline_hit.replace('    // PATCH-PIPELINE-DIFF-HOT-PATH: shader names are read only inside diagnostic branches.',
 '    const std::string vs_h = key.vs ? key.vs->hash : "-", fs_h = key.fs ? key.fs->hash : "-";',1)
hash_helpers=block(header,'inline uint64_t hash_bytes(')+'\n'+block(header,'struct ByteKeyHash {')+';'
code=r'''
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cassert>
#include <new>
#include <cstdio>
#include <algorithm>
#include <vector>
#include <map>
#include <set>
#include <string>
#include <cstdlib>
#include <atomic>
#include "pipeline_lru.h"
using nx::nvn::PipelineLru;
bool count_allocations=false;size_t allocations=0;
void* operator new(size_t size){if(count_allocations)++allocations;if(auto p=std::malloc(size?size:1))return p;throw std::bad_alloc{};}
void operator delete(void* p)noexcept{std::free(p);}
void operator delete(void* p,size_t)noexcept{std::free(p);}
void* operator new[](size_t size){return ::operator new(size);}
void operator delete[](void* p)noexcept{::operator delete(p);}
void operator delete[](void* p,size_t)noexcept{::operator delete(p);}
using VkPipeline=uint64_t;
struct ProgramLayout {};
bool host_stats_on(){return false;}
struct HostStats {std::atomic<uint64_t> pipe_hits{0};} g_host_stats;
using VkFormat=uint32_t;constexpr VkFormat VK_FORMAT_UNDEFINED=0;
constexpr VkFormat VK_FORMAT_R32G32B32A32_SFLOAT=7;
constexpr uint32_t VK_VERTEX_INPUT_RATE_INSTANCE=1,VK_VERTEX_INPUT_RATE_VERTEX=0;
struct VkVertexInputAttributeDescription {uint32_t location,binding;VkFormat format;uint32_t offset;bool operator==(const VkVertexInputAttributeDescription&)const=default;};
struct VkVertexInputBindingDescription {uint32_t binding,stride,inputRate;bool operator==(const VkVertexInputBindingDescription&)const=default;};
struct ShaderIo {uint32_t location=0;};
struct ShaderInfo {struct Reflection {std::vector<ShaderIo> inputs;} refl;std::string hash;};
VkFormat vk_vertex_format(uint32_t format){return format;}
'''+structures+'\n'+hash_helpers+'\n'+helper+'\n'+hit_path+'\n'+baseline_hit+'\n'+vertex_encoder+'\n'+integer_helpers+r'''
std::vector<uint32_t> integer_module(const PipelineKey& key){
 std::vector<uint32_t> shader={0x07230203,0x00010000,0,64,0};
 auto op=[&](uint32_t code,std::initializer_list<uint32_t> operands){shader.push_back(((operands.size()+1)<<16)|code);shader.insert(shader.end(),operands);};
 op(71,{10,30,0});op(71,{11,30,3});op(22,{3,32});op(23,{4,3,4});op(32,{5,1,4});
 op(59,{5,10,1});op(59,{5,11,1});op(61,{4,12,10});op(61,{4,13,11});
 uint8_t kinds[16]={};for(unsigned i=0;i<key.attrib_count && i<16;++i)kinds[i]=key.attribs[i].format%3;
 std::vector<uint32_t> transformed;if(patch_int_inputs(shader,kinds,transformed))return transformed;return shader;
}
PipelineKey state_with_padding(unsigned char poison){
 alignas(DepthStencilInfo) unsigned char storage[sizeof(DepthStencilInfo)];
 for(size_t i=0;i<sizeof storage;i++)reinterpret_cast<volatile unsigned char*>(storage)[i]=poison;
 auto* depth=new(storage)DepthStencilInfo;
 PipelineKey key;std::memset(&key,0,sizeof key);key.depth=*depth;return key;
}
int main(){
 auto first=state_with_padding(0xaa),second=state_with_padding(0x55);
 constexpr size_t begin=offsetof(PipelineKey,depth)+offsetof(DepthStencilInfo,stencil_test)+sizeof(first.depth.stencil_test);
 constexpr size_t end=offsetof(PipelineKey,depth)+offsetof(DepthStencilInfo,depth_func);
 assert(end>begin);assert(std::memcmp(&first,&second,sizeof first)!=0); // old raw-byte key misses
 auto a=pipeline_cache_key(first),b=pipeline_cache_key(second);assert(a==b);
 for(size_t i=begin;i<end;i++)assert(a.b[i]==0);
 // Pipeline state the encoder consumes must remain distinct. Inactive fields are
 // covered independently below; blindly retaining them caused redundant compiles.
 ShaderInfo vs, fs;vs.refl.inputs={{0},{3}};
 vs.hash=std::string(128,'v');fs.hash=std::string(128,'f');
 PipelineKey live{};live.vs=&vs;live.fs=&fs;live.attrib_count=4;
 live.attribs[0]={1,12,2};live.attribs[3]={2,24,4};
 live.streams[2]={48,0};live.streams[4]={64,2};
 live.color_count=1;live.color_formats[0]=37;live.mask.mask[0]=15;
 live.color.blend_enable[0]=1;live.blend[0]={7,1,2,3,4,5,6};live.ufloat_colors=1;
 const auto expected=pipeline_cache_key(live);
 const auto expected_vertex=vertex_description(live);
 const auto expected_module=integer_module(live);
 // Run the actual production prefix through the cache-hit return. Warm static
 // cache initialization, then long diagnostic hashes must cause no allocations.
 unsetenv("NX_PIPE_DIFF");ProgramLayout layout;
 assert(graphics_pipeline(live,layout)==1);
 assert(graphics_pipeline(live,layout)==1);
 count_allocations=true;
 for(unsigned i=0;i<10000;++i)assert(graphics_pipeline(live,layout)==1);
 count_allocations=false;assert(allocations==0);
 assert(baseline_graphics_pipeline(live,layout)==1);
 allocations=0;count_allocations=true;
 for(unsigned i=0;i<10000;++i)assert(baseline_graphics_pipeline(live,layout)==1);
 count_allocations=false;assert(allocations==20000);
 auto differs=[&](const PipelineKey& changed){assert(!(pipeline_cache_key(changed)==expected));};
 auto changed=live;changed.vs=&fs;differs(changed);
 changed=live;changed.fs=nullptr;differs(changed);
 changed=live;changed.topology++;differs(changed);
 changed=live;changed.attribs[0].format++;differs(changed);
 changed=live;changed.attribs[3].offset++;differs(changed);
 changed=live;changed.attribs[3].stream++;differs(changed);
 changed=live;changed.attrib_count=3;differs(changed);
 changed=live;changed.streams[2].stride++;differs(changed);
 changed=live;changed.streams[4].divisor=0;differs(changed);
 changed=live;changed.color_count=2;differs(changed);
 changed=live;changed.color_formats[0]++;differs(changed);
 changed=live;changed.mask.mask[0]^=1;differs(changed);
 changed=live;changed.color.blend_enable[0]=0;differs(changed);
 changed=live;changed.blend[0].src_rgb++;differs(changed);
 changed=live;changed.blend[0].dst_rgb++;differs(changed);
 changed=live;changed.blend[0].src_a++;differs(changed);
 changed=live;changed.blend[0].dst_a++;differs(changed);
 changed=live;changed.blend[0].eq_rgb++;differs(changed);
 changed=live;changed.blend[0].eq_a++;differs(changed);
 changed=live;changed.ufloat_colors=0;differs(changed);
 changed=live;changed.depth.depth_func++;differs(changed);
 changed=live;changed.depth.depth_test++;differs(changed);
 changed=live;changed.depth.stencil_test++;differs(changed);
 changed=live;changed.depth.stencil_func[1]++;differs(changed);
 changed=live;changed.polygon.cull++;differs(changed);
 changed=live;changed.polygon.offset_enables++;differs(changed);
 changed=live;changed.depth_clamp++;differs(changed);
 changed=live;changed.alpha_to_coverage++;differs(changed);
 // Vary old draw bindings: 4,096 distinct raw keys collapse to one effective key.
 for(unsigned variation=1;variation<=4096;++variation){
  auto stale=live;
  stale.attrib_count=16;stale.stream_count=variation;
  for(unsigned i=0;i<16;++i){
   if(i!=0 && i!=3)stale.attribs[i]={variation,i*variation,variation+17};
   if(i!=2 && i!=4)stale.streams[i]={variation,variation+1};
  }
  stale.streams[4].divisor=variation; // encoder uses only nonzero/zero
  stale.color.alpha_test=variation;stale.color.logic_op=variation*3;
  stale.blend[0].target=variation;stale.mask.mask[0]|=0xF0;
  for(unsigned i=1;i<8;++i){
   stale.blend[i]={variation,variation,variation,variation,variation,variation,variation};
   stale.color.blend_enable[i]=variation;stale.mask.mask[i]=variation;
   stale.color_formats[i]=variation;stale.ufloat_colors|=1u<<i;
  }
  assert(std::memcmp(&stale,&live,sizeof live)!=0);
  assert(pipeline_cache_key(stale)==expected);
  assert(vertex_description(stale)==expected_vertex);
  assert(integer_module(stale)==expected_module);
 }
 changed=live;changed.attribs[0].format=2;assert(integer_module(changed)!=expected_module);
 // Disabled attachment blending ignores factors, but enabling it stays distinct.
 auto disabled=live;disabled.color.blend_enable[0]=0;
 auto disabled_other=disabled;disabled_other.blend[0]={};disabled_other.ufloat_colors=0;
 assert(pipeline_cache_key(disabled)==pipeline_cache_key(disabled_other));
 // Invalid and missing vertex attributes select the zero binding. Invalid stream
 // indices never index the small stream mask; out-of-range inputs are harmless.
 vs.refl.inputs.push_back({99});
 changed=live;changed.attribs[0].stream=99;differs(changed);
 changed=live;changed.attribs[0].format=0;differs(changed);
 // Both cache probes consume the same normalized key, and normalization is idempotent.
 PipelineKey normalized;std::memcpy(&normalized,a.b,sizeof normalized);assert(pipeline_cache_key(normalized)==a);
 std::printf("PASS %zu-byte pipeline key: padding [%zu,%zu), 4096 equivalent binding variants, consumed state distinct; 10000 cache hits allocate zero diagnostic strings\n",sizeof first,begin,end);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-pipeline-key-') as td:
 d=Path(td);f=d/'test.cpp';exe=d/'test';f.write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(r),str(f),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)

# The public installer must safely round-trip the production source, including
# the older padding fix; a bad anchor must never write a partial modification.
patch=Path(__file__).resolve().parents[2]/'patches/patch-pipeline-effective-state.py'
with tempfile.TemporaryDirectory(prefix='sp2-pipeline-install-') as td:
 root=Path(td);target=root/'runtime/src/nvn/nvn_pipeline.cpp';target.parent.mkdir(parents=True)
 original=a.source.read_bytes();target.write_bytes(original)
 def apply(*flags,ok=True):
  result=subprocess.run([sys.executable,str(patch),'--root',str(root),*flags],capture_output=True,text=True)
  assert (result.returncode==0)==ok,result.stdout+result.stderr
 apply('--check');assert target.read_bytes()==original
 apply();assert target.read_bytes()==original
 apply('--restore');restored=target.read_bytes();assert b'PATCH-PIPELINE-EFFECTIVE-STATE' not in restored
 apply();assert target.read_bytes()==original
 apply();assert target.read_bytes()==original
 broken=original.replace(b'    ByteKey<sizeof(PipelineKey)> result;',b'    // missing anchor',1)
 target.write_bytes(broken);apply(ok=False);assert target.read_bytes()==broken
 print('PASS effective pipeline patch preflight, idempotence, restore and failed-anchor safety')
