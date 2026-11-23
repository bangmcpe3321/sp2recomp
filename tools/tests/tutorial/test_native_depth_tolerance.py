"""Check actual depth tolerance selection for native Vulkan, Metal, and explicit diagnostics."""
from pathlib import Path
import argparse,os,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();s=a.source.read_text()
def function(signature):
 start=s.index(signature);pos=s.index('{',start);depth=1;end=pos+1
 while depth:
  depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]
code='''#include <cstdlib>
#include <cassert>
struct DepthStencilInfo { bool depth_write=false; unsigned depth_func=3; };
'''+function('float equal_slack_units(')+'\n'+function('bool equal_slack_pass(')+'''
int main(int argc,char** argv) {
 assert(argc==2);float expected=std::atof(argv[1]);assert(equal_slack_units()==expected);
 DepthStencilInfo d;assert(equal_slack_pass(d)==(expected!=0));
 d.depth_write=true;assert(!equal_slack_pass(d));d.depth_write=false;
 for (unsigned cmp: {1u,2u,4u,5u,6u,7u,8u}) { d.depth_func=cmp;assert(!equal_slack_pass(d)); }
}
'''
code='#include <initializer_list>\n'+code
with tempfile.TemporaryDirectory(prefix='sp2-native-depth-') as td:
 d=Path(td);cpp=d/'test.cpp';cpp.write_text(code)
 for apple in [False,True]:
  exe=d/('metal' if apple else 'vulkan');cmd=['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
  if apple:cmd+=['-D__APPLE__']
  subprocess.run(cmd+[str(cpp),'-o',str(exe)],check=True)
  for override in [None,'0','4']:
   env=os.environ.copy();env.pop('NX_EQUAL_SLACK',None);env.pop('NX_GREATER_SLACK',None)
   if override is not None:env['NX_EQUAL_SLACK']=override
   expected=override if override is not None else ('4' if apple else '0')
   subprocess.run([str(exe),expected],env=env,check=True)
print('PASS native Vulkan depth preservation, retained Metal tolerance, overrides and depth-write exclusion')
