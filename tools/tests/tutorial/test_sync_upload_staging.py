"""Exercise actual sync/async upload selection without a Vulkan device."""
from pathlib import Path
import subprocess,sys,tempfile

root=Path(sys.argv[1]);folder=root/'runtime/src/nvn'
vk=(folder/'nvn_vk.cpp').read_text();frames=(folder/'nvn_frames.cpp').read_text();uploads=(folder/'nvn_upload.cpp').read_text();header=(folder/'nvn_vk.h').read_text()
def block(text,signature):
    start=text.index(signature);cur=text.index('{',start);depth=1;end=cur+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
helpers='\n'.join(block(vk,signature) for signature in ['uint64_t upload_capacity()', 'uint64_t upload_bytes_used()', 'Upload upload_alloc(', 'Upload upload('])
helpers+='\n'+block(uploads,'bool staging_wanted(')
submit=block(vk,'void gpu_submit(')
reset=block(submit,'    if (!async) {')
# Extract only the real synchronous branch, without introducing an alternate reset.
reset='void begin_submit(){bool async=async_gpu();\n'+reset+'\n}'
actual_frame=block(frames,'Upload frame_upload_alloc(')
actual_counts='\n'.join(block(frames,s) for s in ['uint64_t frame_upload_used()', 'uint64_t frame_ring_size()'])
assert 'linear.size() >= (1u << 20)' in uploads and 'staging_wanted(linear.size())' in uploads
assert 'free_retired_images(UINT64_MAX)' in reset and 'g_upload_used = 0;' in reset

code=r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
using VkBuffer=uint64_t;using VkFence=uint64_t;
constexpr VkBuffer VK_NULL_HANDLE=0;
'''+block(header,'struct Upload {')+';'+r'''
bool async_mode=false;
bool async_gpu(){return async_mode;}
uint64_t g_upload_size=256ull<<20,g_upload_used=0,g_upload=11;
uint8_t* g_upload_ptr=nullptr;
uint64_t g_head=0,g_begin=0,g_tail=0,g_ring_size=128ull<<20,g_ring=22;
uint8_t* g_ring_ptr=nullptr;
struct Slot {uint32_t waited=0,part=0;};Slot* g_current=nullptr;
constexpr unsigned kMaxParts=32;
unsigned retired_calls=0,descriptor_resets=0,ring_pressure=0;
uint64_t g_device=0,g_descriptors=0;
void free_retired_images(uint64_t until){assert(until==UINT64_MAX);++retired_calls;}
void p_vkResetDescriptorPool(uint64_t,uint64_t,uint32_t){++descriptor_resets;}
bool retire_oldest(){++ring_pressure;return false;}
void wait_fences(VkFence*,uint32_t){assert(false);}
uint32_t queued_fences(Slot&,uint32_t,VkFence*){assert(false);return 0;}
namespace replay {unsigned resets=0;void dedup_reset(){++resets;}}
void log(const char*,...){assert(false);}
'''+actual_counts+'\n'+actual_frame+'\n'+helpers+'\n'+reset+r'''
uint64_t reference_used(){return async_mode?g_head-g_begin:g_upload_used;}
bool reference_policy(uint64_t size,bool force){
 const uint64_t capacity=async_mode?g_ring_size:g_upload_size;
 const uint64_t used=reference_used();
 if(force || !capacity || size>capacity/8 || used>capacity/4)return true;
 return size>capacity/4-used;
}
int main(int argc,char** argv){
 assert(argc==2);const bool force=std::strcmp(argv[1],"force0")==0;
 if(force)setenv("NX_STAGING_MIN","0",1);
 else if(std::strcmp(argv[1],"configured1")==0)setenv("NX_STAGING_MIN","1",1);
 else unsetenv("NX_STAGING_MIN");
 constexpr uint64_t MB=1ull<<20;
 // Policy-only cases allocate no buffers even for extreme metadata values.
 for(bool asynchronous:{false,true}){
  async_mode=asynchronous;
  for(uint64_t capacity:{uint64_t(0),uint64_t(1),uint64_t(8),uint64_t(128)*MB,uint64_t(256)*MB,UINT64_MAX}){
   g_upload_size=g_ring_size=capacity;
   for(uint64_t used:{uint64_t(0),capacity/4,capacity/4+1,capacity/2,UINT64_MAX-1,UINT64_MAX}){
    g_upload_used=used;g_begin=0;g_head=used;
    assert(upload_capacity()==capacity && upload_bytes_used()==used);
    for(uint64_t size:{uint64_t(0),uint64_t(1),MB,capacity/8,capacity/8+1,capacity/4,UINT64_MAX})
     assert(staging_wanted(size)==reference_policy(size,force));
   }
  }
 }
 async_mode=false;g_upload_size=256*MB;g_upload_used=0;
 assert(staging_wanted(MB)==force);
 g_upload_used=63*MB;assert(staging_wanted(MB)==force); // exactly the quarter
 assert(staging_wanted(MB+1));
 g_upload_used=0;assert(staging_wanted(32*MB)==force); // exactly the eighth
 assert(staging_wanted(32*MB+1));
 // Existing async accounting is selected even when the synchronous metadata differs.
 async_mode=true;g_ring_size=128*MB;g_begin=100;g_head=200;g_upload_size=1;g_upload_used=UINT64_MAX;
 assert(upload_capacity()==128*MB && upload_bytes_used()==100);
 assert(staging_wanted(MB)==force);
 // Real allocator and upload copies: enough backing for every allowed test upload.
 std::vector<uint8_t> sync_memory(65*MB,0xCC),async_memory(65*MB,0xDD),payload(MB);
 g_upload_ptr=sync_memory.data();g_ring_ptr=async_memory.data();
 async_mode=false;g_upload_size=256*MB;g_upload_used=7;
 begin_submit();assert(g_upload_used==0 && retired_calls==1 && descriptor_resets==1);
 std::vector<Upload> saved;
 for(unsigned index=0;index<48;++index){
  std::fill(payload.begin(),payload.end(),uint8_t(index+1));
  assert(upload_bytes_used()==index*MB);
  if(!force)assert(!staging_wanted(payload.size()));
  auto copy=upload(payload.data(),payload.size(),16);
  assert(copy.buffer==g_upload && copy.offset==index*MB && copy.ptr==g_upload_ptr+copy.offset);
  saved.push_back(copy);
 }
 for(unsigned index=0;index<saved.size();++index)
  for(uint64_t byte=0;byte<MB;++byte)assert(saved[index].ptr[byte]==uint8_t(index+1));
 assert(g_upload_used==48*MB && replay::resets==0);
 // Alignment never overwrites an earlier allocation and its padding stays untouched.
 auto pad=upload_alloc(3,16);std::memset(pad.ptr,0xA1,3);
 auto aligned=upload_alloc(5,256);assert(aligned.offset%256==0 && aligned.offset>=pad.offset+3);
 assert(pad.ptr[0]==0xA1 && pad.ptr[2]==0xA1);
 for(uint64_t at=pad.offset+3;at<aligned.offset;++at)assert(sync_memory[at]==0xCC);
 // A completed synchronous submit may reuse its buffer from zero on the next submit.
 begin_submit();assert(upload_bytes_used()==0 && retired_calls==2 && descriptor_resets==2);
 auto next=upload_alloc(32,16);assert(next.offset==0);
 // Actual async allocator remains in charge; sync counters and reset stay untouched.
 async_mode=true;g_ring_size=128*MB;g_begin=g_head=g_tail=0;
 const uint64_t sync_used=g_upload_used;begin_submit();
 assert(retired_calls==2 && descriptor_resets==2 && g_upload_used==sync_used);
 auto async_first=upload(payload.data(),payload.size(),16);
 auto async_second=upload(payload.data(),payload.size(),256);
 assert(async_first.buffer==g_ring && async_first.offset==0 && async_second.offset==MB);
 assert(g_upload_used==sync_used && upload_bytes_used()==2*MB && ring_pressure==0);
 assert(std::memcmp(async_first.ptr,payload.data(),MB)==0 && std::memcmp(async_second.ptr,payload.data(),MB)==0);
 std::printf("PASS sync upload staging %s: actual capacity/accounting, exact thresholds/overflow, retained copies, sync reset and unchanged async allocator\n",argv[1]);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-sync-staging-') as td:
    directory=Path(td);cpp=directory/'test.cpp';exe=directory/'test';cpp.write_text(code)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
    for mode in ['default','configured1','force0']:
        subprocess.run([str(exe),mode],check=True)

patch=Path(__file__).resolve().parents[2]/'patches/patch-sync-upload-staging.py'
files=['runtime/src/nvn/nvn_vk.cpp','runtime/src/nvn/nvn_vk.h','runtime/src/nvn/nvn_upload.cpp']
installed={name:(root/name).read_bytes() for name in files}
for style in ['original','lf','crlf','mixed_lf_body','mixed_crlf_body']:
    with tempfile.TemporaryDirectory(prefix='sp2-staging-install-') as td:
        fixture=Path(td);expected={}
        for name,original in installed.items():
            normalized=original.replace(b'\r\n',b'\n')
            data=original if style=='original' else normalized
            if style in ['crlf','mixed_crlf_body']:data=normalized.replace(b'\n',b'\r\n')
            if style=='mixed_lf_body':data=b'// unrelated CRLF prefix\r\n'+data+b'// unrelated CRLF suffix\r\n'
            if style=='mixed_crlf_body':data=b'// unrelated LF prefix\n'+data+b'// unrelated LF suffix\n'
            target=fixture/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);expected[name]=data
        def snapshot():return {name:(fixture/name).read_bytes() for name in files}
        def apply(*flags,ok=True):
            result=subprocess.run([sys.executable,str(patch),'--root',str(fixture),*flags],capture_output=True,text=True)
            assert (result.returncode==0)==ok,style+': '+result.stdout+result.stderr
        apply('--check');assert snapshot()==expected
        apply();assert snapshot()==expected
        apply('--restore');restored=snapshot()
        assert all(b'PATCH-SYNC-UPLOAD-STAGING' not in data for data in restored.values())
        apply('--restore');assert snapshot()==restored
        apply('--check');assert snapshot()==restored
        apply();assert snapshot()==expected
        apply('--check','--restore');assert snapshot()==expected
        # A partial installation must not apply or restore any of the three files.
        (fixture/files[0]).write_bytes(restored[files[0]]);before=snapshot()
        for flags in [[],['--check'],['--restore']]:
            apply(*flags,ok=False);assert snapshot()==before
        (fixture/files[0]).write_bytes(expected[files[0]])
        # An extra anchor outside the installed block is not an idempotent patch.
        duplicate=fixture/files[1]
        duplicate.write_bytes(expected[files[1]]+b'\nUpload upload_alloc(uint64_t size, uint64_t align);\n')
        before=snapshot();apply(ok=False);assert snapshot()==before
        duplicate.write_bytes(expected[files[1]])
        # A late-file anchor failure must preserve earlier files after preflight.
        broken=fixture/files[-1];broken.write_bytes(b'// unknown upload implementation\n');before=snapshot()
        apply(ok=False);assert snapshot()==before
print('PASS sync staging installer: all-file preflight, idempotence, exact restore/reapply, LF/CRLF/mixed newlines and partial/duplicate/failed-anchor safety')
