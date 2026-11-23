"""Actual-source Vulkan pipeline-cache compatibility and persistence regressions (Linux/WSL)."""
from pathlib import Path
import argparse,os,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();s=a.source.read_text()
def function(signature):
 start=s.index(signature);cur=s.index('{',start);depth=1;end=cur+1
 while depth:
  depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]
code=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
using VkPipelineCache=uint64_t;
constexpr uint64_t VK_NULL_HANDLE=0;
constexpr uint32_t VK_UUID_SIZE=16,VK_PIPELINE_CACHE_HEADER_VERSION_ONE=1,VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO=17;
constexpr int VK_SUCCESS=0;
struct VkPipelineCacheHeaderVersionOne { uint32_t headerSize,headerVersion,vendorID,deviceID;uint8_t pipelineCacheUUID[16]; };
struct VkPhysicalDeviceProperties { uint32_t vendorID=0x10de,deviceID=0x2520;uint8_t pipelineCacheUUID[16]={1,2,3,4}; };
struct VkPipelineCacheCreateInfo { uint32_t sType;void* pNext=nullptr;uint32_t flags=0;size_t initialDataSize=0;const void* pInitialData=nullptr; };
VkPhysicalDeviceProperties properties;
std::vector<uint8_t> serialized;
std::vector<size_t> initial_sizes;
unsigned query_calls=0;bool reject_initial=false,fail_create=false,fail_query=false;
int vk_physical(){return 1;} int vk_device(){return 2;}
void p_vkGetPhysicalDeviceProperties(int,VkPhysicalDeviceProperties* p){*p=properties;}
int p_vkCreatePipelineCache(int,const VkPipelineCacheCreateInfo* ci,void*,VkPipelineCache* out){
 initial_sizes.push_back(ci->initialDataSize);
 if(fail_create || (reject_initial && ci->initialDataSize)){*out=0xdead;return -1;}
 *out=42;return VK_SUCCESS;
}
int p_vkGetPipelineCacheData(int,VkPipelineCache,size_t* n,void* out){
 query_calls++;
 if(fail_query)return -1;
 if(!out){*n=serialized.size();return VK_SUCCESS;}
 assert(*n>=serialized.size());std::memcpy(out,serialized.data(),serialized.size());*n=serialized.size();return VK_SUCCESS;
}
uint64_t log_calls=0,image_stats_calls=0,holder_stats_calls=0;
void log(const char*,...){++log_calls;}
void image_stats_log(){++image_stats_calls;}
void image_holder_log(){++holder_stats_calls;}
std::atomic<uint64_t> g_image_live_count{1},g_image_live_bytes{1024},g_pipelines_alive{2};
std::string directory;
namespace plat {
 std::string data_root(){return directory;}
 FILE* fopen_utf8(const std::string& p,const char* m){return std::fopen(p.c_str(),m);}
 int fseek64(FILE* f,int64_t p,int w){return std::fseek(f,p,w);}
 int64_t ftell64(FILE* f){return std::ftell(f);}
}
VkPipelineCache g_cache=0;bool g_tried=false;uint64_t g_cache_revision=0,g_saved_revision=0;std::string g_path;uint64_t g_pipelines=0,g_pipeline_ns=0,g_astc=0,g_astc_ns=0;
uint64_t g_total_pipelines=0,g_total_pipeline_ns=0;
bool host_stats_on(){return false;}
struct { std::atomic<uint64_t> pipe_builds{0},pipe_build_ns{0}; } g_host_stats;
'''
code+='\n'.join(function(f) for f in ['static bool compatible_pipeline_cache(', 'VkPipelineCache pipeline_cache(', 'void pipeline_cache_save(', 'void creation_log(', 'void note_pipeline_created(', 'void pipeline_compile_totals('])
code+=r'''
std::vector<uint8_t> blob(size_t bytes,uint8_t fill=0){
 std::vector<uint8_t> b(std::max(bytes,sizeof(VkPipelineCacheHeaderVersionOne)),fill);
 VkPipelineCacheHeaderVersionOne h{};h.headerSize=sizeof h;h.headerVersion=1;h.vendorID=properties.vendorID;h.deviceID=properties.deviceID;std::memcpy(h.pipelineCacheUUID,properties.pipelineCacheUUID,16);std::memcpy(b.data(),&h,sizeof h);return b;
}
std::string filename(){return directory+"/pipelines_10de_2520.bin";}
void write(const std::vector<uint8_t>& b){std::ofstream f(filename(),std::ios::binary);f.write((const char*)b.data(),b.size());}
std::vector<uint8_t> read(){std::ifstream f(filename(),std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
void reset(){g_cache=0;g_tried=false;g_cache_revision=g_saved_revision=0;g_path.clear();initial_sizes.clear();query_calls=0;reject_initial=fail_create=fail_query=false;}
int main(int argc,char** argv){
 assert(argc==4);directory=argv[1];unsetenv("NX_PIPELINE_CACHE");
 auto valid=blob(256,7);assert(compatible_pipeline_cache(valid,properties));
 for(unsigned mode=0;mode<5;mode++){
  auto bad=valid;
  if(mode==0)bad.resize(8);
  if(mode==1)bad[4]=2;
  if(mode==2)bad[8]^=1;
  if(mode==3)bad[12]^=1;
  if(mode==4)bad[16]^=1;
  assert(!compatible_pipeline_cache(bad,properties));
 }
 auto bad_size=valid;uint32_t too_big=4096;std::memcpy(bad_size.data(),&too_big,4);assert(!compatible_pipeline_cache(bad_size,properties));
 // Valid initial bytes are supplied to the driver, then persisted once.
 write(valid);serialized=valid;assert(pipeline_cache()==42);assert(initial_sizes==std::vector<size_t>{256});pipeline_cache_save();assert(query_calls==2);assert(read()==valid);auto queries=query_calls;
 pipeline_cache_save();assert(query_calls==queries); // no new pipeline-cache requests
 // A driver can change cache contents without changing length.
 serialized.back()^=0x55;pipeline_cache();pipeline_cache_save();assert(query_calls==queries+2);assert(read()==serialized);
 // UUID-mismatched large cache must not prevent saving a smaller replacement.
 reset();auto stale=blob(4096,6);stale[16]^=0x55;write(stale);serialized=blob(64,9);assert(pipeline_cache()==42);assert(initial_sizes==std::vector<size_t>{0});pipeline_cache_save();assert(read()==serialized);
 // A matching header may still be explicitly rejected by a driver. Retry empty.
 reset();write(valid);reject_initial=true;serialized=blob(48,3);assert(pipeline_cache()==42);assert(initial_sizes==(std::vector<size_t>{256,0}));pipeline_cache_save();assert(read()==serialized);
 // Failed serialization preserves the old cache and stays dirty for a retry.
 auto before=read();pipeline_cache();serialized=blob(80,4);fail_query=true;pipeline_cache_save();assert(read()==before);fail_query=false;pipeline_cache_save();assert(read()==serialized);
 // A failed temporary-file open cannot delete the last valid cache.
 before=read();pipeline_cache();serialized=blob(96,5);std::filesystem::create_directory(filename()+".tmp");pipeline_cache_save();assert(read()==before);std::filesystem::remove(filename()+".tmp");pipeline_cache_save();assert(read()==serialized);
 // If creation fails entirely no invalid handle is serialized.
 reset();write(valid);fail_create=true;assert(pipeline_cache()==0);pipeline_cache_save();assert(query_calls==0);assert(read()==valid);
 // Normal creation-stat ticks do no logging or cache serialization unless requested.
 g_cache=42;g_tried=true;g_cache_revision=1;g_saved_revision=0;query_calls=0;
 serialized=valid;log_calls=image_stats_calls=holder_stats_calls=0;
 g_pipelines=2;g_pipeline_ns=1000;g_astc=1;g_astc_ns=500;
 for(int i=0;i<10;i++)creation_log(60);
 assert(g_pipelines==0 && g_pipeline_ns==0 && g_astc==0 && g_astc_ns==0);
 // Lifetime compile totals remain monotonic across timing-window resets.
 uint64_t count=99,ns=99;pipeline_compile_totals(count,ns);assert(count==0 && ns==0);
 note_pipeline_created(123);note_pipeline_created(456);pipeline_compile_totals(count,ns);assert(count==2 && ns==579);
 // A reset must only clear the rolling statistics, not the lifetime counter.
 auto save_logs=log_calls,save_images=image_stats_calls,save_holders=holder_stats_calls;
 creation_log(0);pipeline_compile_totals(count,ns);assert(count==2 && ns==579);
 assert(g_pipelines==0 && g_pipeline_ns==0);
 note_pipeline_created(10);pipeline_compile_totals(count,ns);assert(count==3 && ns==589);
 log_calls=save_logs;image_stats_calls=save_images;holder_stats_calls=save_holders;
 bool verbose=std::atoi(argv[2])!=0, checkpoint=std::atoi(argv[3])!=0;
 assert((log_calls>0)==verbose);assert(image_stats_calls==(verbose?10:0));assert(holder_stats_calls==(verbose?10:0));
 assert(query_calls==(checkpoint?2:0));

}
'''
with tempfile.TemporaryDirectory(prefix='sp2-pipeline-cache-') as td:
 d=Path(td);cpp=d/'test.cpp';exe=d/'test';cpp.write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Wno-deprecated-declarations',str(cpp),'-o',str(exe)],check=True)
 for verbose,interval in [(None,None),('1','600'),('0','0')]:
  env=os.environ.copy();env.pop('NX_RENDER_STATS',None);env.pop('NX_PIPELINE_CACHE_SAVE_INTERVAL',None)
  if verbose is not None:env['NX_RENDER_STATS']=verbose
  if interval is not None:env['NX_PIPELINE_CACHE_SAVE_INTERVAL']=interval
  subprocess.run([str(exe),str(d),'1' if verbose=='1' else '0','1' if interval=='600' else '0'],env=env,check=True)
print('PASS pipeline-cache headers, rejected/obsolete loads, smaller and same-size persistence, clean skip, atomic replacement, failed-write retry and opt-in checkpoints/statistics')
