#!/usr/bin/env python3
"""Verify the actual upload cache after inline writes, overlapping copies and front-cache collisions."""
from pathlib import Path
import subprocess,sys,tempfile
text=Path(sys.argv[1]).read_text();start=text.index('namespace {');end=text.index('// c[0], the NVN',start);body=text[start:end]
source=r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <vector>
#include <iostream>
struct Upload {uint8_t* ptr=nullptr;uint64_t offset=0;};
std::vector<std::unique_ptr<uint8_t[]>> allocations;
Upload upload_alloc(uint64_t n,uint64_t align){
 auto p=std::make_unique<uint8_t[]>(n);Upload u{p.get(),uint64_t(allocations.size()+1)*65536};allocations.push_back(std::move(p));return u;
}
'''+body+r'''
int main(){
 std::vector<uint8_t> data(4096*1024);for(unsigned i=0;i<data.size();i++)data[i]=uint8_t(i/1024);
 dedup_reset();std::vector<Upload> original;
 for(unsigned i=0;i<4096;i++)original.push_back(dedup_upload(data.data()+i*1024,128,256,256));
 assert(g_largest_copy==128);
 uint64_t visited=g_invalidate_visits;
 // Real inline writes: only that block's old upload must be replaced. Cached bytes must match the mutated source.
 for(unsigned i=0;i<4096;i++){
  uint8_t* p=data.data()+i*1024;p[64]^=0x55;dedup_invalidate(p+64,1);
  Upload u=dedup_upload(p,128,256,256);assert(u.ptr!=original[i].ptr);assert(!memcmp(u.ptr,p,128));
  for(unsigned j=128;j<256;j++)assert(u.ptr[j]==0);
 }
 assert(g_invalidate_visits-visited==4096); // The old scan visits millions of unrelated entries in this layout.
 // Copies beginning before an update must be invalidated; copies merely touching either end must survive.
 dedup_reset();auto large=dedup_upload(data.data(),65536,65536,16);
 auto inside=dedup_upload(data.data()+30000,128,128,16);
 auto touching=dedup_upload(data.data()+30128,128,128,16);
 dedup_invalidate(data.data()+30000,128);
 assert(dedup_upload(data.data(),65536,65536,16).ptr!=large.ptr);
 assert(dedup_upload(data.data()+30000,128,128,16).ptr!=inside.ptr);
 assert(dedup_upload(data.data()+30128,128,128,16).ptr==touching.ptr);
 // A shorter replacement does not reduce the conservative bound, and empty updates preserve cached data.
 dedup_upload(data.data(),64,64,16);assert(g_largest_copy==65536);
 auto keep=dedup_upload(data.data()+40000,128,128,16);dedup_invalidate(data.data()+40000,0);
 assert(dedup_upload(data.data()+40000,128,128,16).ptr==keep.ptr);
 dedup_reset();assert(g_largest_copy==0&&g_copies.empty());
 // Front-slot collisions must not permit a stale copy after invalidation.
 const uint8_t* a=data.data();const uint8_t* b=nullptr;
 for(unsigned i=1;i<4096;i++)if(&front_of(a)==&front_of(data.data()+i*1024)){b=data.data()+i*1024;break;}
 assert(b);auto ua=dedup_upload(a,32,32,16),ub=dedup_upload(b,32,32,16);dedup_invalidate(a+8,1);
 assert(dedup_upload(b,32,32,16).ptr==ub.ptr&&dedup_upload(a,32,32,16).ptr!=ua.ptr);
 // Compare overlap decisions against a full scan for many irregular update positions.
 for(unsigned step=0;step<80;step++){
  dedup_reset();for(unsigned i=0;i<40;i++)dedup_upload(data.data()+i*37,23+(i%7)*19,256,16);
  uint8_t* p=data.data()+step*19;uint64_t n=1+step%53;std::vector<const uint8_t*> expected;
  for(const auto& [key,e]:g_copies)if(key<p+n&&key+e.size>p)expected.push_back(key);
  size_t count=g_copies.size();dedup_invalidate(p,n);assert(g_copies.size()==count-expected.size());
  for(auto key:expected)assert(!g_copies.contains(key));
 }
 std::cout<<"PASS: inline changes, exact overlap, padded bytes, conservative bounds, empty updates and front-cache collisions; 4096 updates examine 4096 ranges\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-upload-range-') as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(source)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
