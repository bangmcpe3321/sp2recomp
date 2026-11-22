"""Exercise the actual sampler HLE, including AGL's opaque 0x60-byte copies."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

path = Path(sys.argv[1]).resolve()
source = path.read_text()
if '--baseline' in sys.argv:
    source = subprocess.check_output(
        ['git', '-C', str(path.parents[3]), 'show', 'HEAD:runtime/src/nvn/nvn_sampler_objects.cpp'], text=True)
info = re.search(r'struct SamplerInfo\s*\{.*?\n\};',
                 (path.parent / 'nvn.h').read_text(), re.S).group()
source = '\n'.join(line for line in source.splitlines() if not line.startswith('#include'))
prefix = r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
struct CPU { uint64_t x[31]{}; struct { float f32[4]{}; } v[32]; };
template<class T> T ld(uint64_t p) { T v; std::memcpy(&v,(void*)p,sizeof v); return v; }
template<class T> void st(uint64_t p,T v) { std::memcpy((void*)p,&v,sizeof v); }
#define NX_HLE(name, fn)
namespace nx::nvn {
'''+info+r'''
struct Object { virtual ~Object() = default; };
struct DescriptorPool : Object { std::map<uint32_t,SamplerInfo> samplers; };
struct SamplerSlot { bool has=false; SamplerInfo info; };
std::map<uint64_t,std::unique_ptr<Object>> objects;
std::vector<SamplerSlot> history;
template<class T> T* get(uint64_t p) {
    auto i=objects.find(p); return i==objects.end()?nullptr:dynamic_cast<T*>(i->second.get());
}
template<class T> T& make(uint64_t p) {
    auto o=std::make_unique<T>(); auto* r=o.get(); objects[p]=std::move(o); return *r;
}
void destroy(uint64_t p) { objects.erase(p); }
std::mutex& objects_lock() { static std::mutex m; return m; }
void note_sampler_change(uint64_t,uint32_t,const SamplerSlot& old) { history.push_back(old); }
std::vector<std::string> log_formats;
template<class... T> void log(const char* format,T...) { log_formats.emplace_back(format); }
uint64_t scratch(CPU&,uint64_t) { alignas(16) static unsigned char bytes[32]; return (uint64_t)bytes; }
uint64_t real_proc(CPU&,const char* name) { return (uint64_t)name; }
float guest_call_f(CPU&,uint64_t proc,std::initializer_list<uint64_t> args) {
    auto& s=*(SamplerInfo*)*args.begin(); std::string name((char*)proc);
    if(name=="nvnSamplerBuilderGetLodBias") return s.lod_bias;
    assert(name=="nvnSamplerBuilderGetMaxAnisotropy"); return s.max_anisotropy;
}
uint64_t driver(CPU&,const char* proc,std::initializer_list<uint64_t> args) {
    std::vector<uint64_t> a(args); auto& s=*(SamplerInfo*)a[0]; std::string n(proc);
    if(n=="nvnSamplerBuilderGetMinMagFilter") { st(a[1],s.min_filter);st(a[2],s.mag_filter); }
    else if(n=="nvnSamplerBuilderGetWrapMode") for(int k=0;k<3;k++) st(a[k+1],s.wrap[k]);
    else if(n=="nvnSamplerBuilderGetLodClamp") { st(a[1],s.lod_min);st(a[2],s.lod_max); }
    else if(n=="nvnSamplerBuilderGetCompare") { st(a[1],s.compare_mode);st(a[2],s.compare_func); }
    else if(n=="nvnSamplerBuilderGetBorderColor") std::memcpy((void*)a[1],s.border,16);
    else { assert(n=="nvnSamplerBuilderGetReductionFilter"); return s.reduction; }
    return 0;
}
}
'''
tests = r'''
using namespace nx::nvn;
struct Opaque {
    std::array<unsigned char,16> before;
    std::array<unsigned char,96> bytes{};
    std::array<unsigned char,16> after;
    Opaque() { before.fill(0xa5);after.fill(0x5a); }
    uint64_t ptr() { return (uint64_t)bytes.data(); }
    void guards() {
        for(auto v:before) assert(v==0xa5);
        for(auto v:after) assert(v==0x5a);
    }
};
void initialize(Opaque& o,SamplerInfo& s) {
    CPU c; c.x[0]=o.ptr();c.x[1]=(uint64_t)&s;SamplerInitialize(c);assert(c.x[0]==1);o.guards();
}
void reg(uint64_t pool,uint32_t slot,Opaque& o) {
    CPU c;c.x[0]=pool;c.x[1]=slot;c.x[2]=o.ptr();RegisterSampler(c);
}
int main(int argc,char**) {
    const bool verbose=argc==1;
    if(verbose) setenv("NX_NVN_STATES","1",1); else unsetenv("NX_NVN_STATES");
    SamplerInfo linear;linear.min_filter=5;linear.mag_filter=1;
    linear.wrap[0]=7;linear.wrap[1]=1;linear.wrap[2]=2;
    linear.lod_min=1;linear.lod_max=14;linear.lod_bias=-.25f;linear.max_anisotropy=8;
    linear.compare_mode=1;linear.compare_func=3;linear.reduction=1;
    for(int i=0;i<4;i++) linear.border[i]=(i+1)*.25f;
    Opaque original,copy,equivalent,point,unknown;
    initialize(original,linear);initialize(equivalent,linear);
    std::memcpy(copy.bytes.data(),original.bytes.data(),96);copy.guards();
    uint64_t pool_id=0x1234;auto& pool=make<DescriptorPool>(pool_id);
    reg(pool_id,258,copy);
    assert(pool.samplers.contains(258)); // The pre-fix HLE drops this copied sampler.
    assert(std::memcmp(&pool.samplers.at(258),&linear,sizeof linear)==0);
    assert(std::memcmp(original.bytes.data(),equivalent.bytes.data(),96)==0);
    for(size_t i=72;i<96;i++) assert(original.bytes[i]==0);
    size_t changes=history.size();reg(pool_id,258,copy);assert(history.size()==changes);
    uint32_t u[3]{};float f[4]{};CPU c;
    c.x[0]=copy.ptr();c.x[1]=(uint64_t)&u[0];c.x[2]=(uint64_t)&u[1];
    GetMinMagFilter(c);assert(u[0]==5&&u[1]==1);
    c.x[3]=(uint64_t)&u[2];GetWrapMode(c);assert(u[0]==7&&u[1]==1&&u[2]==2);
    c.x[1]=(uint64_t)&f[0];c.x[2]=(uint64_t)&f[1];GetLodClamp(c);assert(f[0]==1&&f[1]==14);
    GetLodBias(c);assert(c.v[0].f32[0]==-.25f);GetMaxAnisotropy(c);assert(c.v[0].f32[0]==8);
    c.x[1]=(uint64_t)&u[0];c.x[2]=(uint64_t)&u[1];GetCompare(c);assert(u[0]==1&&u[1]==3);
    c.x[1]=(uint64_t)f;GetBorderColor(c);assert(std::memcmp(f,linear.border,16)==0);
    GetReductionFilter(c);assert(c.x[0]==1);
#if HAS_COMPARE
    c={};c.x[0]=copy.ptr();c.x[1]=equivalent.ptr();SamplerCompare(c);assert(c.x[0]==1);
#endif
    SamplerInfo nearest;initialize(point,nearest);initialize(original,nearest);
    reg(pool_id,259,original);assert(pool.samplers.at(259).min_filter==0);
    c={};c.x[0]=original.ptr();SamplerFinalize(c);
    reg(pool_id,260,copy);assert(pool.samplers.at(260).min_filter==5);
#if HAS_COMPARE
    c={};c.x[0]=copy.ptr();c.x[1]=point.ptr();SamplerCompare(c);assert(c.x[0]==0);
#endif
    reg(pool_id,258,point);assert(history.size()==changes+3);
    assert(history.back().has&&history.back().info.min_filter==5);
    c={};c.x[0]=copy.ptr();SamplerFinalize(c);
    reg(pool_id,261,copy);assert(!pool.samplers.contains(261));
    assert(pool.samplers.at(260).min_filter==5); // Registration stores a value, not an owner pointer.
    reg(pool_id,262,unknown);assert(!pool.samplers.contains(262));
    c={};c.x[0]=unknown.ptr();c.x[1]=(uint64_t)&u[0];c.x[2]=(uint64_t)&u[1];
    GetMinMagFilter(c);assert(u[0]==0&&u[1]==0);
    c={};c.x[0]=pool_id;c.x[1]=263;c.x[2]=(uint64_t)&linear;RegisterSamplerBuilder(c);
    assert(pool.samplers.at(263).min_filter==5);
    Opaque overwritten;
    initialize(overwritten,nearest);
    std::memcpy(overwritten.bytes.data(),equivalent.bytes.data(),96);
    reg(pool_id,264,overwritten);
    assert(pool.samplers.at(264).min_filter==5); // A copied value replaces an initialized destination too.
    c={};c.x[0]=overwritten.ptr();c.x[1]=(uint64_t)&u[0];c.x[2]=(uint64_t)&u[1];
    GetMinMagFilter(c);assert(u[0]==5&&u[1]==1);
    overwritten.guards();
    original.guards();copy.guards();equivalent.guards();point.guards();unknown.guards();
    const size_t before_logs=log_formats.size();
    for(int i=0;i<8192;i++) initialize(original,linear);
    const auto printed=std::count_if(log_formats.begin()+before_logs,log_formats.end(),[](const std::string& s) {
        return s.starts_with("nvn state sampler: filter");
    });
    if(verbose) assert(printed>0&&printed<70); else assert(printed==0);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-sampler-copies-') as directory:
    work = Path(directory)
    cpp = work / 'test.cpp'
    cpp.write_text(prefix + '\n#define HAS_COMPARE ' + str(int('void SamplerCompare(' in source)) +
                   '\n' + source + '\n' + tests)
    exe = work / 'test'
    subprocess.run(['g++', '-std=c++20', '-O1', '-g', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', '-pthread', str(cpp), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
    subprocess.run([str(exe), '--quiet'], check=True)
print('PASS: sampler copies, bounds, getters, filters, comparison, history, lifetimes and bounded/disabled tracing')
