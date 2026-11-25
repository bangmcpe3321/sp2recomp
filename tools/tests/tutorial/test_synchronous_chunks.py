from pathlib import Path
import subprocess,sys,tempfile,os
root=Path(sys.argv[1]);folder=root/'runtime/src/nvn';frames=(folder/'nvn_frames.cpp').read_text();vk=(folder/'nvn_vk.cpp').read_text()
def block(s,signature):
 start=s.index(signature);at=s.index('{',start);end=at+1;depth=1
 while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]
assert 'if (async_gpu() || synchronous_chunks()) // PATCH-SYNC-CHUNKS\n        frame_init(' in vk
assert 'if (!async_gpu())\n        g_descriptors = make_descriptor_pool();' in vk
submit=block(vk,'void gpu_submit(');start=submit.index('    if (async || synchronous_chunks())');end=submit.index('    ph[3]',start)
finish='void finish_submit(bool async){\n'+submit[start:end]+'}\n'
source=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <vector>
using VkCommandBuffer=uint64_t;using VkSemaphore=uint64_t;using VkFence=uint64_t;
using VkDescriptorPool=uint64_t;using VkCommandPool=uint64_t;
constexpr uint64_t VK_NULL_HANDLE=0;constexpr unsigned kMaxParts=8;
constexpr int VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO=1,VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT=2;
struct VkCommandBufferBeginInfo {int sType;void* pNext=nullptr;unsigned flags=0;};
struct WriteBack {uint8_t* from;uint8_t* to;uint64_t size;};
struct CmdList{};
namespace plat {uint64_t monotonic_ns(){return 100;}}
namespace replay {void trace_nan_write_back(const uint8_t*,uint8_t*,uint64_t){}uint64_t written_bind_count(){return 0;}}
bool asynchronous=false;bool async_gpu(){return asynchronous;}bool pipelined(){return false;}
'''+block(frames,'bool synchronous_chunks()')+'\n'+block(frames,'struct Slot {')+r''';
Slot g_slots[2];Slot* g_current=nullptr;unsigned g_slot_count=2,g_max_replays=2;
uint64_t g_chunk_from=UINT64_MAX,g_chunk_draws=150,g_submitted=0,g_completed=0,g_head=0,g_tail=0,g_barrier=0;
bool g_chunking=false,g_slot_pools=false;int failed_cb=-1;bool all_waited=false;
std::vector<uint64_t> queued,waited,reads,resets;unsigned writebacks=0,freed=0;
struct {uint64_t submits=0,replay_ns=0,chunks=0,throttled=0,waited_first=0,waited_whole=0;} g_stats;
void log(const char*,...){}int vk_device(){return 1;}
void pass_end_only(VkCommandBuffer,uint64_t){}
void gpu_busy_part_begin(unsigned,unsigned,VkCommandBuffer){}void gpu_busy_part_end(unsigned,unsigned,VkCommandBuffer){}
void gpu_busy_retired(unsigned,unsigned){}
void p_vkResetDescriptorPool(int,VkDescriptorPool,unsigned){assert(all_waited);}
void p_vkResetCommandPool(int,VkCommandPool,unsigned){assert(all_waited);}
bool janitor_on(){return false;}void janitor_run(std::function<void()> f){f();}
void free_retired_images(uint64_t){++freed;}
void counter_queries_collect(VkCommandBuffer cb,const std::vector<WriteBack>*){assert(all_waited);reads.push_back(cb);}
void counter_queries_discard(VkCommandBuffer){}bool counter_queries_pending(VkCommandBuffer){return false;}
void apply_write_back(const WriteBack& w){assert(all_waited);++writebacks;memcpy(w.to,w.from,w.size);}
void wait_fences(const VkFence* fences,uint32_t n){waited.assign(fences,fences+n);assert(n==queued.size());all_waited=true;}
bool submit_part(VkCommandBuffer cb,VkFence,VkSemaphore,VkSemaphore){if(int(cb)==failed_cb)return false;queued.push_back(cb);all_waited=false;return true;}
bool begin_part(VkCommandBuffer){return true;}
'''+block(frames,'void apply_write_backs(')+'\n'+block(frames,'uint32_t queued_fences(')+'\n'+block(frames,'bool retire_oldest()')+'\n'+block(frames,'void retire_through(')+'\n'+block(frames,'uint32_t replays_in_flight()')+'\n'+block(frames,'VkCommandBuffer next_part(')+'\n'+block(frames,'VkCommandBuffer frame_chunk(')+'\n'+block(frames,'void frame_submit(')+r'''
std::vector<WriteBack> pending;std::vector<WriteBack> draw_take_write_backs(){return std::move(pending);}
bool gpu_profile_on(){return false;}bool zero_draws_on(){return false;}bool debug_snapshots_pending(){return false;}
unsigned legacy_finishes=0;void end_and_wait(VkSemaphore,VkSemaphore){++legacy_finishes;all_waited=true;}
'''+finish+r'''
VkCommandBuffer g_cb=77;bool check(bool b,const char*){return b;}
void p_vkResetCommandBuffer(VkCommandBuffer cb,unsigned){assert(cb==77);resets.push_back(cb);}
bool p_vkBeginCommandBuffer(VkCommandBuffer,const VkCommandBufferBeginInfo*){return true;}
VkCommandBuffer frame_begin(bool replay){assert(replay);return 201;}
'''+block(vk,'bool begin(bool replay = false)')+r'''
void prepare(){
 queued.clear();waited.clear();reads.clear();all_waited=false;g_chunk_from=UINT64_MAX;
 g_current=&g_slots[0];auto& s=*g_current;s.part=s.queued=s.waited=0;s.split_part=-1;s.ok=true;s.serial=0;s.replay=true;
 for(unsigned i=0;i<kMaxParts;i++){s.cbs[i]=100+i;s.fences[i]=200+i;}
}
int main(int argc,char** argv){
 assert(argc==2);bool requested=!strcmp(argv[1],"on");
 if(requested)setenv("NX_SYNC_CHUNKS","1",1);
 else if(!strcmp(argv[1],"invalid"))setenv("NX_SYNC_CHUNKS","10",1);
 else if(!strcmp(argv[1],"async")){setenv("NX_SYNC_CHUNKS","1",1);asynchronous=true;}
 else unsetenv("NX_SYNC_CHUNKS");
 assert(synchronous_chunks()==requested);
 if(!requested)return 0;
 // Original presentation CB remains separate from every replay chunk CB.
 assert(begin(false)&&g_cb==77);assert(begin(true)&&g_cb==201);assert(begin(false)&&g_cb==77);
 uint8_t input=42,output=0;prepare();g_chunking=true;
 VkCommandBuffer cb=100;
 for(unsigned draw=0;draw<1600;draw++)cb=frame_chunk(cb,draw,false);
 assert(queued.size()==6 && g_current->part==6 && !all_waited); // capped; GPU work may run during later recording
 pending={{&input,&output,1}};finish_submit(false);
 assert(!g_current && queued.size()==7 && all_waited && waited.size()==7);
 assert(reads.size()==7 && writebacks==1 && output==42 && g_slots[0].serial==0 && g_completed==g_submitted);
 assert(legacy_finishes==0 && freed==0); // regular sync retire/present locations retain image cache aging
 // Open passes get twice the threshold. Full submit still waits all parts.
 prepare();cb=100;for(unsigned draw=0;draw<300;draw++)cb=frame_chunk(cb,draw,true);assert(queued.empty());
 cb=frame_chunk(cb,300,true);assert(queued.size()==1);pending.clear();finish_submit(false);assert(all_waited&&waited.size()==2);
 // Debug/no-chunk mode records one part but retains full completion.
 prepare();g_chunking=false;assert(frame_chunk(100,999,false)==100);assert(queued.empty());finish_submit(false);assert(all_waited&&queued.size()==1);
 // A final part that never queued must not be waited or publish its counters.
 prepare();g_chunking=true;cb=frame_chunk(100,0,false);cb=frame_chunk(cb,150,false);assert(queued.size()==1);
 failed_cb=101;pending.clear();finish_submit(false);assert(all_waited&&waited.size()==1&&reads.size()==1);failed_cb=-1;
 // If no part queued no fence is waited and no write-back is published.
 prepare();failed_cb=100;all_waited=false;auto before=writebacks;pending={{&input,&output,1}};finish_submit(false);
 assert(!all_waited && waited.empty() && reads.empty() && writebacks==before && !g_current);
 puts("PASS synchronous chunks: opt-in gate, separate present buffer, early ordered parts, full completion/writebacks/counters, limits, debug path and failed submission");
}
'''
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp);(path/'test.cpp').write_text(source)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
 for mode in ['off','invalid','async','on']:subprocess.run([str(path/'test'),mode],check=True)

# Existing draw/descriptor caches must rebind when a chunk changes command buffers.
draw=(folder/'nvn_draw.cpp').read_text();sets=(folder/'nvn_sets.cpp').read_text()
assert 'g_bound.cb != cb' in draw
bind=block(sets,'void bind_sets(');assert 'cb' in bind and 'CmdBindDescriptorSets' in bind
# Installer preflights every consumer before writing, with byte-exact restore.
import importlib.util
installer=Path(__file__).resolve().parents[2]/'patches/patch-synchronous-chunks.py'
spec=importlib.util.spec_from_file_location('sync_chunks_patch',installer);patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
with tempfile.TemporaryDirectory() as tmp:
 fixture=Path(tmp);command=[sys.executable,str(installer),'--root',str(fixture)]
 for nl in [b'\n',b'\r\n']:
  original={}
  for name,changes in patch.CHANGES.items():
   path=fixture/name;path.parent.mkdir(parents=True,exist_ok=True)
   data=('\n// between anchors\n'.join(old for old,_ in changes)+'\n').encode().replace(b'\n',nl);path.write_bytes(data);original[name]=data
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);applied={n:(fixture/n).read_bytes() for n in original}
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);assert applied=={n:(fixture/n).read_bytes() for n in original}
  subprocess.run(command+['--restore'],check=True,stdout=subprocess.DEVNULL);assert original=={n:(fixture/n).read_bytes() for n in original}
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
  name='runtime/src/nvn/nvn_vk.h';path=fixture/name;old,new=patch.CHANGES[name][0];path.write_bytes(path.read_bytes().replace(new.encode().replace(b'\n',nl),old.encode().replace(b'\n',nl)))
  partial={n:(fixture/n).read_bytes() for n in original};result=subprocess.run(command,capture_output=True)
  assert result.returncode!=0 and partial=={n:(fixture/n).read_bytes() for n in original}
print('PASS synchronous chunk installer LF/CRLF restore, idempotence and all-file partial-patch refusal')
