#!/usr/bin/env python3
"""Test the native renderer against independently constructed audio packets."""
from pathlib import Path
import subprocess,sys,tempfile
HEADER=Path(sys.argv[1]).resolve()
SOURCE=r'''
#include "sp2_audio_renderer.h"
#include <cassert>
#include <iostream>
using namespace nx::sp2::audio;
struct Fixture {
 std::vector<uint8_t> packet, memory;
 size_t voice,mix,sink,channel;
 Fixture(unsigned nvoices=1,unsigned nchannel=1,unsigned nmix=1,unsigned neffects=0):memory(0x20000) {
  std::array<unsigned,10> sizes{};sizes[1]=16;sizes[2]=32;sizes[3]=nvoices*0x170;sizes[4]=nchannel*0x70;sizes[5]=neffects*0xc0;sizes[6]=nmix*0x930;sizes[7]=0x140;sizes[8]=16;
  unsigned total=64;for(auto s:sizes)total+=s;packet.resize(total);
  put<uint32_t>(packet,0,0x32564552);put<uint32_t>(packet,0x3c,total);
  size_t p=64;for(unsigned k:{1u,2u,4u,3u,5u,9u,6u,7u,8u}){put<uint32_t>(packet,4*k,sizes[k]);if(k==3)voice=p;if(k==4)channel=p;if(k==6)mix=p;if(k==7)sink=p;p+=sizes[k];}
  put<uint32_t>(packet,64+16+16,4);
  for(unsigned i=0;i<nchannel;i++){put<uint32_t>(packet,channel+i*0x70,i);put<float>(packet,channel+i*0x70+4+i*4,1);put<uint8_t>(packet,channel+i*0x70+0x64,1);}
  for(unsigned i=0;i<nmix;i++){size_t m=mix+i*0x930;put<float>(packet,m,1);put<uint32_t>(packet,m+4,48000);put<uint32_t>(packet,m+8,2);put<uint8_t>(packet,m+12,1);put<uint32_t>(packet,m+16,i);put<uint32_t>(packet,m+0x924,i?0:0x7fffffff);put<uint32_t>(packet,m+0x928,0xffffffff);}
  put<uint8_t>(packet,sink,1);put<uint8_t>(packet,sink+1,1);put<uint32_t>(packet,sink+0x120,2);put<uint8_t>(packet,sink+0x125,1);
  for(unsigned i=0;i<nvoices;i++){size_t v=voice+i*0x170;put<uint32_t>(packet,v,i);put<uint8_t>(packet,v+8,1);put<uint8_t>(packet,v+9,1);put<uint8_t>(packet,v+11,2);put<uint32_t>(packet,v+12,48000);put<uint32_t>(packet,v+24,nchannel);put<float>(packet,v+28,1);put<float>(packet,v+32,1);put<uint32_t>(packet,v+60,1);put<uint32_t>(packet,v+92,0xffffffff);for(unsigned c=0;c<nchannel;c++)put<uint32_t>(packet,v+320+c*4,c);}
 }
 Memory read(){return [this](uint64_t addr,size_t size)->const uint8_t*{if(addr<0x10000||addr-0x10000>memory.size()||size>memory.size()-(addr-0x10000))return nullptr;return memory.data()+addr-0x10000;};}
 WritableMemory write(){return [this](uint64_t addr,size_t size)->uint8_t*{if(addr<0x10000||addr-0x10000>memory.size()||size>memory.size()-(addr-0x10000))return nullptr;return memory.data()+addr-0x10000;};}
 void wave(unsigned slot,unsigned start,unsigned end,unsigned bytes,bool loop=false){size_t w=voice+96+slot*56;put<uint64_t>(packet,w,0x10000);put<uint64_t>(packet,w+8,bytes);put<int32_t>(packet,w+16,start);put<int32_t>(packet,w+20,end);put<uint8_t>(packet,w+24,loop);}
 void accepted(){put<uint8_t>(packet,voice+8,0);for(unsigned s=0;s<4;s++)put<uint8_t>(packet,voice+96+s*56+26,1);}
};
int main(){
 {Fixture f;for(unsigned i=0;i<1000;i++)put<int16_t>(f.memory,2*i,1000);f.wave(0,0,1000,2000);Renderer r(f.read());auto out=r.update(f.packet,true);for(unsigned i=0;i<240;i++){assert(r.pcm[2*i]==1000);assert(r.pcm[2*i+1]==0);}assert(get<uint64_t>(out,80)==240);assert(get<uint32_t>(out,64)==5);f.accepted();out=r.update(f.packet,true);assert(get<uint64_t>(out,80)==480);assert(r.pcm[0]==1000);}
 {Fixture f(1,2);for(unsigned i=0;i<500;i++){put<int16_t>(f.memory,4*i,2000);put<int16_t>(f.memory,4*i+2,-3000);}f.wave(0,0,500,2000);put<float>(f.packet,f.voice+32,0.5f);put<float>(f.packet,f.mix,0.5f);Renderer r(f.read());r.update(f.packet,true);assert(r.pcm[0]==500&&r.pcm[1]==-750);}
 {Fixture f;for(unsigned i=0;i<500;i++)put<int16_t>(f.memory,2*i,int16_t(i*100));f.wave(0,0,500,1000);put<float>(f.packet,f.voice+28,0.5f);Renderer r(f.read());auto out=r.update(f.packet,true);assert(r.pcm[0]==0&&r.pcm[2]==50&&r.pcm[4]==100);assert(get<uint64_t>(out,80)==120);}
 {Fixture f;put<int16_t>(f.memory,0,100);put<int16_t>(f.memory,2,200);f.wave(0,0,2,4,true);Renderer r(f.read());auto out=r.update(f.packet,true);for(unsigned s=0;s<240;s++)assert(r.pcm[s*2]==(s%2?200:100));f.accepted();out=r.update(f.packet,true);assert(get<uint32_t>(out,88)==0);assert(get<uint64_t>(out,80)==480);}
 {Fixture f;for(unsigned i=0;i<500;i++)put<int16_t>(f.memory,2*i,1000);f.wave(0,0,500,1000);Renderer r(f.read());r.update(f.packet,true);f.accepted();put<uint8_t>(f.packet,f.voice+10,2);auto out=r.update(f.packet,true);assert(r.pcm[0]==0&&get<uint64_t>(out,80)==240);put<uint8_t>(f.packet,f.voice+10,0);out=r.update(f.packet,true);assert(get<uint64_t>(out,80)==480);put<uint8_t>(f.packet,f.voice+10,1);out=r.update(f.packet,true);assert(r.pcm[0]==0&&get<uint32_t>(out,88)==1);}
 {Fixture f;std::fill(f.memory.begin(),f.memory.begin()+8,0x11);f.memory[0]=0;put<int16_t>(f.memory,0x1000,2048);put<uint8_t>(f.packet,f.voice+11,6);put<uint64_t>(f.packet,f.voice+72,0x11000);put<uint64_t>(f.packet,f.voice+80,32);f.wave(0,0,14,8);Renderer r(f.read());auto out=r.update(f.packet,true);for(unsigned s=0;s<14;s++)assert(r.pcm[s*2]==int(s+1));assert(r.pcm[28]==0&&get<uint32_t>(out,88)==1);}
 {Fixture f;std::fill(f.memory.begin(),f.memory.begin()+8,0x11);f.memory[0]=0;put<int16_t>(f.memory,0x1000,2048);put<int16_t>(f.memory,0x1102,100);put<uint8_t>(f.packet,f.voice+11,6);put<uint64_t>(f.packet,f.voice+72,0x11000);put<uint64_t>(f.packet,f.voice+80,32);f.wave(0,3,14,8);put<uint64_t>(f.packet,f.voice+96+32,0x11100);put<uint64_t>(f.packet,f.voice+96+40,6);Renderer r(f.read());r.update(f.packet,true);assert(r.pcm[0]==101&&r.pcm[20]==111);}
 for(unsigned format:{1u,3u,4u,5u}){Fixture f;put<uint8_t>(f.packet,f.voice+11,format);if(format==1)f.memory[0]=uint8_t(int8_t(-4));if(format==3){f.memory[0]=0;f.memory[1]=0;f.memory[2]=0xfc;}if(format==4)put<int32_t>(f.memory,0,-1024*65536);if(format==5)put<float>(f.memory,0,-0.03125f);f.wave(0,0,1,format==1?1:format==3?3:4);Renderer r(f.read());r.update(f.packet,true);assert(r.pcm[0]==-1024);}
 {Fixture f(1,1,2);for(unsigned i=0;i<500;i++)put<int16_t>(f.memory,2*i,1000);f.wave(0,0,500,1000);put<uint32_t>(f.packet,f.voice+88,1);put<float>(f.packet,f.mix+0x930+0x24,0.25f);put<float>(f.packet,f.mix+0x930+0x28,0.75f);Renderer r(f.read());r.update(f.packet,true);assert(r.pcm[0]==250&&r.pcm[1]==750);}
 {Fixture f;f.wave(0,0,1,2);put<uint64_t>(f.packet,f.voice+96,0x90000000);Renderer r(f.read());r.update(f.packet,true);assert(r.pcm[0]==0);put<uint32_t>(f.packet,12,0xffffffff);bool caught=false;try{r.update(f.packet,true);}catch(const std::runtime_error&){caught=true;}assert(caught);}
 {Fixture f;put<float>(f.packet,f.voice+32,NAN);f.wave(0,0,1,2);Renderer r(f.read());r.update(f.packet,true);assert(r.pcm[0]==0);auto original=f.packet;for(size_t size=0;size<original.size();size+=97){bool caught=false;try{r.update(std::span<const uint8_t>(original).first(size),true);}catch(const std::runtime_error&){caught=true;}assert(caught);}}
 {Fixture f(1,1,1,1);for(unsigned i=0;i<1000;i++)put<int16_t>(f.memory,2*i,1000);f.wave(0,0,1000,2000);Sections sections(f.packet);size_t e=sections.data[5].data()-f.packet.data();put<uint8_t>(f.packet,e,2);put<uint8_t>(f.packet,e+2,1);put<uint32_t>(f.packet,e+0x50,1);put<uint32_t>(f.packet,e+0x58,720);put<uint64_t>(f.packet,e+0x60,0x12000);put<uint64_t>(f.packet,e+0x70,0x12100);put<uint64_t>(f.packet,e+0x68,0x13000);put<uint64_t>(f.packet,e+0x78,0x14000);put<uint32_t>(f.memory,0x2144,240);for(unsigned s=0;s<240;s++)put<int32_t>(f.memory,0x4000+4*s,500);Renderer r(f.read(),f.write());r.update(f.packet,true);assert(r.pcm[0]==500&&r.pcm[478]==500);assert(get<int32_t>(f.memory,0x3000)==1000);assert(get<uint32_t>(f.memory,0x2044)==240&&get<uint32_t>(f.memory,0x2140)==240);assert(r.auxSent==240&&r.auxReturned==240);f.accepted();put<uint32_t>(f.memory,0x2000,240);put<uint32_t>(f.memory,0x2144,240);r.update(f.packet,true);assert(r.pcm[0]==0&&r.auxUnderflows==1);put<uint32_t>(f.memory,0x2140,600);put<uint32_t>(f.memory,0x2144,120);for(unsigned s=0;s<720;s++)put<int32_t>(f.memory,0x4000+4*s,600);put<uint32_t>(f.memory,0x2000,480);r.update(f.packet,true);assert(r.pcm[0]==600&&r.pcm[478]==600&&get<uint32_t>(f.memory,0x2140)==120);}
 std::cout<<"PASS: PCM formats, ADPCM prediction/context, stereo/pan/gain, resampling, loops, pause/stop, sample/buffer feedback, submix routing, invalid addresses and packet bounds\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-audio-test-') as tmp:
    p=Path(tmp);(p/'test.cpp').write_text(SOURCE)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(HEADER.parent),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
