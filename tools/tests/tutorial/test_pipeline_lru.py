"""Test the real bounded pipeline LRU under hot/cold access, collisions and retirement."""
from pathlib import Path
import subprocess,sys,tempfile
header=Path(sys.argv[1])
code=r'''
#include <cassert>
#include <cstdint>
#include <vector>
#include "pipeline_lru.h"
struct Collide {size_t operator()(int)const{return 0;}};
int main(){
 using Cache=nx::nvn::PipelineLru<int,uint64_t,Collide>;
 Cache c(3);std::vector<uint64_t> dead;
 auto retire=[&](uint64_t p){dead.push_back(p);};
 c.insert(1,101,retire);c.insert(2,102,retire);c.insert(3,103,retire);
 assert(*c.find(1)==101);c.insert(4,104,retire);
 assert(c.size()==3&&c.find(2)==nullptr&&dead==std::vector<uint64_t>{102});
 assert(*c.find(3)==103);c.insert(5,105,retire);
 assert(c.find(1)==nullptr&&c.find(4)&&c.find(3));
 // A frequently used pipeline survives a stream of cold states, unlike FIFO.
 for(int i=6;i<10000;i++){assert(*c.find(3)==103);c.insert(i,100+i,retire);assert(c.size()==3);}
 assert(*c.find(3)==103);assert(dead.size()==9996);
 c.insert(3,999,retire);assert(*c.find(3)==999&&c.size()==3&&dead.back()==103);
 // The most-recent pointer survives unordered_map growth and handles key collisions.
 Cache unlimited(0);std::vector<uint64_t> freed;
 for(int i=0;i<1000;i++){unlimited.insert(i,100+i,[&](uint64_t p){freed.push_back(p);});assert(*unlimited.find(i)==uint64_t(100+i));}
 assert(unlimited.size()==1000&&freed.empty());
 for(int i=0;i<1000;i++)assert(*unlimited.find(i)==uint64_t(100+i));
 Cache one(1);one.insert(1,1,retire);assert(*one.find(1)==1);one.insert(2,2,retire);assert(!one.find(1)&&*one.find(2)==2);
 // Retirement only hands resources to the caller; it performs no immediate destruction.
 puts("PASS pipeline LRU: hot-state retention, bounded/unbounded caches, collisions, last-hit pointers and deferred retirement");
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-pipeline-lru-') as td:
 d=Path(td);cpp=d/'t.cpp';exe=d/'t';cpp.write_text('#include <cstdio>\n'+code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-I',str(header.parent),str(cpp),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
