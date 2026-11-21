"""Compile the actual integer-interface patch; validate authored SPIR-V when spirv-val is available."""
from pathlib import Path
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).read_text()
body = source[source.index("enum : uint32_t {"):source.index("// ---- constant buffer reads")]
formats = sorted(set(re.findall(r"VK_FORMAT_\w+", body)))
prefix = "#include <bits/stdc++.h>\nusing VkFormat = uint32_t;\nenum {" + ",".join(formats) + "};\n"
prefix += "VkFormat vk_vertex_format(uint32_t n) { return n == 0x55 ? VK_FORMAT_R32_UINT : VK_FORMAT_R8_UINT; }\nnamespace {\n"
owner = tempfile.TemporaryDirectory(prefix="sp2-integer-io-")
folder = Path(owner.name)
words = [0x07230203, 0x00010000, 0, 64, 0]


def op(code, *operands):
    words.extend([((len(operands) + 1) << 16) | code, *operands])


# Authored fragment shader: two float outputs, a flat input and scalar/vector pointer accesses.
op(17, 1)
op(14, 0, 1)
op(15, 4, 30, 0x6E69616D, 0, 10, 11, 12)
op(16, 30, 7)
op(71, 10, 30, 0)
op(71, 11, 30, 1)
op(71, 12, 30, 2)
op(71, 12, 14)
op(19, 1)
op(33, 2, 1)
op(22, 3, 32)
op(23, 4, 3, 4)
op(32, 5, 3, 4)
op(32, 6, 3, 3)
op(32, 7, 1, 4)
op(32, 8, 1, 3)
op(21, 9, 32, 0)
op(43, 9, 20, 0)
op(43, 3, 21, 0x3F800000)
op(43, 3, 22, 0x7FC12345)
op(44, 4, 23, 21, 22, 21, 22)
op(59, 5, 10, 3)
op(59, 5, 11, 3)
op(59, 7, 12, 1)
op(54, 1, 30, 0, 2)
op(248, 31)
op(62, 10, 23)
op(65, 6, 32, 11, 20)
op(62, 32, 22)
op(65, 8, 33, 12, 20)
op(61, 3, 34, 33)
op(61, 4, 35, 12)
op(62, 10, 35)
op(61, 4, 36, 10)
op(253)
op(56)
(folder / "fixture.spv").write_bytes(struct.pack("<" + "I" * len(words), *words))

test = r'''
std::vector<uint32_t> read(const char* path) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    auto n = f.tellg(); assert(n > 0 && n % 4 == 0);
    std::vector<uint32_t> v(size_t(n) / 4); f.seekg(0); f.read((char*)v.data(), n); return v;
}
void save(const char* path, const std::vector<uint32_t>& v) {
    std::ofstream f(path, std::ios::binary); f.write((const char*)v.data(), v.size() * 4);
}
int main(int argc, char** argv) {
    if (argc == 3) {
        auto in = read(argv[1]); std::vector<uint32_t> out; uint8_t kinds[16] = {}; kinds[0] = 1;
        assert(patch_int_outputs(in, kinds, out)); save(argv[2], out); return 0;
    }
    assert(argc == 4);
    auto in = read(argv[1]); std::vector<uint32_t> out, both;
    uint8_t outputs[16] = {}, inputs[16] = {}, none[16] = {};
    outputs[0] = 1; outputs[1] = 2; inputs[2] = 1;
    assert(integer_format_kind(VK_FORMAT_R32G32B32A32_UINT) == 1);
    assert(integer_format_kind(VK_FORMAT_R16_SINT) == 2);
    assert(vertex_int_kind(0x55) == 0 && vertex_int_kind(1) == 1);
    assert(!patch_int_outputs(in, none, out));
    assert(patch_int_outputs(in, outputs, out));
    unsigned casts = 0, stores = 0; std::set<uint32_t> cast_ids;
    std::map<uint32_t, std::pair<uint32_t, uint32_t>> int_types;
    std::map<uint32_t, uint32_t> vectors, pointers;
    for (size_t i = 5; i < out.size(); i += out[i] >> 16) {
        const auto* w = out.data() + i; auto op = w[0] & 0xffff;
        if (op == 21) int_types[w[1]] = {w[2], w[3]};
        if (op == 23) vectors[w[1]] = w[2];
        if (op == 32) pointers[w[1]] = w[3];
        if (op == 59 && (w[2] == 10 || w[2] == 11)) {
            auto scalar = vectors.at(pointers.at(w[1]));
            assert(int_types.at(scalar).first == 32);
            assert(int_types.at(scalar).second == (w[2] == 11));
        }
        if (op == 124) { casts++; cast_ids.insert(w[2]); }
        if (op == 62) { stores++; assert(cast_ids.count(w[2])); }
        assert(op != 109 && op != 110);  // No numeric float-to-integer conversions.
    }
    assert(stores == 3 && casts == 4); // Three output stores plus an output read cast back to float.
    assert(patch_int_inputs(out, inputs, both));
    save(argv[2], out); save(argv[3], both);
    assert(patch_int_inputs(in, inputs, out));
    // A type introduced after an earlier output variable cannot be reused there: fail closed.
    assert(!patch_int_outputs(out, outputs, both));
    auto alias = in;
    alias.insert(alias.end() - 2, {(4u << 16) | 83, 5, 40, 10});
    assert(!patch_int_outputs(alias, outputs, out));
    for (auto bad : {std::vector<uint32_t>{}, std::vector<uint32_t>{1,2,3,4,5}})
        assert(!patch_int_outputs(bad, outputs, out));
    auto truncated = in; truncated.pop_back(); truncated.back() = (10u << 16) | 61;
    assert(!patch_int_outputs(truncated, outputs, out));
    std::cout << "PASS: signed/unsigned output bitcasts, scalar stores, input compatibility and fail-closed aliases\n";
}
'''
(folder / "test.cpp").write_text(prefix + body + test)
exe = folder / "test"
subprocess.run(["g++", "-std=c++20", "-O1", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                str(folder / "test.cpp"), "-o", str(exe)], check=True)
paths = [folder / name for name in ("fixture.spv", "outputs.spv", "both.spv")]
subprocess.run([str(exe), *map(str, paths)], check=True)
if len(sys.argv) > 2:
    actual = folder / "actual-output.spv"
    subprocess.run([str(exe), sys.argv[2], str(actual)], check=True)
    paths.append(actual)
validator = os.environ.get("SPIRV_VAL") or shutil.which("spirv-val")
if validator:
    for path in paths:
        argument = str(path)
        if os.name != "nt" and validator.lower().endswith(".exe"):
            argument = subprocess.check_output(["wslpath", "-w", argument], text=True).strip()
        subprocess.run([validator, "--target-env", "vulkan1.1", argument], check=True)
    print("PASS: spirv-val validates the original and both integer-interface variants")
else:
    print("spirv-val unavailable: structural CPU assertions only")
