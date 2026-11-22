"""Exercise the actual copy recorder with reused guest descriptors (Linux/WSL)."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--baseline-file', type=Path)
args = parser.parse_args()
path = args.source.resolve()
source = (args.baseline_file or path).read_text()


def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


copy_info = re.search(r'struct CopyInfo\s*\{.*?\n\};', source, re.S).group()
view_info = re.search(r'struct ViewInfo\s*\{.*?\n\};',
                      (path.parent / 'nvn.h').read_text(), re.S).group()
recorder = function(source, 'void CopyTextureToTexture(CPU& c)')
prefix = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <map>
#include <memory>
#include <utility>
#include <vector>
struct CPU { uint64_t x[31]{}; };
template<class T> T ld(uint64_t p) { T v; std::memcpy(&v,(void*)p,sizeof v); return v; }
namespace nx::nvn {
''' + view_info + r'''
struct Texture { uint64_t memory=0; uint32_t format=0,width=0,height=0; };
std::map<uint64_t,Texture> objects;
struct Descriptor { uint64_t named=0; Texture own; };
std::map<uint64_t,Descriptor> copies;
uint64_t next_key=0xd000000000000000ull;
struct RecordedTexture {
    uint64_t key=0;
    ~RecordedTexture() { objects.erase(key); }
};
std::shared_ptr<RecordedTexture> record_texture_descriptor(uint64_t raw) {
    auto it=copies.find(raw);
    if(it==copies.end()) return {};
    auto owner=std::make_shared<RecordedTexture>();
    owner->key=++next_key; objects[owner->key]=it->second.own; return owner;
}
uint64_t texture_descriptor_ref(uint64_t raw) {
    auto it=copies.find(raw); return it==copies.end()?0:it->second.named;
}
bool atlas_xfer_trace_on(uint64_t) { return false; }
void atlas_xfer_trace_note(const char*,uint64_t,uint64_t,uint32_t,uint32_t) {}
ViewInfo read_view(CPU&,uint64_t raw) { return raw?*(const ViewInfo*)raw:ViewInfo{}; }
struct Cmd { enum Op { CopyTextureToTexture }; Op op; uint64_t a[9]{}; };
struct List {
    Cmd cmd{Cmd::CopyTextureToTexture};
    std::vector<uint8_t> blob;
    std::vector<std::shared_ptr<RecordedTexture>> textures;
};
std::map<uint64_t,std::shared_ptr<List>> lists;
void record(uint64_t buffer,Cmd cmd,const void* blob,size_t size,
            std::vector<std::shared_ptr<RecordedTexture>> textures={}) {
    auto list=std::make_shared<List>(); list->cmd=cmd;
    list->blob.assign((const uint8_t*)blob,(const uint8_t*)blob+size);
    list->textures=std::move(textures); lists[buffer]=std::move(list);
}
'''
tests = r'''
}
using namespace nx::nvn;
bool same(const Texture& a,const Texture& b) {
    return a.memory==b.memory&&a.format==b.format&&a.width==b.width&&a.height==b.height;
}
void exercise(bool source_copy,bool destination_copy) {
    const Texture source{0xa000,37,512,256},destination{0xb000,37,512,256};
    objects[101]=source;objects[102]=destination;
    // The named object already points at another storage when its older copy is recorded.
    copies[201]={101,source};copies[202]={102,destination};
    if(source_copy) objects[101]={0xc000,63,1920,1080};
    if(destination_copy) objects[102]={0xd000,52,960,540};
    ViewInfo sv{3,1,2,1,0x05040302,37},dv{4,1,5,1,0x05040302,37};
    const ViewInfo expected_sv=sv,expected_dv=dv;
    std::array<int32_t,6> sr{4,8,2,64,32,1},dr{12,16,5,32,16,1};
    const auto expected_sr=sr,expected_dr=dr;
    CPU c;c.x[0]=301;c.x[1]=source_copy?201:101;c.x[2]=(uint64_t)&sv;
    c.x[3]=(uint64_t)sr.data();c.x[4]=destination_copy?202:102;
    c.x[5]=(uint64_t)&dv;c.x[6]=(uint64_t)dr.data();c.x[7]=1|4|8|16;
    CopyTextureToTexture(c);
    auto list=lists.at(301);
    assert(list->cmd.op==Cmd::CopyTextureToTexture);
    CopyInfo info;assert(list->blob.size()==sizeof info);std::memcpy(&info,list->blob.data(),sizeof info);
    // Both view records, regions and flags are values, independent of the guest's scratch area.
    sv={};dv={};sr.fill(-1);dr.fill(-1);
    assert(std::memcmp(&info.src_view,&expected_sv,sizeof sv)==0);
    assert(std::memcmp(&info.dst_view,&expected_dv,sizeof dv)==0);
    assert(std::memcmp(info.src,expected_sr.data(),sizeof info.src)==0);
    assert(std::memcmp(info.dst,expected_dr.data(),sizeof info.dst)==0);
    assert(info.flags==29);
    if(source_copy) { copies[201]={102,{0xe000,1,8,8}};objects.erase(101); }
    if(destination_copy) { copies.erase(202);objects[102]={0xf000,2,16,16}; }
    // Replay resolves host objects; a raw copied descriptor has no registered Texture.
    assert(objects.contains(list->cmd.a[0])&&objects.contains(list->cmd.a[1]));
    assert(same(objects.at(list->cmd.a[0]),source));
    assert(same(objects.at(list->cmd.a[1]),destination));
    if(!source_copy) assert(list->cmd.a[0]==101);
    if(!destination_copy) assert(list->cmd.a[1]==102);
    const auto sk=list->cmd.a[0],dk=list->cmd.a[1];
    // Retained/reused command lists keep the owners after the command buffer is reset.
    lists.erase(301);assert(objects.contains(sk)&&objects.contains(dk));
    list.reset();
    assert(objects.contains(sk)==!source_copy);
    assert(objects.contains(dk)==!destination_copy);
    objects.clear();copies.clear();
}
int main() {
    exercise(true,true);exercise(true,false);exercise(false,true);exercise(false,false);
    CPU c;c.x[0]=302;CopyTextureToTexture(c);
    const auto list=lists.at(302);assert(list->cmd.a[0]==0&&list->cmd.a[1]==0);
    assert(list->textures.empty());
    CopyInfo info;std::memcpy(&info,list->blob.data(),sizeof info);
    assert(info.flags==0);for(int k=0;k<6;k++) assert(info.src[k]==0&&info.dst[k]==0);
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-texture-copies-') as directory:
    work = Path(directory)
    cpp = work / 'test.cpp'
    cpp.write_text(prefix + copy_info + '\n' + recorder + '\n' + tests)
    exe = work / 'test'
    subprocess.run(['g++', '-std=c++20', '-O1', '-g', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(cpp), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS: texture copy storage identities, scratch reuse, list lifetimes, views, regions and flags')
