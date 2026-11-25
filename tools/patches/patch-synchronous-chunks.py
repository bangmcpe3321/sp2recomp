#!/usr/bin/env python3
"""Opt-in command chunks that preserve full synchronous submit completion."""
from pathlib import Path
import argparse,os
CHANGES={'runtime/src/nvn/nvn_frames.cpp': [('FrameTimes& frame_times() { return g_times; }', '// PATCH-SYNC-CHUNKS: overlap recording/execution, but retire the entire submit before return.\nbool synchronous_chunks() {\n    static const bool requested = [] {\n        const char* e = std::getenv("NX_SYNC_CHUNKS");\n        return e && e[0] == \'1\' && e[1] == 0;\n    }();\n    return requested && !async_gpu();\n}\n\nFrameTimes& frame_times() { return g_times; }'), ('    if (!pipelined()) free_retired_images(g_completed);', '    if (!pipelined() && !synchronous_chunks()) free_retired_images(g_completed); // PATCH-SYNC-CHUNKS'), ('    else\n        log("nvn/vk: asynchronous submits (NX_ASYNC_GPU): %u frames in flight, %u slots", frames, g_slot_count);', '    else if (synchronous_chunks())\n        log("nvn/vk: synchronous command chunks: complete submit waited before returning");\n    else\n        log("nvn/vk: asynchronous submits (NX_ASYNC_GPU): %u frames in flight, %u slots", frames, g_slot_count);')], 'runtime/src/nvn/nvn_vk.h': [('bool async_gpu();', 'bool async_gpu();\nbool synchronous_chunks(); // PATCH-SYNC-CHUNKS: full-submit completion retained')], 'runtime/src/nvn/nvn_vk.cpp': [("    if (async_gpu())\n        frame_init(g_pool, g_family, g_upload, g_upload_ptr, g_upload_size);  // the upload buffer: the slots' ring\n    else\n        g_descriptors = make_descriptor_pool();", '    if (async_gpu() || synchronous_chunks()) // PATCH-SYNC-CHUNKS\n        frame_init(g_pool, g_family, g_upload, g_upload_ptr, g_upload_size);\n    if (!async_gpu())\n        g_descriptors = make_descriptor_pool();'), ('    if (async_gpu()) return (g_cb = frame_begin(replay)) != VK_NULL_HANDLE;\n    p_vkResetCommandBuffer(g_cb, 0);', '    // PATCH-SYNC-CHUNKS: presentation keeps its own original command buffer.\n    static const VkCommandBuffer legacy_cb = g_cb;\n    if (async_gpu() || (replay && synchronous_chunks()))\n        return (g_cb = frame_begin(replay)) != VK_NULL_HANDLE;\n    g_cb = legacy_cb;\n    p_vkResetCommandBuffer(g_cb, 0);'), ("    if (async)  // the profile, zero-draw queries and snapshots read this submit's results right below: waited for\n        frame_submit(VK_NULL_HANDLE, VK_NULL_HANDLE, draw_take_write_backs(),\n                     gpu_profile_on() || zero_draws_on() || debug_snapshots_pending());", '    if (async || synchronous_chunks()) // PATCH-SYNC-CHUNKS: all parts retire before a synchronous return\n        frame_submit(VK_NULL_HANDLE, VK_NULL_HANDLE, draw_take_write_backs(),\n                     !async || gpu_profile_on() || zero_draws_on() || debug_snapshots_pending());')]}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(os.environ.get('SP2PORT',str(Path.home()/'sp2port'))));p.add_argument('--restore',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args()
 pending=[];states=[]
 for name,changes in CHANGES.items():
  path=a.root/name;data=path.read_bytes()
  for old,new in changes:
   choices=[]
   for nl in (b'\n',b'\r\n'):
    left=old.encode().replace(b'\n',nl);right=new.encode().replace(b'\n',nl)
    if data.count(right)==1:choices.append((right,left if a.restore else right,True))
   if not choices:
    for nl in (b'\n',b'\r\n'):
     left=old.encode().replace(b'\n',nl);right=new.encode().replace(b'\n',nl)
     if data.count(left)!=1:continue
     if b'\n' not in left:
      end=data.index(left)+len(left);local=b'\r\n' if data[end:end+2]==b'\r\n' else b'\n'
      if nl!=local:continue
     choices.append((left,left if a.restore else right,False))
   choices=list(dict.fromkeys(choices))
   if len(choices)!=1:raise SystemExit('Synchronous chunk source mismatch: '+name+'; no files changed')
   before,after,state=choices[0];data=data.replace(before,after,1);states.append(state)
  pending.append((path,data))
 if len(set(states))!=1:raise SystemExit('Partial synchronous chunk patch; no files changed')
 if a.check:print('Preflight passed');return
 for path,data in pending:path.write_bytes(data)
 print('Restored' if a.restore else 'Applied; rebuild nvn_vk.cpp and nvn_frames.cpp')
if __name__=='__main__':main()
