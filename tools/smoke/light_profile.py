"""Light profile ("ligero") on a real 26.3 dedicated server, restarting the same world.

Usage: python3 tools/smoke/light_profile.py --jar build/libs/heraldia-X.jar [--work build/smoke-ligero]
  1. First start without a profile in the file (TEST_CONFIG): the log has the suggestion line (memory and cores) and the
     world's generation options are recorded silently (a new world). 1,300 ticks pass (/tick sprint): the world is "already played".
  2. From the console, /heraldia config profile ligero in that world does not save anything: it explains the seams and gives
     the confirm command; with `confirm` it is saved (the file has "perfil": "ligero" and none of its options written).
  3. Restart: the light profile is in use (log, /heraldia profile with the generation reminder) and the log warns that
     world generation changed (medianas.frecuencia_porcentaje 100 → 50, ...); the suggestion is quiet (a profile is chosen).
  4. Restart again without changes: no seam warning.
Exit code 0 if everything passes.
"""
import argparse, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from guide import Server

SUGGESTION = r"Heraldia: perfil: no está elegido en config/heraldia\.json; la JVM tiene [\d.]+ GB y \d+ núcleos"
SEAMS = r"Heraldia: la generación del mundo ha cambiado desde el último arranque \(([^)]*)\)"


def read(work):
    with open(os.path.join(work, "config", "heraldia.json"), encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-ligero"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    launcher = s.prepare(a.work, os.path.abspath(a.jar), s.gradle_properties())
    fails, srv = [], None

    def check(cond, msg):
        if not cond:
            fails.append(msg)
            print("FAIL:", msg)

    def answer(ctx, cmd, finish):
        s.pending(ctx.lines, ctx.seen)
        n0 = len(ctx.seen)
        ctx.run(cmd, finish)
        ctx.run("seed", r"Seed: \[")
        return "".join(ctx.seen[n0:])

    try:
        # 1. first start: suggestion, no seam warning (a new world)
        srv = Server(a.work, launcher)
        ctx = srv.ctx
        log = ctx.log()
        check(re.search(SUGGESTION, log), "first start: no suggestion line in the log")
        check(not re.search(SEAMS, log), "first start: seam warning in a new world")
        ctx.run("tick sprint 1300", r"[Ss]print|ticks")
        end = time.monotonic() + s.TICK_TIMEOUT_S
        while ctx.gametime() < 1250:
            if time.monotonic() > end:
                raise SystemExit("the world does not reach 1,250 ticks")
            time.sleep(1)
        # 2. the panel's command from the console: explains, then confirm saves
        text = answer(ctx, "heraldia config profile ligero", r"profile ligero confirm|Unknown|Incorrect")
        check("seams" in text and "confirm" in text, f"no seam explanation before confirming: {text[-400:]!r}")
        check(read(a.work).get("perfil") == "estandar", "the light profile was saved without confirmation")
        ctx.run("heraldia config profile ligero confirm", r"configuración recargada")
        written = read(a.work)
        check(written.get("perfil") == "ligero", f"confirm did not save the light profile: {written.get('perfil')}")
        check("activado" not in written.get("aldeas", {}).get("caminos", {}) and
              "frecuencia_porcentaje" not in written.get("medianas", {}),
              "the file writes the light profile's options (they are not set by hand)")
        check(written.get("_perfil", {}).get("efectivo") == "ligero", f"_perfil.efectivo {written.get('_perfil', {}).get('efectivo')}")
        # 3. restart: in use, and the seam warning
        srv.stop()
        srv = Server(a.work, launcher)
        ctx = srv.ctx
        log = ctx.log()
        check(re.search(r"Heraldia: perfil ligero\r?\n", log), "restart: the log does not say the light profile")
        m = re.search(SEAMS, log)
        check(m and "medianas.frecuencia_porcentaje 100 → 50" in m.group(1) and "aldeas.caminos.activado true → false" in m.group(1),
              f"restart: no seam warning with what changed: {m.group(1) if m else None}")
        check(not re.search(SUGGESTION, log), "restart: the suggestion speaks although a profile is chosen")
        check(re.search(r"caminos entre aldeas desactivados", log), "restart: roads still enabled")
        text = answer(ctx, "heraldia profile", r"also changes world generation|Unknown|Incorrect")
        check("Gameplay profile: Light" in text and "also changes world generation" in text, f"/heraldia profile: {text[-400:]!r}")
        # 4. restart without changes: quiet
        srv.stop()
        srv = Server(a.work, launcher)
        check(not re.search(SEAMS, srv.ctx.log()), "second restart: seam warning without changes")
        print("light profile: suggestion, confirmation, seams and quiet restart checked")
    finally:
        if srv:
            srv.stop()
    print("LIGERO:", "OK" if not fails else fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
