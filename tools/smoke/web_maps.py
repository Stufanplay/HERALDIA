"""Heraldia markers on the web maps, on a real dedicated 26.3 server (complements server_smoke.py).

Usage: python3 tools/smoke/web_maps.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"

1. With no web map: the mod registers nothing ("Heraldia: mapas web" does not appear in the log and its file is not written in the
   world) and /heraldia webmap refresh answers that there is no map.
2. With squaremap (pinned Modrinth version, checked against its sha512) and Carpet (simulated player):
   - /locate is used to find a medium structure and a village and their chunks are generated with /forceload: both enter
     the registry (the world's heraldia_mapas_web.json) when those chunks load;
   - with mapas_web.solo_descubiertas (default) squaremap shows none: its layers are there, empty;
   - the simulated player enters the medium structure: gets its advancement and, with nothing else done, its marker appears in
     squaremap (layer, position, icon and name in the language of web_maps.language); the village still does not appear;
   - with mapas_web.solo_descubiertas = false and /heraldia reload the village also appears; with the villages' layer
     turned off, its layer disappears from the map;
   - after restarting, the markers appear again without loading those chunks (from the world's file).
squaremap serves the layers at http://127.0.0.1:<port>/tiles/minecraft_overworld/markers.json (it rebuilds them every 5 s).
"""
import argparse, json, os, queue, shutil, subprocess, sys, threading, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from modrinth import MODS, Mod, fetch

# squaremap (server web map) pinned for this test (python3 tools/smoke/modrinth.py --find squaremap); it is not
# in modrinth.MODS so as not to affect the compatibility tests (COMPAT_PATHS of tools/test.py).
SQUAREMAP = Mod("squaremap", "1.4.3", "squaremap-fabric-mc26.3-1.4.3.jar",
                "https://cdn.modrinth.com/data/PFb7ZqK6/versions/YPMtDS9D/squaremap-fabric-mc26.3-1.4.3.jar",
                "c20e76d91a1c3a26d1985240c4199b6955180a6fbaf2f13bef25e06dd9c2c01df22d51a845f4bd2d36aa953559c29532ec8c3390432fb3faa34e73bff00d8533")
CARPET = MODS["carpet"]
PLAYER = "Cartografa"
LAYERS = ["unicas", "aldeas", "medianas", "minas", "costa", "arena"]
REGISTRY = "heraldia_mapas_web.json"
_LOCATE = r"is at \[(-?\d+), [~\d-]+, (-?\d+)\]|Could not find|There is no structure"


class WebServer:
    def __init__(self, work, launcher):
        self.work = work
        self.proc = subprocess.Popen(["java", "-Xmx2G", "-jar", launcher, "nogui"], cwd=work, text=True,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.lines, self.seen = queue.Queue(), []
        threading.Thread(target=s.reader, args=(self.proc, self.lines), daemon=True).start()
        self.ctx = s.Context(self.proc, self.lines, self.seen)

    def wait(self, pattern, timeout=s.START_TIMEOUT_S):
        return s.wait_for(self.lines, pattern, timeout, self.seen)

    def run(self, cmd, ok):
        return self.ctx.run(cmd, ok)

    def log(self):
        return "".join(self.seen)

    def halt(self):
        if self.proc.poll() is None:
            s.send(self.proc, "stop")
            try:
                self.proc.wait(timeout=180)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        s.pending(self.lines, self.seen)


def config(work, **web_maps):
    """config/heraldia.json of the tests with the given mapas_web options (the layers, in "capas")."""
    cfg = json.loads(json.dumps(s.TEST_CONFIG))
    cfg.pop("inventada", None)
    # the published keys are Spanish (mapas_web.solo_descubiertas, mapas_web.capas.<layer>): T47c translated these
    # arguments and the mod ignored them ("opción desconocida")
    keys = {"only_discovered": "solo_descubiertas", "layers": "capas"}
    cfg["mapas_web"] = {"idioma": "es_es", **{keys.get(k, k): v for k, v in web_maps.items()}}
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def squaremap_config(work):
    """squaremap's config.yml with its web server on a free port (so several tests can be launched at once) and without
    checking for new versions; squaremap fills in the rest. Returns the port."""
    port = s.free_port()
    os.makedirs(os.path.join(work, "squaremap"), exist_ok=True)
    with open(os.path.join(work, "squaremap", "config.yml"), "w") as f:
        f.write("config-version: 3\nsettings:\n    update-checker: false\n    internal-webserver:\n        enabled: true\n"
                f"        bind: 127.0.0.1\n        port: {port}\n")
    return port


def layers(port):
    """{Heraldia layer id: layer} from the Overworld markers.json served by squaremap (empty if it does not have it yet).
    squaremap 1.4 does not write it to disk: it serves it from memory with its web server."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/tiles/minecraft_overworld/markers.json", timeout=5) as r:
            dataset = json.load(r)
    except (OSError, ValueError):
        return {}
    return {c["id"][len("heraldia_"):]: c for c in dataset if str(c.get("id", "")).startswith("heraldia_")}


def wait_layers(port, cond, timeout=120):
    """Waits for markers.json to satisfy `cond` (squaremap rebuilds it every few seconds); returns its layers."""
    end = time.monotonic() + timeout
    while True:
        c = layers(port)
        if cond(c):
            return c
        if time.monotonic() > end:
            return c
        time.sleep(1)


def ids(layer):
    return sorted(m.get("tooltip", "") for m in layer.get("markers", []))


def registry(work):
    f = os.path.join(work, "world", REGISTRY)
    if not os.path.isfile(f):
        return []
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)["sitios"]


def wait_registry(work, cond, timeout=120):
    end = time.monotonic() + timeout
    while True:
        r = registry(work)
        if cond(r) or time.monotonic() > end:
            return r
        time.sleep(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-mapas-web"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    jar = os.path.abspath(a.jar)
    fails = []

    def check(desc, ok, detail=""):
        print(f"[{'OK' if ok else 'FALLO'}] {desc}" + (f": {detail}" if detail and not ok else ""))
        if not ok:
            fails.append(desc)
        return ok

    es = jar_lang(jar)

    # --- 1. no web maps ---
    print("== no web maps")
    launcher = s.prepare(a.work, jar, s.gradle_properties())
    config(a.work)
    srv = WebServer(a.work, launcher)
    try:
        srv.wait(r"Heraldia: (\d+) estructuras registradas")
        m = srv.run("heraldia webmap refresh", r"mapa web|web map|Unknown|Incorrect")
        check("sin mapas, /heraldia webmap refresh dice que no hay ninguno", "web" in m.group(0) and "Unknown" not in m.group(0),
              m.group(0))
        srv.run("forceload add 0 0 47 47", r"Marked|Added|chunks? .*force")
        srv.ctx.ticks(40)
    finally:
        srv.halt()
    check("sin mapas, nada en el log de los mapas web", "Heraldia: mapas web" not in srv.log())
    check("sin mapas, no escribe su fichero en el mundo", not os.path.exists(os.path.join(a.work, "world", REGISTRY)))

    # --- 2. with squaremap ---
    print("== with squaremap")
    launcher = s.prepare(a.work, jar, s.gradle_properties())
    shutil.rmtree(os.path.join(a.work, "squaremap"), ignore_errors=True)
    port = squaremap_config(a.work)
    for m in (SQUAREMAP, CARPET):
        shutil.copy(fetch(a.work, m.file, m.url, m.sha512), os.path.join(a.work, "mods"))
    config(a.work)
    srv = WebServer(a.work, launcher)
    sites = {}
    try:
        srv.wait(r"Heraldia: mapas web: squaremap")
        srv.wait(r"Heraldia: (\d+) estructuras registradas")
        for category, sel in (("medianas", "#heraldia:medianas"), ("aldeas", "#heraldia:aldeas")):
            m = srv.run(f"locate structure {sel}", _LOCATE)
            if not check(f"/locate encuentra una {category}", m.group(1) is not None, m.group(0)):
                continue
            x, z = int(m.group(1)), int(m.group(2))
            srv.run(f"forceload add {x - 16} {z - 16} {x + 16} {z + 16}", r"Marked|Added|chunks? .*force")
            sites[category] = (x, z)
        reg = wait_registry(a.work, lambda r: {e["capa"] for e in r} >= set(sites))
        check("las estructuras generadas entran en el registro del mundo", {e["capa"] for e in reg} >= set(sites),
              json.dumps(reg)[:400])
        c = wait_layers(port, lambda c: set(c) >= set(LAYERS))
        check(f"squaremap tiene las {len(LAYERS)} capas de Heraldia", set(c) >= set(LAYERS), sorted(c))
        check("las capas llevan su nombre traducido", c.get("unicas", {}).get("name") == es.get("heraldia.mapas_web.capa.unicas"),
              str(c.get("unicas", {}).get("name")))
        check("con solo_descubiertas, nada sin descubrir", all(not v.get("markers") for v in c.values()),
              {k: len(v.get("markers", [])) for k, v in c.items()})
        medium = next((e for e in reg if e["capa"] == "medianas"), None)
        if medium:
            s.require_carpet(srv)
            srv.run(f"player {PLAYER} spawn at {medium['x']} {medium['y']} {medium['z']}", r"joined the game|already")
            s.send(srv.proc, f"gamemode creative {PLAYER}")     # no suffocation or falls; it does not always answer on the console
            c = wait_layers(port, lambda c: c.get("medianas", {}).get("markers"))
            marks = c.get("medianas", {}).get("markers", [])
            check("al descubrir la mediana sale su marcador sin hacer nada más", len(marks) == 1, marks)
            if marks:
                mk = marks[0]
                name = es.get(f"heraldia.medianas.{medium['sub']}.nombre")
                check("el marcador está en la estructura", abs(mk["point"]["x"] - medium["x"]) <= 1 and
                      abs(mk["point"]["z"] - medium["z"]) <= 1, mk)
                check("el marcador lleva el icono de su capa", mk.get("icon") == "heraldia_medianas", mk.get("icon"))
                check("el marcador lleva su nombre en español", name and name in mk.get("tooltip", "") and
                      name in mk.get("popup", ""), mk)
                check("y su descripción", es.get("heraldia.mapas_web.descripcion.medianas") in mk.get("popup", ""), mk)
            check("la aldea, sin descubrir, sigue sin salir", not c.get("aldeas", {}).get("markers"))
        # without solo_descubiertas: the village too
        config(a.work, only_discovered=False)
        srv.run("heraldia reload", r"[Rr]ecarg|[Rr]eload|aplicad|applied")
        c = wait_layers(port, lambda c: c.get("aldeas", {}).get("markers"))
        check("sin solo_descubiertas sale también la aldea", bool(c.get("aldeas", {}).get("markers")), c.get("aldeas"))
        village = next((e for e in reg if e["capa"] == "aldeas"), None)
        if village and c.get("aldeas", {}).get("markers"):
            mk = c["aldeas"]["markers"][0]
            fam = es.get(f"heraldia.familia.{village['sub']}", "?")
            check("la aldea se llama «Aldea: <familia>»", f"Aldea: {fam}" in mk.get("tooltip", ""), mk.get("tooltip"))
        # a turned-off layer disappears
        config(a.work, only_discovered=False, layers={"aldeas": False})
        srv.run("heraldia reload", r"[Rr]ecarg|[Rr]eload|aplicad|applied")
        c = wait_layers(port, lambda c: "aldeas" not in c and c.get("medianas", {}).get("markers"))
        check("con su capa apagada, la de las aldeas no sale", "aldeas" not in c and bool(c.get("medianas")), sorted(c))
        # the console answers in the server's language (en_us) or, without it, with the Spanish fallback
        m = srv.run("heraldia webmap refresh", r"(?:Mapas web actualizados|Web maps updated): (\d+) (?:marcadores en|markers on) "
                                              r"([^(]+) \((\d+)|Unknown|Incorrect")
        check("/heraldia webmap refresh publica y cuenta", m.group(1) is not None and "squaremap" in (m.group(2) or ""), m.group(0))
        srv.run("forceload remove all", r"Removed|No force|Unmarked|chunks")
    finally:
        srv.halt()
    log = srv.log()
    check("sin errores de los mapas web en el log", "no aceptó los marcadores" not in log and "no se pudo usar" not in log,
          "\n".join(l for l in srv.seen if "mapas web" in l)[:600])

    # --- 3. after restarting: from the world's file, without loading those chunks again ---
    print("== reinicio")
    before = len(registry(a.work))
    shutil.rmtree(os.path.join(a.work, "logs"), ignore_errors=True)
    config(a.work, only_discovered=False)
    srv = WebServer(a.work, launcher)
    try:
        m = srv.wait(r"Heraldia: mapas web: (\d+) estructuras conocidas \((\d+) del fichero\)")
        check("al arrancar lee el registro del mundo", int(m.group(2)) == before and before >= 2, m.group(0))
        c = wait_layers(port, lambda c: c.get("aldeas", {}).get("markers") and c.get("medianas", {}).get("markers"))
        check("tras reiniciar vuelven a salir los marcadores", bool(c.get("aldeas", {}).get("markers")) and
              bool(c.get("medianas", {}).get("markers")), {k: len(v.get("markers", [])) for k, v in c.items()})
    finally:
        srv.halt()
    print("WEB MAPS TEST " + ("OK" if not fails else "FALLIDA: " + ", ".join(fails)))
    return 1 if fails else 0


def jar_lang(jar):
    import zipfile
    with zipfile.ZipFile(jar) as z:
        return json.loads(z.read("assets/heraldia/lang/es_es.json"))


if __name__ == "__main__":
    sys.exit(main())
