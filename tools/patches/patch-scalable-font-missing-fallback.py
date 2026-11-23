#!/usr/bin/env python3
"""Complete ScalableFont output when its fallback cache node is absent.

The 2026-11-23 plaza crash is main_013629FC+0x2b4: GetGlyph measured
the requested character (advance 40), looked up U+0020, then read [NULL+0x4c].
HasGlyph tests the font face; FindGlyph tests a separate cache tree. A usable
face therefore does not guarantee a cached SPACE node. The initializer tries
to register/pin fallback nodes, but registration can fail, and this failure
is checked there. GetGlyph incorrectly assumes it cannot happen later.

Return a transparent, fully initialized Glyph with the measured advance and
the cache's normal texture descriptors. Do not mutate the glyph tree from
the UI reader or attribute the miss to a freed font without evidence. Bounded
diagnostics expose the missing node's cache state for the next manual run.

Usage: SP2PORT=/home/hexa/sp2port python3 this-script.py [--restore]
"""
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("SP2PORT", "/home/hexa/sp2port"))
TARGET = ROOT / "gen/main/code_417.cpp"
FUNCTION = "void main_013629FC(nx::CPU& NX_RESTRICT c) {\n"
ENTRY = "    const uint32_t fss_requested_glyph = uint32_t(c.x[2]); // PATCH-FSS-MISSING-FALLBACK\n"
OLD = """L_1362AB8:;
    { uint64_t a = c.x[0] + 0x4aull; c.x[21] = uint32_t(nx::ld<uint16_t>(a)); } // ldrh w21, [x0, #0x4a]
L_1362ABC:;
"""
NEW = """L_1362AB8:;
    if (c.x[0] != 0) {
        { uint64_t a = c.x[0] + 0x4aull; c.x[21] = uint32_t(nx::ld<uint16_t>(a)); } // ldrh w21, [x0, #0x4a]
    }
L_1362ABC:;
    // PATCH-FSS-MISSING-FALLBACK: face coverage does not imply a cached fallback.
    // Keep measured layout advance when the SPACE placeholder is absent. A zero
    // bitmap is transparent; all Glyph fields still carry their normal ABI values.
    if (c.x[0] == 0) {
        const uint64_t font = c.x[20], out = c.x[19];
        const uint64_t cache = nx::ld<uint64_t>(font + 0x10ull);
        const uint16_t advance = c.x[30] == NXB + 0x1362aa0ull ? uint16_t(c.x[21]) : 0;
        static std::atomic<unsigned> missing_fallback_logs{0};
        if (missing_fallback_logs.fetch_add(1, std::memory_order_relaxed) < 16) {
            nx::log("FSSGLYPH missing fallback font=%llx cache=%llx chr=%u mode=%u default=%u size=%u face=%u root=%llx free=%llx advance=%u",
                    (unsigned long long)font, (unsigned long long)cache, fss_requested_glyph,
                    unsigned(nx::ld<uint8_t>(font + 0x2full)), nx::ld<uint32_t>(font + 0x34ull),
                    nx::ld<uint32_t>(font + 0x18ull), unsigned(nx::ld<uint16_t>(font + 0x30ull)),
                    (unsigned long long)nx::ld<uint64_t>(cache + 0x30ull),
                    (unsigned long long)nx::ld<uint64_t>(cache + 0x38ull), unsigned(advance));
        }
        nx::st<uint64_t>(out, nx::ld<uint64_t>(cache + 0x20ull));
        nx::st<uint64_t>(out + 0x8ull, uint64_t(advance) << 32);
        nx::st<uint64_t>(out + 0x10ull, 0);
        nx::st<uint64_t>(out + 0x18ull, uint64_t(8) << 16);
        nx::st<uint16_t>(out + 0x12ull, uint16_t(nx::ld<uint32_t>(cache + 0x28ull)));
        nx::st<uint16_t>(out + 0x14ull, uint16_t(nx::ld<uint32_t>(cache + 0x2cull)));
        nx::st<uint64_t>(out + 0x20ull, cache + 0x1ba0ull);
        nx::st<uint8_t>(out + 0x28ull, 0);
        { uint64_t a = c.x[31] + 0x20ull; auto v0 = nx::ld<uint64_t>(a); auto v1 = nx::ld<uint64_t>(a + 8); c.x[29] = v0; c.x[30] = v1; }
        { uint64_t a = c.x[31] + 0x10ull; auto v0 = nx::ld<uint64_t>(a); auto v1 = nx::ld<uint64_t>(a + 8); c.x[20] = v0; c.x[19] = v1; }
        { uint64_t a = c.x[31]; c.x[31] += 0x30ull; c.x[21] = nx::ld<uint64_t>(a); }
        return;
    }
"""
INCLUDE = "#include <atomic> // PATCH-FSS-MISSING-FALLBACK\n"


def main():
    source = TARGET.read_text()
    if "--restore" in sys.argv:
        if NEW not in source:
            print("nothing to restore")
            return
        source = source.replace(NEW, OLD, 1).replace(ENTRY, "", 1).replace(INCLUDE, "", 1)
    else:
        if NEW in source:
            print("already applied")
            return
        if source.count(OLD) != 1 or source.count(FUNCTION) != 1:
            raise SystemExit("GetGlyph anchor mismatch; no changes")
        source = source.replace(OLD, NEW, 1).replace(FUNCTION, FUNCTION + ENTRY, 1)
        source = INCLUDE + source
    TARGET.write_text(source)
    print("restored" if "--restore" in sys.argv else "patched", TARGET)


if __name__ == "__main__":
    main()
