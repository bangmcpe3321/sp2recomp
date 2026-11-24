#!/usr/bin/env python3
"""Avoid graphics-pipeline variants for state the current encoder does not consume."""
from pathlib import Path
import argparse, os

ANCHOR = b'    ByteKey<sizeof(PipelineKey)> result;\n    std::memcpy(result.b, &key, sizeof key);'
REPLACEMENT = b'''    // PATCH-PIPELINE-EFFECTIVE-STATE: key the state consumed below, rather than
    // stale bindings left by preceding draws. Keep the caller's state untouched.
    PipelineKey effective = key;
    bool attributes_used[16] = {}, streams_used[16] = {};
    effective.attrib_count = 0;
    if (key.vs)
        for (const ShaderIo& input : key.vs->refl.inputs) {
            if (input.location >= 16 || input.location >= key.attrib_count) continue;
            attributes_used[input.location] = true;
            effective.attrib_count = std::max(effective.attrib_count, input.location + 1);
            const auto& attribute = key.attribs[input.location];
            if (attribute.stream < 15 && vk_vertex_format(attribute.format) != VK_FORMAT_UNDEFINED)
                streams_used[attribute.stream] = true;
        }
    for (size_t i = 0; i < 16; ++i) {
        if (!attributes_used[i]) effective.attribs[i] = {};
        if (!streams_used[i]) effective.streams[i] = {};
        else effective.streams[i].divisor = effective.streams[i].divisor ? 1 : 0;
    }
    // stream_count is not consulted: bindings are selected by the attributes.
    effective.stream_count = 0;
    // The current Vulkan encoder has neither an alpha test nor a logic op.
    effective.color.alpha_test = effective.color.logic_op = 0;
    for (size_t i = 0; i < 8; ++i) {
        effective.blend[i].target = 0; // array position selects the attachment
        if (i >= key.color_count) {
            effective.blend[i] = {};
            effective.color.blend_enable[i] = 0;
            effective.mask.mask[i] = 0;
            effective.color_formats[i] = VK_FORMAT_UNDEFINED;
            effective.ufloat_colors &= ~(1u << i);
        } else {
            effective.mask.mask[i] &= 0xF;
            effective.color.blend_enable[i] = effective.color.blend_enable[i] ? 1 : 0;
            if (!effective.color.blend_enable[i]) {
                effective.blend[i] = {};
                effective.ufloat_colors &= ~(1u << i);
            }
        }
    }
    ByteKey<sizeof(PipelineKey)> result;
    std::memcpy(result.b, &effective, sizeof effective);'''

DIAGNOSTIC_CHANGES = [
    (b'    const std::string vs_h = key.vs ? key.vs->hash : "-", fs_h = key.fs ? key.fs->hash : "-";\n',
     b'    // PATCH-PIPELINE-DIFF-HOT-PATH: shader names are read only inside diagnostic branches.\n'),
    (b'        prev_vs = vs_h, prev_fs = fs_h, have_prev = true;',
     b'        prev_vs = key.vs ? key.vs->hash : "-";\n        prev_fs = key.fs ? key.fs->hash : "-";\n        have_prev = true;'),
    (b'''    // PATCH-PIPE-DIFF-BEGIN: the first differing field against the key the previous draw used.
    if (diff) {
        struct Field''',
     b'''    // PATCH-PIPE-DIFF-BEGIN: the first differing field against the key the previous draw used.
    if (diff) {
        const std::string vs_h = key.vs ? key.vs->hash : "-", fs_h = key.fs ? key.fs->hash : "-";
        struct Field'''),
]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home()/'sp2port'))))
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    path = args.root/'runtime/src/nvn/nvn_pipeline.cpp'
    data = path.read_bytes()
    result = data
    for old, new in [(ANCHOR, REPLACEMENT), *DIAGNOSTIC_CHANGES]:
        if result.count(new) == 1:
            result = result.replace(new, old if args.restore else new, 1)
        elif result.count(old) == 1:
            result = result.replace(old, old if args.restore else new, 1)
        else:
            raise SystemExit('Pipeline key anchor mismatch; no files changed')
    if args.check:
        print('Preflight passed')
        return
    path.write_bytes(result)
    print('Restored' if args.restore else 'Applied; rebuild nvn_pipeline.cpp')

if __name__ == '__main__':
    main()
