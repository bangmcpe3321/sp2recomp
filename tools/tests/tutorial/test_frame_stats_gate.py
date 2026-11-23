"""Exercise real frame-statistics gates without rendering or platform dependencies."""
from pathlib import Path
import os,subprocess,sys,tempfile
s=Path(sys.argv[1]).read_text()
def function(signature):
 start=s.index(signature);cur=s.index('{',start);end=cur+1;depth=1
 while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]
prefix=r'''
#include <cstdint>
#include <cstdlib>
#include <cassert>
struct Role {const char* name;uint64_t ticks=0,cpu_from=0,wall_from=0,on[4]={};long faults_from[2]={},switches_from[2]={};};
Role g_roles[2]={{"present"},{"main"}};
unsigned clocks=0,logs=0;
uint64_t monotonic_ns(){return ++clocks*1000000ull;}
uint64_t thread_cpu_ns(){return 1000;}
void thread_usage(long f[2],long s[2]){f[0]=f[1]=s[0]=s[1]=0;}
int current_thread_id(){return 1;}
void log(const char*,...){logs++;}
'''
code=prefix+'\n'.join(function(f) for f in ['static bool frame_stats_enabled()', 'void frame_thread_tick(', 'void frame_presented()'])+r'''
int main(){
 for(int i=0;i<1200;i++){frame_thread_tick(1);frame_presented();}
 assert(g_roles[0].ticks==1200&&g_roles[1].ticks==1200);
 if(frame_stats_enabled()){assert(clocks>0&&logs==10);}else{assert(clocks==0&&logs==0);}
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-frame-stats-') as td:
 d=Path(td);cpp=d/'t.cpp';exe=d/'t';cpp.write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-fsanitize=address,undefined',str(cpp),'-o',str(exe)],check=True)
 for value in [None,'0','1']:
  env=os.environ.copy();env.pop('NX_PRESENT_STATS',None)
  if value is not None:env['NX_PRESENT_STATS']=value
  subprocess.run([str(exe)],check=True,env=env)
print('PASS frame statistics: default/zero skip clocks and logging; opt-in summaries retain thread ticks')
