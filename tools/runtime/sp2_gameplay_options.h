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
