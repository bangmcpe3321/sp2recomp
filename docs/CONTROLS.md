# Current Windows controls

Open the launcher's **Inputs** page to change keyboard and mouse bindings. Click
an action's binding and press a key or mouse button. Esc cancels recording;
Clear unassigns that action. Restore input defaults resets this page only.
Changes save automatically and apply when the game next starts. A duplicate
assignment is allowed but reported, since it activates both actions.

F1 (mouse lock), F3 (FPS) and F11 (fullscreen) remain reserved host shortcuts.
Native controller buttons are unaffected by keyboard/mouse remapping.
The table below shows defaults.

Press **F1 once** to lock the mouse and aim without holding right mouse. Press F1
again to unlock. A right-button click/release no longer cancels an F1 lock.
Holding right mouse still provides temporary mouse look when not locked.
Switching away releases capture and clears the lock; press F1 after returning.
Mouse lock does not change shooting or controller button bindings.

Default mouse aiming is mapped to the right stick. For up/down mouse aiming,
turn Motion Controls OFF in the game's TV/Tabletop options (current docked mode).
The launcher's Mouse gyro checkbox selects six-axis mouse aiming instead.

| Keyboard / mouse | Game input | Common action |
| --- | --- | --- |
| W/A/S/D or arrow keys | Left stick | Move / menu navigation |
| Mouse movement while captured | Right stick (default) | Camera / aim |
| F | A | Confirm / interact |
| Space | B | Jump / back |
| J | X | Game menu |
| K | Y | Reset camera |
| Q | L | L action, context dependent |
| E | R | Sub weapon / bomb, where available |
| Shift or Z (hold) | ZL | Squid / swim |
| Left click or C (hold) | ZR | Shoot |
| Enter | + | Plus action, context dependent |
| Escape | − | Minus action, context dependent |
| F1 | Host mouse lock | Toggle capture |
| Right mouse (hold) | Host mouse capture | Temporary aiming |
| F3 | Host overlay | Show/hide FPS |
| F11 or Alt+Enter | Host window | Toggle fullscreen |
| [ / ] | Mouse gyro sensitivity | Decrease/increase; only in mouse gyro mode |

Keyboard D-pad and stick-click actions are unassigned by default; assign them
on the Inputs page. Arrow keys default to the left stick, not the D-pad.
Game actions depend on the scene and the game's own settings.

A native Switch Pro Controller forwards A/B/X/Y, L/R/ZL/ZR, both sticks and stick
clicks, D-pad, +/− and motion samples. Home and Capture have no game action mapped
by this port. Use the game's settings to enable physical gyro aiming.

Xbox/XInput uses Nintendo button positions: Xbox B → A, A → B, Y → X, X → Y.
LB/RB → L/R; LT/RT → ZL/ZR (trigger threshold 100/255); Start/Back → +/−;
sticks, clicks and D-pad map to the matching controls. Native Pro is preferred
when present. Keyboard inputs remain available alongside a controller.

The F1 fix is installed through `tools/patches/patch-mouse-capture-lock.py`.
Rebuild `platform_win.cpp` after applying or restoring. The event regression
covers lock/hold mixing, autorepeat, explicit unlock, focus loss, disabled or
background input and repeated lock cycles. This change keeps the accepted FPS
settings: coherent cached read-back and synchronous command chunks.

The game is not launched automatically after installation.

The PC key remap is applied with `tools/patches/patch-pc-controls.py`; rebuild
`platform_win.cpp` after applying or restoring it. Controller bindings are unchanged.

The launcher passes each action as `NX_BIND_<ACTION>` with up to four decimal
Windows virtual-key codes, or `0` to disable its keyboard/mouse binding. Missing
or invalid overrides retain runtime defaults. Saved configuration migrates old
settings by retaining current defaults. Bindings are loaded once per game start.
The runtime integration is `tools/patches/patch-launcher-inputs.py`.
