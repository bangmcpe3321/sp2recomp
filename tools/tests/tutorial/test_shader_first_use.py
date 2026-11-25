from pathlib import Path
import argparse,importlib.util,re,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--corpus',type=Path);p.add_argument('--sample',type=int,default=192);p.add_argument('--emit-cpp',type=Path);a=p.parse_args()
folder=a.root/'runtime/src/nvn';src=(folder/'nvn_spirv_patch.cpp').read_text()
installer=Path(__file__).resolve().parents[2]/'patches/patch-shader-first-use.py'
spec=importlib.util.spec_from_file_location('first_use_patch',installer);patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
baseline=src
for old,new in reversed(patch.CHANGES):assert baseline.count(new)==1;baseline=baseline.replace(new,old,1)
def region(s):return s[s.index('namespace {'):s.index('uint32_t unwritten_inputs(')]
oldbody,newbody=region(baseline),region(src)
formats=sorted(set(re.findall(r'VK_FORMAT_\w+',oldbody)))
code=r'''
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <mutex>
#include <new>
#include <set>
#include <string>
#include <tuple>
#include <vector>
using namespace std;
using VkFormat=uint32_t;
'''+ 'enum {'+','.join(formats)+'};\n'+r'''
VkFormat vk_vertex_format(uint32_t){return VK_FORMAT_R32_UINT;}
bool counting=false;uint64_t allocation_count=0;
void* operator new(size_t n){if(counting)allocation_count++;if(void* p=malloc(n?n:1))return p;throw bad_alloc();}
void operator delete(void* p)noexcept{free(p);}void operator delete(void* p,size_t)noexcept{free(p);}
void* operator new[](size_t n){return ::operator new(n);}void operator delete[](void* p)noexcept{free(p);}void operator delete[](void* p,size_t)noexcept{free(p);}
'''+ '\nnamespace original {\n'+oldbody+'\n}\nnamespace optimized {\n'+newbody+'\n}\n'+r'''
struct Result {bool changed;vector<uint32_t> words;uint64_t mask;};
Result transform(const vector<uint32_t>& in,bool fast,unsigned mode){
 Result r{false,{0xBAADF00D},0xDEADBEEF};uint8_t kinds[16];for(unsigned i=0;i<16;i++)kinds[i]=uint8_t(i%2+1);
 if(mode==0)r.changed=fast?optimized::clamp_uniform_indices(in,r.words,&r.mask):original::clamp_uniform_indices(in,r.words,&r.mask);
 if(mode==1)r.changed=fast?optimized::patch_int_inputs(in,kinds,r.words):original::patch_int_inputs(in,kinds,r.words);
 if(mode==2)r.changed=fast?optimized::patch_int_outputs(in,kinds,r.words):original::patch_int_outputs(in,kinds,r.words);
 if(mode==3)r.changed=fast?optimized::default_unwritten_inputs(in,0xFFFF,r.words):original::default_unwritten_inputs(in,0xFFFF,r.words);
 return r;
}
uint64_t cases=0,total_old=0,total_new=0;double ms_old=0,ms_new=0;
void compare(const vector<uint32_t>& in){
 for(unsigned mode=0;mode<4;mode++){
  Result a{},b{};
  // Alternate execution order to reduce the advantage of warm instruction/data caches.
  for(unsigned order=0;order<2;order++){
   bool fast=((cases&1)!=0)^(order!=0);
   allocation_count=0;counting=true;auto start=chrono::steady_clock::now();auto result=transform(in,fast,mode);auto stop=chrono::steady_clock::now();counting=false;
   double elapsed=chrono::duration<double,milli>(stop-start).count();
   if(fast){b=std::move(result);ms_new+=elapsed;total_new+=allocation_count;}
   else {a=std::move(result);ms_old+=elapsed;total_old+=allocation_count;}
  }
  assert(a.changed==b.changed && a.mask==b.mask && a.words==b.words);cases++;
 }
}
vector<uint32_t> authored(unsigned instructions,unsigned model){
 vector<uint32_t> v{0x07230203,0x10000,0,40000,0};
 auto op=[&](uint32_t code,initializer_list<uint32_t> args){v.push_back(uint32_t(args.size()+1)<<16|code);v.insert(v.end(),args);};
 op(11,{1,0x4C534C47,0x6474732E,0x3035342E,0}); // GLSL.std.450
 op(15,{model,30,0x6e69616d,0,10,11});op(71,{10,34,0});op(71,{10,33,3});op(71,{11,30,0});
 op(21,{2,32,0});op(22,{3,32});op(23,{4,3,4});op(32,{5,2,4});op(32,{6,1,4});op(32,{7,3,4});
 op(43,{2,20,0});op(59,{5,10,2});op(59,{model==4?6u:7u,11,model==4?1u:3u});
 op(54,{3,30,0,4});op(248,{31});op(128,{2,32,20,20});op(65,{5,33,10,20,32});
 for(unsigned i=0;i<instructions;i++)op(129,{3,100+i,20,20});
 op(61,{4,40,11});op(253,{});op(56,{});return v;
}
int main(int argc,char** argv){
 for(unsigned model:{0,4})for(unsigned size:{0,1,100,30000})compare(authored(size,model));
 auto malformed=authored(100,4);for(unsigned i:{5,20,45,80}){auto m=malformed;if(i<m.size()){m[i]=0;compare(m);}}
 for(unsigned n=0;n<5;n++)compare(vector<uint32_t>(n));
 uint64_t corpus=0;
 if(argc>1){ifstream manifest(argv[1]);string name;while(getline(manifest,name)){
  ifstream f(name,ios::binary);f.seekg(0,ios::end);auto bytes=f.tellg();assert(bytes>0 && bytes%4==0);f.seekg(0);vector<uint32_t> words(size_t(bytes)/4);f.read((char*)words.data(),bytes);assert(f);compare(words);corpus++;
 }}
 printf("PASS shader transforms: %llu exact result/mask/output cases across %llu corpus modules; heap allocations %llu -> %llu; measured transform time %.3f -> %.3f ms\n",(unsigned long long)cases,(unsigned long long)corpus,(unsigned long long)total_old,(unsigned long long)total_new,ms_old,ms_new);
 assert(total_new<total_old/3);
}
'''
if a.emit_cpp:
 a.emit_cpp.write_text(code);raise SystemExit(0)
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp);(path/'test.cpp').write_text(code)
 subprocess.run(['g++','-std=c++20','-O2','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
 manifest=path/'corpus.txt';files=[]
 if a.corpus:
  allfiles=sorted(a.corpus.glob('*.spv'));assert allfiles
  largest=sorted(allfiles,key=lambda p:p.stat().st_size,reverse=True)[:min(24,a.sample)]
  distributed=[allfiles[(i*len(allfiles))//max(1,a.sample)] for i in range(min(a.sample,len(allfiles)))]
  files=list(dict.fromkeys(largest+distributed))
 manifest.write_text('\n'.join(map(str,files)))
 subprocess.run([str(path/'test'),str(manifest)],check=True)
 # Round-trip patch test against actual full source with both local line endings.
 fixture=path/'fixture/runtime/src/nvn/nvn_spirv_patch.cpp';fixture.parent.mkdir(parents=True)
 command=[__import__('sys').executable,str(installer),'--root',str(path/'fixture')]
 for nl in [b'\n',b'\r\n']:
  data=baseline.encode().replace(b'\n',nl);fixture.write_bytes(data)
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);installed=fixture.read_bytes()
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);assert fixture.read_bytes()==installed
  subprocess.run(command+['--restore'],check=True,stdout=subprocess.DEVNULL);assert fixture.read_bytes()==data
 subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
 applied=fixture.read_bytes();old,new=patch.CHANGES[0];fixture.write_bytes(applied.replace(new.encode().replace(b'\n',b'\r\n'),old.encode().replace(b'\n',b'\r\n'),1))
 partial=fixture.read_bytes();result=subprocess.run(command,capture_output=True)
 assert result.returncode!=0 and fixture.read_bytes()==partial
 print('PASS shader transform installer: LF/CRLF exact restore, idempotence and partial-patch refusal')
