"""Exercise actual submission completion waits with concurrent callers and delayed replay."""
from pathlib import Path
import sys,tempfile,subprocess
s=Path(sys.argv[1]).read_text();a=s.index('std::mutex g_sub_lock;');b=s.index('\nvoid log_wait_sites()',a)
code=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <mutex>
#include <set>
#include <thread>
#include <cstdint>
constexpr int kWaitSites=4;
void log(const char*,...){}
namespace plat {uint64_t monotonic_ns(){return std::chrono::steady_clock::now().time_since_epoch().count();}}
'''+s[a:b]+r'''
int main(){
 submit_done(2);assert(g_sub_done==0);
 assert(!wait_submits(2,0,WaitClock::now()+std::chrono::milliseconds(10)));
 submit_done(1);assert(g_sub_done==2);assert(wait_submits(2,0));
 std::atomic<bool> returned=false;
 std::thread waiter([&]{assert(wait_submits(3,0));returned=true;});
 std::this_thread::sleep_for(std::chrono::milliseconds(2100));
 assert(!returned);submit_done(3);waiter.join();assert(returned);
 auto deadline=WaitClock::now()+std::chrono::milliseconds(30);
 std::thread spurious([]{for(int k=0;k<10;k++){g_sub_cv.notify_all();std::this_thread::sleep_for(std::chrono::milliseconds(2));}});
 assert(!wait_submits(4,0,deadline));spurious.join();assert(g_sub_done==3);
 g_replay_seq=4;assert(!wait_submits(4,0,WaitClock::now()));g_replay_seq=0;
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-submit-wait-') as td:
 p=Path(td);cpp=p/'t.cpp';exe=p/'t';cpp.write_text(code)
 subprocess.run(['g++','-std=c++20','-O1','-pthread','-fsanitize=address,undefined',str(cpp),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
print('PASS ordered completion, no two-second escape, finite deadlines, spurious wakeups and reentrant deadline')
