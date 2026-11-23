"""Actual GPU-counter implementation with Vulkan/fence mocks; no driver or game data needed."""
from pathlib import Path
import subprocess,sys,tempfile
header=Path(sys.argv[1]);s=header.read_text();body='\n'.join(line for line in s.splitlines() if not line.startswith('#include') and line!='#pragma once')
vk=header.with_name('nvn_vk.cpp').read_text()
start=vk.index('void end_and_wait(');end=vk.index('\nbool render_stats_enabled()',start);waiter=vk[start:end]
frames=header.with_name('nvn_frames.cpp').read_text()
# These checks bind fence safety to the actual production call sites as well as the executable mocks below.
retire=frames[frames.index('bool retire_oldest()'):frames.index('void retire_through(')]
assert retire.index('wait_fences(')<retire.index('counter_queries_collect(')
submit=frames[frames.index('void frame_submit('):frames.index('void frame_wait_all(')]
assert submit.index('counter_queries_pending(')<submit.index('if (pipelined()) {\n        // At most')
assert 'counter_queries_pending(s.cbs[part])) wait_done=true;' in submit
assert 'if (wait_done)' in submit and 'if (wait_done ||' in submit
prefix=r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>
struct WriteBack{uint8_t* from;uint8_t* to;uint64_t size;};
using VkCommandBuffer=uint64_t;using VkQueryPool=uint64_t;using VkDevice=uint64_t;using VkSemaphore=uint64_t;using VkFence=uint64_t;
using VkResult=int;using VkPipelineStageFlags=uint32_t;
constexpr uint64_t VK_NULL_HANDLE=0;constexpr int VK_SUCCESS=0,VK_NOT_READY=1,VK_TIMEOUT=2;
constexpr uint32_t VK_TRUE=1,VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO=1,VK_QUERY_TYPE_TIMESTAMP=2,VK_QUERY_TYPE_OCCLUSION=3,VK_QUERY_CONTROL_PRECISE_BIT=1,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT=4,VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT=8,VK_QUERY_RESULT_64_BIT=16,VK_PIPELINE_STAGE_ALL_COMMANDS_BIT=32,VK_STRUCTURE_TYPE_SUBMIT_INFO=64;
struct VkQueryPoolCreateInfo{uint32_t sType;void* pNext=nullptr;uint32_t flags=0,queryType=0,queryCount=0;};
struct VkSubmitInfo{uint32_t sType;void* pNext=nullptr;uint32_t waitSemaphoreCount=0;const VkSemaphore* pWaitSemaphores=nullptr;const VkPipelineStageFlags* pWaitDstStageMask=nullptr;uint32_t commandBufferCount=0;const VkCommandBuffer* pCommandBuffers=nullptr;uint32_t signalSemaphoreCount=0;const VkSemaphore* pSignalSemaphores=nullptr;};
struct VkPhysicalDeviceFeatures{bool occlusionQueryPrecise=true;};
const VkPhysicalDeviceFeatures& vk_features(){static VkPhysicalDeviceFeatures f;return f;}
struct VkPhysicalDeviceProperties{struct{float timestampPeriod=2;}limits;};
struct VkQueueFamilyProperties{uint32_t timestampValidBits=64;};
namespace nx::vk{}
namespace nx::nvn{uint32_t vk_queue_family(){return 0;}}
namespace nx::plat{uint64_t now=1000000000;uint64_t monotonic_ns(){return now;}}
namespace nx::nvn::replay{bool overlap=false;bool written_overlaps(const uint8_t*,uint64_t){return overlap;}unsigned invalidates=0,writes=0;void dedup_invalidate(const uint8_t*,uint64_t){invalidates++;}void written_cpu_write(const uint8_t*,uint64_t){writes++;}}
unsigned pools=0,resets=0,ends=0,reads=0;bool fence=false,in_pass=true,fail_create=false,fail_query=false,queue_ok=true,wait_ok=true;
uint64_t gpu_tick=1000000;std::vector<uint32_t> stages;std::map<uint64_t,std::vector<uint64_t>> results;
void log(const char*,...){}
int vk_physical(){return 1;} int vk_device(){return 2;}
void p_vkGetPhysicalDeviceProperties(int,VkPhysicalDeviceProperties* p){*p={};}
void p_vkGetPhysicalDeviceQueueFamilyProperties(int,uint32_t* n,VkQueueFamilyProperties* p){if(p)p[0]={};*n=1;}
VkResult p_vkCreateQueryPool(int,const VkQueryPoolCreateInfo* ci,void*,VkQueryPool* out){assert(ci->queryType==VK_QUERY_TYPE_TIMESTAMP&&ci->queryCount==4096);if(fail_create)return -1;*out=++pools;return 0;}
void p_vkCmdBeginQuery(VkCommandBuffer,VkQueryPool,uint32_t,uint32_t){assert(false);}
void p_vkCmdEndQuery(VkCommandBuffer,VkQueryPool,uint32_t){assert(false);}
void draw_end_rendering(VkCommandBuffer){ends++;in_pass=false;}
void p_vkCmdResetQueryPool(VkCommandBuffer,VkQueryPool pool,uint32_t first,uint32_t count){assert(!in_pass&&first==0&&count==4096);resets++;results[pool].clear();}
void p_vkCmdWriteTimestamp(VkCommandBuffer,uint32_t stage,VkQueryPool pool,uint32_t q){stages.push_back(stage);assert(q==results[pool].size());results[pool].push_back(gpu_tick);gpu_tick+=1000;}
VkResult p_vkGetQueryPoolResults(int,VkQueryPool pool,uint32_t first,uint32_t count,size_t bytes,void* out,size_t stride,uint32_t flags){assert(fence&&first==0&&bytes==8*count&&stride==8&&flags==VK_QUERY_RESULT_64_BIT);reads++;if(fail_query)return VK_NOT_READY;assert(results[pool].size()==count);std::memcpy(out,results[pool].data(),bytes);return 0;}
void p_vkEndCommandBuffer(VkCommandBuffer){} void p_vkResetFences(VkDevice,uint32_t,VkFence*){fence=false;}
VkResult p_vkQueueSubmit(int,uint32_t,const VkSubmitInfo*,VkFence){return queue_ok?0:-1;}
VkResult p_vkWaitForFences(VkDevice,uint32_t,VkFence*,uint32_t,uint64_t){fence=wait_ok;return wait_ok?0:-1;}
VkDevice g_device=2;int g_queue=0;VkCommandBuffer g_cb=1;VkFence g_fence=1;
bool check(VkResult r,const char*){return r==0;}void gpu_hung(const char*){assert(false);}
uint64_t fence_timeout_ns(){return 1000000;}
struct Times{uint64_t encode_ns=0,fence_ns=0;}times;
Times& frame_times(){return times;}
'''
tests=r'''
int main(int argc,char**argv){
 unsetenv("NX_GPU_COUNTERS");unsetenv("NX_GPU_TIMESTAMPS");
 if(argc>1){
  const char* mode=argv[1];bool enabled=false;
  if(!std::strcmp(mode,"alias")){setenv("NX_GPU_COUNTERS","1",1);enabled=true;}
  else if(!std::strcmp(mode,"precedence1")){setenv("NX_GPU_COUNTERS","0",1);setenv("NX_GPU_TIMESTAMPS","1",1);enabled=true;}
  else if(!std::strcmp(mode,"precedence0")){setenv("NX_GPU_COUNTERS","1",1);setenv("NX_GPU_TIMESTAMPS","0",1);}
  else if(!std::strcmp(mode,"disabled"))setenv("NX_GPU_TIMESTAMPS","0",1);
  uint64_t a[2]={77,88};assert(counter_timestamp_report(1,0,(uint8_t*)a,5)==enabled);assert(counter_timestamp_report(1,16,(uint8_t*)a,6)==enabled);assert(a[0]==77&&a[1]==88&&pools==unsigned(enabled));return 0;
 }
 setenv("NX_GPU_TIMESTAMPS","1",1);
uint64_t a[2]={77,88},b[2]={99,111},c[2]={222,333};
 // The recording path never publishes a timestamp, and only the two timestamp types are intercepted.
 assert(!counter_timestamp_report(1,1,(uint8_t*)a,5));assert(pools==0);
 assert(counter_timestamp_report(1,16,(uint8_t*)a,10));assert(counter_timestamp_report(1,0,(uint8_t*)b,11));
 assert(a[0]==77&&a[1]==88&&b[0]==99&&b[1]==111);assert(ends==1&&resets==1);
 assert(stages==std::vector<uint32_t>({VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT}));
 assert(counter_queries_pending(1));end_and_wait(0,0);assert(fence&&reads==1&&!counter_queries_pending(1));
 assert(a[0]==10&&b[0]==11&&b[1]-a[1]==2000);assert(b[1]==nx::plat::now);
 const uint64_t last=b[1];nx::plat::now+=500000000;
 // A new command buffer has a separate pool, but the same GPU epoch conversion.
 assert(counter_timestamp_report(2,0,(uint8_t*)c,12));assert(c[0]==222);g_cb=2;end_and_wait(0,0);
 assert(c[0]==12&&c[1]-last==2000);assert(pools==2); // recording delay was 500ms, measuredGPUdelay2us
 // Reuse resets only after its prior fence; a failed read does not publish fabricated results.
 counter_queries_discard(1);fail_query=true;assert(counter_timestamp_report(1,0,(uint8_t*)a,50));
 auto old=a[1];g_cb=1;end_and_wait(0,0);assert(a[0]==10&&a[1]==old&&!counter_queries_pending(1));fail_query=false;
 // Failed submit and failed fence cannot publish. Discard prevents accidental later publication.
 assert(counter_timestamp_report(1,0,(uint8_t*)a,60));queue_ok=false;end_and_wait(0,0);assert(a[0]==10);counter_queries_discard(1);queue_ok=true;
 assert(counter_timestamp_report(1,0,(uint8_t*)a,61));wait_ok=false;end_and_wait(0,0);assert(a[0]==10);counter_queries_discard(1);wait_ok=true;
 fail_create=true;assert(!counter_timestamp_report(3,0,(uint8_t*)a,62));fail_create=false;
 // Counter/SSBO aliases are not silently overwritten or given an invented ordering.
 counter_queries_discard(1);assert(counter_timestamp_report(1,0,(uint8_t*)a,70));nx::nvn::replay::overlap=true;end_and_wait(0,0);assert(a[0]==10);nx::nvn::replay::overlap=false;
 assert(counter_timestamp_report(1,0,(uint8_t*)a,71));fence=true;std::vector<WriteBack> aliases={{nullptr,(uint8_t*)a+4,8}};counter_queries_collect(1,&aliases);assert(a[0]==10);
 assert(counter_timestamp_report(1,0,(uint8_t*)a,72));std::vector<WriteBack> disjoint={{nullptr,(uint8_t*)b,16}};counter_queries_collect(1,&disjoint);assert(a[0]==72);
 // Fixed offset, non-unit timestampPeriod, finite-bit wrap and an out-of-order pipeline-stage result.
 CounterClock clock;clock.period=2;clock.bits=8;clock.anchor(250,1000);
 assert(clock.nanoseconds(250,1000)==1000);assert(clock.nanoseconds(4,1020)==1020);assert(clock.nanoseconds(2,1020)==1016);
 assert(clock.nanoseconds(14,1552)==1552); // one additional wrap while idle
 assert(nx::nvn::replay::invalidates==4&&nx::nvn::replay::writes==4);
 puts("PASS GPUcounter queries: stages, fence-only publication, real GPU deltas, fixed clock epoch, period/wrap, failures and async whole-submit waits");
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-gpu-counter-') as td:
 d=Path(td);cpp=d/'t.cpp';exe=d/'t';cpp.write_text(prefix+body+'\nnamespace nx::nvn{'+waiter+'}\nusing namespace nx::nvn;\n'+tests)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined',str(cpp),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
 for mode in ["default","disabled","alias","precedence1","precedence0"]:subprocess.run([str(exe),mode],check=True)
