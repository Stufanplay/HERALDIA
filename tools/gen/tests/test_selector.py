"""tools/test.py: selection of server tests by changed paths (the same one CI uses) and distribution into groups."""
import json, os, subprocess, sys
import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# tools/test.py by its path (the name "test" would clash with the standard library test package)
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("heraldia_test_selector", os.path.join(TOOLS, "test.py"))
sel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sel)

ALL_COMBOS = sel.discover()
J = sel.JAVA
EVERY_UNIQUE = set(sel.OF_EVERY_UNIQUE)
AQUATIC = "tools/smoke/aquatic_dry.py"
COMPAT = [p for p in ALL_COMBOS if sel.is_compat(p)]
NO_COMPAT = [p for p in ALL_COMBOS if not sel.is_compat(p)]


def pick(*routes):
    return sel.choose(list(routes), ALL_COMBOS)


def test_discovers_all_the_tests_of_server():
    assert sel.SMOKE not in ALL_COMBOS and len(ALL_COMBOS) >= 24
    assert "tools/gen/uniques/castle/smoke_redstone.py" in ALL_COMBOS and "tools/smoke/trophies.py" in ALL_COMBOS
    for sid, ps in sel.SMOKE_OF_UNIQUE.items():
        assert all(p in ALL_COMBOS for p in ps), sid
    assert all(p in ALL_COMBOS for p in sel.OF_EVERY_UNIQUE + sel.VILLAGES)
    for p in ALL_COMBOS:                                       # every known test has a measured duration
        assert p in sel.DURATION_S, p
    assert "tools/smoke/modrinth.py" not in ALL_COMBOS and sel.COMPAT not in ALL_COMBOS   # common module; the compat one, by groups
    assert {p.split("::")[1] for p in COMPAT} == set(sel.compat_groups()) and "tools/smoke/compat_mods.py::base" in COMPAT


def test_discovering_leaves_the_import_path_alone():
    """discover()/compat_groups() must not put tools/smoke on sys.path or import its modules: eight of them share a name
    with a generator module (treasure, guide, quests...) and would shadow it for every test run afterwards."""
    smoke = os.path.join(TOOLS, "smoke")
    before = set(sys.modules)
    sel.discover()
    assert all(os.path.abspath(p) != smoke for p in sys.path)
    new = [m for m in set(sys.modules) - before if (getattr(sys.modules[m], "__file__", None) or "").startswith(smoke)]
    assert not new, new


@pytest.mark.parametrize("routes", [
    ["docs/DEVELOPMENT.md"], ["README.md", "CHANGELOG.md"], ["tools/gen/tests/test_core.py"],
    ["src/test/java/io/github/albertosa23/heraldia/config/X.java"], ["src/client/java/x/ConfigScreen.java"],
    ["tools/gen/render.py"], ["tools/gen/loot.py"], [J + "command/KeyCommand.java"],
])
def test_no_smoke_servers(routes):
    assert pick(*routes) == (False, [])


@pytest.mark.parametrize("route", [
    "tools/gen/uniques/_common/redstone.py", "tools/gen/uniques/__init__.py", "tools/gen/writer.py", "tools/gen/core.py",
    "tools/gen/pack.py", "tools/gen/lint.py", "tools/gen/validate.py", "tools/gen/build.py", "tools/gen/options.py",
    "tools/smoke/server_smoke.py", "tools/test.py", ".github/workflows/ci.yml", ".github/actions/preparar/action.yml",
    "build.gradle", "gradle.properties", "src/main/resources/fabric.mod.json", J + "Heraldia.java",
    J + "config/GridPlacement.java", J + "common/Heights.java", J + "loot/PerPlayerChest.java",
    J + "mixin/ChunkGeneratorMixin.java", J + "unicas/paquete_nuevo/X.java", "fichero/que/nadie/conoce.txt",
])
def test_code_common_requests_the_battery_full(route):
    """The full suite of a PR includes the compatibility ones only if what changed is about placement (COMPAT_RUTAS)."""
    full, tests = pick(route)
    is_placement = any(sel.fnmatch.fnmatch(route, p) for p in sel.COMPAT_PATHS)
    assert full and tests == (ALL_COMBOS if is_placement else NO_COMPAT)


@pytest.mark.parametrize("route", [J + "mixin/ChunkGeneratorMixin.java", J + "config/GridPlacement.java",
                                  J + "common/ForeignZone.java", "gradle.properties"])
def test_placement_common_drags_the_of_compatibility(route):
    assert pick(route) == (True, ALL_COMBOS)


def test_compatibility_only_with_their_paths():
    assert pick(sel.COMPAT) == (False, COMPAT)                                  # the test itself: all its groups
    assert pick("tools/smoke/compat_mods.py::rendimiento") == (False, ["tools/smoke/compat_mods.py::rendimiento"])
    full, p = pick("tools/smoke/modrinth.py")                               # the pinned mods: whoever downloads them
    assert not full and set(p) == set(COMPAT) | {"tools/smoke/trophies.py", "tools/smoke/story.py",
                                                      "tools/smoke/village_life.py", "tools/smoke/terralith_biomes.py"}
    assert set(pick("tools/gen/biomes.py")[1]) == {"tools/smoke/terralith_biomes.py"} | set(COMPAT)
    assert pick("tools/gen/writer.py") == (True, NO_COMPAT)                    # common, but not placement
    assert pick(J + "command/InfoCommand.java") == (False, ["tools/smoke/admin.py"])   # not placement


def test_order_of_one_test_per_group():
    assert sel.order("tools/smoke/compat_mods.py::terreno")[1:] == ["--group", "terreno"]
    assert sel.order("tools/smoke/compat_mods.py::terreno")[0].endswith(os.path.join("tools", "smoke", "compat_mods.py"))
    assert sel.order("tools/smoke/trophies.py")[1:] == []
    assert sel.name(["tools/smoke/compat_mods.py::base", "tools/smoke/galleon_test.py"]) == "compat base + galleon_test"


def test_a_unique_with_folder():
    full, p = pick("tools/gen/uniques/castle/blueprints.py")
    assert not full and set(p) == {"tools/gen/uniques/castle/smoke_redstone.py"} | EVERY_UNIQUE


def test_a_single_module_unique_and_its_smoke_test():
    full, p = pick("tools/gen/uniques/observatory.py")
    assert not full and set(p) == {"tools/smoke/observatory_smoke.py"} | EVERY_UNIQUE


def test_unique_without_own_test():
    full, p = pick("tools/gen/uniques/aqueduct/construction.py")
    assert not full and set(p) == EVERY_UNIQUE


def test_java_of_a_unique():
    assert set(pick(J + "uniques/island/IslandStructure.java")[1]) == {"tools/gen/uniques/corsair_island/smoke_server.py",
                                                                        AQUATIC} | EVERY_UNIQUE
    # the island zone also decides which foreign structures spawn nearby: it drags in the compatibility ones
    assert set(pick(J + "uniques/island/IslandZone.java")[1]) == {"tools/gen/uniques/corsair_island/smoke_server.py",
                                                                   AQUATIC} | EVERY_UNIQUE | set(COMPAT)
    assert set(pick(J + "uniques/galleon/GalleonStructure.java")[1]) == {"tools/smoke/galleon_test.py", AQUATIC} | EVERY_UNIQUE
    assert set(pick(J + "uniques/mine/Mine.java")[1]) == {"tools/gen/uniques/lost_mine/smoke_server.py"} | EVERY_UNIQUE


def test_change_a_smoke_only_runs_that():
    assert pick("tools/smoke/palace_redstone.py") == (False, ["tools/smoke/palace_redstone.py"])
    assert pick("tools/gen/uniques/pyramid/smoke_server.py") == (False, ["tools/gen/uniques/pyramid/smoke_server.py"])


def test_villages_and_data():
    assert set(pick("tools/gen/houses.py")[1]) == set(sel.VILLAGES)
    assert set(pick(J + "villages/VillageStructure.java")[1]) == set(sel.VILLAGES)
    assert pick("tools/gen/board.py")[1] == ["tools/smoke/village_life.py"]
    assert "tools/smoke/terralith_biomes.py" in pick("tools/gen/biomes.py")[1]
    assert pick(J + "mixin/ZombieMixin.java")[1] == ["tools/smoke/adult_guardians.py"]
    assert pick(J + "common/Anchoring.java")[1] == ["tools/smoke/anchored_guardians.py"]
    assert pick(J + "common/ToGroundProcessor.java")[0]          # the rest of comun/: full suite
    assert set(pick("tools/gen/advancements.py")[1]) == {"tools/smoke/trophies.py", "tools/smoke/story.py", "tools/smoke/village_life.py"}
    assert pick(J + "roads/RoadLayout.java") == (False, ["tools/smoke/roads.py"])
    assert pick("tools/gen/roads.py") == (False, ["tools/smoke/roads.py"])


def test_union_of_several_changes_and_a_common_one_drags_everything():
    full, p = pick("tools/gen/uniques/palace/blueprint.py", "tools/gen/board.py", "docs/x.md")
    assert not full and set(p) == {"tools/smoke/palace_redstone.py", "tools/smoke/village_life.py"} | EVERY_UNIQUE
    assert pick("tools/gen/uniques/palace/blueprint.py", "tools/gen/writer.py") == (True, NO_COMPAT)
    assert pick("tools/gen/writer.py", J + "config/UniqueSeparation.java") == (True, ALL_COMBOS)


def test_groups_distribute_without_exceeding_of_the_cap():
    g = sel.groups(ALL_COMBOS)
    assert sorted(p for x in g for p in x) == ALL_COMBOS                       # each test once
    length = max(sel.DURATION_S.values())
    cap = max(sel.GROUP_CAP_S, length)
    assert all(sum(sel.DURATION_S[p] for p in x) <= cap for x in g)
    assert len(g) <= 18                     # with the build and the smoke one, in a batch of 20 free jobs
    assert len(sel.groups(NO_COMPAT)) <= 15  # a PR with common changes (without the compatibility ones) fits in a batch of 20 jobs (15 with the search memory's search_cache.py and the ambience test: + build, smoke, long JUnit, cost and selection = 20 of 20)
    assert sel.groups([]) == [] and sel.groups(ALL_COMBOS) == g                # determinista
    assert sel.groups(["x/nueva.py"]) == [["x/nueva.py"]]                  # without a measured duration: DEFECTO_S


def test_matrix_and_names():
    m = sel.matrix(False, ["tools/smoke/galleon_test.py", "tools/gen/uniques/pyramid/smoke_server.py"])
    assert m["include"] == [{"name": "pyramid + galleon_test",
                             "tests": "tools/gen/uniques/pyramid/smoke_server.py tools/smoke/galleon_test.py"}]
    assert sel.matrix(False, []) == {"include": []}


def test_ci_matrix_by_line_of_commands():
    """--ci-matrix --full gives all the tests in groups, as on push to develop."""
    out = subprocess.run([sys.executable, os.path.join(TOOLS, "test.py"), "--ci-matrix", "--full"],
                         capture_output=True, text=True, check=True).stdout
    m = json.loads(out)
    assert m["full"] is True
    assert sorted(p for g in m["include"] for p in g["tests"].split()) == ALL_COMBOS


def test_mediums():
    mobs = ["tools/smoke/adult_guardians.py", "tools/smoke/anchored_guardians.py", "tools/smoke/medium_structures.py",
            "tools/smoke/nether_end.py"]
    assert pick("tools/gen/mediums/inn.py") == (False, mobs)       # its mobs go into the anchored tests
    assert pick("tools/gen/mediums/__init__.py") == (False, mobs)
    assert pick("tools/smoke/medium_structures.py") == (False, ["tools/smoke/medium_structures.py"])
    full, p = pick(J + "common/MediumStructures.java")      # it decides where they spawn: the compatibility ones too
    assert not full and set(p) == {"tools/smoke/medium_structures.py", "tools/smoke/nether_end.py"} | set(COMPAT)


def test_nether_end():
    """T44: the Nether and End content passes its server test."""
    ne = "tools/smoke/nether_end.py"
    assert pick(J + "dimensions/DimensionStructure.java") == (False, [ne])
    full, p = pick("tools/gen/dimensions.py")
    assert not full and ne in p and "tools/smoke/medium_structures.py" in p
    full, p = pick("tools/gen/uniques/ash_citadel.py")
    assert not full and ne in p and "tools/smoke/trophies.py" in p
    assert pick(ne) == (False, [ne])


def test_mines():
    m = ["tools/smoke/mine_entrances.py"]
    assert pick("tools/gen/mines/blueprints.py") == (False, m)
    assert pick("tools/gen/mines/__init__.py") == (False, m)
    assert pick(J + "mines/Hillside.java") == (False, sorted(m + ["tools/smoke/coast.py"])), "the coast rule is the mines rule"
    assert pick("tools/smoke/mine_entrances.py") == (False, m)
    # T36: the shared height cache and the parallel /locate (only the mines use them)
    assert pick(J + "common/HeightCache.java") == (False, m)
    assert pick(J + "mixin/ChunkGeneratorLocateMixin.java") == (False, m)
    assert pick(J + "mines/ParallelLocate.java") == (False, sorted(m + ["tools/smoke/coast.py"]))


def test_search_cache():
    m = sorted(["tools/smoke/search_cache.py", "tools/smoke/mine_entrances.py"])
    for p in ("common/SearchCache.java", "common/SearchCaches.java", "common/UnwrittenRegions.java",
              "mixin/IOWorkerMixin.java", "mixin/RegionFileStorageMixin.java"):
        assert pick(J + p) == (False, m), p
    assert pick("tools/smoke/search_cache.py") == (False, ["tools/smoke/search_cache.py"])
    assert sel.DURATION_S["tools/smoke/search_cache.py"] > 0


def test_coast():
    c = ["tools/smoke/coast.py"]
    mobs = ["tools/smoke/adult_guardians.py", "tools/smoke/anchored_guardians.py"] + c
    assert pick("tools/gen/shore/constructions.py") == (False, sorted(mobs + [AQUATIC])), "the drowned of the half-sunk one"
    assert pick("tools/gen/shore/__init__.py") == (False, sorted(mobs + [AQUATIC]))
    assert pick(J + "coast/Shoreline.java") == (False, sorted(c + [AQUATIC])), "the dry rooms of the aquatic structures"
    assert pick("tools/smoke/coast.py") == (False, c)
    assert sel.cost([J + "coast/Shoreline.java"]) and sel.cost(["tools/gen/shore/constructions.py"])


def test_profiles():
    p = ["tools/smoke/light_profile.py", "tools/smoke/profiles.py"]
    assert pick(J + "config/Profiles.java") == (False, p)
    assert pick(J + "command/ProfileCommand.java") == (False, p)
    assert pick(J + "config/ProfileAdvice.java") == (False, p)
    assert pick(J + "command/ProfileNotice.java") == (False, p)
    assert pick("tools/gen/light_profile.py") == (False, p)
    assert pick("tools/smoke/profiles.py") == (False, ["tools/smoke/profiles.py"])
    assert pick("tools/smoke/light_profile.py") == (False, ["tools/smoke/light_profile.py"])
    assert pick(J + "config/HeraldiaConfig.java")[0]          # the rest of the configuration: common, full suite
    assert pick("tools/gen/options.py")[0]


def test_herald_guide():
    assert pick(J + "command/Guide.java") == (False, ["tools/smoke/guide.py"])
    assert pick(J + "command/Texts.java") == (False, ["tools/smoke/guide.py"])
    assert pick("tools/gen/guide.py") == (False, ["tools/smoke/guide.py"])
    assert pick("tools/smoke/guide.py") == (False, ["tools/smoke/guide.py"])
    # languages: the translations and their check only run the Guide one (the fallback in the client's language)
    assert pick("tools/gen/languages.py") == (False, ["tools/smoke/guide.py"])
    assert pick("tools/gen/languages/fr_fr.json", "tools/gen/languages/gl_es.json") == (False, ["tools/smoke/guide.py"])
    assert pick("README.fr.md", "docs/CONFIGURACION.md", "tools/gen/tests/test_readme.py") == (False, [])
    assert pick(J + "command/KeyCommand.java") == (False, [])       # the rest of comando/: only the smoke one


def test_admin_tools():
    admin = (False, ["tools/smoke/admin.py"])
    for r in ("command/ReviewCommand.java", "command/Revision.java", "command/SafeSpot.java",
              "command/State.java", "command/ReloadCommand.java",
              "command/InfoCommand.java", "config/Reload.java"):
        assert pick(J + r) == admin, r
    # the status links to the journal and they share the advancements and the texts (admin.py)
    journal = (False, ["tools/smoke/admin.py", "tools/smoke/journal.py"])
    assert (pick(J + "command/StatusCommand.java")[0], sorted(pick(J + "command/StatusCommand.java")[1])) == journal
    assert (pick("tools/gen/admin.py")[0], sorted(pick("tools/gen/admin.py")[1])) == journal
    assert pick(J + "command/Journal.java") == (False, ["tools/smoke/journal.py"])
    assert pick("tools/smoke/journal.py") == (False, ["tools/smoke/journal.py"])
    # the end of the Chronicle: its scenario runs inside journal.py (the server groups are full)
    assert pick(J + "chronicle/ChronicleEnding.java") == (False, ["tools/smoke/journal.py"])
    assert pick("tools/gen/chronicle_ending.py") == (False, ["tools/smoke/journal.py"])
    assert pick("tools/smoke/admin.py") == admin
    assert pick(J + "config/HeraldiaConfig.java")[0]           # the rest of config/: common, full suite


def test_commands_in_english_and_warning_of_version():
    update = (False, ["tools/smoke/update_check.py"])
    for r in ("command/VersionNotice.java", "version/Version.java", "version/Releases.java", "version/Notified.java"):
        assert pick(J + r) == update, r
    assert pick("tools/smoke/update_check.py") == update
    commands = (False, sorted(["tools/smoke/update_check.py", "tools/smoke/admin.py", "tools/smoke/guide.py", "tools/smoke/arena.py",
                               "tools/smoke/arena_modes.py", "tools/smoke/journal.py"]))
    for r in (J + "command/HeraldiaCommands.java", J + "command/Alias.java", J + "mixin/CommandsMixin.java", "tools/gen/commands.py"):
        assert (pick(r)[0], sorted(pick(r)[1])) == commands, r


def test_loot_that_gets_replenishes_and_difficulty():
    assert pick(J + "loot/RestockedLoot.java") == (False, ["tools/smoke/loot_restock.py"])
    assert pick(J + "loot/Restock.java") == (False, ["tools/smoke/loot_restock.py"])
    assert pick(J + "bosses/ClearedSpawners.java") == (False, ["tools/smoke/boss_phases.py", "tools/smoke/cleared_spawners.py"])
    assert pick(J + "common/TemplateBlocks.java") == (False, ["tools/smoke/cleared_spawners.py", "tools/smoke/loot_restock.py"])
    assert pick(J + "difficulty/MobDifficulty.java") == (False, ["tools/smoke/difficulty.py"])
    assert pick(J + "difficulty/ModDifficulty.java", "tools/smoke/loot_restock.py") == \
        (False, ["tools/smoke/difficulty.py", "tools/smoke/loot_restock.py"])
    assert pick(J + "loot/PerPlayerChest.java")[0]         # the rest of loot/: common, full suite


def test_arena_of_waves():
    arena = (False, ["tools/smoke/arena.py", "tools/smoke/arena_modes.py"])
    assert pick(J + "arena/Game.java") == arena
    assert pick(J + "arena/Waves.java") == arena
    assert pick(J + "arena/Fame.java") == arena                  # T41: modes, ranking and hall of fame
    assert pick(J + "mixin/ArenaExplosionMixin.java") == arena
    assert pick("tools/gen/arena_waves.py") == arena
    assert pick("tools/smoke/arena.py") == (False, ["tools/smoke/arena.py"])
    assert pick("tools/smoke/arena_modes.py") == (False, ["tools/smoke/arena_modes.py"])
    assert pick(J + "mixin/ArenaPistonMixin.java", "tools/gen/guide.py") == \
        (False, ["tools/smoke/arena.py", "tools/smoke/arena_modes.py", "tools/smoke/guide.py"])


def test_cost_of_generation_by_paths():
    """The cost test (a CI job of its own) goes in a PR if the generation Java, the generator or the test itself
    changes; not with documentation, tests, commands or mobs. It does not enter the server groups."""
    assert sel.COST not in ALL_COMBOS and "tools/smoke/generation_cost.py" in [sel.rel(p) for p in
                                                                            sel.glob.glob(os.path.join(sel.ROOT, "tools", "smoke", "*.py"))]
    for r in [J + "mixin/ChunkGeneratorMixin.java", J + "mixin/StructureCheckMixin.java", J + "common/MediumStructures.java",
              J + "roads/RoadLayout.java", J + "mines/Hillside.java", J + "villages/Shoreline.java", J + "uniques/island/IslandZone.java",
              J + "config/GridPlacement.java", "tools/gen/houses.py", "tools/gen/mediums/inn.py", "tools/gen/uniques/castillo.py",
              "tools/smoke/generation_cost.py", "tools/smoke/cost_reference.json", "gradle.properties"]:
        assert sel.cost([r]), r
    for r in ["docs/DEVELOPMENT.md", "CHANGELOG.md", "tools/gen/tests/test_core.py", "tools/gen/README.md", "tools/gen/render.py",
              J + "command/Guide.java", J + "mixin/ZombieMixin.java", J + "bosses/Phases.java", J + "loot/RestockedLoot.java",
              "src/test/java/io/github/albertosa23/heraldia/common/ProfilerTest.java", "tools/smoke/trophies.py", ".github/workflows/ci.yml"]:
        assert not sel.cost([r]), r
    assert sel.cost(["docs/DEVELOPMENT.md", J + "mines/Hillside.java"]) and not sel.cost([])


def test_ci_matrix_says_yes_goes_the_cost():
    out = subprocess.run([sys.executable, os.path.join(TOOLS, "test.py"), "--ci-matrix", "--full"],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out)["cost"] is True and json.loads(out)["runtime"] is True
    out = subprocess.run([sys.executable, os.path.join(TOOLS, "test.py"), "--list-only", "--full"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out[-2:] == [sel.COST, sel.RUNTIME] and sorted(out[:-2]) == ALL_COMBOS


def test_play_cost_by_paths():
    """The play cost test (tick time while playing: a CI job of its own, "juego") goes in a PR if something that runs while
    playing or what the villages hold changes; not with documentation, tests or the generation of other structures. It is not
    a server group, and changing it alone runs no group."""
    assert sel.RUNTIME not in ALL_COMBOS
    for r in [J + "villages/VillageStructure.java", J + "caravans/Caravans.java", J + "arena/Arena.java", J + "mixin/ZombieMixin.java",
              J + "common/Anchoring.java", J + "bosses/Phases.java", "tools/gen/houses.py", "tools/gen/traces.py", "tools/gen/fillers.py",
              "tools/smoke/runtime_cost.py", "tools/smoke/TickSampler.java", "tools/smoke/runtime_reference.json", "gradle.properties",
              "tools/gen/mediums/inn.py", J + "inhabitants/Inhabitants.java"]:   # the mediums' inhabitants live and tick
        assert sel.runtime([r]), r
    for r in ["docs/DEVELOPMENT.md", "CHANGELOG.md", "tools/gen/tests/test_traces.py", "tools/gen/uniques/castillo.py",
              J + "command/Guide.java", "tools/smoke/generation_cost.py", ".github/workflows/ci.yml"]:
        assert not sel.runtime([r]), r
    for r in ["tools/smoke/runtime_cost.py", "tools/smoke/TickSampler.java", "tools/smoke/runtime_reference.json"]:
        assert pick(r) == (False, []), r


def test_caravans():
    p = ["tools/smoke/caravans.py"]          # the wayfarers' scenario (same engine) runs inside it
    assert pick(J + "caravans/Caravans.java") == (False, p)
    assert pick(J + "caravans/Journey.java") == (False, p)
    assert pick(J + "caravans/Wayfarers.java") == (False, p)
    assert pick("tools/gen/caravans.py") == (False, p)
    assert pick("tools/smoke/caravans.py") == (False, ["tools/smoke/caravans.py"])
    assert "wayfarers.py" in sel.NOT_TESTS
    assert pick("tools/smoke/wayfarers.py") == (False, p)
    assert sel.DURATION_S["tools/smoke/caravans.py"] > 0


def test_wizard_huts():
    p = ["tools/smoke/wizard_huts.py"]
    assert pick(J + "huts/Wizards.java") == (False, p)
    assert pick(J + "huts/Decision.java") == (False, p)
    assert pick("tools/gen/wizard_huts.py") == (False, p)
    assert pick("tools/smoke/wizard_huts.py") == (False, p)
    entire, tests = pick("tools/gen/mediums/wizard_hut.py")
    assert not entire and set(p) <= set(tests) and "tools/smoke/medium_structures.py" in tests
    assert sel.DURATION_S["tools/smoke/wizard_huts.py"] > 0


def test_safe_updates():
    """The Java in update/ also runs path B and undo (update_path_b.py); the panel, menus and texts only update.py."""
    both = (False, ["tools/smoke/update.py", "tools/smoke/update_path_b.py"])
    assert pick(J + "update/Execution.java") == both
    assert pick(J + "update/Analysis.java") == both
    assert pick(J + "command/ConfigPanel.java") == (False, ["tools/smoke/update.py"])
    assert pick("tools/smoke/update_path_b.py") == (False, ["tools/smoke/update_path_b.py"])
    assert sel.DURATION_S["tools/smoke/update_path_b.py"] > 0


def test_aquatic_dry():
    """The dry rooms' test runs with the aquatic structures and the coast, not with the mines (which reuse the coast's rule)."""
    for p in ("tools/gen/uniques/atlantis/districts.py", J + "uniques/atlantis/BasePiece.java", "tools/gen/uniques/galleon/ship.py",
              "tools/gen/uniques/corsair_island/caves.py", "tools/gen/uniques/lighthouse/blueprint.py",
              J + "uniques/lighthouse/LighthouseStructure.java", "tools/gen/shore/constructions.py", J + "coast/CoastStructure.java",
              AQUATIC):
        assert AQUATIC in pick(p)[1], p
    assert AQUATIC not in pick(J + "mines/Hillside.java")[1]
    assert AQUATIC not in pick("tools/gen/uniques/castle/__init__.py")[1]
    assert sel.DURATION_S[AQUATIC] > 0


def test_the_cost_jobs_say_why_they_run_or_not():
    """The reason CI prints for each cost job names the files that decided it, and says so when none did."""
    assert sel.why([], sel.COST_PATHS, "COST_PATHS", True).startswith("full suite")
    r = sel.why(["docs/CONTENT.md", "tools/smoke/roads.py"], sel.COST_PATHS, "COST_PATHS")
    assert r.startswith("none of the 2 changed file(s) is in COST_PATHS")
    r = sel.why(["tools/gen/houses.py", "README.md"], sel.RUNTIME_PATHS, "RUNTIME_PATHS")
    assert r == "1 changed file(s) in RUNTIME_PATHS: tools/gen/houses.py"
    assert sel.why(["tools/gen/tests/test_x.py"], sel.COST_PATHS, "COST_PATHS").startswith("none")   # COST_WITHOUT
    many = [f"tools/gen/f{i}.py" for i in range(7)]
    assert sel.why(many, sel.COST_PATHS, "COST_PATHS").endswith("(+2 more)")
