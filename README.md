# MARIONETTE

A diabolical 2D troll-platformer in the spirit of Level Devil — built in a
single Python file. 120 hand-crafted levels across 8 acts of escalating cruelty.

```
120 levels, 8 acts, ~6400 lines of single-file Python
35+ unique troll mechanics — floor drops, fake exits, gravity flip,
control invert, warden hands, mirror world, teleport loops,
reactive ambush spikes/saws/ceilings, snap-kill dwell zones, ...
the Warden — an unhinged narrator who mocks, whispers, threatens
persistent blood-pool death marks · gamepad support · fullscreen by default
```

You are a little black stickman. The Warden designs each room. The Warden
hates you.

---

## One-command install (any Linux, macOS, or Termux)

```sh
curl -sL https://raw.githubusercontent.com/the-priest/marionette/main/install.sh | sh
```

The installer:

- detects your OS and package manager (apt, dnf, pacman, zypper, apk,
  xbps, emerge, brew, pkg on Termux)
- installs whatever's missing: `git`, `python3`, `pip`, `pygame`
- clones the repo to `~/marionette`
- creates a `mari` command on your PATH
- creates an app-launcher entry with icon (Linux desktops)

Tap the icon, or run:

```sh
mari
```

## Update

Just re-run the installer — it's idempotent and force-syncs the clone
to whatever's on `main`:

```sh
curl -sL https://raw.githubusercontent.com/the-priest/marionette/main/install.sh | sh
```

---

## Controls

### Keyboard

```
A / D / arrows         move
Space / W / Up         jump
R                      restart current level
F                      toggle fullscreen
F1                     skip dialogue
F2                     level select (after first death)
Esc / Q                quit
```

### Gamepad (Xbox / 8BitDo layout, auto-detected, hot-plug)

```
Left stick / D-pad     move
A (btn 0)              jump / confirm
B / X (btn 1/2)        restart
Y (btn 3)              level select
Start (btn 7)          advance dialogue
Back (btn 6)           quit
LB / RB (btn 4/5)      level-select navigation
```

---

## Difficulty

Open `marionette.py` and edit the `DIFF` constant near the top:

```
DIFF = 0.70    # default — 30% faster than baseline
DIFF = 0.50    # masochism mode
DIFF = 1.00    # the original, gentler timings
```

This scales every time-based hazard.

---

## Save data

`~/.local/share/marionette/save.json`

Reset: `rm ~/.local/share/marionette/save.json`

---

## Verifying solvability

`solver.py` runs two passes:

1. **Static**: spawn isn't buried, no ceiling above spawn, spawn floor isn't a spike.
2. **Dynamic BFS**: simulates the player's physics envelope and proves
   the exit is reachable from spawn using only the static tile layout.
   Levels that require moving platforms are flagged for manual review.

```sh
python3 solver.py
```

All 120 levels currently pass.

---

## License

MIT.
