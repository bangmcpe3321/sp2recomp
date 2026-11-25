#!/usr/bin/env python3
"""Compare storage-range lookup with the original full scan over 80,000 image keys."""
from pathlib import Path
import subprocess,sys,tempfile
source=Path(sys.argv[1]).read_text()
key=source[source.index('struct StorageKey {'):source.index('// PATCH-MEMORY-ACCOUNTING')]
test=r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <tuple>
#include <vector>
#include <iostream>
struct GpuImage {uint64_t rendered_at=0;bool rendered=false;};
'''+key+r'''
int main(){
 std::vector<std::shared_ptr<GpuImage>> held;
 for(uint64_t i=0;i<80000;i++){
  auto image=std::make_shared<GpuImage>();image->rendered_at=i;image->rendered=true;
  g_live_images.emplace(StorageKey{i*0x1000,37,1280,720,1,1,1,1,0},image);
  if(i%2==0)held.push_back(image); // Include expired entries, preserving full-scan semantics.
 }
 for(uint64_t memory:{uint64_t(0),uint64_t(2000),uint64_t(2*0x1000),uint64_t(79999*0x1000),UINT64_MAX}){
  for(unsigned size=0;size<4;size++){
   auto image=std::make_shared<GpuImage>();image->rendered_at=90000+size;image->rendered=size!=3;
   g_live_images.emplace(StorageKey{memory,size,640+size,360,1,1,1,1,0},image);held.push_back(image);
  }
  std::vector<StorageKey> expected,actual;std::shared_ptr<GpuImage> oldBest,newBest;
  for(const auto& [key,weak]:g_live_images){
   if(key.memory!=memory)continue;expected.push_back(key);
   auto live=weak.lock();if(live&&live->rendered&&(!oldBest||oldBest->rendered_at<live->rendered_at))oldBest=live;
  }
  auto [first,last]=images_at_memory(memory);
  for(auto it=first;it!=last;++it){
   actual.push_back(it->first);auto live=it->second.lock();
   if(live&&live->rendered&&(!newBest||newBest->rendered_at<live->rendered_at))newBest=live;
  }
  assert(expected.size()==actual.size()&&actual.size()<=5);
  for(unsigned i=0;i<actual.size();i++)assert(!(actual[i]<expected[i])&&!(expected[i]<actual[i]));
  assert(oldBest==newBest);
 }
 auto [first,last]=images_at_memory(12345);assert(first==last);
 std::cout<<"PASS: identical image order and freshest rendered content; visits <=5 keys instead of 80000, including expired entries and UINT64_MAX\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-image-storage-') as tmp:
 p=Path(tmp);(p/'test.cpp').write_text(test)
 subprocess.run(['g++','-std=c++20','-O2','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
