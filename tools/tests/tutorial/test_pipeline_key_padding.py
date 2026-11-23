"""Actual-source graphics pipeline cache keys ignore padding while retaining state (Linux/WSL)."""
from pathlib import Path
import argparse,subprocess,tempfile
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
assert 'const Key k = pipeline_cache_key(key);' in body
assert 'cache.find(k)' in body and 'cache.insert(k,p,' in body
assert 'std::memcpy(k.b, &key' not in body
code=r'''
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cassert>
#include <new>
#include <cstdio>
using VkFormat=uint32_t;constexpr VkFormat VK_FORMAT_UNDEFINED=0;
struct ShaderInfo {};
'''+structures+'\n'+helper+r'''
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
 // No semantic byte, including every scalar/array field and shader pointer, is discarded.
 for(size_t i=0;i<sizeof(PipelineKey);i++){
  auto changed=first;reinterpret_cast<unsigned char*>(&changed)[i]^=0x80;
  assert((pipeline_cache_key(changed)==a)==(i>=begin && i<end));
 }
 // Both cache probes consume the same normalized key, and normalization is idempotent.
 PipelineKey normalized;std::memcpy(&normalized,a.b,sizeof normalized);assert(pipeline_cache_key(normalized)==a);
 std::printf("PASS %zu-byte pipeline key: padding range [%zu,%zu) ignored, every semantic byte retained\n",sizeof first,begin,end);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-pipeline-key-') as td:
 d=Path(td);f=d/'test.cpp';exe=d/'test';f.write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(f),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
