# Inventory NFC initialization crash

Opening the inventory produced an access violation in `nn::nfp::Initialize`
after `nfp:user` command 0 returned success with no child interface. The SDK
then loaded a virtual-function table through that null pointer. The captured
guest caller was `Lp::Sys::Nfp::jobFunc` at main+0x1218714.

`tools/patches/patch-nfp-no-reader.py` adds a small NFP service through the
existing `svc_misc.cpp` object:

- The manager's command 0 returns a valid IUser child object.
- Initialize succeeds for the software interface; GetState reports its actual
  initialized/finalized state. The SDK treats failed initialization as fatal.
- ListDevices returns DeviceNotFound (`0x8073`). The game's existing worker
  recognizes this result and completes its no-reader path, rather than polling
  an empty successful list forever.
- Availability notifications return a valid, unsignaled kernel event. No NFC
  reader, tag, amiibo data or successful write operation is fabricated.
- Empty IPC response payloads avoid passing a null vector pointer to memcpy,
  including zero-byte copies.

The production CMIF parser regression exercises manager/child sessions, domain
objects, cloning, software initialization, no-reader results, event ownership
and output bounds under AddressSanitizer/UndefinedBehaviorSanitizer. Another
regression executes the game's actual generated worker and error handler. It
confirms that no-reader detection exits after one request and preserves the
guest's callee-saved registers and stack; other errors remain distinct.

```bash
python3 tools/patches/patch-nfp-no-reader.py --root "$HOME/sp2port"
python3 tools/tests/tutorial/test_nfp_no_reader_ipc.py "$HOME/sp2port"
python3 tools/tests/tutorial/test_nfp_no_reader_worker.py "$HOME/sp2port"
```

Rebuild `runtime/src/svc_misc.cpp` and `runtime/src/ipc.cpp`, then relink against
the existing object manifest. The helper supports `--check` and `--restore`;
restoration also requires rebuilding those units. Installer checks confirm
idempotence, exact round-trip restoration and no writes on failed preflight.

These regressions establish the missing-interface and supported no-reader
contracts. The user subsequently confirmed that opening and navigating the
inventory works in the Windows candidate. This service does not implement
amiibo scanning.
