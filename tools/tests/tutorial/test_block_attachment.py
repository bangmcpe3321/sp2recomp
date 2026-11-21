"""Exercise the actual attachment helpers with checked format-capability stubs."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1])
text = source.read_text()
body = text[text.index('VkFormat attachment_format('):text.index('VkImageViewType view_type(')]
prefix = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
using VkFormat = uint32_t;
constexpr VkFormat VK_FORMAT_UNDEFINED=0, BC1=100, BC3=101, RGBA32_UINT=16, RG32_UINT=8, RGBA8=4, DEPTH=200;
constexpr uint32_t VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT=1;
struct VkFormatProperties { uint32_t optimalTilingFeatures=0; };
struct VkExtent2D { uint32_t width,height; };
struct GpuImage { bool block_renderable=true; VkFormat format=BC3; uint32_t nvn_format=BC3,width=256,height=256; };
static bool support=true;
static unsigned checks=0, fallbacks=0;
VkFormat vk_format(uint32_t f) { return f; }
bool compressed_format(VkFormat f) { return f==BC1 || f==BC3; }
uint32_t format_aspect(uint32_t f) { return f==DEPTH ? 1 : 0; }
uint32_t vk_block_bytes(VkFormat f) { return compressed_format(f) ? 0 : f==DEPTH ? 4 : f; }
void format_block(uint32_t f,uint32_t& w,uint32_t& h,uint32_t& b) {
    w=h=compressed_format(f)?4:1; b=f==BC1?8:f==BC3?16:vk_block_bytes(f);
}
int vk_physical() { return 42; }
void p_vkGetPhysicalDeviceFormatProperties(int physical,VkFormat f,VkFormatProperties* p) {
    assert(physical==42 && !compressed_format(f)); checks++;
    p->optimalTilingFeatures=support?VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT:0;
}
VkFormat view_format(const GpuImage& img,uint32_t) { fallbacks++; return img.format; }
'''
tests = r'''
int main() {
    GpuImage img;
    assert(attachment_format(img,RGBA32_UINT)==RGBA32_UINT && checks==1 && fallbacks==0);
    assert(attachment_format(img,RG32_UINT)==BC3 && checks==1);
    assert(attachment_format(img,BC1)==BC3 && checks==1);
    assert(attachment_format(img,VK_FORMAT_UNDEFINED)==BC3 && checks==1);
    assert(attachment_format(img,DEPTH)==BC3 && checks==1);
    support=false;
    assert(attachment_format(img,RGBA32_UINT)==BC3 && checks==2);
    support=true; img.block_renderable=false;
    assert(attachment_format(img,RGBA32_UINT)==BC3 && checks==2);
    img.block_renderable=true; img.format=img.nvn_format=BC1;
    assert(attachment_format(img,RG32_UINT)==RG32_UINT && checks==3);
    assert(attachment_format(img,RGBA32_UINT)==BC1 && checks==3);
    img.format=img.nvn_format=BC3;
    for (uint32_t level=0;level<12;level++) {
        auto a=attachment_extent(img,level,RGBA32_UINT);
        uint32_t expected=std::max(1u,(std::max(1u,256u>>level)+3)/4);
        assert(a.width==expected && a.height==expected);
    }
    auto a=attachment_extent(img,0,BC3); assert(a.width==256 && a.height==256);
    img.width=257; img.height=9;
    a=attachment_extent(img,0,RGBA32_UINT); assert(a.width==65 && a.height==3);
    a=attachment_extent(img,40,RGBA32_UINT); assert(a.width==1 && a.height==1);
    img.block_renderable=false; img.format=img.nvn_format=RGBA8;
    a=attachment_extent(img,0,RGBA8); assert(a.width==257 && a.height==9);
    a=attachment_extent(img,1,RGBA8); assert(a.width==128 && a.height==4);
    std::cout << "PASS: block format capabilities, exact byte compatibility, fallback and mip extents\n";
}
'''
temporary = tempfile.TemporaryDirectory(prefix='sp2-block-attachment-')
folder = Path(temporary.name)
cpp = folder / 'test.cpp'
exe = folder / 'test'
cpp.write_text(prefix + body + tests)
subprocess.run(['g++', '-std=c++20', '-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(cpp), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True)
