#pragma once
#include <array>
#include <cstdint>
#include <cstdlib>
namespace nx::plat {
enum class PcAction : unsigned { Left, Right, Up, Down, A, B, X, Y, L, R, ZL, ZR, Plus, Minus, StickL, StickR, DpadLeft, DpadUp, DpadRight, DpadDown, Count };
struct PcBindingSpec { const char* name; const char* defaults; };
inline constexpr PcBindingSpec pc_binding_specs[] = {
    {"LEFT","65,37"},{"RIGHT","68,39"},{"UP","87,38"},{"DOWN","83,40"},
    {"A","70"},{"B","32"},{"X","74"},{"Y","75"},{"L","81"},{"R","69"},
    {"ZL","16,90"},{"ZR","1,67"},{"PLUS","13"},{"MINUS","27"},
    {"STICK_L","0"},{"STICK_R","0"},{"DPAD_LEFT","0"},{"DPAD_UP","0"},{"DPAD_RIGHT","0"},{"DPAD_DOWN","0"}
};
struct PcKeyBinding {
    std::array<unsigned,4> keys{};
    unsigned count = 0;
    bool parse(const char* text) {
        std::array<unsigned,4> parsed{}; unsigned size = 0;
        if (!text || !*text) return false;
        if (text[0]=='0' && !text[1]) { keys={}; count=0; return true; }
        const char* p=text;
        for (;;) {
            if (size==parsed.size() || *p<'0' || *p>'9') return false;
            unsigned value=0, digits=0;
            while (*p>='0' && *p<='9') {
                if (++digits>3) return false;
                value=value*10+unsigned(*p++-'0');
            }
            if (!value || value>254) return false;
            for (unsigned i=0;i<size;i++) if (parsed[i]==value) return false;
            parsed[size++]=value;
            if (!*p) break;
            if (*p++!=',' || !*p) return false;
        }
        keys=parsed; count=size; return true;
    }
    template<class KeyDown> bool pressed(KeyDown down) const {
        for (unsigned i=0;i<count;i++) if (down(int(keys[i]))) return true;
        return false;
    }
};
class PcInputBindings {
    std::array<PcKeyBinding,unsigned(PcAction::Count)> bindings_{};
public:
    PcInputBindings() {
        for (unsigned i=0;i<bindings_.size();i++) {
            bindings_[i].parse(pc_binding_specs[i].defaults);
            char name[48]="NX_BIND_"; unsigned at=8;
            for (const char* p=pc_binding_specs[i].name;*p;p++) name[at++]=*p;
            name[at]=0;
            if (const char* value=std::getenv(name)) bindings_[i].parse(value); // invalid overrides retain defaults
        }
    }
    template<class KeyDown> bool pressed(PcAction action,KeyDown down) const { return bindings_[unsigned(action)].pressed(down); }
};
inline const PcInputBindings& pc_inputs() { static PcInputBindings inputs; return inputs; }
} // namespace nx::plat
