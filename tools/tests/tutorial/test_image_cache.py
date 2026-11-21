#!/usr/bin/env python3
"""Exercise the actual image retirement policy without a GPU or game assets."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).read_text()
start = source.index('static bool cached_image_expired(')
end = source.index('GpuImage* image_of(', start)
helper = source[start:end]
test = r'''
#include <cassert>
#include <cstdint>
#include <limits>
struct GpuImage { bool rendered; uint64_t rendered_at; };
'''+helper+r'''
int main() {
    GpuImage cpu{false, 0}, current{true, 25}, obsolete{true, 24}, unknown{true, 0};
    for (uint64_t frame : {uint64_t(0), uint64_t(99), uint64_t(100), uint64_t(101), uint64_t(102)}) {
        assert(!cached_image_expired(cpu, 100, frame, 25));
        assert(!cached_image_expired(obsolete, 100, frame, 25));
    }
    assert(cached_image_expired(cpu, 100, 103, 0));
    assert(cached_image_expired(obsolete, 100, 103, 25));
    assert(!cached_image_expired(current, 100, 103, 25));
    assert(!cached_image_expired(current, 100, 1000000, 25));
    assert(!cached_image_expired(unknown, 100, 1000000, 25));
    assert(!cached_image_expired(current, 100, 1000000, 0));
    assert(!cached_image_expired(current, 100, 1000000, 24));
    assert(cached_image_expired(current, 100, 1000000, 26));
    assert(!cached_image_expired(cpu, UINT64_MAX, 0, 25));
}
'''
# Range-for over a braced list needs its own standard header.
test = '#include <initializer_list>\n' + test
with tempfile.TemporaryDirectory(prefix='sp2-image-cache-') as directory:
    cpp = Path(directory) / 'test.cpp'
    exe = Path(directory) / 'test'
    cpp.write_text(test)
    subprocess.run(['g++', '-std=c++20', '-O1', '-g', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(cpp), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS: idle GPU contents retained; only reloadable or superseded images expire')
