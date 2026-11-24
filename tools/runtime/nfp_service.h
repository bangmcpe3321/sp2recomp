// Minimal NFP software service: valid interfaces, honestly no NFC reader.
#pragma once
#include "ipc.h"

namespace nx::nfp_no_reader {
constexpr uint32_t device_not_found = (64u << 9) | 115u;
constexpr uint32_t wrong_argument = (65u << 9) | 115u;

class User final : public Service {
    bool initialized_ = false;
    std::shared_ptr<EventState> availability_ = std::make_shared<EventState>();

public:
    User() : Service("nfp:IUser") {}

    uint32_t handle(IpcCtx& c) override {
        switch (c.cmd) {
        case 0: // Initialize: initialize the software interface, not a device.
            initialized_ = true;
            log("nfp: software interface initialized; no NFC reader available");
            return 0;
        case 1: // Finalize
            initialized_ = false;
            return 0;
        case 2: // ListDevices: the game explicitly handles this no-reader result.
            c.push<uint32_t>(0);
            return device_not_found;
        case 19: // GetState: NonInitialized=0, Initialized=1.
            c.push<uint32_t>(initialized_ ? 1u : 0u);
            return 0;
        case 20: // GetDeviceState: Unavailable=0, with no matching reader.
            c.push<uint32_t>(0);
            return device_not_found;
        case 23: { // AttachAvailabilityChangeEvent: no reader changes to signal.
            auto event = std::make_shared<KEvent>();
            event->state = availability_;
            c.out_copy.push_back(handle_add(event));
            return 0;
        }
        default:
            // No fabricated reader, tag, application data or successful writes.
            if ((c.cmd >= 3 && c.cmd <= 18) || c.cmd == 21 || c.cmd == 24 || c.cmd == 102)
                return device_not_found;
            return wrong_argument;
        }
    }
};

class Manager final : public Service {
public:
    Manager() : Service("nfp:user") {}
    uint32_t handle(IpcCtx& c) override {
        if (c.cmd != 0) return wrong_argument;
        c.push_object(std::make_shared<User>()); // CreateUserInterface
        return 0;
    }
};

inline ServiceRegistrar registration("nfp:user", [] { return std::make_shared<Manager>(); });
} // namespace nx::nfp_no_reader
