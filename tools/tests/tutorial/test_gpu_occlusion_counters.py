"""Actual precise-occlusion backend: scopes, passes, resets, fences and NVN command ABI."""
from pathlib import Path
import os,subprocess,sys,tempfile
h=Path(sys.argv[1]);s=h.read_text();body='\n'.join(x for x in s.splitlines() if not x.startswith('#include') and x!='#pragma once')
def block(text,sig):
 start=text.index(sig);end=text.index('{',start)+1;depth=1
 while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
nvn=h.with_name('nvn.h').read_text();state=h.with_name('nvn_state.cpp').read_text();draw=h.with_name('nvn_draw.cpp').read_text();replay=h.with_name('nvn_draw_state.cpp').read_text()
assert 'NX_HLE("nvnCommandBufferResetCounter", ResetCounter)' in state
assert 'case Cmd::ResetCounter: counter_samples_reset(cb,c.n); break;' in replay
assert 'if (c.n==1 && counter_samples_report(cb,p)) break;' in replay
assert draw.index('counter_occlusion_prepare(cb); //')<draw.index('p_vkCmdBeginRendering(cb, &ri);')<draw.index('counter_occlusion_begin_pass(cb);')
endpass=block(draw,'void pass_end_only(');assert endpass.index('counter_occlusion_end_pass(cb);')<endpass.index('p_vkCmdEndRenderPass(cb);')
assert draw.count('!counter_occlusion_pass_active(cb) && zero_draws_begin')==2
prefix=r'''
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <vector>
using VkCommandBuffer=uint64_t;using VkQueryPool=uint64_t;using VkDevice=uint64_t;using VkResult=int;
constexpr uint64_t VK_NULL_HANDLE=0;constexpr int VK_SUCCESS=0,VK_NOT_READY=1;
constexpr uint32_t VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO=1,VK_QUERY_TYPE_TIMESTAMP=2,VK_QUERY_TYPE_OCCLUSION=3,VK_QUERY_CONTROL_PRECISE_BIT=1,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT=4,VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT=8,VK_QUERY_RESULT_64_BIT=16;
struct VkQueryPoolCreateInfo{uint32_t sType;void* pNext=nullptr;uint32_t flags=0,queryType=0,queryCount=0;};
struct VkPhysicalDeviceFeatures{bool occlusionQueryPrecise=true;}features;
const VkPhysicalDeviceFeatures& vk_features(){return features;}
struct VkPhysicalDeviceProperties{struct{float timestampPeriod=2;}limits;};
struct VkQueueFamilyProperties{uint32_t timestampValidBits=64;};
struct WriteBack{uint8_t* from;uint8_t* to;uint64_t size;};
namespace nx::vk{}
namespace nx::plat{uint64_t now=1000000000;uint64_t monotonic_ns(){return now;}}
namespace nx::nvn{uint32_t vk_queue_family(){return 0;}void counter_occlusion_end_pass(VkCommandBuffer);}
namespace nx::nvn::replay{bool overlap=false;bool written_overlaps(const uint8_t*,uint64_t){return overlap;}void dedup_invalidate(const uint8_t*,uint64_t){}void written_cpu_write(const uint8_t*,uint64_t){}}
void log(const char*,...){}
int vk_physical(){return 1;}int vk_device(){return 2;}
void p_vkGetPhysicalDeviceProperties(int,VkPhysicalDeviceProperties* p){*p={};}
void p_vkGetPhysicalDeviceQueueFamilyProperties(int,uint32_t* n,VkQueueFamilyProperties* p){if(p)p[0]={};*n=1;}
struct Pool{uint32_t type;std::vector<uint64_t> values;};
struct Open{VkQueryPool pool=0;uint32_t query=0;};
std::map<VkQueryPool,Pool> pools;std::map<VkCommandBuffer,Open> opened;
unsigned creates=0,begins=0,ends=0,draws=0,resets=0;bool in_pass=false,fence=false,fail_samples=false,fail_timestamps=false,fail_create=false;
VkCommandBuffer pass_cb=0;uint64_t gpu_tick=1000;
VkResult p_vkCreateQueryPool(int,const VkQueryPoolCreateInfo* info,void*,VkQueryPool* out){if(fail_create)return -1;assert(info->queryType==2||info->queryType==3);*out=++creates;pools[*out]={info->queryType,{}};return 0;}
void p_vkCmdResetQueryPool(VkCommandBuffer,VkQueryPool pool,uint32_t first,uint32_t count){assert(!in_pass&&first==0);assert(count==(pools[pool].type==2?4096:8192));pools[pool].values.clear();resets++;}
void p_vkCmdWriteTimestamp(VkCommandBuffer,uint32_t,VkQueryPool pool,uint32_t query){assert(pools[pool].type==2&&query==pools[pool].values.size());pools[pool].values.push_back(gpu_tick);gpu_tick+=1000;}
void p_vkCmdBeginQuery(VkCommandBuffer cb,VkQueryPool pool,uint32_t query,uint32_t flags){assert(in_pass&&pass_cb==cb&&flags==VK_QUERY_CONTROL_PRECISE_BIT&&!opened[cb].pool&&pools[pool].type==3);assert(query==pools[pool].values.size());pools[pool].values.push_back(0);opened[cb]={pool,query};begins++;}
void p_vkCmdEndQuery(VkCommandBuffer cb,VkQueryPool pool,uint32_t query){assert(in_pass&&pass_cb==cb&&opened[cb].pool==pool&&opened[cb].query==query);opened[cb]={};ends++;}
VkResult p_vkGetQueryPoolResults(int,VkQueryPool pool,uint32_t first,uint32_t count,size_t bytes,void* out,size_t stride,uint32_t flags){assert(fence&&first==0&&bytes==8*count&&stride==8&&flags==VK_QUERY_RESULT_64_BIT&&pools[pool].values.size()==count);if((pools[pool].type==3&&fail_samples)||(pools[pool].type==2&&fail_timestamps))return VK_NOT_READY;std::memcpy(out,pools[pool].values.data(),bytes);return 0;}
void draw_end_rendering(VkCommandBuffer cb){if(in_pass){assert(pass_cb==cb);nx::nvn::counter_occlusion_end_pass(cb);in_pass=false;}}
'''
tests=r'''
struct CPU{uint64_t x[32]={};};
Cmd recorded;uint64_t recorded_target=0;
void record(uint64_t target,const Cmd& cmd){recorded_target=target;recorded=cmd;}
'''+block(state,'void ResetCounter(CPU& c)')+r'''
using namespace nx::nvn;
void beginpass(VkCommandBuffer cb){assert(!in_pass);counter_occlusion_prepare(cb);pass_cb=cb;in_pass=true;counter_occlusion_begin_pass(cb);}
void draw(uint64_t samples){assert(in_pass);draws++;auto q=opened[pass_cb];if(q.pool)pools[q.pool].values[q.query]+=samples;}
void finish(VkCommandBuffer cb){assert(!in_pass);fence=true;counter_queries_collect(cb);fence=false;}
int main(int argc,char**argv){
 static_assert(sizeof(Cmd)==128&&offsetof(Cmd,n)==4&&offsetof(Cmd,a)==16&&offsetof(Cmd,blob)==120);
 static_assert(Cmd::ReportCounter==25&&Cmd::DispatchCompute==30&&Cmd::BindMultisampleState==38&&Cmd::ResetCounter==39);
 CPU c;c.x[0]=0xfeed;c.x[1]=1;ResetCounter(c);assert(recorded_target==0xfeed&&recorded.op==Cmd::ResetCounter&&recorded.n==1);
 uint64_t a[2]={999,888},b[2]={777,666},z[2]={555,444};
 if(argc>1){features.occlusionQueryPrecise=false;counter_samples_reset(1,1);beginpass(1);draw(200);draw_end_rendering(1);counter_samples_report(1,(uint8_t*)a);finish(1);assert(a[0]==999&&begins==0);return 0;}
 // An unsupported initial read has no invented positive/zero result.
 counter_samples_report(1,(uint8_t*)a);assert(a[0]==999);
 counter_samples_reset(1,1);beginpass(1);for(int k=0;k<10;k++)draw(2);draw_end_rendering(1);
 beginpass(1);draw(0);draw(4);counter_samples_report(1,(uint8_t*)a);
 beginpass(1);draw(5);counter_samples_report(1,(uint8_t*)b); // cumulative, no reset
 counter_samples_reset(1,1);beginpass(1);draw(0);counter_samples_report(1,(uint8_t*)z);
 assert(a[0]==999&&b[0]==777&&z[0]==555);assert(begins==4&&ends==4&&draws==14);
 finish(1);assert(a[0]==24&&b[0]==29&&z[0]==0&&!counter_queries_pending(1));
 // Pass segments span command buffers. Reporting does not reset the NVN counter.
 counter_queries_discard(2);beginpass(2);draw(3);counter_samples_report(2,(uint8_t*)a);finish(2);assert(a[0]==3);
 counter_queries_discard(3);beginpass(3);draw(7);counter_samples_report(3,(uint8_t*)a);finish(3);assert(a[0]==10);
 // Failed occlusion results invalidate the accumulation until the next real reset.
 counter_queries_discard(4);counter_samples_reset(4,1);beginpass(4);draw(6);counter_samples_report(4,(uint8_t*)a);fail_samples=true;finish(4);fail_samples=false;assert(a[0]==10);
 counter_queries_discard(5);beginpass(5);draw(1);counter_samples_report(5,(uint8_t*)a);finish(5);assert(a[0]==10);
 counter_queries_discard(6);counter_samples_reset(6,1);counter_samples_report(6,(uint8_t*)a);finish(6);assert(a[0]==0); // no draws since reset
 // A failed time measurement cannot erase a successfully measured sample count.
 counter_queries_discard(9);counter_samples_reset(9,1);beginpass(9);draw(17);counter_samples_report(9,(uint8_t*)a);fail_timestamps=true;finish(9);fail_timestamps=false;assert(a[0]==17);
 // A zeroed counter buffer becomes ready even for legitimate zero coverage.
 uint64_t ready[2]={0,0};counter_queries_discard(10);counter_samples_reset(10,1);beginpass(10);draw(0);counter_samples_report(10,(uint8_t*)ready);assert(ready[0]==0&&ready[1]==0);finish(10);assert(ready[0]==0&&ready[1]!=0);
 ready[0]=ready[1]=0;counter_queries_discard(11);counter_samples_reset(11,1);beginpass(11);draw(0);counter_samples_report(11,(uint8_t*)ready);fail_timestamps=true;finish(11);fail_timestamps=false;assert(ready[0]==0&&ready[1]!=0);
 // Allocation failure and query exhaustion cannot fabricate coverage.
 counter_queries_discard(7);fail_create=true;counter_samples_reset(7,1);beginpass(7);draw(12);counter_samples_report(7,(uint8_t*)b);finish(7);fail_create=false;assert(b[0]==29);
 counter_queries_discard(8);counter_samples_reset(8,1);
 for(unsigned k=0;k<8193;k++){beginpass(8);draw(1);draw_end_rendering(8);}
 counter_samples_report(8,(uint8_t*)b);finish(8);assert(b[0]==29);
 // Reusing a retired command buffer resets query storage, but preserves the old NVN value until reset.
 counter_queries_discard(1);counter_samples_reset(1,1);beginpass(1);draw(11);counter_samples_report(1,(uint8_t*)b);finish(1);assert(b[0]==11);
 // A scene transition does not clear the global NVN counter by itself. The next
 // explicit ResetCounter must erase all old scene draws, including one open pass.
 counter_queries_discard(12);beginpass(12);draw(1000000);draw_end_rendering(12);finish(12);
 counter_queries_discard(13);beginpass(13);draw(2000000);counter_samples_reset(13,1);
 beginpass(13);draw(0);counter_samples_report(13,(uint8_t*)a);finish(13);assert(a[0]==0&&a[1]!=0);
 counter_queries_discard(13);counter_samples_reset(13,1);counter_samples_report(13,(uint8_t*)a);finish(13);assert(a[0]==0);
 assert(!in_pass);for(auto [cb,open]:opened)assert(!open.pool);
 puts("PASS precise sample counters: ResetCounter ABI/HLE, per-pass scopes, prefix/cross-submit counts, zero coverage, fence-only publication, failure/exhaustion and legal query lifetimes");
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-occlusion-') as td:
 d=Path(td);cpp=d/'t.cpp';exe=d/'t';cpp.write_text(prefix+body+'\n'+block(nvn,'struct Cmd {')+';\n'+tests)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined',str(cpp),'-o',str(exe)],check=True)
 env=os.environ.copy();env.pop('NX_OCCLUSION_COUNTERS',None);env.pop('NX_GPU_COUNTERS',None);env.pop('NX_GPU_TIMESTAMPS',None)
 subprocess.run([str(exe)],env=env,check=True);subprocess.run([str(exe),'unsupported'],env=env,check=True);subprocess.run([str(exe)],env={**env,'NX_GPU_TIMESTAMPS':'0'},check=True);subprocess.run([str(exe)],env={**env,'NX_GPU_TIMESTAMPS':'1'},check=True)
