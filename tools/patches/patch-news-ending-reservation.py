#!/usr/bin/env python3
"""Honor the news ending's original reserved duration and preserve hook registers."""
import argparse
import os
from pathlib import Path

CHANGES = {
    'runtime/src/hle_audio.cpp': [
        ('''std::atomic<uint64_t>& bgm_frames() {
  static std::atomic<uint64_t> f{0};
  return f;
}''', '''// PATCH-NEWS-ENDING-RESERVATION: the original request divides count by
// the float 60.0 at main+0x289d708, independently of broadcast frame rate.
std::atomic<uint64_t>& bgm_started_ns() {
  static std::atomic<uint64_t> started{0};
  return started;
}'''),
        ('''  bgm_frames().store(0);
  bgm_phase().store(1);''', '''  bgm_started_ns().store(plat::monotonic_ns());
  bgm_phase().store(1);'''),
        ('''  if (p == 2) return true;
  if (p != 1) return false;
  uint64_t f = bgm_frames().fetch_add(1) + 1;
  if (f < bgm_delay().load()) return false;
  bgm_phase().store(2);
  return true;''', '''  if (p == 2 || p == 3) return true;
  if (p != 1) return false;
  // Polling must not advance time: several audio callbacks can run in one
  // presented frame, or none while a conductor is absent. Keep the exact
  // count/60 reservation even in either case.
  const uint64_t started = bgm_started_ns().load();
  const uint64_t now = plat::monotonic_ns();
  const uint64_t duration = (bgm_delay().load() * 1000000000ull + 59) / 60;
  if (now < started || now - started < duration) return false;
  uint32_t waiting = 1;
  bgm_phase().compare_exchange_strong(waiting, 2);
  return bgm_phase().load() >= 2;'''),
    ],
    'gen/main/code_213.cpp': [
        ('''            nx::hle_audio_news_bgm_pending(c.x[0])) {
            c.x[0] = 1ull;
            return;
''', '''            nx::hle_audio_news_bgm_pending(c.x[0])) {
            // PATCH-NEWS-ENDING-RESERVATION: an armed delay is not completion.
            c.x[0] = nx::hle_audio_news_bgm_elapsed(c.x[0]) ? 1ull : 0ull;
            return;
'''),
    ],
    'gen/main/code_027.cpp': [
        ('''                uint64_t saved_ = c.x[0];
                c.x[0] = plaza_;
                main_009DF0B4(c);
                c.x[0] = plaza_;
                main_009DF154(c);
                nx::st<uint32_t>(plaza_ + 0x3f0ull, uint32_t(0x2u));
                c.x[0] = saved_;
''', '''                // PATCH-NEWS-ENDING-RESERVATION: this injected call is not a
                // guest call site; retain every incoming CPU register/flag.
                nx::CPU handover_ = c;
                handover_.x[0] = plaza_;
                main_009DF0B4(handover_);
                handover_.x[0] = plaza_;
                main_009DF154(handover_);
                nx::st<uint32_t>(plaza_ + 0x3f0ull, uint32_t(0x2u));
'''),
    ],
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(os.environ.get('SP2PORT', str(Path.home()/'sp2port'))))
    p.add_argument('--restore', action='store_true')
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    pending = []
    states = []
    for name, replacements in CHANGES.items():
        path = a.root/name
        data = path.read_bytes()
        for old, new in replacements:
            old, new = old.encode(), new.encode()
            if data.count(new) == 1:
                states.append(True)
                if a.restore: data = data.replace(new, old, 1)
            elif data.count(old) == 1:
                states.append(False)
                if not a.restore: data = data.replace(old, new, 1)
            else:
                raise SystemExit(f'News reservation source mismatch: {name}; no files changed')
        pending.append((path, data))
    if len(set(states)) != 1:
        raise SystemExit('Partially applied news reservation patch; no files changed')
    if a.check:
        print('Preflight passed')
        return
    for path, data in pending: path.write_bytes(data)
    print('Restored' if a.restore else 'Applied; rebuild hle_audio.cpp, code_213.cpp and code_027.cpp')


if __name__ == '__main__':
    main()
