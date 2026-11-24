#!/usr/bin/env python3
"""Exercise NFP manager/child objects through the production CMIF session parser."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
assert '#include "nfp_service.h" // PATCH-NFP-NO-READER' in (root/'runtime/src/svc_misc.cpp').read_text()
code = r'''
#include "nfp_service.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <map>
namespace nx {
bool g_trace=false;
void log(const char*,...){}
std::string describe(uint64_t){return {};}
[[noreturn]]void fatal(const char*,...){std::abort();}
std::map<uint32_t,std::shared_ptr<KObject>> handles;
uint32_t next_handle=100;
uint32_t handle_add(std::shared_ptr<KObject> o){auto h=next_handle++;handles[h]=std::move(o);return h;}
std::shared_ptr<KObject> handle_get(uint32_t h){auto i=handles.find(h);return i==handles.end()?nullptr:i->second;}
void handle_close(uint32_t h){handles.erase(h);}
uint64_t kernel_alloc(uint64_t,uint64_t){std::abort();}
bool commit(uint64_t,uint64_t){std::abort();}
void vm_set(uint64_t,uint64_t,uint32_t,uint32_t){std::abort();}
}
using namespace nx;
struct Reply {uint32_t result=0,value=0;std::vector<uint32_t> moved,copied,objects;};
Reply request(uint32_t handle,uint32_t command,uint32_t object=0,uint32_t type=4){
 alignas(16)std::array<uint32_t,80> words{};
 words.fill(0xa5a5a5a5);for(unsigned i=0;i<64;i++)words[i]=0;
 words[0]=type;words[1]=object?12:8;
 unsigned raw=4;
 if(object){words[4]=(16u<<16)|1;words[5]=object;raw+=4;}
 words[raw]=0x49434653;words[raw+2]=command;
 CPU cpu{};assert(ipc_request(cpu,handle,uint64_t(words.data()),0x100)==0);
 for(unsigned i=64;i<words.size();i++)assert(words[i]==0xa5a5a5a5);
 Reply r;unsigned pos=2;
 if(words[1]>>31){uint32_t special=words[pos++];unsigned copy=(special>>1)&15,move=(special>>5)&15;
  while(copy--)r.copied.push_back(words[pos++]);while(move--)r.moved.push_back(words[pos++]);}
 pos=(pos+3)&~3u;unsigned count=0;
 if(object){count=words[pos];pos+=4;}
 assert(words[pos]==0x4f434653);r.result=words[pos+2];r.value=words[pos+4];
 for(unsigned i=0;i<count;i++)r.objects.push_back(words[pos+4+i]);
 return r;
}
int main(){
 uint64_t root_handle=0;assert(ipc_connect("nfp:user",&root_handle)==0);
 auto parent=request(uint32_t(root_handle),0);
 assert(parent.result==0&&parent.moved.size()==1&&parent.copied.empty());
 uint32_t child=parent.moved[0];assert(handle_get(child));
 assert(request(child,19).value==0);
 assert(request(child,0).result==0); // SDK Initialize is void/fatal-on-error.
 assert(request(child,19).value==1);
 auto devices=request(child,2);assert(devices.result==0x8073&&devices.value==0);
 assert(devices.moved.empty()&&devices.copied.empty());
 for(unsigned cmd:{3u,5u,7u,9u,10u,17u,18u,20u,21u,24u,102u}){
  auto absent=request(child,cmd);assert(absent.result==0x8073&&absent.moved.empty()&&absent.copied.empty());}
 assert(request(child,999).result==0x8273&&request(uint32_t(root_handle),999).result==0x8273);
 auto event1=request(child,23),event2=request(child,23);
 assert(event1.result==0&&event1.copied.size()==1&&event1.moved.empty());
 auto first=std::dynamic_pointer_cast<KEvent>(handle_get(event1.copied[0]));
 auto second=std::dynamic_pointer_cast<KEvent>(handle_get(event2.copied[0]));
 assert(first&&second&&first->state==second->state&&!first->signaled());
 handle_close(event1.copied[0]);assert(!second->signaled());
 assert(request(child,1).result==0&&request(child,19).value==0);
 assert(request(child,0).result==0&&request(child,19).value==1);
 // Independent sessions do not share initialized state.
 auto another=request(uint32_t(root_handle),0);assert(another.moved.size()==1);
 assert(request(another.moved[0],19).value==0&&request(child,19).value==1);
 // Real IPC domain conversion and child-object response, plus a cloned session.
 uint64_t domain=0;assert(ipc_connect("nfp:user",&domain)==0);
 auto converted=request(uint32_t(domain),0,0,5);assert(converted.result==0&&converted.value==1);
 auto object=request(uint32_t(domain),0,1);assert(object.result==0&&object.objects.size()==1&&object.moved.empty());
 uint32_t id=object.objects[0];assert(id!=0&&id!=1);
 assert(request(uint32_t(domain),0,id).result==0);
 assert(request(uint32_t(domain),19,id).value==1);
 assert(request(uint32_t(domain),2,id).result==0x8073);
 auto clone=request(uint32_t(domain),2,0,5);assert(clone.moved.size()==1);
 assert(request(clone.moved[0],19,id).value==1);
 assert(request(clone.moved[0],23,id).copied.size()==1);
 puts("PASS real CMIF: manager child sessions/domains, software initialization, handled no-reader result, unsignaled events, clone and output bounds");
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-nfp-ipc-') as temp:
    path = Path(temp)
    (path/'test.cpp').write_text(code)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer','-I',str(root/'runtime/include'),
                    '-I',str(root/'runtime/src'),str(path/'test.cpp'),
                    str(root/'runtime/src/ipc.cpp'),'-o',str(path/'test')],check=True)
    env = os.environ.copy()
    env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    subprocess.run([str(path/'test')],check=True,env=env)
