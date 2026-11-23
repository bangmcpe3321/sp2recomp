#!/usr/bin/env python3
"""Run CPU-only sanitizer regressions against the patched external runtime (Linux/WSL)."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path,
                        default=Path(os.environ.get('SP2PORT', str(Path.home() / 'sp2port'))))
    args = parser.parse_args()
    root = args.root.resolve()
    if not shutil.which('g++'):
        parser.error('g++ with C++20, AddressSanitizer and UndefinedBehaviorSanitizer is required')
    tests = [
        ('test_gameplay_options.py', 'runtime/src/sp2_gameplay_options.h'),
        ('test_switch_pro_lifecycle.py', 'runtime/src/switch_pro_win.h'),
        ('test_switch_pro_mapping.py', 'runtime/src/switch_pro_mapping.h'),
        ('test_controller_motion.py', 'runtime/src/controller_motion.h'),
        ('test_submit_wait_safety.py', 'runtime/src/nvn/nvn_queue.cpp'),
        ('test_scalable_font_missing_fallback.py', 'gen/main/code_417.cpp'),
        ('test_tutorial_sixaxis.py', 'runtime/src/hle_hid.cpp'),
        ('test_linear_texture_readback.py', 'runtime/src/nvn/nvn_upload.cpp'),
        ('test_image_cache.py', 'runtime/src/nvn/nvn_image.cpp'),
        ('test_block_attachment.py', 'runtime/src/nvn/nvn_pipeline.cpp'),
        ('test_instance_chunk.py', 'runtime/src/nvn/nvn_draw.cpp'),
        ('test_integer_shader_io.py', 'runtime/src/nvn/nvn_spirv_patch.cpp'),
        ('test_sampler_copies.py', 'runtime/src/nvn/nvn_sampler_objects.cpp'),
        ('test_texture_copies.py', 'runtime/src/nvn/nvn_copy.cpp'),
        ('test_cache_texture_readiness.py', 'runtime/src/nvn/nvn_pipeline.cpp'),
        ('test_stable_sine.py', 'runtime/src/nvn/nvn_spirv_patch.cpp'),
        ('test_zero_texture_upload.py', 'runtime/src/nvn/nvn_pipeline.cpp'),
        ('test_native_depth_tolerance.py', 'runtime/src/nvn/nvn_raster.cpp'),
        ('test_draw_trace_fastpath.py', 'runtime/src/nvn/nvn_draw_trace.cpp'),
        ('test_stall_sampler_optin.py', 'runtime/src/kernel_watch.cpp'),
        ('test_frame_stats_gate.py', 'runtime/src/frame_stats.cpp'),
        ('test_present_pacing_stats.py', 'runtime/src/nvn/nvn_queue.cpp'),
        ('test_gpu_counter_timestamps.py', 'runtime/src/nvn/nvn_counter_timestamps.h'),
        ('test_gpu_occlusion_counters.py', 'runtime/src/nvn/nvn_counter_timestamps.h'),
        ('test_pipeline_cache_persistence.py', 'runtime/src/nvn/nvn_pipeline_cache.cpp'),
        ('test_pipeline_lru.py', 'runtime/src/nvn/pipeline_lru.h'),
        ('test_pipeline_key_padding.py', 'runtime/src/nvn/nvn_pipeline.cpp'),
        ('test_frame_time_capture.py', 'runtime/src/nvn/nvn_vk.cpp'),
        ('test_fps_overlay.py', 'runtime/src/platform_win.cpp'),
        ('test_mouse_movement.py', 'runtime/src/platform_win.cpp'),
        ('test_mouse_gyro.py', 'runtime/src/mouse_gyro.h'),
        ('test_unit_point.py', None),
    ]
    for _, source in tests:
        if source and not (root / source).is_file():
            parser.error(f'missing runtime source: {root / source}')
    directory = Path(__file__).resolve().parent / 'tests/tutorial'
    for name, source in tests:
        print(f'Running {name}', flush=True)
        subprocess.run([sys.executable, str(directory / name),
                        str(root / source) if source else str(root)], check=True)
    print(f'PASS: all {len(tests)} tutorial runtime sanitizer regressions')


if __name__ == '__main__':
    main()
