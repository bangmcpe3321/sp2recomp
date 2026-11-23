"""Check original AArch64 branch semantics and reversible source installation."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]).resolve().parents[2]
tools = Path(__file__).resolve().parents[2]
helper = tools / 'patches/patch-gameplay-options.py'
spec = importlib.util.spec_from_file_location('gameplay_patch', helper)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

scene = function((root / 'gen/main/code_006.cpp').read_text(), 'void main_00051BA4(')
gpu_line = next(line for line in (root / 'gen/main/code_348.cpp').read_text().splitlines() if 'PATCH-SP2-DYNAMIC-RESOLUTION' in line)
prefix = r'''
#include <cassert>
#include <cstdint>
#include <cstdarg>
#include <cstring>
#include <map>
#include <cstdlib>
#define NX_RESTRICT
constexpr uint64_t NXB=0x7100000000ull;
unsigned mode=3, intervals=0, stress_calls=0;
namespace nx {
struct CPU { uint64_t x[32]{};bool zf=false; };
std::map<uint64_t,uint64_t> memory;
template<class T>T ld(uint64_t a) { return T(memory[a]); }
template<class T>void st(uint64_t a,T v) {memory[a]=uint64_t(v);}
void subs32(CPU& c,uint32_t a,uint32_t b){c.zf=a==b;}
void call(CPU&,uint64_t){}
}
#include "sp2_gameplay_options.h"
void main_0007FA68(nx::CPU& c){c.x[0]=mode;}
void main_00E67D58(nx::CPU& c){assert(c.x[1]==2);++intervals;}
void main_01405D84(nx::CPU&){++stress_calls;}
'''
import re
callees = set(re.findall(r'(main_[0-9A-F]+)\(c\)', scene)) - {'main_0007FA68', 'main_00E67D58'}
prefix += '\n'.join(f'void {name}(nx::CPU&){{}}' for name in sorted(callees))
test = r'''
void stress(nx::CPU& c) {
PATCH_GPU_LINE
}
int main(int argc,char** argv) {
 assert(argc==3);bool plaza=std::atoi(argv[1]),disable=std::atoi(argv[2]);
 // Reference: 0x54000181 is B.NE +0x30; 0x1400000c always branches +0x30.
 // Test the entire generated sceneEnter, including its interval setter block.
 for(mode=0;mode<8;++mode) {
  nx::CPU c;c.x[0]=0x100000;c.x[31]=0x800000;
  unsigned before=intervals;main_00051BA4(c);
  assert(intervals-before==unsigned(!plaza && mode==3));
  assert(c.x[31]==0x800000); // Patched branch still follows the normal epilogue.
 }
 // AArch64 NOP changes neither LR nor registers and invokes no stress callback.
 nx::CPU c;c.x[30]=0x123456;stress(c);
 assert(stress_calls==unsigned(!disable));
 assert(c.x[30]==(disable ? 0x123456 : NXB+0x1021fb0));
 // Startup options are latched; mid-session environment edits cannot mix modes.
 setenv("NX_PLAZA_60FPS",plaza?"0":"1",1);
 setenv("NX_DISABLE_DYNAMIC_RESOLUTION",disable?"0":"1",1);
 assert(nx::sp2::plaza_60fps_enabled()==plaza);
 assert(nx::sp2::dynamic_resolution_disabled()==disable);
}
'''.replace('PATCH_GPU_LINE', gpu_line)

with tempfile.TemporaryDirectory(prefix='sp2-gameplay-options-') as tmp:
    directory = Path(tmp)
    (directory / 'nx').mkdir()
    (directory / 'nx/runtime.h').write_text('#pragma once\nnamespace nx { inline void log(const char*,...){} }\n')
    cpp, exe = directory / 'test.cpp', directory / 'test'
    cpp.write_text(prefix + '\n' + scene + '\n' + test)
    subprocess.run(['g++', '-std=c++20', '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I', str(directory), '-I', str(root / 'runtime/src'), str(cpp), '-o', str(exe)], check=True)
    for plaza, disable in [(None,None),('0','0'),('1','0'),('0','1'),('1','1'),('garbage','true')]:
        env = os.environ.copy()
        for name, value in [('NX_PLAZA_60FPS',plaza),('NX_DISABLE_DYNAMIC_RESOLUTION',disable)]:
            env.pop(name, None)
            if value is not None:
                env[name] = value
        subprocess.run([str(exe), str(int(plaza=='1')), str(int(disable=='1'))], env=env, check=True)

    fixture = directory / 'runtime-fixture'
    (fixture / 'runtime/src').mkdir(parents=True)
    (fixture / 'private/analysis').mkdir(parents=True)
    (fixture / 'gen/main').mkdir(parents=True)
    originals = {}
    image = bytearray(0x1021FB0)
    for relative, address, instruction, old, new in patch.SITES:
        data = (root / relative).read_bytes().replace(new, old).replace(patch.INCLUDE, b'')
        originals[relative] = data
        (fixture / relative).write_bytes(data)
        image[address:address+4] = instruction
    image_path = fixture / 'private/analysis/main.bin'
    image_path.write_bytes(image)
    nso = directory / 'main.nso'
    nso.write_bytes(b'NSO0' + bytes(0x3c) + patch.BUILD_ID)
    base = [sys.executable,str(helper),'--root',str(fixture),'--nso',str(nso)]
    def run(*args, success=True):
        result = subprocess.run([*base,*args],capture_output=True,text=True)
        assert (result.returncode==0)==success, result.stdout+result.stderr
    run('--check')
    assert all((fixture/p).read_bytes()==data for p,data in originals.items())
    run();run();run('--check');run('--restore','--check');run('--restore');run('--restore')
    assert all((fixture/p).read_bytes()==data for p,data in originals.items())
    assert not (fixture / 'runtime/src/sp2_gameplay_options.h').exists()
    nso.write_bytes(b'NSO0'+bytes(0x5c))
    run(success=False)
    nso.write_bytes(b'NSO0'+bytes(0x3c)+patch.BUILD_ID)
    image[0x1021FAC] ^= 1
    image_path.write_bytes(image)
    run(success=False)
    image[0x1021FAC] ^= 1
    image_path.write_bytes(image)
    path = fixture / patch.SITES[1][0]
    path.write_bytes(path.read_bytes().replace(patch.SITES[1][3],b'changed anchor\n'))
    run(success=False)
    assert (fixture / patch.SITES[0][0]).read_bytes()==originals[patch.SITES[0][0]]
    assert not (fixture / 'runtime/src/sp2_gameplay_options.h').exists()
print('PASS original branch/interval behavior, independent options, NOP registers, build/anchor rejection, idempotence and byte-exact rollback')
