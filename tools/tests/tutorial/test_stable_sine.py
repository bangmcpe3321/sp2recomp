"""Exercise the actual SPIR-V sine precision pass with sanitizer and numerical checks."""
import argparse,struct,subprocess,tempfile,math,shutil,os
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);a=p.parse_args();source=a.source.read_text()
def function(text,signature):
 start=text.index(signature);i=text.index('{',start);depth=1;j=i+1
 while depth:depth+=(text[j]=='{')-(text[j]=='}');j+=1
 return text[start:j]
fn=function(source,'static bool stable_sine_near_pi(')
prefix='#include <vector>\n#include <set>\n#include <cstring>\n#include <cstdint>\n#include <fstream>\n#include <cassert>\n#include <iterator>\n'
main='int main(int argc,char**argv) {\n assert(argc==3);std::ifstream f(argv[1],std::ios::binary);std::vector<char> b((std::istreambuf_iterator<char>(f)),{});assert(b.size()%4==0);\n std::vector<uint32_t> w(b.size()/4),out{123};std::memcpy(w.data(),b.data(),b.size());assert(stable_sine_near_pi(w,out));\n std::ofstream o(argv[2],std::ios::binary);o.write((char*)out.data(),out.size()*4);o.close();\n auto bad=w;bad.pop_back();std::vector<uint32_t> keep{123};assert(!stable_sine_near_pi(bad,keep));assert(keep==std::vector<uint32_t>{123});\n bad=w;bad[5]=0;assert(!stable_sine_near_pi(bad,keep));assert(keep==std::vector<uint32_t>{123});\n std::vector<uint32_t> tiny{0x07230203,0x10000,0,1,0};assert(!stable_sine_near_pi(tiny,keep));\n bool changed=false;for(size_t i=5;i<w.size();i+=w[i]>>16) if((w[i]&65535)==12&&(w[i]>>16)==6&&w[i+4]==13){w[i+4]=14;changed=true;}\n assert(changed&&!stable_sine_near_pi(w,keep));assert(keep==std::vector<uint32_t>{123});\n}\n'
w=[0x07230203,0x10000,0,14,0]
def op(code,*args):w.extend([(len(args)+1)<<16|code,*args])
def string(s):
 b=s.encode()+b'\0';b+=b'\0'*((-len(b))%4);return struct.unpack('<%dI'%(len(b)//4),b)
op(17,1);op(11,1,*string('GLSL.std.450'));op(14,0,1);op(15,4,10,*string('main'),8,9);op(16,10,7);op(71,8,30,0);op(71,9,30,0);op(19,2);op(22,3,32);op(32,4,1,3);op(32,5,3,3);op(33,6,2);op(59,4,8,1);op(59,5,9,3);op(54,2,10,0,6);op(248,11);op(61,3,12,8);op(12,3,13,1,13,12);op(62,9,13);op(253);op(56)
fixture=struct.pack('<%dI'%len(w),*w)

with tempfile.TemporaryDirectory(prefix='sp2-sine-') as td:
 d=Path(td);cpp=d/'test.cpp';exe=d/'test';base=d/'fixture.spv';patched=d/'patched.spv'
 cpp.write_text(prefix+fn+main);base.write_bytes(fixture)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
 subprocess.run([str(exe),str(base),str(patched)],check=True)
 validator=shutil.which('spirv-val')
 if validator:subprocess.run([validator,'--target-env','vulkan1.1',str(patched)],check=True)
 else:print('spirv-val unavailable: fixture structure and numerical checks only')
 f=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
 bad=f(3.1415929794311523)
 def run(path,value):
  w=struct.unpack('<%dI'%(path.stat().st_size//4),path.read_bytes());v={8:value};p=5;result=None
  def native_sin(x):
   if abs(x)==bad:return math.copysign(0.0,-x)
   return f(math.sin(x)) if math.isfinite(x) else math.nan
  while p<len(w):
   n=w[p]>>16;op=w[p]&65535;a=w[p+1:p+n]
   if op==43:v[a[1]]=struct.unpack('<f',struct.pack('<I',a[2]))[0]
   elif op==61:v[a[1]]=v[a[2]]
   elif op==12:v[a[1]]=f(abs(v[a[4]])) if a[3]==4 else native_sin(v[a[4]])
   elif op==131:v[a[1]]=f(v[a[2]]-v[a[3]])
   elif op==127:v[a[1]]=f(-v[a[2]])
   elif op==184:v[a[1]]=v[a[2]]<v[a[3]]
   elif op==169:v[a[1]]=v[a[3]] if v[a[2]] else v[a[4]]
   elif op==62:result=v[a[1]]
   p+=n
  return result
 assert run(base,bad)==0;result=run(patched,bad);assert result!=0 and math.isfinite(1/result)
 for x in [0.0,-0.0,0.1,-0.1,1.0,-1.0,2.0,-2.0,5.0,-5.0,100.0,-100.0]:assert run(base,x)==run(patched,x)
 maxerr=0
 for i in range(2001):
  for sign in [1,-1]:
   x=f(sign*(math.pi+(i-1000)*9.5e-7));actual=run(patched,x);expected=math.sin(x);maxerr=max(maxerr,abs(actual-expected));assert abs(actual-expected)<1e-10
 print('PASS actual SPIR-V numerical path: old native zero -> finite corrected sine/reciprocal; untouched far inputs; +/-pi maxerror',maxerr)
