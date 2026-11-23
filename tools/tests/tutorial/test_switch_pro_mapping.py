"""Exercise real Nintendo label mapping and full signed axis domain under sanitizers.
Usage: python3 test_switch_pro_mapping.py /path/runtime/src/switch_pro_mapping.h
"""
from pathlib import Path
import subprocess
import sys
import tempfile

header=Path(sys.argv[1]).resolve()
source=r'''
#include "switch_pro_mapping.h"
#include <cassert>
#include <cstdio>
using namespace nx::plat;
int main(){
 bool b[15]={}; int16_t a[6]={};
 auto p=map_switch_pro(b,a);assert(!p.buttons&&!p.lx&&!p.ly&&!p.rx&&!p.ry);
 // Physical B,A,Y,X positions retain Nintendo labels, including chords.
 b[0]=true;assert(map_switch_pro(b,a).buttons==kB);
 b[1]=true;assert(map_switch_pro(b,a).buttons==(kA|kB));
 b[2]=b[3]=true;assert(map_switch_pro(b,a).buttons==(kA|kB|kX|kY));
 for(bool& v:b)v=false;
 b[4]=b[6]=b[7]=b[8]=b[9]=b[10]=true;
 assert(map_switch_pro(b,a).buttons==(kMinus|kPlus|kStickL|kStickR|kL|kR));
 for(bool& v:b)v=false;
 b[5]=true;assert(!map_switch_pro(b,a).buttons); // HOME never becomes a gameplay button.
 b[11]=b[14]=true;assert(map_switch_pro(b,a).buttons==(kUp|kRight));
 b[11]=b[14]=false;b[12]=b[13]=true;assert(map_switch_pro(b,a).buttons==(kDown|kLeft));
 a[4]=a[5]=32767;assert((map_switch_pro(b,a).buttons&(kZL|kZR))==(kZL|kZR));
 a[4]=a[5]=0;assert(!(map_switch_pro(b,a).buttons&(kZL|kZR)));
 // SDL Y-down becomes HID Y-up; negative full scale never exceeds +32767.
 a[0]=-32768;a[1]=-32768;a[2]=32767;a[3]=32767;p=map_switch_pro(b,a);
 assert(p.lx==-32767&&p.ly==32767&&p.rx==32767&&p.ry==-32767);
 a[0]=a[1]=a[2]=a[3]=3500;p=map_switch_pro(b,a);
 assert(!p.lx&&!p.ly&&!p.rx&&!p.ry);
 int previous=-32768;
 for(int raw=-32768;raw<=32767;++raw){
  int value=switch_pro_axis(int16_t(raw));
  assert(value>=-32767&&value<=32767&&value>=previous);previous=value;
  if(raw>=-32767)assert(switch_pro_axis(int16_t(raw),true)==-value);
 }
 puts("native Switch Pro mapping passed");
}
'''
with tempfile.TemporaryDirectory(prefix='switch-pro-mapping-') as tmp:
    cpp=Path(tmp)/'test.cpp';exe=Path(tmp)/'test'
    cpp.write_text(source)
    subprocess.run(['clang++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(header.parent),str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
