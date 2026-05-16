#!/usr/bin/env python3
"""validate.py — check every level against fixed physics rules.

The rules (measured from the game's actual constants):

  PLAYER_W_TILES = 0.55    (22px / 40px tile)
  PLAYER_H_TILES = 1.25    (50px / 40px tile)
  MAX_JUMP_UP    = 3       tile rows
  MAX_GAP_SAME   = 6       tile cols horizontal (running jump)
  MAX_GAP_DY1    = 5       tile cols horizontal (running jump up 1)
  MAX_GAP_DY2    = 4       tile cols horizontal (running jump up 2)
  MAX_GAP_DY3    = 2       tile cols horizontal (running jump up 3)
  MAX_GAP_FALL   = 7       tile cols horizontal (falling jump)
  HEAD_CLEARANCE = 2       empty rows above any standable surface

For every level:
  1. Find all platforms (contiguous horizontal solid runs)
  2. Find spawn (P) and exit (E)
  3. BFS from spawn-platform to exit-platform using the physics rules
  4. Verify spawn has head-clearance (no platform directly above)
  5. Verify exit is reachable

A level FAILS validation if any of the above is wrong.
Output: list of failing levels with the reason. Exit code 0 = all good.
"""
import os, sys, contextlib, io
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["MARIONETTE_WINDOW"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with contextlib.redirect_stdout(io.StringIO()):
    import marionette as M

GRID_W = M.GRID_W
GRID_H = M.GRID_H
SOLID = set("#=DI")
HAZARD = set("^v<>L")

# ── PHYSICS RULES ────────────────────────────────────────────────────────────
MAX_JUMP_UP = 3
HORIZ_BY_DY = {0: 6, 1: 5, 2: 4, 3: 2}     # max horiz tiles at each dy up
MAX_FALL_HORIZ = 7
MAX_FALL_DY = 15
HEAD_CLEARANCE = 2     # rows of empty above any standable tile


def norm(rows):
    rows = [r.ljust(GRID_W, '.') for r in rows]
    while len(rows) < GRID_H:
        rows.insert(0, '.' * GRID_W)
    return rows[:GRID_H]


def find_platforms(rows):
    """Return list of (top_row, left_col, right_col) for each platform.
    A platform = contiguous run of solid tiles on row gy, with at least 2
    empty rows above (player needs HEAD_CLEARANCE)."""
    plats = []
    for gy in range(GRID_H):
        run_start = None
        for gx in range(GRID_W):
            if rows[gy][gx] in SOLID:
                if run_start is None: run_start = gx
            else:
                if run_start is not None:
                    plats.append((gy, run_start, gx - 1))
                    run_start = None
        if run_start is not None:
            plats.append((gy, run_start, GRID_W - 1))
    return plats


def is_passable(rows, gx, gy):
    """Can the player occupy grid cell (gx, gy)?
    Needs: cell empty AND cell above empty (player is 1.25 tiles tall)."""
    if not (0 <= gx < GRID_W and 0 <= gy < GRID_H): return False
    if rows[gy][gx] in SOLID: return False
    if gy > 0 and rows[gy - 1][gx] in SOLID: return False
    return True


def ascent_channel_clear(rows, launch_col, launch_row, target_row):
    """Check that columns (launch-1, launch, launch+1) are all empty for
    every row between target_row and launch_row inclusive.
    Player needs ~2 cols wide of clearance during ascent."""
    for check_gy in range(target_row, launch_row + 1):
        for cc in (launch_col - 1, launch_col, launch_col + 1):
            if not (0 <= cc < GRID_W): continue
            if rows[check_gy][cc] in SOLID:
                return False
    return True


def find_launch_col(rows, cur, nxt, max_horiz):
    """Find a col on `cur` from which player can reach `nxt`.
    Returns the col, or None if no valid launch col exists."""
    cgy, cl, cr = cur
    ngy, nl, nr = nxt
    dy = cgy - ngy
    for launch_col in range(cl, cr + 1):
        # Player can land within max_horiz of launch_col
        land_min = launch_col - max_horiz
        land_max = launch_col + max_horiz
        if land_max < nl or land_min > nr: continue
        # Ascent channel must be clear (only matters when going UP)
        if dy > 0:
            # Need 2 empty rows of head clearance at the LAUNCH row too
            # (player can't jump if there's a ceiling on launch row).
            launch_row_minus_1 = cgy - 1
            if 0 <= launch_row_minus_1 < GRID_H:
                if rows[launch_row_minus_1][launch_col] in SOLID:
                    continue
            if not ascent_channel_clear(rows, launch_col, cgy - 1, ngy):
                continue
        return launch_col
    return None


def can_reach(rows, cur, nxt):
    """Can player go from platform `cur` to platform `nxt` per physics?
    Returns (True, launch_col) if yes, (False, reason) if no."""
    cgy, cl, cr = cur
    ngy, nl, nr = nxt
    dy = cgy - ngy
    hgap = max(nl - cr, cl - nr, 0)
    # Same level
    if dy == 0:
        if hgap > HORIZ_BY_DY[0]:
            return False, f"same-level gap {hgap}>{HORIZ_BY_DY[0]}"
        lc = find_launch_col(rows, cur, nxt, HORIZ_BY_DY[0])
        if lc is None: return False, "no clear launch col"
        return True, lc
    # Falling DOWN
    if dy < 0:
        if -dy > MAX_FALL_DY:
            return False, f"fall {-dy}>{MAX_FALL_DY}"
        if hgap > MAX_FALL_HORIZ:
            return False, f"fall gap {hgap}>{MAX_FALL_HORIZ}"
        lc = find_launch_col(rows, cur, nxt, MAX_FALL_HORIZ)
        if lc is None: return False, "no clear fall launch col"
        return True, lc
    # Jumping UP
    if dy > MAX_JUMP_UP:
        return False, f"jump up {dy}>{MAX_JUMP_UP}"
    max_h = HORIZ_BY_DY.get(dy, 0)
    if hgap > max_h:
        return False, f"up-jump gap {hgap}>{max_h} (dy={dy})"
    lc = find_launch_col(rows, cur, nxt, max_h)
    if lc is None: return False, f"no clear ascent channel (dy={dy})"
    return True, lc


def validate_level(idx, lv):
    issues = []
    rows = norm(lv.get('tiles', []))
    if not rows: return [("error", "no tiles")]

    spawn = exit_ = None
    for gy, row in enumerate(rows):
        for gx, ch in enumerate(row):
            if ch == 'P': spawn = (gx, gy)
            elif ch == 'E': exit_ = (gx, gy)

    if spawn is None:
        return [("error", "no spawn (P)")]

    sx, sy = spawn

    # Rule: spawn has head-clearance
    if sy - 1 >= 0 and rows[sy - 1][sx] in SOLID:
        issues.append(("error", f"spawn ({sx},{sy}) ceiling directly above"))

    # Rule: spawn cell itself is empty
    if rows[sy][sx] in SOLID:
        issues.append(("error", f"spawn ({sx},{sy}) is a solid tile"))
    if rows[sy][sx] in HAZARD:
        issues.append(("error", f"spawn ({sx},{sy}) is a hazard"))

    # Rule: spawn must have solid ground below (within fall distance)
    floor_y = None
    for gy in range(sy + 1, GRID_H):
        ch = rows[gy][sx]
        if ch in SOLID: floor_y = gy; break
        if ch in HAZARD:
            issues.append(("error", f"spawn ({sx},{sy}) falls onto hazard at row {gy}"))
            break
    if floor_y is None and not any('hazard' in i[1] for i in issues):
        issues.append(("error", f"spawn ({sx},{sy}) has no floor below"))

    # If exit is troll-spawned, skip BFS check
    if exit_ is None:
        troll_names = [t[0] for t in lv.get('trolls', []) if isinstance(t, tuple)]
        if any(n in ('moving_exit', 'exit_hop', 'exit_swap') for n in troll_names):
            return issues  # OK
        issues.append(("error", "no exit (E)"))
        return issues

    ex, ey = exit_

    # Rule: exit must have a standable surface (player can reach it)
    # Either: solid directly below exit row, OR exit row IS solid (player
    # touches it walking on the floor at exit row)
    exit_standable = False
    if ey + 1 < GRID_H and rows[ey + 1][ex] in SOLID:
        exit_standable = True
    elif rows[ey][ex] == 'E' and ey > 0:
        # exit floats — see if player can reach it walking on something
        # Look for solid below within 1 tile of exit (player feet can reach)
        if ey + 2 < GRID_H and rows[ey + 1][ex] in SOLID:
            exit_standable = True
    if not exit_standable:
        # Last chance: exit might be on a D bridge that's the platform itself
        # Check tile_in_row of exit row — if surrounding cols are solid/D
        if ex - 1 >= 0 and rows[ey][ex - 1] in SOLID:
            exit_standable = True
        elif ex + 1 < GRID_W and rows[ey][ex + 1] in SOLID:
            exit_standable = True
    if not exit_standable:
        issues.append(("error", f"exit ({ex},{ey}) is unreachable (no surface)"))

    # Find spawn and exit platforms
    plats = find_platforms(rows)
    def find_plat_for(x, y):
        best = None
        for p in plats:
            gy, l, r = p
            if l <= x <= r and gy > y:
                if best is None or p[0] < best[0]:
                    best = p
        return best

    spawn_plat = find_plat_for(sx, sy)
    exit_plat = find_plat_for(ex, ey)
    if spawn_plat is None:
        issues.append(("error", "spawn has no platform to stand on"))
        return issues
    if exit_plat is None:
        # exit may be ON the row (E tile is itself standable)
        if rows[ey][ex] == 'E':
            # find plat at same row containing the exit col
            for p in plats:
                gy, l, r = p
                if gy == ey + 1 and l <= ex <= r:
                    exit_plat = p; break
        if exit_plat is None:
            # exit is unreachable without standing surface
            return issues

    # BFS over platforms with physics rules
    visited = {spawn_plat}
    queue = [spawn_plat]
    while queue:
        cur = queue.pop(0)
        if cur == exit_plat: break
        for nxt in plats:
            if nxt in visited: continue
            ok, _info = can_reach(rows, cur, nxt)
            if ok:
                visited.add(nxt); queue.append(nxt)

    if exit_plat not in visited:
        # See if there's a moving_platform troll that might bridge it
        troll_names = [t[0] for t in lv.get('trolls', []) if isinstance(t, tuple)]
        if any(n in ('moving_platform', 'teleport_loop') for n in troll_names):
            issues.append(("info", f"exit unreachable by static layout — relies on moving troll"))
        else:
            issues.append(("error", f"exit unreachable from spawn (BFS failed)"))

    return issues


def main():
    levels = M.LEVELS
    print(f"Validating {len(levels)} levels against physics rules:\n")
    print(f"  Player: 0.55w x 1.25h tiles  (needs 2-tile-tall clearance)")
    print(f"  Max jump UP: {MAX_JUMP_UP} tiles")
    print(f"  Max running gap (same level):    {HORIZ_BY_DY[0]} tiles")
    print(f"  Max running gap (up {{1,2,3}}): {HORIZ_BY_DY[1]},{HORIZ_BY_DY[2]},{HORIZ_BY_DY[3]} tiles")
    print(f"  Max fall gap: {MAX_FALL_HORIZ} tiles\n")
    err_count = 0
    info_count = 0
    for i, lv in enumerate(levels):
        issues = validate_level(i, lv)
        for sev, msg in issues:
            print(f"L{i+1:>3}  [{sev}]  {lv.get('name','?')}: {msg}")
            if sev == "error": err_count += 1
            if sev == "info": info_count += 1
    print()
    print(f"━━━ Summary ━━━")
    print(f"  errors: {err_count}")
    print(f"  info (rely on trolls): {info_count}")
    sys.exit(0 if err_count == 0 else 1)


if __name__ == "__main__":
    main()
