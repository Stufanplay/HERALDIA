"""tools/smoke/server_smoke.py: test server downloads (a cut-off download is not left in the cache), whether a
command's reply is looked at (`run` fails by default on an error reply it does not accept) and where an entity has
to be standing for `land` to call it settled; and the pure functions of tools/smoke/existing_world.py (reading sections
and comparing saved chunks)."""
import io, os, re, sys, zipfile
import pytest

SMOKE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "smoke")
_path = list(sys.path)      # tools/smoke only while importing (see test_compat_mods.py)
sys.path.insert(0, SMOKE)
import server_smoke as s  # noqa: E402
import existing_world as me  # noqa: E402
sys.path[:] = _path


def _jar():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("fabric.mod.json", "{}" * 2000)
    return b.getvalue()


class _Resp(io.BytesIO):
    def __init__(self, data, length):
        super().__init__(data)
        self.headers = {"Content-Length": str(length)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_valid_jar(tmp_path):
    good, truncated = tmp_path / "a.jar", tmp_path / "b.jar"
    good.write_bytes(_jar())
    truncated.write_bytes(_jar()[:200])
    assert s.valid_jar(str(good))
    assert not s.valid_jar(str(truncated))
    assert not s.valid_jar(str(tmp_path / "no.jar"))


def test_download_cut_gets_repeats(tmp_path, monkeypatch):
    jar = _jar()
    answers = [_Resp(jar[:300], len(jar)), _Resp(jar, len(jar))]       # the first one, cut by the network
    monkeypatch.setattr(s.urllib.request, "urlopen", lambda url: answers.pop(0))
    monkeypatch.setattr(s.time, "sleep", lambda t: None)
    dest = tmp_path / "fabric-api.jar"
    s.download("https://ejemplo/fabric-api.jar", str(dest))
    assert dest.read_bytes() == jar and not answers


def test_corrupt_jar_in_cache_is_redownloaded(tmp_path, monkeypatch):
    jar = _jar()
    dest = tmp_path / "fabric-api.jar"
    dest.write_bytes(jar[:300])                       # what an earlier run left
    monkeypatch.setattr(s.urllib.request, "urlopen", lambda url: _Resp(jar, len(jar)))
    s.download("https://ejemplo/fabric-api.jar", str(dest))
    assert dest.read_bytes() == jar


def test_download_always_cut_fails(tmp_path, monkeypatch):
    jar = _jar()
    monkeypatch.setattr(s.urllib.request, "urlopen", lambda url: _Resp(jar[:300], len(jar)))
    monkeypatch.setattr(s.time, "sleep", lambda t: None)
    with pytest.raises(SystemExit):
        s.download("https://ejemplo/fabric-api.jar", str(tmp_path / "x.jar"), attempts=2)
    assert not (tmp_path / "x.jar").exists()


# ------------------------------------------------------------------ mundo_existente.py
def _build_section(palette, indices):
    """block_states of a section with `paleta` (names) and `indices` (4096), packed like the game."""
    bits = max(4, (len(palette) - 1).bit_length())
    per, data = 64 // bits, []
    for i in range(0, 4096, per):
        v = 0
        for k, idx in enumerate(indices[i:i + per]):
            v |= idx << (k * bits)
        data.append(v - (1 << 64) if v >= 1 << 63 else v)
    return {"palette": [{"Name": n} for n in palette], "data": data}


def test_states_of_a_section():
    assert me.states(None) is None
    assert me.states({"palette": [{"Name": "minecraft:air"}]}) == [("minecraft:air", ())] * 4096
    ind = [i % 3 for i in range(4096)]
    sty = me.states(_build_section(["minecraft:air", "minecraft:stone", "minecraft:dirt"], ind))
    assert len(sty) == 4096 and sty[0][0] == "minecraft:air" and sty[4095][0] == ["minecraft:air", "minecraft:stone", "minecraft:dirt"][4095 % 3]
    # 17 states: 5 bits, 12 per long (not split across two)
    pal = [f"minecraft:b{i}" for i in range(17)]
    ind = [(i * 7) % 17 for i in range(4096)]
    assert [e[0] for e in me.states(_build_section(pal, ind))] == [pal[i] for i in ind]


def _footprint(palette, indices, be=None):
    return me.footprint({"sections": [{"Y": 0, "block_states": _build_section(palette, indices), "biomes": {"palette": ["minecraft:plains"]}}],
                      "block_entities": be or [], "Heightmaps": {}, "structures": {"References": {}, "starts": {}},
                      "LastUpdate": 5, "InhabitedTime": 9, "Status": "minecraft:full"})


def test_same_section_with_another_palette_does_not_change():
    ind = [i % 2 for i in range(4096)]
    a = _footprint(["minecraft:air", "minecraft:stone"], ind)
    b = _footprint(["minecraft:stone", "minecraft:air"], [1 - i for i in ind])
    assert me.differences(a, b) == []


def test_a_changed_block_is_detected():
    ind = [0] * 4096
    a = _footprint(["minecraft:air", "minecraft:stone"], ind)
    ind2 = list(ind)
    ind2[(5 << 8) | (3 << 4) | 2] = 1                  # x=2, y=5, z=3
    d = me.differences(a, _footprint(["minecraft:air", "minecraft:stone"], ind2))
    assert len(d) == 1 and "1 bloques cambian" in d[0] and "x=2 y=5 z=3" in d[0] and "minecraft:stone" in d[0]


def test_blocks_with_data_and_fields_volatile():
    ind = [0] * 4096
    place_chest = {"id": "minecraft:chest", "x": 1, "y": 2, "z": 3, "LootTable": "heraldia:unicas/x"}
    a = _footprint(["minecraft:air"], ind, [place_chest])
    assert me.differences(a, _footprint(["minecraft:air"], ind, [dict(place_chest, keepPacked=1)])) == []
    d = me.differences(a, _footprint(["minecraft:air"], ind, [dict(place_chest, LootTable="heraldia:otra")]))
    assert len(d) == 1 and "LootTable" in d[0]
    assert me.differences(a, _footprint(["minecraft:air"], ind)) != []


def test_chain_palette_of_26_3():
    ind = [i % 2 for i in range(4096)]
    sec = _build_section(["minecraft:air", "minecraft:stone"], ind)
    sec["palette"] = ["minecraft:air", "minecraft:stone"]               # as 26.3 stores it
    assert [e[0] for e in me.states(sec)] == [["minecraft:air", "minecraft:stone"][i] for i in ind]


def test_mixed_list_of_26_3():
    mixed = [{"": "minecraft:air"}, {"id": "minecraft:oak_log", "properties": {"axis": "y"}}]
    assert me._blueprint(mixed) == ["minecraft:air", {"id": "minecraft:oak_log", "properties": {"axis": "y"}}]
    sec = {"palette": me._blueprint(mixed), "data": [0x10]}                 # index 0 and then 1
    sty = me.states(sec)
    assert sty[0] == ("minecraft:air", ()) and sty[1] == ("minecraft:oak_log", (("axis", "y"),))


def test_forceload_pieces_of_256_chunks():
    C = {(x, z) for x in range(-10, 12) for z in range(-90, -68)}         # 22 x 22 = 484 chunks
    t = me.fragments(C)
    assert all(((x1 - x0 + 1) // 16) * ((z1 - z0 + 1) // 16) <= 256 for x0, z0, x1, z1 in t)
    roofed_set = {(x // 16, z // 16) for x0, z0, x1, z1 in t for x in range(x0, x1 + 1, 16) for z in range(z0, z1 + 1, 16)}
    assert roofed_set == C


# --- where a command's reply is looked at, and where an entity has to be standing (server_smoke.must / land)

class _Server:
    """The least that `server_smoke.run` needs of a server: `write` is the command going out, and the reply arrives
    right after it, as it does on a real one (`pending` drains the queue before sending, so a pre-loaded reply would be
    thrown away instead of matched)."""

    def __init__(self, lines, reply):
        self.stdin, self.lines, self.reply, self.sent = self, lines, reply, []

    def write(self, text):
        self.sent.append(text)
        for line in (self.reply if isinstance(self.reply, list) else [self.reply]):     # a list: lines in order
            self.lines.put(line)

    def flush(self):
        pass


def _answer(reply, cmd, ok, how):
    import queue
    lines, seen = queue.Queue(), []
    return how(_Server(lines, reply), lines, seen, cmd, ok)


OK_REPLY = "[00:00:00] [Server thread/INFO]: Game rule keep_inventory is now set to true\n"
BAD_REPLY = "[00:00:00] [Server thread/INFO]: Incorrect argument for command at position 9\n"
RULE = r"[Gg]ame ?rule .*keep_inventory.*true"


def test_run_fails_by_default_on_the_error_reply():
    """The switch: `run` waits for `ok` OR `ERROR_PATTERN` (so a failure ends the wait at once) and raises when the
    reply that ended it is not one `ok` accepts. It used to return it, so a caller that did not read the reply accepted
    the failure."""
    assert _answer(OK_REPLY, "gamerule keep_inventory true", RULE, s.run).string == OK_REPLY
    with pytest.raises(SystemExit) as e:
        _answer(BAD_REPLY, "gamerule keep_inventory true", RULE, s.run)
    assert "Incorrect argument" in str(e.value) and "gamerule keep_inventory true" in str(e.value)


def test_run_hands_back_a_failure_the_caller_accepts():
    """The retry idiom stays possible: a caller that lists the failure in its own `ok` gets it back to read."""
    unloaded = "[00:00:00] [Server thread/INFO]: System chat: That position is not loaded\n"
    ok = r"Successfully filled|No blocks|not loaded(?! yet)"
    assert "not loaded" in _answer(unloaded, "fill 0 0 0 1 1 1 minecraft:stone", ok, s.run).string


def test_must_accepts_the_success_reply_and_rejects_the_error_one():
    assert _answer(OK_REPLY, "gamerule keep_inventory true", RULE, s.must).string == OK_REPLY
    with pytest.raises(SystemExit) as e:
        _answer(BAD_REPLY, "gamerule keep_inventory true", RULE, s.must)
    assert "Incorrect argument" in str(e.value)


def test_must_cannot_tell_apart_a_pattern_that_matches_the_failure():
    """Why the two gamerule patterns had to lose `Unknown|Incorrect`: with the failure's words in `ok`, the error reply
    *is* the accepted reply and `must` has nothing left to reject."""
    loose = RULE + r"|Unknown|Incorrect"
    assert _answer(BAD_REPLY, "gamerule keep_inventory true", loose, s.must).string == BAD_REPLY


def test_resting_is_the_feet_on_the_aimed_spot_not_floor_of_the_y():
    """`land`'s own comparison, with `want` shaped as the teleport reports it (integer x and z come back centred on the
    block). The aimed y is a feet level -- the heightmap's y above its top block -- so a block shorter than a full cube
    holds the feet just under it and that is still resting; a whole block down is not."""
    want = (0.5, 91.0, 48.5)
    assert s._resting((0.5, 91.0, 48.5), want)              # full block, exactly where the teleport left it
    assert s._resting((0.5, 90.9375, 48.5), want)           # a path block: measured on a server, floor 90, aimed 91
    assert not s._resting((0.5, 90.0, 48.5), want)          # fell one whole block: the fault this guards against
    assert not s._resting((0.5, 89.9375, 48.5), want)       # fell one block onto a path
    assert not s._resting((0.5, 92.0, 48.5), want)          # still in the air one block up
    assert not s._resting((1.5, 91.0, 48.5), want)          # right height, wrong column
    assert not s._resting(None, want)                       # no entity at all


def test_the_teleport_reply_gives_the_aimed_spot():
    """The only race-free source of where the teleport aimed: the game writes it inside the teleport. Both replies are
    verbatim from a dedicated server, 26.3."""
    ok = "[00:00:00] [Server thread/INFO]: System chat: Teleported Probe to 0.500000, 63.000000, 48.500000\n"
    m = re.search(s._TELEPORTED, ok)
    assert tuple(float(v) for v in m.groups()) == (0.5, 63.0, 48.5)
    unloaded = "[00:00:00] [Server thread/INFO]: System chat: That position is not loaded\n"
    m = re.search(s._TELEPORTED, unloaded)
    assert m and m.group(1) is None        # `land` keeps waiting on this one instead of taking it for a destination


def test_one_asks_for_exactly_one_entity():
    """`data get entity` refuses a selector that could match more than one, with a message `ERROR_PATTERN` does not
    cover, so the wait would run its full 300 s. And a bare name cannot carry the `[limit=1]` `pos` appends."""
    assert s._one("rep") == "@a[name=rep,limit=1]"
    assert s._one("@a[name=rep]") == "@a[name=rep,limit=1]"
    assert s._one("@a[name=rep,limit=1]") == "@a[name=rep,limit=1]"
    assert s._one("@e") == "@e[limit=1]"


def test_the_error_word_has_to_stand_on_its_own():
    """`ERROR_PATTERN`'s `error` alternative. The bare word matched `error=null` in the Mojang profile lookup the server
    logs for every Carpet fake player, so `run` returned that log line as the reply to a spawn that had worked; it also
    matched a test's own success line. It must still match `Registry loading errors`, which is a real 26.3 failure, so
    the word cannot just be removed and `error:` would have dropped it."""
    must_not = ["...minecraft/hrd_testigo, error=null, errorMessage=Couldn't find any profile with name hrd_testigo",
                "[OK] sin errores de los mapas web en el log",
                "errorMessage=Couldn't find any profile"]
    must = ["Registry loading errors:", "An unexpected error occurred while handling the command"]
    for line in must_not:
        assert not re.search(s.ERROR_PATTERN, line), line
    for line in must:
        assert re.search(s.ERROR_PATTERN, line), line


# Verbatim from #155's CI log (admin.py): Carpet's profile lookup refused with HTTP 429 while `player ... spawn` was
# awaited; the spawn itself worked a second later.
MOJANG_ERROR = ("[22:39:09] [Server thread/ERROR]: Got an error with a html body connecting to "
                "https://api.mojang.com/users/profiles/minecraft/revisor: <!DOCTYPE html>\n")
JOINED = "[22:39:10] [Server thread/INFO]: Revisor joined the game\n"
UNLOADED_INFO = "[00:00:00] [Server thread/INFO]: System chat: That position is not loaded\n"


def test_a_line_logged_at_error_level_is_not_the_reply():
    """The switch raises on replies, not on whatever the server logs meanwhile: an ERROR line from another lookup that
    lands in the wait is skipped, and the real reply that follows is returned."""
    assert re.search(s.ERROR_PATTERN, MOJANG_ERROR), "the case only means something if the line looks like a failure"
    m = _answer([MOJANG_ERROR, JOINED], "player Revisor spawn at 0 100 0", r"joined the game", s.run)
    assert m.string == JOINED


def test_a_failure_reply_after_a_logged_error_still_raises():
    """Skipping logged lines must not blunt the switch: the INFO failure reply after it still stops the test."""
    with pytest.raises(SystemExit) as e:
        _answer([MOJANG_ERROR, UNLOADED_INFO], "fill 0 0 0 1 1 1 minecraft:stone", r"Successfully filled", s.run)
    assert "not loaded" in str(e.value)


def test_a_logged_line_counts_when_ok_asks_for_it():
    """Like the mod's own lines: a caller that waits for a WARN or ERROR line on purpose still gets it."""
    m = _answer([MOJANG_ERROR], "player Revisor spawn at 0 100 0", r"Got an error with a html body", s.run)
    assert m.string == MOJANG_ERROR


# Verbatim from a 26.3 server, with and without Carpet, same .jar.
CARPET_HERE = "[02:04:47] [Server thread/INFO]: System chat: Can only manipulate existing players\n"
CARPET_ABSENT = "[02:32:20] [Server thread/INFO]: System chat: Unknown or incomplete command. See below for error\n"


class _Ctx:
    """A Context-like object over `_Server`: `require_carpet` only needs `.run` and somewhere to remember."""

    def __init__(self, reply):
        import queue
        self.lines, self.seen = queue.Queue(), []
        self.server = _Server(self.lines, reply)

    def run(self, cmd, ok):
        return s.run(self.server, self.lines, self.seen, cmd, ok)


def test_require_carpet_passes_with_carpet_and_asks_once():
    ctx = _Ctx(CARPET_HERE)
    s.require_carpet(ctx)
    s.require_carpet(ctx)
    assert ctx.server.sent == [s.CARPET_PROBE + "\n"], "it asks once per server, then remembers"


def test_require_carpet_stops_the_test_and_says_where_carpet_is_missing():
    with pytest.raises(SystemExit) as e:
        s.require_carpet(_Ctx(CARPET_ABSENT))
    msg = str(e.value)
    assert "Carpet is not loaded" in msg and "mods/" in msg and "Unknown or incomplete command" in msg

