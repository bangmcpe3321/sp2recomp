"""Compile the actual row-readback implementation with checked Vulkan recording stubs."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1])
text = source.read_text()
start = text.index('void readback_linear_texture(')
end = text.index('\nnamespace {', start)
body = text[start:end]
prefix = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <memory>
#include <numeric>
#include <vector>
#include <iostream>
using VkCommandBuffer = int;
using VkImageLayout = int;
constexpr int VK_IMAGE_ASPECT_COLOR_BIT=1, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL=2;
constexpr int VK_STRUCTURE_TYPE_MEMORY_BARRIER=3, VK_ACCESS_TRANSFER_WRITE_BIT=4, VK_ACCESS_HOST_READ_BIT=8;
constexpr int VK_PIPELINE_STAGE_TRANSFER_BIT=16, VK_PIPELINE_STAGE_HOST_BIT=32;
struct Texture { uint32_t flags=0x40, stride=48, levels=1, depth=1, samples=1, width=2, height=2, format=16; uint64_t memory=0, storage_size=96; };
struct GpuImage { uint32_t levels=1,layers=1,depth=1,aspect=1,format=16,width=2,height=2; int image=7,layout=5; };
struct WriteBack { uint8_t* from; uint8_t* to; uint64_t size; std::shared_ptr<std::vector<uint8_t>> before; };
struct Upload { int buffer; uint64_t offset; uint8_t* ptr; };
struct Subresource { uint32_t aspect,level,layer,count; };
struct Extent { uint32_t width,height,depth; };
struct VkBufferImageCopy { uint64_t bufferOffset{}; Subresource imageSubresource{}; Extent imageExtent{}; };
struct VkMemoryBarrier { int type; int srcAccessMask{},dstAccessMask{}; };
static uint8_t staging[8192], pixels[8192];
static int allocations=0, copies=0, barriers=0;
static uint32_t copyBytes=16;
uint32_t vk_format(uint32_t f) { return f==200 ? 8 : f; }
uint32_t vk_block_bytes(uint32_t f) { return f; }
void format_block(uint32_t f,uint32_t& w,uint32_t& h,uint32_t& b) { w=h=f==100?4:1; b=f==200?4:f; }
Upload upload_alloc(uint64_t size,uint64_t align) { assert(size<=8000 && align>=16 && (32%align)==0); allocations++; return {42,32,staging+32}; }
void transition(int,GpuImage& i,int to) { i.layout=to; }
void p_vkCmdCopyImageToBuffer(int,int image,int layout,int buffer,int count,const VkBufferImageCopy* r) {
    assert(image==7 && layout==2 && buffer==42 && count==1 && r->bufferOffset%4==0 && r->bufferOffset%copyBytes==0);
    assert(r->imageSubresource.aspect==1 && r->imageSubresource.level==0 && r->imageSubresource.layer==0 && r->imageSubresource.count==1);
    assert(r->imageExtent.depth==1); copies++;
    std::memcpy(staging+r->bufferOffset,pixels,r->imageExtent.width*r->imageExtent.height*copyBytes);
}
void p_vkCmdPipelineBarrier(int,int src,int dst,int,int n,const VkMemoryBarrier* b,int,const void*,int,const void*) {
    assert(src==16 && dst==32 && n==1 && b->srcAccessMask==4 && b->dstAccessMask==8); barriers++;
}
'''
tests = r'''
int main() {
    uint8_t guest[128]; std::memset(guest,0xcc,sizeof guest);
    for(unsigned i=0;i<sizeof pixels;i++) pixels[i]=uint8_t(i+1);
    Texture t; t.memory=reinterpret_cast<uint64_t>(guest); GpuImage image;
    std::vector<WriteBack> writes;
    readback_linear_texture(1,t,image,writes);
    assert(allocations==1 && copies==1 && barriers==1 && image.layout==5 && writes.size()==2);
    assert(writes[0].size==32 && writes[1].size==32 && writes[0].to==guest && writes[1].to==guest+48);
    for(const auto& w:writes) std::memcpy(w.to,w.from,w.size);
    assert(std::memcmp(guest,pixels,32)==0 && std::memcmp(guest+48,pixels+32,32)==0);
    for(unsigned i=32;i<48;i++) assert(guest[i]==0xcc);
    for(unsigned i=80;i<sizeof guest;i++) assert(guest[i]==0xcc);
    auto reject=[&](Texture bad,GpuImage badImage) { writes.clear(); int before=allocations; readback_linear_texture(1,bad,badImage,writes); assert(writes.empty() && allocations==before); };
    Texture bad=t; bad.flags=0; reject(bad,image);
    bad=t; bad.memory=0; reject(bad,image);
    bad=t; bad.stride=16; reject(bad,image);
    bad=t; bad.storage_size=79; reject(bad,image);
    bad=t; bad.memory=UINT64_MAX-16; reject(bad,image);
    bad=t; bad.levels=2; reject(bad,image);
    bad=t; bad.samples=4; reject(bad,image);
    bad=t; bad.depth=2; reject(bad,image);
    auto bi=image; bi.layers=2; reject(t,bi);
    bi=image; bi.aspect=2; reject(t,bi);
    bi=image; bi.width=3; reject(t,bi);
    bi=image; bi.height=0; reject(t,bi);
    bad=t; bad.format=200; bi=image; bi.format=8; reject(bad,bi);
    bad=t; bad.format=100; bi=image; bi.format=100; reject(bad,bi);
    for(uint32_t bytes : {1u,2u,3u,4u,6u,8u,12u,16u}) {
        std::memset(guest,0xcc,sizeof guest); writes.clear(); copyBytes=bytes;
        auto a=t; auto b=image; a.format=b.format=bytes;
        readback_linear_texture(1,a,b,writes); assert(writes.size()==2 && b.layout==5);
        for(const auto& w:writes) std::memcpy(w.to,w.from,w.size);
        assert(std::memcmp(guest,pixels,2*bytes)==0 && std::memcmp(guest+48,pixels+2*bytes,2*bytes)==0);
        for(unsigned i=2*bytes;i<48;i++) assert(guest[i]==0xcc);
        for(unsigned i=48+2*bytes;i<sizeof guest;i++) assert(guest[i]==0xcc);
    }
    std::cout << "PASS: actual readback recorder, packed rows, pitch padding, bounds, format and subresource guards\n";
}
'''
temporary = tempfile.TemporaryDirectory(prefix='sp2-readback-')
temp = Path(temporary.name)
cpp = temp / 'test.cpp'
exe = temp / 'test'
cpp.write_text(prefix + body + tests)
subprocess.run(['g++', '-std=c++20', '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(cpp), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True)
