#pragma once
namespace nx::plat {
// Window-thread state: distinguish a persistent lock from a temporary button hold.
class MouseCaptureLock {
    bool locked_ = false;
    bool held_ = false;
public:
    bool toggle() { locked_ = !locked_; held_ = false; return locked_; }
    bool button(bool down) { held_ = down; return locked_ || held_; }
    bool release() { locked_ = held_ = false; return false; }
};
} // namespace nx::plat
