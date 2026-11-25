from pathlib import Path
import subprocess,sys,tempfile,re,importlib.util
root=Path(sys.argv[1]);folder=root/'runtime/src';src=(folder/'platform_win.cpp').read_text()
start=src.index('static bool key(int vk)');end=src.index('\n',start);key=src[start:end]
start=src.index('    // PATCH-LAUNCHER-INPUTS:');end=src.index('    // Mouse -> right stick:',start);routing=src[start:end]
header=folder/'pc_input_bindings.h'
# Launcher and runtime defaults must agree for every action, including currently unassigned buttons.
launcher=Path(__file__).resolve().parents[2]/'windows/launcher/InputOptions.cs'
specs=dict(re.findall(r'\{"([A-Z_]+)","([0-9,]+)"\}',header.read_text()))
ui=dict(re.findall(r'new InputDefinition\("([A-Z_]+)","[^"]+","([0-9,]+)"',launcher.read_text()))
assert specs==ui and len(specs)==20
code=r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
'''+ '#include "'+str(folder/'platform.h')+'"\n#include "'+str(header)+'"\n'+r'''
using namespace nx::plat;
int g_window=1,foreground=1;bool held[256]{};
int GetForegroundWindow(){return foreground;}int GetAsyncKeyState(int key){return held[key]?0x8000:0;}
'''+key+'\nvoid route(PadState& p){\n'+routing+'\n}\n'+r'''
PadState press(int vk){memset(held,0,sizeof held);held[vk]=true;PadState p{};route(p);return p;}
int main(int argc,char** argv){
 PcKeyBinding b;assert(b.parse("32,1,16,254") && b.count==4);
 for(auto bad:{"","0,32","32,","1,,2",",2","-1","+1","256","255","9999","32,32","1,2,3,4,5"," 32","32 ","NaN"}){
  assert(!b.parse(bad));assert(b.count==4 && b.keys[0]==32 && b.keys[3]==254);
 }
 assert(b.parse("0") && b.count==0 && !b.pressed([](int){return true;}));
 assert(b.parse("70") && b.pressed([](int k){return k==70;}));
 assert(argc==2);
 for(const auto& spec:pc_binding_specs){std::string name="NX_BIND_";name+=spec.name;unsetenv(name.c_str());}
 bool custom=!strcmp(argv[1],"custom"),none=!strcmp(argv[1],"none"),bad=!strcmp(argv[1],"bad");
 if(custom){setenv("NX_BIND_B","71",1);setenv("NX_BIND_ZR","4",1);setenv("NX_BIND_ZL","17",1);setenv("NX_BIND_STICK_R","86",1);setenv("NX_BIND_DPAD_UP","84",1);setenv("NX_BIND_UP","73",1);}
 if(none)for(const auto& spec:pc_binding_specs){std::string name="NX_BIND_";name+=spec.name;setenv(name.c_str(),"0",1);}
 if(bad){setenv("NX_BIND_B","not-a-key",1);setenv("NX_BIND_ZR","1,1",1);}
 PcInputBindings actual;
 if(none){for(int vk=1;vk<255;vk++){auto p=press(vk);assert(p.buttons==0&&p.lx==0&&p.ly==0);}return 0;}
 if(custom){
  assert(press(71).buttons==kB && press(32).buttons==0);assert(press(4).buttons==kZR && press(1).buttons==0);
  assert(press(17).buttons==kZL && press(16).buttons==0);assert(press(86).buttons==kStickR && press(84).buttons==kUp);
  assert(press(73).ly==kStickMax && press(87).ly==0);
 }else{
  assert(press(32).buttons==kB && press(70).buttons==kA);
  assert(press(16).buttons==kZL && press(90).buttons==kZL);assert(press(1).buttons==kZR && press(67).buttons==kZR);
  assert(press(65).lx==-kStickMax && press(37).lx==-kStickMax);assert(press(68).lx==kStickMax);
  assert(press(87).ly==kStickMax && press(40).ly==-kStickMax);
  assert(press(74).buttons==kX && press(75).buttons==kY && press(81).buttons==kL && press(69).buttons==kR);
  assert(press(13).buttons==kPlus && press(27).buttons==kMinus);
 }
 // Multiple input actions and native controller state compose, rather than replacing each other.
 memset(held,0,sizeof held);held[custom?71:32]=held[custom?4:1]=true;PadState p{};p.buttons=kStickL;route(p);assert(p.buttons==(kStickL|kB|kZR));
 foreground=2;p={};route(p);assert(!p.buttons && !p.lx && !p.ly);foreground=1;g_window=0;p={};route(p);assert(!p.buttons);
 printf("PASS actual configurable PC inputs %s: saved bindings, defaults/fallback, disabled actions, mouse, controller composition and focus gating\n",argv[1]);
}
'''
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp);(path/'test.cpp').write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
 for mode in ['default','custom','none','bad']:subprocess.run([str(path/'test'),mode],check=True)
 installer=Path(__file__).resolve().parents[2]/'patches/patch-launcher-inputs.py'
 spec=importlib.util.spec_from_file_location('launcher_inputs_patch',installer);patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
 original=src
 for old,new in reversed(patch.CHANGES):assert original.count(new)==1;original=original.replace(new,old,1)
 target=path/'fixture/runtime/src/platform_win.cpp';target.parent.mkdir(parents=True)
 command=[sys.executable,str(installer),'--root',str(path/'fixture')]
 for nl in [b'\n',b'\r\n']:
  data=original.encode().replace(b'\n',nl);target.write_bytes(data)
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);installed=target.read_bytes()
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL);assert target.read_bytes()==installed
  subprocess.run(command+['--restore'],check=True,stdout=subprocess.DEVNULL);assert target.read_bytes()==data
 print('PASS launcher input installer exact restore/idempotence and cross-language default consistency')
