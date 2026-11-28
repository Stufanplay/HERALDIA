"""tools/smoke/server_smoke.free_port: a port below the kernel's ephemeral range, free when chosen, never the same twice
in one process (the server port and runtime_cost.py's JMX port must not coincide)."""
import os, socket, sys

SMOKE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "smoke")
_path = list(sys.path)      # tools/smoke only while importing (see test_compat_mods.py)
sys.path.insert(0, SMOKE)
import server_smoke as s  # noqa: E402
sys.path[:] = _path


def test_below_the_ephemeral_range_free_and_distinct():
    lo, _ = s.ephemeral_range()
    ports = [s.free_port() for _ in range(200)]
    assert len(set(ports)) == 200
    assert all(20000 <= p < lo for p in ports), (lo, [p for p in ports if not 20000 <= p < lo][:5])
    for p in ports[:20]:
        with socket.socket() as so:
            so.bind(("", p))                 # still free right after


def test_an_outgoing_connection_cannot_take_it():
    """What took the port in CI: a connection's local port. Those come from the ephemeral range only."""
    lo, hi = s.ephemeral_range()
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(64)
    try:
        for _ in range(50):
            with socket.socket() as c:
                c.connect(srv.getsockname())
                assert lo <= c.getsockname()[1] <= hi
                srv.accept()[0].close()
    finally:
        srv.close()


def test_a_busy_port_is_skipped(monkeypatch):
    held = socket.socket()
    held.bind(("", 0))
    port = held.getsockname()[1]
    seq = iter([port, port, 20001])
    monkeypatch.setattr(s, "ephemeral_range", lambda: (port + 1, 60999))
    import random
    monkeypatch.setattr(random, "randrange", lambda a, b: next(seq))
    s._given_ports.discard(20001)
    try:
        assert s.free_port(low=port - 1) == 20001
    finally:
        held.close()
