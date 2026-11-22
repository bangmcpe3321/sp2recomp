"""Exercise the actual Windows mouse-message branch with portable API stubs."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).read_text()
branch = source[source.index('        case WM_MOUSEMOVE:'):source.index('        case WM_KILLFOCUS:')]
prefix = r'''
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
struct POINT { int32_t x, y; };
struct RECT { int32_t left, top, right, bottom; };
std::atomic<bool> g_mouse_capture{true};
std::atomic<int32_t> g_mouse_dx{0}, g_mouse_dy{0};
POINT g_mouse_last{500,400}, current{};
bool g_mouse_have_last=true;
constexpr int WM_MOUSEMOVE=0;
void GetCursorPos(POINT* p) { *p=current; }
void GetClientRect(int, RECT* r) { *r={0,0,1000,800}; }
void ScreenToClient(int, POINT*) {}
void mouse_recenter(int) { current={500,400}; g_mouse_last=current; g_mouse_have_last=true; }
void move(int32_t x,int32_t y) { current={x,y}; int h=1; switch(0) {
'''
suffix = r'''
} }
int main() {
    move(505,402); move(510,405); move(510,405);
    assert(g_mouse_dx==10 && g_mouse_dy==5);
    move(650,450); move(500,400);
    assert(g_mouse_dx==150 && g_mouse_dy==50);
    move(497,399);
    assert(g_mouse_dx==147 && g_mouse_dy==49);
    g_mouse_capture=false; move(550,450);
    assert(g_mouse_dx==147 && g_mouse_dy==49);
    g_mouse_capture=true; g_mouse_have_last=false;
    move(500,400); move(501,401);
    assert(g_mouse_dx==148 && g_mouse_dy==50);
    std::cout << "PASS: relative movement, duplicate messages, recentering, focus and first event\n";
}
'''
with tempfile.TemporaryDirectory(prefix='sp2-mouse-') as folder:
    cpp = Path(folder)/'test.cpp'
    exe = Path(folder)/'test'
    cpp.write_text(prefix + branch + suffix)
    subprocess.run(['g++','-std=c++20','-O1','-g','-fsanitize=address,undefined',str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
