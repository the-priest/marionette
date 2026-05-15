#!/usr/bin/env python3
"""solver.py — verify every Marionette level is mechanically solvable."""
import os, sys, contextlib, io, time
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["MARIONETTE_WINDOW"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with contextlib.redirect_stdout(io.StringIO()):
    import marionette as M

GRID_W = M.GRID_W; GRID_H = M.GRID_H; TILE = M.TILE
GRAV = M.GRAVITY; JUMP_V = M.JUMP_V; MOVE_V = M.MOVE_V; FPS = M.FPS
DT = 1.0 / FPS
SOLID = set("#=DI")
HAZARD = set("^v<>L")


def norm(rows):
    rows = [r.ljust(GRID_W, '.') for r in rows]
    while len(rows) < GRID_H:
        rows.insert(0, '.' * GRID_W)
    return rows[:GRID_H]


def static_check(lv):
    issues = []
    rows = norm(lv.get("tiles", []))
    spawn = exit_ = None
    for gy, row in enumerate(rows):
        for gx, ch in enumerate(row):
            if ch == 'P': spawn = (gx, gy)
            elif ch == 'E': exit_ = (gx, gy)
    if spawn is None:
        return [("error", "no spawn")]
    sx, sy = spawn
    def solid(gx, gy):
        return 0 <= gx < GRID_W and 0 <= gy < GRID_H and rows[gy][gx] in SOLID
    def hazard(gx, gy):
        return 0 <= gx < GRID_W and 0 <= gy < GRID_H and rows[gy][gx] in HAZARD
    if solid(sx, sy):
        issues.append(("error", f"spawn ({sx},{sy}) is solid"))
    if solid(sx, sy - 1):
        issues.append(("error", f"spawn ({sx},{sy}) has ceiling above"))
    if hazard(sx, sy):
        issues.append(("error", f"spawn ({sx},{sy}) is a hazard"))
    # find first solid below spawn
    floor_y = None
    for gy in range(sy + 1, GRID_H):
        if solid(sx, gy): floor_y = gy; break
        if hazard(sx, gy):
            issues.append(("error",
                f"spawn ({sx},{sy}) falls onto hazard at ({sx},{gy})"))
            break
    if floor_y is None and not any(("error" in i[0] or "hazard" in i[1])
                                    for i in issues):
        issues.append(("error", f"spawn ({sx},{sy}) has no floor below"))
    return issues


def precompute_envelope():
    JUMP_TILES = abs(JUMP_V) ** 2 / (2 * GRAV) / TILE
    AIR_TIME = 2 * abs(JUMP_V) / GRAV
    env = set()
    for sign in (-1, 1):
        x = 0.0; y = 0.0; vx = sign * MOVE_V; vy = JUMP_V
        t = 0.0
        while t <= AIR_TIME * 1.05:
            env.add((int(round(x / TILE)), int(round(y / TILE))))
            x += vx * DT; y += vy * DT; vy += GRAV * DT; t += DT
            if y > TILE * (JUMP_TILES + 1): break
    # straight-up
    x = 0.0; y = 0.0; vx = 0.0; vy = JUMP_V; t = 0.0
    while t <= AIR_TIME * 1.05:
        env.add((int(round(x/TILE)), int(round(y/TILE))))
        x += vx * DT; y += vy * DT; vy += GRAV * DT; t += DT
    # falls
    for sign in (-1, 1):
        x = 0.0; y = 0.0; vx = sign * MOVE_V; vy = 0.0; t = 0.0
        while t < 1.2:
            env.add((int(round(x/TILE)), int(round(y/TILE))))
            x += vx * DT; y += vy * DT
            vy = min(vy + GRAV * DT, M.MAX_FALL)
            t += DT
            if y > GRID_H * TILE: break
    return env

ENV = precompute_envelope()


def dyn_solvable(lv, time_budget=4.0):
    rows = norm(lv.get("tiles", []))
    spawn = exit_ = None
    for gy, row in enumerate(rows):
        for gx, ch in enumerate(row):
            if ch == 'P': spawn = (gx, gy)
            elif ch == 'E': exit_ = (gx, gy)
    if not spawn:
        return False, "no spawn"
    if not exit_:
        names = [t[0] for t in lv.get("trolls", []) if isinstance(t, tuple)]
        if any(n in ("moving_exit", "exit_hop", "exit_swap")
               for n in names):
            return True, "troll-spawned exit"
        return False, "no exit"
    # Trolls that move platforms or hands so layout-static BFS would lie
    troll_names = [t[0] for t in lv.get("trolls", []) if isinstance(t, tuple)]
    has_dynamic_path = any(n in ("moving_platform", "teleport_loop",
                                  "exit_hop", "exit_swap")
                            for n in troll_names)
    def solid(gx, gy):
        return 0 <= gx < GRID_W and 0 <= gy < GRID_H and rows[gy][gx] in SOLID
    def hazard(gx, gy):
        return 0 <= gx < GRID_W and 0 <= gy < GRID_H and rows[gy][gx] in HAZARD
    def grounded(gx, gy):
        # Player is 1.25 tiles tall — needs row gy AND gy-1 empty + floor below
        return (not solid(gx, gy)
                and not solid(gx, gy - 1)
                and solid(gx, gy + 1)
                and not hazard(gx, gy)
                and not hazard(gx, gy - 1))
    sx, sy = spawn
    start = None
    for dy in range(0, GRID_H - sy):
        if grounded(sx, sy + dy): start = (sx, sy + dy); break
    if start is None:
        # spawn might be just-in-air, snap to where they'd land
        for dy in range(0, GRID_H - sy):
            if solid(sx, sy + dy + 1): start = (sx, sy + dy); break
    if start is None:
        return False, "no grounded spawn"
    ex, ey = exit_
    visited = {start}
    queue = [start]
    t0 = time.time()
    while queue:
        if time.time() - t0 > time_budget:
            return False, "BFS timeout"
        gx, gy = queue.pop(0)
        if abs(gx - ex) <= 1 and abs(gy - ey) <= 1:
            return True, "reached exit"
        for dx, dy in ENV:
            nx, ny = gx + dx, gy + dy
            if not (0 <= nx < GRID_W and 0 <= ny < GRID_H): continue
            if solid(nx, ny) or hazard(nx, ny): continue
            if abs(nx - ex) <= 1 and abs(ny - ey) <= 1:
                return True, "reached exit"
            if not grounded(nx, ny): continue
            if (nx, ny) in visited: continue
            visited.add((nx, ny)); queue.append((nx, ny))
    return False, "exit not reachable" + (
        "  (note: this level has moving_platform troll — manual review)"
        if has_dynamic_path else "")


def main():
    levels = M.LEVELS
    static_errs = []
    print(f"=== STATIC pass ({len(levels)} levels) ===")
    for i, lv in enumerate(levels):
        for sev, msg in static_check(lv):
            print(f"L{i+1:>2} [{sev:5}] {msg}")
            if sev == "error":
                static_errs.append((i, msg))
    print(f"\n=== DYNAMIC BFS pass ===")
    dyn_fail = []
    for i, lv in enumerate(levels):
        ok, reason = dyn_solvable(lv)
        if not ok:
            print(f"L{i+1:>2} UNREACHABLE: {reason}  ({lv.get('name','?')})")
            dyn_fail.append((i, reason))
    print(f"\n━━━ Summary ━━━")
    print(f"  static errors:    {len(static_errs)}")
    print(f"  dynamic failures: {len(dyn_fail)}")
    sys.exit(0 if not (static_errs or dyn_fail) else 1)


if __name__ == "__main__":
    main()
