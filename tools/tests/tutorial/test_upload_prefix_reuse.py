"""Compare production prefix reuse against fresh-copy bytes and original policy."""
from pathlib import Path
import subprocess,sys,tempfile,os
text=Path(sys.argv[1]).read_text();start=text.index('namespace {');end=text.index('// c[0], the NVN',start);body=text[start:end]
old='    if (e && e->size == size && e->padded == padded && e->upload.offset % align == 0) {'
a=body.index('    // PATCH-UPLOAD-PREFIX-REUSE:');b=body.index('        g_saved += padded;',a)
original=body[:a]+old+'\n'+body[b:]
code=r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <vector>
#include <cstdio>
struct Upload {uint8_t* ptr=nullptr;uint64_t offset=0;};
std::vector<std::unique_ptr<uint8_t[]>> allocations;
uint64_t next_offset=256;
Upload upload_alloc(uint64_t n,uint64_t align){
 auto p=std::make_unique<uint8_t[]>(n);next_offset=(next_offset+align-1)&~(align-1);
 Upload u{p.get(),next_offset};next_offset+=n;allocations.push_back(std::move(p));return u;
}
'''+ '\nnamespace reference {\n'+original+'\n}\nnamespace actual {\n'+body+'\n}\n'+r'''
void verify(Upload u,const uint8_t* source,uint64_t size,uint64_t padded,uint64_t align){
 assert(u.offset%align==0);assert(!memcmp(u.ptr,source,size));
 for(uint64_t i=size;i<padded;i++)assert(u.ptr[i]==0);
}
int main(){
 const bool off=getenv("NX_NO_DEDUP")!=nullptr;
 std::vector<uint8_t> data(16384);for(unsigned i=0;i<data.size();i++)data[i]=uint8_t(i*31+7);
 unsigned cases=0,hits=0;
 for(uint64_t oldSize=1;oldSize<=31;oldSize++)for(uint64_t oldPadding:{0,3,9})
 for(uint64_t size=1;size<=oldSize+3;size++)for(uint64_t padding:{0,2,7})for(uint64_t align:{16,256,1024}){
  actual::dedup_reset();reference::dedup_reset();allocations.clear();next_offset=256;
  auto held=actual::dedup_upload(data.data(),oldSize,oldSize+oldPadding,16);
  auto originalHeld=reference::dedup_upload(data.data(),oldSize,oldSize+oldPadding,16);
  auto u=actual::dedup_upload(data.data(),size,size+padding,align);
  auto v=reference::dedup_upload(data.data(),size,size+padding,align);
  verify(u,data.data(),size,size+padding,align);verify(v,data.data(),size,size+padding,align);
  assert(!memcmp(u.ptr,v.ptr,size+padding));
  bool expected=!off&&oldSize>=size&&oldSize+oldPadding>=size+padding&&(!padding||oldSize==size)&&held.offset%align==0;
  assert((u.ptr==held.ptr)==expected);hits+=expected;cases++;
 }
 actual::dedup_reset();reference::dedup_reset();allocations.clear();next_offset=256;
 auto large=actual::dedup_upload(data.data(),4096,4096,16);
 auto prefix=actual::dedup_upload(data.data(),1024,1024,16);assert((prefix.ptr==large.ptr)==!off);
 // Writes inside a reused prefix must invalidate the retained larger source too.
 data[30]^=0x99;actual::dedup_invalidate(data.data()+30,1);
 auto changed=actual::dedup_upload(data.data(),1024,1024,16);assert(changed.ptr!=large.ptr);verify(changed,data.data(),1024,1024,16);
 auto keep=actual::dedup_upload(data.data()+8192,64,128,16);actual::dedup_invalidate(data.data()+8192+64,1);
 auto same=actual::dedup_upload(data.data()+8192,64,96,16);assert((same.ptr==keep.ptr)==!off);verify(same,data.data()+8192,64,96,16);
 // Reset must never reuse an upload buffer from an earlier submission.
 actual::dedup_reset();auto fresh=actual::dedup_upload(data.data()+8192,64,96,16);assert(fresh.ptr!=same.ptr);
 // Front-slot collisions fall back to the map without losing prefix validity.
 actual::dedup_reset();const uint8_t* other=nullptr;
 for(unsigned i=1;i<16000;i++)if(&actual::front_of(data.data()+i)==&actual::front_of(data.data())){other=data.data()+i;break;}
 assert(other);large=actual::dedup_upload(data.data(),4096,4096,16);actual::dedup_upload(other,32,32,16);
 prefix=actual::dedup_upload(data.data(),512,512,16);assert((prefix.ptr==large.ptr)==!off);verify(prefix,data.data(),512,512,16);
 // Synthetic multi-draw replay: compare copied bytes, never use this as FPS evidence.
 actual::dedup_reset();reference::dedup_reset();actual::g_copied=reference::g_copied=0;
 for(unsigned repeat=0;repeat<300;repeat++){
  for(uint64_t size:{4096,2048,1024,512,256,2048,512,1024}){
   auto a=actual::dedup_upload(data.data(),size,size,16),b=reference::dedup_upload(data.data(),size,size,16);
   verify(a,data.data(),size,size,16);assert(!memcmp(a.ptr,b.ptr,size));
  }
 }
 if(!off){assert(actual::g_copied==4096 && reference::g_copied>1000000);assert(hits>0);}
 else assert(actual::g_copied==reference::g_copied && hits==0);
 printf("PASS prefix reuse %s: %u byte-equivalence/alignment/padding cases, invalidation, reset, collisions; synthetic copied bytes %llu -> %llu\n",off?"disabled":"enabled",cases,(unsigned long long)reference::g_copied,(unsigned long long)actual::g_copied);
}
'''
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp);(path/'test.cpp').write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
 env=os.environ.copy();env.pop('NX_NO_DEDUP',None);subprocess.run([str(path/'test')],env=env,check=True)
 env['NX_NO_DEDUP']='1';subprocess.run([str(path/'test')],env=env,check=True)

import importlib.util
installer=Path(__file__).resolve().parents[2]/'patches/patch-upload-prefix-reuse.py'
spec=importlib.util.spec_from_file_location('upload_prefix_patch',installer);patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
with tempfile.TemporaryDirectory() as tmp:
 fixture=Path(tmp);target=fixture/'runtime/src/nvn/nvn_dedup.cpp';target.parent.mkdir(parents=True)
 command=[sys.executable,str(installer),'--root',str(fixture)]
 for newline in [b'\n',b'\r\n']:
  original=b'// sentinel'+newline+patch.OLD.encode()+newline+b'// unchanged'+newline
  target.write_bytes(original);subprocess.run(command,check=True,stdout=subprocess.DEVNULL);installed=target.read_bytes()
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);assert target.read_bytes()==installed
  subprocess.run(command+['--restore'],check=True,stdout=subprocess.DEVNULL);assert target.read_bytes()==original
 target.write_bytes(patch.OLD.encode()*2);original=target.read_bytes()
 result=subprocess.run(command,capture_output=True);assert result.returncode!=0 and target.read_bytes()==original
print('PASS: prefix installer exact LF/CRLF restore, idempotence and duplicate refusal')
