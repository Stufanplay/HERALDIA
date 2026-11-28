"""New-version notice and old command names on a real dedicated 26.3 server (T35b).

Usage: python3 tools/smoke/update_check.py --jar build/libs/heraldia-X.jar --work "$PWD/build/smoke"
A local HTTP server acts as the GitHub Releases API (the heraldia.update_check.url system property points to it) and
the following is checked, with simulated players (Carpet):
  1. with a 99.0.0 version published for this Minecraft (plus a newer pre-release and a draft, which do not
     count), the server says so on the console with the link and the backup; the request carries the generic
     User-Agent and no server data; an operator receives the notice on joining, only once per session even if they join
     again, and a non-operator player, never; /heraldia update check answers with the new version;
  2. the old names (/heraldia guia, info cerca, llave ... todas, arena parar) still work and warn that
     they are obsolete with the new name;
  3. with no network (a port that does not respond: the connection hangs until the timeout), the server starts
     anyway, answers commands in the meantime and leaves only one line in the log; /heraldia update check says it
     could not check;
  4. with update_check.activado = false nothing is asked.
"""
import argparse, copy, http.server, json, os, queue, re, shutil, socket, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server_smoke as s
from trophies import CARPET
from modrinth import fetch

OPERATOR, GUEST = "Operador", "Invitado"
ROUTE = "/repos/Stufanplay/HERALDIA"
NEW_ONE = "99.0.0"
DOWNLOAD = f"https://github.com/Stufanplay/HERALDIA/releases/tag/v{NEW_ONE}"
START = r"Heraldia: (\d+) estructuras registradas"


def publications():
    jar = [{"name": f"heraldia-{NEW_ONE}.jar"}]
    return [
        {"tag_name": "v99.1.0-beta.1", "name": "Beta", "draft": False, "prerelease": True,
         "html_url": f"https://github.com/Stufanplay/HERALDIA/releases/tag/v99.1.0-beta.1", "assets": jar},
        {"tag_name": "v99.0.5", "name": "Borrador", "draft": True, "prerelease": False,
         "html_url": f"https://github.com/Stufanplay/HERALDIA/releases/tag/v99.0.5", "assets": jar},
        {"tag_name": f"v{NEW_ONE}", "name": f"Heraldia {NEW_ONE}", "draft": False, "prerelease": False, "html_url": DOWNLOAD,
         "assets": jar, "body": "## [99.0.0]"},
        {"tag_name": "v0.0.1", "name": "Vieja", "draft": False, "prerelease": False,
         "html_url": "https://github.com/Stufanplay/HERALDIA/releases/tag/v0.0.1", "assets": jar},
    ]


class Api(http.server.BaseHTTPRequestHandler):
    """The fake GitHub API: the list of releases and the gradle.properties of each tag."""
    requests = []
    mc = "26.3"

    def do_GET(self):
        Api.requests.append((self.path, dict(self.headers)))
        if self.path.startswith(ROUTE + "/releases"):
            body, kind = json.dumps(publications()), "application/json"
        elif self.path == f"{ROUTE}/contents/gradle.properties?ref=v{NEW_ONE}":
            body, kind = f"mod_version={NEW_ONE}\nminecraft_version={Api.mc}\n", "text/plain"
        else:
            self.send_response(404)
            self.end_headers()
            return
        b = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


def hole():
    """A port that accepts connections and never responds (like a network that hangs). Returns (port, socket)."""
    so = socket.socket()
    so.bind(("127.0.0.1", 0))
    so.listen(16)
    open_ones = []

    def accept():
        while True:
            try:
                c, _ = so.accept()
                open_ones.append(c)
            except OSError:
                return
    threading.Thread(target=accept, daemon=True).start()
    return so.getsockname()[1], so


class WebServer:
    def __init__(self, work, launcher, url):
        self.t0 = time.monotonic()
        self.proc = subprocess.Popen(["java", "-Xmx2G", f"-Dheraldia.update_check.url={url}", "-jar", launcher, "nogui"],
                                     cwd=work, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.lines, self.seen = queue.Queue(), []
        threading.Thread(target=s.reader, args=(self.proc, self.lines), daemon=True).start()
        self.ctx = s.Context(self.proc, self.lines, self.seen)
        s.wait_for(self.lines, START, s.START_TIMEOUT_S, self.seen)
        self.start_s = time.monotonic() - self.t0

    def wait(self, pattern, timeout=s.COMMAND_TIMEOUT_S):
        return s.wait_for(self.lines, pattern, timeout, self.seen)

    def player(self, name):
        s.require_carpet(self.ctx)
        self.ctx.run(f"player {name} spawn at 0 100 0", r"joined the game|Player .* spawn")
        if not self.ctx.until(f"execute if entity @a[name={name}]"):
            raise SystemExit(f"the simulated player {name} does not appear (Carpet)")

    def hits(self, name):
        self.ctx.run(f"player {name} kill", r"left the game")
        self.ctx.until(f"execute if entity @a[name={name}]", want=False)

    def stop(self):
        if self.proc.poll() is None:
            s.send(self.proc, "stop")
            try:
                self.proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def write(work, switched_on):
    cfg = copy.deepcopy(s.TEST_CONFIG)
    cfg["update_check"] = {"activado": switched_on}
    with open(os.path.join(work, "config", "heraldia.json"), "w") as f:
        json.dump(cfg, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--work", default=os.path.join(s.ROOT, "build", "smoke-update"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    props = s.gradle_properties()
    Api.mc = props["minecraft_version"]
    launcher = s.prepare(a.work, os.path.abspath(a.jar), props)
    shutil.copy(fetch(a.work, *CARPET), os.path.join(a.work, "mods"))
    for f in ("ops.json", "usercache.json"):     # from a previous run: the operator must join without being one
        if os.path.exists(os.path.join(a.work, f)):
            os.remove(os.path.join(a.work, f))
    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Api)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{api.server_address[1]}{ROUTE}/releases?per_page=20"
    fails, ok = [], 0

    def check(cond, msg):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fails.append(msg)
            print("FAIL:", msg)

    def warnings(srv, name):
        return len(re.findall(rf"Heraldia: aviso de la versión {re.escape(NEW_ONE)} a {name}\b", "".join(srv.seen)))

    srv = None
    try:
        # ---------- 1 and 2: with a new version published ----------
        write(a.work, True)
        srv = WebServer(a.work, launcher, url)
        ctx = srv.ctx
        m = srv.wait(r"comprobación de versión nueva \(([^ ]+) para Minecraft ([^)]+)\): (\S+) en (\d+) ms")
        check(m.group(3) == NEW_ONE, f"la comprobación encuentra {m.group(3)}, se esperaba {NEW_ONE}")
        print(f"check: {m.group(1)} -> {m.group(3)} for Minecraft {m.group(2)} in {m.group(4)} ms")
        m = srv.wait(r"A new version of Heraldia is available: (\S+) .*")
        line = m.group(0)
        check(NEW_ONE in line and DOWNLOAD in line and "back up" in line,
              f"la consola no da la versión, el enlace y la copia de seguridad: {line.strip()}")
        routes = [p for p, _ in Api.requests]
        check(any(p.startswith(ROUTE + "/releases") for p in routes), f"no se pidió la lista de publicaciones: {routes}")
        check(f"{ROUTE}/contents/gradle.properties?ref=v{NEW_ONE}" in routes, f"no se miró el Minecraft de la v{NEW_ONE}: {routes}")
        check(not any("beta" in p or "99.0.5" in p for p in routes), f"se miró una pre-publicación o un borrador: {routes}")
        for p, header in Api.requests:
            agent = {k.lower(): v for k, v in header.items()}.get("user-agent", "")
            check(agent == "Heraldia-update-check", f"User-Agent «{agent}» en {p}")
            surplus = {k.lower() for k in header} - {"user-agent", "accept", "host", "connection", "content-length", "upgrade",
                                                 "http2-settings", "accept-encoding"}
            check(not surplus, f"cabeceras de más en {p}: {surplus}")
            check("?" not in p or p.split("?", 1)[1] in ("per_page=20", f"ref=v{NEW_ONE}"), f"datos en la petición: {p}")

        # the operator, on joining (once per session); the guest, never
        srv.player(OPERATOR)
        srv.player(GUEST)
        ctx.run(f"op {OPERATOR}", r"Made .* a server operator|Nothing changed|Unknown|Incorrect")
        s.drain(ctx, 3)
        check(warnings(srv, OPERATOR) == 0, "entró sin ser operador: no debía recibir el aviso")
        srv.hits(OPERATOR)
        srv.player(OPERATOR)
        try:
            srv.wait(rf"Heraldia: aviso de la versión {re.escape(NEW_ONE)} a {OPERATOR}\b", 30)
        except SystemExit:
            pass
        check(warnings(srv, OPERATOR) == 1, f"el operador debía recibir el aviso una vez al entrar: {warnings(srv, OPERATOR)}")
        srv.hits(OPERATOR)
        srv.player(OPERATOR)
        s.drain(ctx, 3)
        check(warnings(srv, OPERATOR) == 1, f"al volver a entrar en la misma sesión no se repite: {warnings(srv, OPERATOR)}")
        check(warnings(srv, GUEST) == 0, "un jugador que no es operador no debe recibir el aviso")

        # /heraldia update check from the console
        ctx.run("heraldia update check", r"Checking for a new version|Comprobando si hay")
        m = srv.wait(rf"(?:A new version of Heraldia is available|Hay una versión nueva de Heraldia): {re.escape(NEW_ONE)}|"
                        r"Could not check|No se pudo comprobar|up to date|está al día")
        check(NEW_ONE in m.group(0), f"/heraldia update check: {m.string.strip()}")
        # (that a player without permissions does not have it is checked by ComandosTest: "execute as" keeps the console's)

        # ---------- 2: nombres antiguos ----------
        obsolete = r"(?:“|«)([^”»]+)(?:”|») (?:is deprecated|está obsoleto)[^:]*: (?:use|usa) (/heraldia [\w ]+|\w+)"
        for old, new_one, follows in [
                ("heraldia guia", "/heraldia guide", r"player is required|jugador"),
                ("heraldia info cerca 64", "/heraldia info nearby", r"info nearby 64 en|estructuras en"),
                ("heraldia arena parar", "/heraldia arena stop", r"arena|Arena"),
                ("heraldia llave @a atlantida", "/heraldia key", r"llaves|keys|Entregadas|Given"),
                ("heraldia key @a todas", "all", r"llaves|keys|Entregadas|Given")]:
            m = ctx.run(old, obsolete)
            check(m.lastindex and m.group(2).strip() == new_one, f"{old}: aviso de obsoleto {m.string.strip()}")
            s.drain(ctx, 3)
        # does the same as the new name: the player's guide
        for order in ("heraldia guia", "heraldia guide"):
            m = ctx.run(f"execute as {OPERATOR} run {order}", r"entregada a (\w+) en \d+ µs|Unknown|Incorrect")
            check(m.lastindex and m.group(1) == OPERATOR, f"/{order} no da la guía: {m.string.strip()}")
        srv.stop()
        srv = None

        # ---------- 3: no network (the connection hangs) ----------
        harbor, cavity = hole()
        Api.requests.clear()
        srv = WebServer(a.work, launcher, f"http://127.0.0.1:{harbor}{ROUTE}/releases?per_page=20")
        ctx = srv.ctx
        print(f"no network: started in {srv.start_s:.1f} s")
        t0 = time.monotonic()
        m = ctx.run("heraldia status", r"Heraldia \S+: (?:server status|estado del servidor)")
        check(m.group(0).startswith("Heraldia"), f"el servidor no responde mientras espera a la red: {m.string.strip()}")
        check(time.monotonic() - t0 < 10, "el servidor tarda en responder mientras espera a la red")
        m = srv.wait(r"no se pudo comprobar si hay una versión nueva \(([^:]+): ", 60)
        print(f"no network: {m.group(0).strip()}")
        ctx.run("heraldia update check", r"Checking for a new version|Comprobando si hay")
        m = srv.wait(r"Could not check for a new version|No se pudo comprobar si hay una versión nueva \(sin red|"
                        r"A new version of Heraldia", 60)
        check(m.group(0).startswith(("Could not", "No se pudo")), f"sin red, /heraldia update check: {m.string.strip()}")
        log = "".join(srv.seen)
        check("A new version of Heraldia" not in log, "sin red no puede haber aviso")
        bad_all = [l.strip() for l in log.splitlines() if "Exception" in l and "heraldia" in l.lower() and "no se pudo comprobar" not in l]
        check(not bad_all, f"excepciones en el log: {bad_all[:3]}")
        srv.stop()
        srv = None
        cavity.close()

        # ---------- 4: desactivado ----------
        write(a.work, False)
        Api.requests.clear()
        srv = WebServer(a.work, launcher, url)
        s.drain(srv.ctx, 3)
        check("aviso de versión nueva desactivado" in "".join(srv.seen), "desactivado: falta la línea del log")
        check(not Api.requests, f"con update_check.activado = false se preguntó: {Api.requests}")
    finally:
        if srv:
            srv.stop()
        api.shutdown()

    print(f"\n{ok} comprobaciones correctas, {len(fails)} fallos")
    for f in fails:
        print("  -", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
