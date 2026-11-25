// US 1.0.0 equivalents of theboy181's two instruction patches.
#pragma once
#include <nx/runtime.h>
#include <cstdlib>
#include <cstring>

namespace nx::sp2 {
inline bool plaza_60fps_enabled() {
    static const bool enabled = [] {
        const char* value = std::getenv("NX_PLAZA_60FPS");
        const bool on = value && std::strcmp(value, "1") == 0;
        nx::log("SP2 option: plaza 60 FPS %s", on ? "enabled" : "disabled");
        return on;
    }();
    return enabled;
}
inline bool dynamic_resolution_disabled() {
    static const bool enabled = [] {
        const char* value = std::getenv("NX_DISABLE_DYNAMIC_RESOLUTION");
        const bool on = value && std::strcmp(value, "1") == 0;
        nx::log("SP2 option: dynamic resolution %s", on ? "disabled" : "enabled");
        return on;
    }();
    return enabled;
}
} // namespace nx::sp2
// PATCH-SP2-NEWS-TIMING
namespace nx::sp2 {
inline void set_plaza_timing(nx::CPU& caller, uint64_t main_base, nx::Fn set_interval, bool gameplay) {
    if (!plaza_60fps_enabled()) return;
    const uint64_t system_slot = nx::ld<uint64_t>(main_base + 0x2f9d2a0ull);
    const uint64_t framework_slot = nx::ld<uint64_t>(main_base + 0x2f9d2a8ull);
    if (!system_slot || !framework_slot) return;
    const uint64_t system = nx::ld<uint64_t>(system_slot);
    const uint64_t framework = nx::ld<uint64_t>(framework_slot);
    if (!system || !framework) return;
    uint32_t flags = nx::ld<uint32_t>(system + 0x550ull);
    nx::st<uint32_t>(system + 0x550ull, gameplay ? flags & ~1u : flags | 1u);
    // The injected lifecycle call must not clobber the guest caller's registers.
    nx::CPU timing = caller;
    timing.x[0] = framework;
    timing.x[1] = gameplay ? 1u : 2u;
    set_interval(timing);
    nx::log("SP2 timing: %s", gameplay ? "plaza gameplay 60 Hz" : "news broadcast native 30 Hz");
}
} // namespace nx::sp2
