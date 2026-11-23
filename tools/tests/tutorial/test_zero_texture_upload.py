"""Run the actual upload decision path against checked image-recording stubs.

Zero texels are valid texture contents, including black lighting maps and empty
coverage masks. Content heuristics must not replace their channels with white.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile


def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


source = Path(sys.argv[1]).resolve()
pipeline = source.read_text()
upload = (source.parent / 'nvn_upload.cpp').read_text()
parts = []
if 'void fill_image_opaque(' in upload:
    parts.append(function(upload, 'void fill_image_opaque('))
parts.append(function(pipeline, 'GpuImage* ensure_contents('))

prefix = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>
#include <string>
#include <vector>
using VkCommandBuffer = int;
constexpr int VK_IMAGE_ASPECT_COLOR_BIT=1, VK_IMAGE_LAYOUT_UNDEFINED=0;
constexpr int VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL=1, VK_IMAGE_LAYOUT_GENERAL=2;
struct VkImageSubresourceRange { uint32_t aspect,baseMip,levels,baseLayer,layers; };
union VkClearColorValue { float float32[4]; uint32_t uint32[4]; };
namespace nx { std::atomic<uint64_t> g_frame{1}; }
struct GpuImage {
    bool uploaded=false,rendered=false,texels=false,content=false;
    uint32_t width=4,height=4,levels=1,layers=1,aspect=1,format=0x25;
    int image=7,layout=0;
    std::vector<uint8_t> pixels;
};
struct Texture {
    std::atomic<bool> dirty{false},has_writes{false};
    std::atomic<uint64_t> dirty_lo{UINT64_MAX},dirty_hi{0};
    uint64_t memory=0,storage_size=0;
    uint32_t flags=0,format=0x25;
};
Texture* active_texture=nullptr;
GpuImage* active_image=nullptr;
template<class T> T* get(uint64_t h) { return h ? active_texture : nullptr; }
GpuImage* image_of(uint64_t) { return active_image; }
void log(const char*,...) {}
bool compressed_format(uint32_t format) { return format==0x46; }
void transition(int,GpuImage& image,int layout) { image.layout=layout; }
uint64_t upload_lo=0,upload_hi=0;
unsigned uploads=0,clears=0,texel_batches=0;
void p_vkCmdClearColorImage(int,int image,int layout,const VkClearColorValue* value,
                           int count,const VkImageSubresourceRange* range) {
    assert(active_image && image==7 && layout==1 && count==1);
    assert(range->levels==active_image->levels && range->layers==active_image->layers);
    ++clears;
    auto& pixels=active_image->pixels;
    if(active_image->format==0x2e) {
        assert(pixels.size()%16==0);
        for(size_t i=0;i<pixels.size();i+=16) std::memcpy(pixels.data()+i,value->float32,16);
    } else {
        for(size_t i=0;i<pixels.size();i++) pixels[i]=uint8_t(value->float32[i%4]*255);
    }
}
void clear_image(int cb,GpuImage& image,bool magenta=false) {
    VkClearColorValue value{};
    if(magenta) value.float32[0]=value.float32[2]=value.float32[3]=1;
    VkImageSubresourceRange range{image.aspect,0,image.levels,0,image.layers};
    transition(cb,image,1);p_vkCmdClearColorImage(cb,image.image,1,&value,1,&range);
}
void upload_texture(int,Texture& texture,GpuImage& image,uint64_t lo,uint64_t hi) {
    assert(texture.memory && texture.storage_size==image.pixels.size());
    ++uploads;upload_lo=lo;upload_hi=hi;
    const auto end=std::min<uint64_t>(hi,texture.storage_size);
    assert(lo<=end);
    std::memcpy(image.pixels.data()+lo,reinterpret_cast<const uint8_t*>(texture.memory)+lo,end-lo);
    image.uploaded=true;image.layout=1;
}
void apply_texel_writes(int,Texture& texture,GpuImage& image) {
    if(texture.has_writes.exchange(false)) {
        ++texel_batches;image.pixels[0]=0x5a;image.texels=true;image.layout=1;
    }
}
'''

tests = r'''
int main() {
    // Exercise the ordinary path regardless of a developer's diagnostic shell settings.
    unsetenv("NX_EMPTY_OPAQUE_ALPHA");unsetenv("NX_FILL_TRACE");
    unsetenv("NX_TEXELS_REUPLOAD");unsetenv("NX_RT_UPLOAD");unsetenv("NX_ALIAS_MAGENTA");
    std::vector<uint8_t> guest(256,0);
    Texture texture;GpuImage image;
    texture.memory=reinterpret_cast<uint64_t>(guest.data());texture.storage_size=guest.size();
    image.pixels.assign(guest.size(),0xcc);active_texture=&texture;active_image=&image;
    // Black RGBA8 is real content: preserve every channel, including zero alpha.
    assert(ensure_contents(1,1)==&image);
    assert(uploads==1 && clears==0 && image.uploaded);
    assert(image.pixels==guest && !image.content);
    // An already uploaded black texture is not cleared or uploaded again.
    assert(ensure_contents(1,1)==&image);assert(uploads==1 && clears==0);
    // A nonzero first upload retains its byte values and existing content metadata.
    image.uploaded=false;guest[0]=0x21;guest[7]=0x42;
    ensure_contents(1,1);assert(uploads==2 && clears==0 && image.pixels==guest && image.content);
    // Dirty zero updates restore black; they cannot be mistaken for missing asset data.
    std::fill(guest.begin(),guest.end(),0);texture.dirty=true;
    texture.dirty_lo=0;texture.dirty_hi=guest.size();
    ensure_contents(1,1);assert(uploads==3 && clears==0 && image.pixels==guest);
    assert(!texture.dirty && texture.dirty_lo==UINT64_MAX && texture.dirty_hi==0);
    // Preserve a genuine dirty subrange and avoid overwriting the remainder.
    guest[9]=0x73;texture.dirty=true;texture.dirty_lo=9;texture.dirty_hi=10;
    ensure_contents(1,1);assert(uploads==4 && upload_lo==9 && upload_hi==10);
    assert(image.pixels==guest && clears==0);
    // The same zero-data contract applies to floating-point lighting textures.
    std::fill(guest.begin(),guest.end(),0);image.uploaded=false;image.format=texture.format=0x2e;
    ensure_contents(1,1);assert(uploads==5 && clears==0 && image.pixels==guest);
    // GPU output is authoritative even when the mapped guest bytes remain zero.
    image.rendered=true;image.pixels.assign(guest.size(),0x3b);texture.dirty=true;
    ensure_contents(1,1);assert(uploads==5 && clears==0 && image.pixels[0]==0x3b);
    // Pending explicit texel writes must still execute after readiness processing.
    image.rendered=false;image.uploaded=true;image.texels=true;texture.has_writes=true;
    ensure_contents(1,1);assert(uploads==5 && clears==0 && texel_batches==1 && image.pixels[0]==0x5a);
    texture.dirty=true;ensure_contents(1,1);assert(uploads==5 && clears==0);
    // Existing never-written render-target initialization still uses its normal black clear.
    image.texels=false;image.uploaded=false;texture.flags=8;
    ensure_contents(1,1);assert(uploads==5 && clears==1 && image.uploaded);
    assert(std::all_of(image.pixels.begin(),image.pixels.end(),[](uint8_t b){return b==0;}));
    active_image=nullptr;assert(!ensure_contents(1,1));assert(!ensure_contents(1,0));
}
'''

with tempfile.TemporaryDirectory(prefix='sp2-zero-upload-') as directory:
    directory = Path(directory)
    cpp, executable = directory / 'test.cpp', directory / 'test'
    cpp.write_text(prefix + '\n'.join(parts) + tests)
    subprocess.run(['g++', '-std=c++20', '-O1', '-g', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(cpp), '-o', str(executable)], check=True)
    environment = os.environ.copy()
    subprocess.run([str(executable)], env=environment, check=True)
print('PASS zero/nonzero and dirty texture uploads, GPU authority, texel writes and black target initialization')
