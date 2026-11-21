"""Check actual batch selection against InstanceIndex/BaseInstance shader semantics."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1])
text = source.read_text()
begin = text.index('uint32_t instance_chunk_size(')
body = text[begin:text.index('\n}\n', begin) + 3]
prefix = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>
struct ShaderInfo { struct { std::vector<uint32_t> builtins_in; } refl; };
'''
tests = r'''
int main() {
    ShaderInfo raw, relative;
    raw.refl.builtins_in = {42, 43};
    relative.refl.builtins_in = {43, 4425};
    for (uint32_t count : {1u, 4096u, 4097u, 98304u}) {
        for (uint32_t limit : {0u, 1u, 4096u, 100000u}) {
            const uint32_t size = instance_chunk_size(raw, count, limit);
            assert(size == (limit && limit < count ? limit : count));
            assert(instance_chunk_size(relative, count, limit) == count);
            for (const ShaderInfo* shader : {&raw, &relative}) {
                const uint32_t step = instance_chunk_size(*shader, count, limit);
                uint32_t seen = 0;
                for (uint32_t at = 0; at < count; at += step) {
                    const uint32_t first = 23 + at;
                    for (uint32_t i = 0; i < std::min(step, count-at); ++i) {
                        const uint32_t index = first + i;
                        const uint32_t value = shader == &relative ? index-first : index-23;
                        assert(value == seen++);
                    }
                }
                assert(seen == count);
            }
        }
    }
    relative.refl.builtins_in = {4425};
    assert(instance_chunk_size(relative, 0xffffffffu, 4096) == 0xffffffffu);
    std::cout << "PASS: split batching preserves instance IDs; BaseInstance shaders remain one draw\n";
}
'''
temporary = tempfile.TemporaryDirectory(prefix='sp2-instance-chunk-')
folder = Path(temporary.name)
cpp, exe = folder / 'test.cpp', folder / 'test'
cpp.write_text(prefix + body + tests)
subprocess.run(['g++', '-std=c++20', '-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(cpp), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True)
