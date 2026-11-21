"""Exercise the actual point proof with an authored fixture and, if present, a local cached VS."""
from pathlib import Path
import subprocess
import sys
import struct
import tempfile

root = Path(sys.argv[1])
text = (root / 'runtime/src/nvn/nvn_spirv_patch.cpp').read_text()
body = text[text.index('bool constant_unit_point_module('):text.index('bool constant_unit_point(const ShaderInfo*')]
draw = (root / 'runtime/src/nvn/nvn_draw.cpp').read_text()
start = draw.index('void align_unit_point_viewport(')
align = draw[start:draw.index('\n}\n', start)+3]
prefix = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <vector>
struct VkViewport { float x,y,width,height,minDepth,maxDepth; };
'''
tests = r'''
int main(int argc, char** argv) {
    assert(argc==2);
    std::ifstream file(argv[1], std::ios::binary|std::ios::ate);
    assert(file);
    size_t bytes = file.tellg(); file.seekg(0);
    std::vector<uint32_t> original(bytes/4);
    file.read(reinterpret_cast<char*>(original.data()),bytes);
    assert(file && constant_unit_point_module(original));
    for (uint32_t bits : {0x3e800000u,0x40000000u}) {
        auto module=original;
        for (size_t at=5;at<module.size();at+=module[at]>>16)
            if ((module[at]&0xffff)==43 && module[at]>>16==4 && module[at+3]==0x3f800000)
                module[at+3]=bits;
        assert(!constant_unit_point_module(module));
    }
    auto add_before_return = [&](std::vector<uint32_t> extra) {
        auto module=original;
        for (size_t at=5;at<module.size();at+=module[at]>>16) {
            if ((module[at]&0xffff)==253) {
                module.insert(module.begin()+at,extra.begin(),extra.end());
                return module;
            }
        }
        assert(false); return module;
    };
    for (auto extra : {std::vector<uint32_t>{(2u<<16)|249,1},  // branch
                       std::vector<uint32_t>{(4u<<16)|57,1,2,3},  // call
                       std::vector<uint32_t>{(4u<<16)|83,1,2,3}}) // pointer alias: no proof
        assert(!constant_unit_point_module(add_before_return(extra)));
    unsigned positive_removals=0;
    for (size_t at=5;at<original.size();at+=original[at]>>16) {
        if ((original[at]&0xffff)!=62) continue;
        auto module=original;
        module.erase(module.begin()+at,module.begin()+at+(module[at]>>16));
        if (!constant_unit_point_module(module)) positive_removals++;
    }
    assert(positive_removals>=1); // PointSize is required; redundant constant Position writes are allowed
    auto missing_position=original;
    bool kept_first=false;
    for (size_t at=5;at<missing_position.size();) {
        size_t count=missing_position[at]>>16;
        if ((missing_position[at]&0xffff)==62) {
            if (kept_first) {
                missing_position.erase(missing_position.begin()+at,missing_position.begin()+at+count);
                continue;
            }
            kept_first=true; // fixtures write PointSize before Position
        }
        at+=count;
    }
    assert(!constant_unit_point_module(missing_position));
    assert(!constant_unit_point_module({}));
    auto malformed=original; malformed[3]=0; assert(!constant_unit_point_module(malformed));
    malformed=original; malformed[5]=0; assert(!constant_unit_point_module(malformed));
    malformed=original; malformed.back()=0xffff0000; assert(!constant_unit_point_module(malformed));
    for (float x : {-9.25f, -0.1f, 0.0f, 0.7f, 11.5f})
        for (float width : {1.0f,7.0f,8.0f,256.0f}) {
            VkViewport vp{x,9.0f,width,-width,0.2f,0.8f};
            float px=std::floor(vp.x+vp.width*0.5f)+0.5f;
            float py=std::floor(vp.y+vp.height*0.5f)+0.5f;
            align_unit_point_viewport(vp);
            assert(std::fabs(vp.x+vp.width*0.5f-px)<0.00001f);
            assert(std::fabs(vp.y+vp.height*0.5f-py)<0.00001f);
            assert(vp.width==width && vp.height==-width && vp.minDepth==0.2f && vp.maxDepth==0.8f);
        }
    std::cout << "PASS: constant-point proof, fail-closed mutations and exact pixel-center alignment\n";
}
'''
temporary = tempfile.TemporaryDirectory(prefix='sp2-unit-point-')
folder = Path(temporary.name)
words = [0x07230203, 0x00010000, 0, 32, 0]
def op(code, *operands):
    words.extend([((len(operands) + 1) << 16) | code, *operands])

# Authored minimal vertex shader: Position=(0,0,0,1), PointSize=1.
op(17, 1)  # Shader capability
op(14, 0, 1)  # Logical, GLSL450
op(15, 0, 20, 0x6e69616d, 0, 10, 11)  # Vertex entry point "main"
op(71, 10, 11, 0)  # BuiltIn Position
op(71, 11, 11, 1)  # BuiltIn PointSize
op(19, 1)  # void
op(33, 2, 1)  # function type
op(22, 3, 32)  # float
op(23, 4, 3, 4)  # vec4
op(32, 5, 3, 4)  # Output vec4 pointer
op(32, 6, 3, 3)  # Output float pointer
op(43, 3, 7, 0)
op(43, 3, 8, 0x3f800000)
op(44, 4, 9, 7, 7, 7, 8)
op(59, 5, 10, 3)
op(59, 6, 11, 3)
op(54, 1, 20, 0, 2)
op(248, 21)
op(62, 11, 8)
op(62, 10, 9)
op(253)
op(56)
shader = folder / 'constant-point.spv'
shader.write_bytes(struct.pack('<' + 'I' * len(words), *words))
cpp, exe = folder/'test.cpp', folder/'test'
cpp.write_text(prefix+body+align+tests)
subprocess.run(['g++','-std=c++20','-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
subprocess.run([str(exe),str(shader)],check=True)
cached = root / 'private/spirv/791a40466e6f19d5.spv'
if cached.is_file():
    subprocess.run([str(exe), str(cached)], check=True)
