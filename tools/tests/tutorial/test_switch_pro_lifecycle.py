"""Exercise the actual SDL worker with deterministic transport events and reconnects."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

header = Path(sys.argv[1]).resolve()
source = header.read_text().replace('#include <windows.h>\n', '')
start = source.index('struct Api {')
end = source.index('inline uint64_t now_ns()', start)
fake_api = r'''
inline std::atomic<bool> transport{true};
inline std::atomic<uint32_t> identity{1};
inline std::mutex events_mutex;
inline std::deque<Event> events;
struct Api {
 bool load(){return !std::getenv("TEST_MISSING_DLL");}
 void SetMainReady(){}
 bool SetHint(const char*,const char*){return true;}
 bool Init(uint32_t){return true;}
 void Quit(){}
 const char* GetError(){return "fake transport";}
 bool PollEvent(Event* e){
  std::lock_guard lock(events_mutex);
  if(events.empty())return false;*e=events.front();events.pop_front();return true;
 }
 uint32_t* GetGamepads(int* count){
  *count=transport?1:0;return *count ? new uint32_t[1]{identity.load()} : nullptr;
 }
 void Free(uint32_t* p){delete[] p;}
 uint16_t GetGamepadVendorForID(uint32_t){return 0x057e;}
 uint16_t GetGamepadProductForID(uint32_t){return 0x2009;}
 Gamepad* OpenGamepad(uint32_t id){return reinterpret_cast<Gamepad*>(uintptr_t(id));}
 void CloseGamepad(Gamepad*){}
 bool GamepadConnected(Gamepad* p){return transport&&uintptr_t(p)==identity.load();}
 const char* GetGamepadName(Gamepad*){return "fake Switch Pro";}
 bool GetGamepadButton(Gamepad*,int index){return index==1;}
 int16_t GetGamepadAxis(Gamepad*,int){return 0;}
 bool GamepadHasSensor(Gamepad*,int){return true;}
 bool SetGamepadSensorEnabled(Gamepad*,int,bool){return true;}
};
'''
source = source[:start] + fake_api + source[end:]
prefix = r'''
#include <deque>
#include <cassert>
#include <cstdio>
namespace nx { inline void log(const char*,...){} }
'''
tests = r'''
using namespace nx::plat;
using namespace nx::plat::switch_pro_detail;
template<class F>void until(F predicate){
 auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(3);
 while(!predicate()){
  assert(std::chrono::steady_clock::now()<deadline);
  std::this_thread::sleep_for(std::chrono::milliseconds(2));
 }
}
void packet(uint32_t id,uint64_t age=0){
 std::lock_guard lock(events_mutex);uint64_t time=now_ns()-age;
 for(int sensor=1;sensor<=2;++sensor){
  Event e{};e.sensor.type=0x659;e.sensor.which=id;e.sensor.sensor=sensor;
  e.sensor.timestamp=e.sensor.sensor_timestamp=time;
  e.sensor.data[1]=sensor==1 ? 9.80665f : .3f;
  events.push_back(e);
 }
}
void stream(uint32_t id,int count=24){
 for(int i=0;i<count;++i){packet(id);std::this_thread::sleep_for(std::chrono::milliseconds(5));}
}
int main(int argc,char** argv){
 assert(argc==2);auto& s=state();start_switch_pro();
 if(!strcmp(argv[1],"disabled")){assert(!s.worker.joinable());return 0;}
 if(!strcmp(argv[1],"missing")){
  s.worker.join();PadState pad{};assert(!read_switch_pro(pad));return 0;
 }
 until([&]{PadState p{};return read_switch_pro(p)&&(p.buttons&kA);});
 stream(1);MouseGyroSample left[16]{},right[16]{};
 assert(read_switch_pro_motion(0,left,16)==16);
 assert(read_switch_pro_motion(1,right,16)==16&&!memcmp(left,right,sizeof(left)));
 set_switch_pro_focus(false);stream(1,5);assert(!read_switch_pro_motion(0,left,16));
 set_switch_pro_focus(true);
 // A pre-focus packet must not become a newly "fresh" motion sample.
 packet(1,1000000000);std::this_thread::sleep_for(std::chrono::milliseconds(15));
 assert(!read_switch_pro_motion(0,left,16));
 stream(1,8);assert(read_switch_pro_motion(0,left,16)>0&&left[0].sampling_number<16);
 transport=false;
 until([&]{PadState p{};return !read_switch_pro(p);});
 assert(!read_switch_pro_motion(0,left,16));
 identity=2;transport=true;
 until([&]{PadState p{};return read_switch_pro(p);});
 assert(!read_switch_pro_motion(0,left,16));
 // Samples from the previous device identity cannot leak across reconnect.
 packet(1);std::this_thread::sleep_for(std::chrono::milliseconds(15));
 assert(!read_switch_pro_motion(0,left,16));
 stream(2,8);assert(read_switch_pro_motion(0,left,16)>0&&left[0].sampling_number<16);
 std::this_thread::sleep_for(std::chrono::milliseconds(120));
 assert(!read_switch_pro_motion(0,left,16)); // stale transport stays neutral
 s.stop=true;s.worker.join();
}
'''
with tempfile.TemporaryDirectory(prefix='switch-pro-lifecycle-') as tmp:
    cpp, exe = Path(tmp) / 'test.cpp', Path(tmp) / 'test'
    cpp.write_text(prefix + source + tests)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I',str(header.parent),str(cpp),'-o',str(exe)],check=True)
    for scenario in ('normal','disabled','missing'):
        env=os.environ.copy()
        env.pop('NX_SWITCH_PRO',None)
        env.pop('TEST_MISSING_DLL',None)
        if scenario=='disabled':env['NX_SWITCH_PRO']='0'
        if scenario=='missing':env['TEST_MISSING_DLL']='1'
        subprocess.run([str(exe),scenario],env=env,check=True)
print('PASS actual worker discovery, sensor identity/history, focus/stale packets, reconnect, shutdown, disabled and missing-DLL fallback')
