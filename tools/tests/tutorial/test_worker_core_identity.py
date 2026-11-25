#!/usr/bin/env python3
"""Exercise production nn::os HLE with SDK ThreadType objects and per-core scratch cursors."""
from pathlib import Path
import re, subprocess, sys, tempfile

root=Path(sys.argv[1])
text=(root/'runtime/src/hle_os.cpp').read_text()
functions=[]
for name in ('get_current_core_number','set_thread_core_mask'):
    start=text.index('void '+name+'(CPU& c) {')
    end=text.index('\n}',start)+2
    functions.append(text[start:end])
sdk=(root/'gen/sdk/code_011.cpp').read_text()
assert 'c.x[1] + 0x1b8ull; c.x[0] = uint32_t(nx::ld<uint32_t>(a));' in sdk
kernel=(root/'runtime/src/svc_process.cpp').read_text()
start=kernel.index('uint32_t set_thread_core_mask(')
end=kernel.index('\n}',start)+2
kernel_helper=kernel[start:end]
start=text.index('std::atomic<uint64_t> g_next_thread_id{1};')
end=text.index('void get_current_thread(',start)
context_helper=text[start:end]
source=r'''
#include <nx/cpu.h>
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdarg>
#include <iostream>
#include <thread>
#include <memory>
#include <atomic>
using nx::CPU;using nx::ld;using nx::st;
struct KObject {virtual ~KObject()=default;};
struct KThread:KObject {uint64_t id=0;uint32_t handle=0;int core=0;};
std::array<std::shared_ptr<KThread>,3> workers;
thread_local KThread* current=nullptr;
KThread* self_thread(){return current;}
void log(const char*,...){}
uint64_t kernel_alloc(uint64_t size,unsigned alignment){
 assert(size==0x200&&alignment==8);
 alignas(8) static thread_local std::array<uint8_t,0x200> storage{};
 return uint64_t(storage.data());
}
namespace nx {
std::shared_ptr<KObject> handle_get(uint32_t handle){
 for(auto& worker:workers)if(worker->handle==handle)return worker;
 return nullptr;
}
'''+kernel_helper+'\n}\n'+context_helper+'\n'.join(functions)+r'''
int main(){
 alignas(8) std::array<std::array<uint8_t,0x200>,3> objects{};
 for(unsigned i=0;i<3;i++){
  workers[i]=std::make_shared<KThread>();workers[i]->id=i+1;workers[i]->handle=101+i;
 }
 for(unsigned i=0;i<3;i++){
  nx::st<uint32_t>(uint64_t(objects[i].data()+0x1b8),workers[i]->handle);
  CPU c{};c.x[0]=uint64_t(objects[i].data());c.x[1]=uint32_t(-1);c.x[2]=1u<<i;
  for(unsigned r=19;r<32;r++)c.x[r]=0xabc000+r;
  ::set_thread_core_mask(c);assert(c.x[0]==0);
  for(unsigned r=19;r<32;r++)assert(c.x[r]==0xabc000+r);
 }
 // Three workers must select different scratch cursors, preserving every record.
 std::array<std::array<uint64_t,10000>,3> scratch{};
 std::array<std::thread,3> threads;
 for(unsigned i=0;i<3;i++)threads[i]=std::thread([&,i]{
  current=workers[i].get();CPU c{};get_current_core_number(c);assert(c.x[0]==i);
  // Synthetic current-thread tokens must be usable by the same SDK handle API.
  uint64_t token=thread_ctx();assert(ld<uint32_t>(token+0x1b8)==current->handle);
  c.x[0]=token;c.x[1]=uint32_t(-3);c.x[2]=7;::set_thread_core_mask(c);assert(current->core==int(i));
  get_current_core_number(c);
  for(unsigned j=0;j<10000;j++)scratch[c.x[0]][j]=(uint64_t(i+1)<<32)|j;
 });
 for(auto& thread:threads)thread.join();
 for(unsigned i=0;i<3;i++)for(unsigned j=0;j<10000;j++)assert(scratch[i][j]==((uint64_t(i+1)<<32)|j));
 current=nullptr;CPU c{};get_current_core_number(c);assert(c.x[0]==0);
 c.x[0]=0;::set_thread_core_mask(c);assert(c.x[0]==0);
 std::cout<<"PASS: SDK handle offset, worker masks, distinct scratch cursors, callee registers, missing thread\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-worker-core-') as tmp:
    p=Path(tmp);(p/'test.cpp').write_text(source)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I',str(root/'runtime/include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
