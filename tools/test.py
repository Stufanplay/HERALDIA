"""Which tests to run depending on the changed files (the same map locally and in CI).

Testing policy (docs/DEVELOPMENT.md): each session tests only its own work (unit tests + the server tests of
what it touches, which this script chooses by paths) and an auditing session runs the full suite.

Usage:
  python3 tools/test.py --affected           # unit tests + server tests of what changed versus origin/develop
  python3 tools/test.py --affected --base REF --jar build/libs/heraldia-X.jar
  python3 tools/test.py --all --jar ...      # full suite (auditing session): unit, smoke and all server tests
  python3 tools/test.py --list-only [--all]     # only says which server tests apply (runs nothing)
  python3 tools/test.py --unit-tests           # only the quick unit tests (generator's pytest)
  python3 tools/test.py --ci-matrix --base SHA [--full]   # JSON of the CI matrix (test groups)
  python3 tools/test.py --group "a.py b.py" --jar ... --work DIR   # runs a group serially (used by CI)

The server tests are discovered automatically: tools/smoke/*.py (except server_smoke.py, the smoke test, which always runs, and the
modules of NOT_TESTS) and tools/gen/uniques/*/smoke_*.py. compat_mods.py is one test per mod group
("tools/smoke/compat_mods.py::<grupo>", with --group): in a PR it only runs if something in COMPAT_PATHS changes. A new test enters the full suite without touching anything; for the path
selection to pick it too, it is enough for it to be in the folder of its unique structure (or, if it is in tools/smoke/, in SMOKE_OF_UNIQUE or in MAP).
The generation cost one (tools/smoke/generation_cost.py) is not in the groups: it has its own job in CI ("coste" in the
output of --ci-matrix) and locally it runs at the end of --affected (if what changed touches COST_PATHS) and of --all (--no-cost
removes it). The play cost one (tools/smoke/runtime_cost.py) likewise: its own CI job ("juego", "runtime" in --ci-matrix),
locally at the end of --affected (if what changed touches RUNTIME_PATHS) and of --all (--no-runtime removes it).
"""
import argparse, fnmatch, glob, json, os, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SMOKE = "tools/smoke/server_smoke.py"
FULL = "*"            # in the map: the change affects everything (common code) -> full suite
NOT_TESTS = {"server_smoke.py", "modrinth.py", "generation_cost.py", "runtime_cost.py", "wayfarers.py"}  # common modules, the cost
# ones (their own jobs) and the wayfarers' scenario, which runs inside caravans.py (same server and corridor)
# Compatibility with other mods (one test per group, with Modrinth mods): long and with downloads, so in a PR
# it only runs if the test itself, the mod list or the common placement code changes (what decides where each
# structure appears and whether it clashes with those of other mods). In the full suite (push to develop, workflow_dispatch, label) always.
COMPAT = "tools/smoke/compat_mods.py"

# Tests in tools/smoke/ that belong to one specific unique structure (those in tools/gen/uniques/<id>/ are associated automatically by folder).
SMOKE_OF_UNIQUE = {
    "citadel": ["tools/smoke/citadel_check.py"],
    "colosseum": ["tools/smoke/colosseum_redstone.py"],
    "galleon": ["tools/smoke/galleon_test.py", "tools/smoke/aquatic_dry.py"],
    "ash_citadel": ["tools/smoke/nether_end.py"], "void_sanctum": ["tools/smoke/nether_end.py"],
    "observatory": ["tools/smoke/observatory_smoke.py"],
    "palace": ["tools/smoke/palace_redstone.py"],
    # the dry rooms of the aquatic structures stay dry (and by the rules of the coast, AQUATIC)
    "atlantis": ["tools/smoke/aquatic_dry.py"], "corsair_island": ["tools/smoke/aquatic_dry.py"], "lighthouse": ["tools/smoke/aquatic_dry.py"],
}
# What every new or changed unique structure must also pass besides its own: its trophy, its chronicle sheet and its adult
# and anchored guardians.
OF_EVERY_UNIQUE = ["tools/smoke/trophies.py", "tools/smoke/story.py", "tools/smoke/adult_guardians.py",
                 "tools/smoke/anchored_guardians.py"]
# Java package of each unique structure with its own code (src/main/java/.../uniques/<package>/).
JAVA_UNIQUE = {"atlantis": "atlantis", "citadel": "citadel", "lighthouse": "lighthouse", "galleon": "galleon",
               "island": "corsair_island", "mine": "lost_mine"}
VILLAGES = ["tools/smoke/village_terrain.py", "tools/smoke/village_life.py", "tools/smoke/village_variants.py",
            "tools/smoke/village_routes.py"]
JAVA = "src/main/java/io/github/albertosa23/heraldia/"
COMPAT_PATHS = [COMPAT, "tools/smoke/modrinth.py", "gradle.properties", "tools/gen/biomes.py", "tools/gen/c_tags.json",
                JAVA + "config/GridPlacement.java", JAVA + "config/UniqueSeparation.java", JAVA + "config/VillageRules.java",
                JAVA + "mixin/ChunkGeneratorMixin.java", JAVA + "mixin/StructureCheckMixin.java", JAVA + "common/ForeignZone.java",
                JAVA + "uniques/island/IslandZone.java", JAVA + "uniques/atlantis/AtlantisAnchor.java", JAVA + "common/MediumStructures.java"]
# Generation cost (with and without Heraldia, compared with tools/smoke/cost_reference.json): CI's own job, in
# parallel with the server groups. In the full suite always; in a PR only if something in COST_PATHS changes (the
# generation Java, the generator or the test itself), except for COST_WITHOUT (tests and documentation).
COST = "tools/smoke/generation_cost.py"
COST_PATHS = [COST, "tools/smoke/cost_reference.json", "tools/gen/*", "gradle.properties",
               JAVA + "villages/*", JAVA + "roads/*", JAVA + "common/*", JAVA + "config/*", JAVA + "mines/*", JAVA + "coast/*",
               JAVA + "uniques/*",
               JAVA + "mixin/ChunkGeneratorMixin.java", JAVA + "mixin/StructureCheckMixin.java"]
COST_WITHOUT = ["tools/gen/tests/*", "*.md", "tools/gen/render.py", "tools/gen/look.py"]
# Play cost (tick time with players in villages, the arena and a caravan, with and without Heraldia, compared with
# tools/smoke/runtime_reference.json): CI's own job ("juego"), like the generation cost. In the full suite always; in a PR
# only if something that runs while playing, or what villages hold (their entities), changes; not tests and documentation.
RUNTIME = "tools/smoke/runtime_cost.py"
RUNTIME_PATHS = [RUNTIME, "tools/smoke/TickSampler.java", "tools/smoke/runtime_reference.json", "gradle.properties",
                 "tools/gen/houses.py", "tools/gen/fillers.py", "tools/gen/traces.py", "tools/gen/specials.py",
                 "tools/gen/streets.py", "tools/gen/pack.py", "tools/gen/board.py", "tools/gen/arena_waves.py",
                 "tools/gen/caravans.py", JAVA + "Heraldia.java", JAVA + "villages/*", JAVA + "caravans/*", JAVA + "arena/*",
                 JAVA + "mixin/*", JAVA + "common/*", JAVA + "bosses/*", JAVA + "quests/*", JAVA + "difficulty/*",
                 JAVA + "welcome/*", "tools/gen/mediums/*", JAVA + "inhabitants/*"]
RUNTIME_PATHS += [JAVA + "events/*"]          # village events: up to 25 entities in a square while one lasts
RUNTIME_PATHS += [JAVA + "herald/*", "tools/gen/herald_house.py", "tools/gen/herald_dress.py"]   # the Herald's House (scenario casa_heraldo)
RUNTIME_PATHS += ["tools/gen/spawn_roads.py", JAVA + "roads/SpawnRoadLayout.java", JAVA + "roads/BuiltRoads.java"]   # its roads' huts (the same scenario)
RUNTIME_PATHS += ["tools/gen/herald_grounds.py"]   # its grounds' houses and trees (the same scenario; no entities)
# The Herald's House roads (herald/SpawnRoads): both placement orders and a town from before the roads.
SPAWN_ROADS = ["tools/smoke/spawn_roads.py"]
# The Herald's House grounds (herald/Outskirts): a town from before them (the command) and a new world (after its roads).
HERALD_GROUNDS = ["tools/smoke/herald_grounds.py"]
# The Herald's House on the owner's own steep spawn (herald/Building, Shores, Outskirts, SpawnRoads): no water standing in
# the air, no ramps of one-block steps, no step on the roads; the saved world read back from its region files.
HERALD_STEEP = ["tools/smoke/herald_steep.py"]
# Look, do not take (herald/HeraldHouse.opened and its mixins): the area's containers as a player who is not an operator.
HERALD_LOOK = ["tools/smoke/herald_look.py"]
MEDIUMS = ["tools/smoke/medium_structures.py"]
ADMIN = ["tools/smoke/admin.py"]
UPDATE = ["tools/smoke/update_check.py"]
WEB_MAPS = ["tools/smoke/web_maps.py"]
# Treasure hunt (T40): its Java (tesoro/ package) and its generator (tables, texts, advancements).
TREASURE = ["tools/smoke/treasure.py"]
# Wave arena (T31) and its modes, weekly ranking and hall of fame (T41).
ARENA = ["tools/smoke/arena.py", "tools/smoke/arena_modes.py"]
COMMANDS = UPDATE + ADMIN + ["tools/smoke/guide.py", "tools/smoke/journal.py"] + ARENA
# Mine entrances: their generator (tools/gen/mines/) and their Java (minas/ package); the placement rule touches the medium structures' one.
MINES = ["tools/smoke/mine_entrances.py"]
# The world's search memory (common/SearchCache, SearchCaches and UnwrittenRegions, the IOWorker mixin): its server test
# (same answers after a restart, discarded with another configuration) and the far /locate of the mines.
SEARCH_CACHE = ["tools/smoke/search_cache.py", "tools/smoke/mine_entrances.py"]
# Coastal lighthouses and shipwrecks (T42): their generator (tools/gen/shore/) and their Java (costa/ package); their rule is that of the
# mines (minas/Minas.familia), and the drowned of the half-sunk one enters the tests that go through the template mobs.
COAST = ["tools/smoke/coast.py"]
COAST_MOBS = COAST + ["tools/smoke/adult_guardians.py", "tools/smoke/anchored_guardians.py"]
# The dry rooms of the aquatic structures (Atlantis, galleon, Corsair's isle, lighthouse, coastal lighthouses and shipwrecks
# and the harbors): with the coast's own rules, not with the mines' (which reuse COAST).
AQUATIC = ["tools/smoke/aquatic_dry.py"]
# Game profiles ("perfil" option, T36): their server test (restarts with each profile and an option set by hand).
PROFILES = ["tools/smoke/profiles.py", "tools/smoke/light_profile.py"]
# Board quests and per-village reputation (T38): their Java, the prices mixin and their texts and advancements; also the
# villager conversations (P9a), whose server scenario is in the same test.
QUESTS = ["tools/smoke/quests.py"]
# Caravans along the roads (T39): their Java and their texts and advancement.
CARAVANS = ["tools/smoke/caravans.py"]
# The medium structure types bring anchored mobs (and adult zombies): the tests that go through all the template mobs.
MEDIUMS_MOBS = MEDIUMS + ["tools/smoke/adult_guardians.py", "tools/smoke/anchored_guardians.py"]
# Nether and End content (T44): medium and unique structures with DIMENSION, their structure type and their placement
NETHER_END = ["tools/smoke/nether_end.py"]
# Wizard huts (T43): the Evil Wizard (Java chozas/) and its loot and texts; its template is a medium structure.
HUTS = ["tools/smoke/wizard_huts.py"]
# Ambient effects (bell, lighthouse siren, mine drips): their Java (ambience/).
AMBIENCE = ["tools/smoke/ambience.py"]
# Village events (market day, wedding, funeral, festival): their Java (events/), texts and spoken lines.
EVENTS = ["tools/smoke/village_events.py"]
# Safe updates (T46): dialog panel, per-player language, per-version fixes and update analyze/apply (path A: pristine
# chunks regenerated) and, for the Java in update/, also path B (new structures placed in generated chunks) and undo.
SAFE_UPDATE = ["tools/smoke/update.py"]
SAFE_UPDATE_JAVA = SAFE_UPDATE + ["tools/smoke/update_path_b.py"]

# Path -> server tests map. It is traversed in order and the FIRST rule that matches wins (fnmatch: * crosses "/").
# An empty list: the change needs no server tests (beyond the smoke test, which always runs in CI).
# Whatever matches no rule is treated as common: full suite (better too many than too few).
MAP = [
    # no server tests: documentation, unit tests, client, changelog
    ("docs/*", []), ("*.md", []), ("tools/gen/tests/*", []), ("src/test/*", []), ("src/client/*", []),
    ("tools/changelog.py", []), ("tools/gen/render.py", []), ("tools/gen/look.py", []), ("tools/gen/README.md", []), (".gitignore", []),
    # the play cost: its own CI job (RUNTIME_PATHS), no server group
    (RUNTIME, []), ("tools/smoke/TickSampler.java", []), ("tools/smoke/runtime_reference.json", []),
    # villages: piece generator and its Java
    ("tools/gen/houses.py", VILLAGES), ("tools/gen/streets.py", VILLAGES), ("tools/gen/specials.py", VILLAGES),
    ("tools/gen/fillers.py", VILLAGES), ("tools/gen/themes.py", VILLAGES), ("tools/gen/sim.py", VILLAGES),
    ("tools/gen/board.py", ["tools/smoke/village_life.py"]),
    ("tools/gen/trades.py", ["tools/smoke/village_life.py"]), (JAVA + "villages/*", VILLAGES),
    ("tools/gen/maps.py", ["tools/smoke/village_life.py", "tools/smoke/story.py"]),
    ("tools/gen/loot.py", []),                 # the smoke test reads all the tables
    # filler loot: every container without a table of its own (the rules live in the generator; its test opens real ones)
    ("tools/gen/filler_loot.py", ["tools/smoke/filler_loot.py"]),
    ("tools/gen/advancements.py", ["tools/smoke/trophies.py", "tools/smoke/story.py", "tools/smoke/village_life.py"]),
    # medium structures: their types (tools/gen/mediums/) and their Java placement rule
    ("tools/gen/dimensions.py", NETHER_END + MEDIUMS), (JAVA + "dimensions/*", NETHER_END),
    ("tools/gen/uniques/_enclosure.py", NETHER_END + OF_EVERY_UNIQUE),
    ("tools/gen/mediums/wizard_hut.py", MEDIUMS_MOBS + HUTS),
    ("tools/gen/mediums/*", MEDIUMS_MOBS + NETHER_END), (JAVA + "common/MediumStructures.java", MEDIUMS + NETHER_END),
    # inhabitants of the medium structures: their option, applied when each one first loads
    (JAVA + "inhabitants/*", MEDIUMS),
    ("tools/gen/mines/*", MINES), (JAVA + "mines/*", MINES + COAST),
    ("tools/gen/shore/*", COAST_MOBS + AQUATIC), (JAVA + "coast/*", COAST + AQUATIC),
    # /locate of the mines (T36): the shared height cache and the parallel look-ahead computation are only used by the mines
    (JAVA + "common/HeightCache.java", MINES), (JAVA + "mixin/ChunkGeneratorLocateMixin.java", MINES),
    # the world's search memory: /locate, the maps, /heraldia info nearby and the Chronicle folios answered from what was asked before
    (JAVA + "common/SearchCache*.java", SEARCH_CACHE), (JAVA + "common/UnwrittenRegions.java", SEARCH_CACHE),
    (JAVA + "mixin/IOWorkerMixin.java", SEARCH_CACHE), (JAVA + "mixin/RegionFileStorageMixin.java", SEARCH_CACHE),
    # board quests and reputation (T38)
    (JAVA + "quests/*", QUESTS), (JAVA + "mixin/VillagerPricesMixin.java", QUESTS), ("tools/gen/quests.py", QUESTS),
    # villager conversations (P9a): their scenario lives in the quests test (a real village and a simulated player)
    (JAVA + "dialogue/*", QUESTS), ("tools/gen/dialogue.py", QUESTS), ("tools/gen/dialogue/*", QUESTS),
    # the choice windows (conversations and the arena bell's menu in the middle of the screen): their scenarios live in
    # the quests test (the conversation as a vanilla client gets it) and the arena modes test (the bell's menu)
    # the look-only windows of the Herald's House area: the mark, the packets dropped and the test's packet commands
    (JAVA + "herald/LookOnly.java", HERALD_LOOK), (JAVA + "mixin/HeraldLook*", HERALD_LOOK),
    (JAVA + "mixin/HeraldOpenMenuMixin.java", HERALD_LOOK), (JAVA + "mixin/HeraldCompoundContainerMixin.java", HERALD_LOOK),
    (JAVA + "choice/ClientPackets.java", HERALD_LOOK + QUESTS),
    (JAVA + "choice/*", QUESTS + ["tools/smoke/arena_modes.py"]),
    # reputation visible in the village: its scenario lives in the quests test too (the same village reaches "conocido")
    (JAVA + "welcome/*", QUESTS),
    # caravans along the roads (T39)
    (JAVA + "caravans/*", CARAVANS), ("tools/gen/caravans.py", CARAVANS), ("tools/smoke/wayfarers.py", CARAVANS),
    # chozas de mago (T43)
    (JAVA + "huts/*", HUTS), ("tools/gen/wizard_huts.py", HUTS),
    # ambient effects
    (JAVA + "ambience/*", AMBIENCE),
    # village events (their spoken lines are in tools/gen/dialogue/*/events.json, matched above by the conversations' rule)
    (JAVA + "events/*", EVENTS), ("tools/gen/village_events.py", EVENTS),
    # safe updates (T46): their Java, the panel, the preferences, the menus, the migration and their texts
    (JAVA + "update/*", SAFE_UPDATE_JAVA), (JAVA + "command/ConfigPanel.java", SAFE_UPDATE),
    (JAVA + "command/Preferences.java", SAFE_UPDATE), (JAVA + "config/Menus.java", SAFE_UPDATE),
    (JAVA + "config/ConfigMigration.java", SAFE_UPDATE), ("tools/gen/updates.py", SAFE_UPDATE),
    # game profiles (T36): their logic and their command (the rest of the configuration is common: full suite)
    (JAVA + "config/Profiles.java", PROFILES), (JAVA + "command/ProfileCommand.java", PROFILES),
    # light profile: the suggestion, the seam warning and their texts
    (JAVA + "config/ProfileAdvice.java", PROFILES), (JAVA + "command/ProfileNotice.java", PROFILES), ("tools/gen/light_profile.py", PROFILES),
    ("tools/gen/biomes.py", ["tools/smoke/terralith_biomes.py"]),
    ("tools/gen/c_tags.json", ["tools/smoke/terralith_biomes.py"]),
    # the pinned Modrinth mods: the tests that download them (the compatibility ones, via COMPAT_PATHS)
    ("tools/smoke/modrinth.py", ["tools/smoke/trophies.py", "tools/smoke/story.py", "tools/smoke/village_life.py",
                                 "tools/smoke/terralith_biomes.py"]),
    # template mob mixins and commands (the smoke test tries /heraldia info and llave)
    (JAVA + "mixin/Zombie*", ["tools/smoke/adult_guardians.py"]),
    (JAVA + "mixin/DrownedMixin.java", ["tools/smoke/adult_guardians.py"]),
    (JAVA + "mixin/DrownedWaterMixin.java", ["tools/smoke/anchored_guardians.py"]),
    (JAVA + "mixin/DrownedBeachMixin.java", ["tools/smoke/anchored_guardians.py"]),
    (JAVA + "mixin/CubeMobJumpMixin.java", ["tools/smoke/anchored_guardians.py"]),
    (JAVA + "mixin/PiglinStrollMixin.java", ["tools/smoke/anchored_guardians.py"]),
    (JAVA + "common/Anchoring.java", ["tools/smoke/anchored_guardians.py"]),
    # template blocks at their world position: the restocking loot and the cleared uniques use them
    (JAVA + "common/TemplateBlocks.java", ["tools/smoke/loot_restock.py", "tools/smoke/cleared_spawners.py"]),
    # replenished loot and configurable difficulty (T29)
    (JAVA + "loot/RestockedLoot.java", ["tools/smoke/loot_restock.py"]), (JAVA + "loot/Restock.java", ["tools/smoke/loot_restock.py"]),
    (JAVA + "difficulty/*", ["tools/smoke/difficulty.py"]),
    # Herald's Guide: its Java (and the per-language texts it uses), its generator and its test
    # each player's journal (/heraldia journal): its Java and its texts; it reads the advancements /heraldia status counts
    (JAVA + "command/Journal.java", ["tools/smoke/journal.py"]),
    # the end of the Chronicle: its Java and its generator (texts, last leaf, advancements); its scenario runs inside journal.py
    (JAVA + "chronicle/*", ["tools/smoke/journal.py"]), ("tools/gen/chronicle_ending.py", ["tools/smoke/journal.py"]),
    (JAVA + "command/Guide*", ["tools/smoke/guide.py"]), (JAVA + "command/Texts.java", ["tools/smoke/guide.py"]),
    ("tools/gen/guide.py", ["tools/smoke/guide.py"]),
    # mod languages (translations and their check): the Guide is the only thing the server delivers in the client's language
    ("tools/gen/languages.py", ["tools/smoke/guide.py"]), ("tools/gen/languages/*", ["tools/smoke/guide.py"]),
    # administration tools (T35): /heraldia review, status and reload (and the info nearby search they reuse)
    (JAVA + "command/Revi*", ADMIN), (JAVA + "command/SafeSpot.java", ADMIN),
    (JAVA + "command/StatusCommand.java", ADMIN + ["tools/smoke/journal.py"]), (JAVA + "command/State.java", ADMIN), (JAVA + "command/ReloadCommand*", ADMIN), (JAVA + "command/InfoCommand.java", ADMIN),
    (JAVA + "config/Reload.java", ADMIN), ("tools/gen/admin.py", ADMIN + ["tools/smoke/journal.py"]),
    # commands in English and their old aliases (T35b): the /heraldia tree is used by all the command tests; the
    # new-version notice, its test with the fake API
    (JAVA + "command/HeraldiaCommands.java", COMMANDS), (JAVA + "command/Alias.java", COMMANDS),
    (JAVA + "mixin/CommandsMixin.java", COMMANDS), ("tools/gen/commands.py", COMMANDS),
    (JAVA + "command/VersionNotice.java", UPDATE), (JAVA + "version/*", UPDATE),
    # web maps (T37): their Java (with the adapters), the advancements mixin and their test with squaremap and without maps
    (JAVA + "maps/*", WEB_MAPS), (JAVA + "mixin/PlayerAdvancementsMixin.java", WEB_MAPS),
    # treasure hunt (T40): its Java and its generator; the reward of the board's feats goes in board.py (above)
    (JAVA + "treasure/*", TREASURE), ("tools/gen/treasure.py", TREASURE),
    (JAVA + "command/*", []),
    # bosses: phases, reinforcements and guardian bar (their Java and the generator's reinforcements contract), and the
    # cleared uniques (spawners turned off when the guardian dies)
    (JAVA + "bosses/*", ["tools/smoke/boss_phases.py", "tools/smoke/cleared_spawners.py"]),
    ("tools/gen/bosses.py", ["tools/smoke/boss_phases.py"]),
    # wave arena (T31) and its modes (T41): its Java, its mixins and its generator (template, data, loot and advancements)
    (JAVA + "arena/*", ARENA), (JAVA + "mixin/Arena*", ARENA), ("tools/gen/arena_waves.py", ARENA),
    # roads between villages: their Java and their data
    # the Herald's House roads (built, not generated): their layout, their build, the huts and the guide
    (JAVA + "roads/SpawnRoadLayout.java", SPAWN_ROADS), (JAVA + "roads/BuiltRoads.java", SPAWN_ROADS + HERALD_STEEP),
    ("tools/gen/spawn_roads.py", SPAWN_ROADS), (JAVA + "herald/SpawnRoads.java", SPAWN_ROADS + ["tools/smoke/arena.py"] + HERALD_STEEP),
    (JAVA + "roads/RoadProfile.java", SPAWN_ROADS + HERALD_STEEP),   # only the built roads (SpawnRoads) use it
    # the Herald's House grounds (built, not generated): their plan, their build, the houses and the trees; the roads
    # cross them and go round their houses
    (JAVA + "herald/Outskirts*.java", HERALD_GROUNDS + SPAWN_ROADS + HERALD_STEEP), ("tools/gen/herald_grounds.py", HERALD_GROUNDS + SPAWN_ROADS),
    # the town's build (its shores) and the shores' own code: the town placed by the arena's test too
    (JAVA + "herald/Shores.java", HERALD_STEEP + HERALD_GROUNDS), (JAVA + "herald/Building.java", HERALD_STEEP + HERALD_GROUNDS + ["tools/smoke/arena.py"]),
    # how our builds put a template into the world (no block of it waterlogged by the water already there): the town, its
    # grounds' houses and the huts of its roads
    (JAVA + "common/Placing.java", HERALD_STEEP + HERALD_GROUNDS + SPAWN_ROADS + ["tools/smoke/arena.py"]),
    (JAVA + "roads/*", ["tools/smoke/roads.py"]), ("tools/gen/roads.py", ["tools/smoke/roads.py"]),
    # common code: full suite
    ("tools/gen/uniques/_common/*", FULL), ("tools/gen/uniques/__init__.py", FULL), ("tools/gen/writer.py", FULL),
    ("tools/gen/core.py", FULL), ("tools/gen/pack.py", FULL), ("tools/gen/lint.py", FULL), ("tools/gen/validate.py", FULL),
    ("tools/gen/main.py", FULL), ("tools/gen/build.py", FULL), ("tools/gen/options.py", FULL), ("tools/gen/requirements.txt", FULL),
    ("tools/smoke/server_smoke.py", FULL), ("tools/test.py", FULL), (".github/*", FULL), ("build.gradle", FULL),
    ("gradle.properties", FULL), ("settings.gradle", FULL), ("gradle/*", FULL), ("gradlew*", FULL),
    ("src/main/resources/*", FULL), (JAVA + "*", FULL),
]


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def compat_groups():
    """Groups of compat_mods.py, read from its source (the GROUPS literal) without importing it. Importing it put
    tools/smoke at the head of sys.path for the rest of the process (compat_mods.py inserts its own folder), and eight
    modules share a name between tools/smoke and tools/gen (treasure, guide, quests...): a later lazy `import treasure`
    of the generator then loaded the server test (test_readme.py failed 12 cases after test_selector.py)."""
    import ast
    with open(os.path.join(ROOT, COMPAT), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "GROUPS" for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise SystemExit(f"{COMPAT}: GROUPS (a literal dict) not found")


def discover():
    """All the server tests (without the smoke test), sorted; compat_mods.py, one per group."""
    smoke = [rel(p) for p in glob.glob(os.path.join(ROOT, "tools", "smoke", "*.py")) if os.path.basename(p) not in NOT_TESTS]
    uniques = [rel(p) for p in glob.glob(os.path.join(ROOT, "tools", "gen", "uniques", "*", "smoke_*.py"))]
    if COMPAT in smoke:
        smoke.remove(COMPAT)
        smoke += [f"{COMPAT}::{g}" for g in compat_groups()]
    return sorted(smoke + uniques)


def is_compat(test):
    return test.split("::")[0] == COMPAT


def order(test):
    """Order to run a test: [script, arguments...] ("path::group" passes --group group)."""
    script, _, group = test.partition("::")
    return [os.path.join(ROOT, script)] + (["--group", group] if group else [])


def for_unique(sid, all_items):
    """Server tests of a unique structure: those in its folder, those of SMOKE_OF_UNIQUE and OF_EVERY_UNIQUE."""
    own_ones = [p for p in all_items if p.startswith(f"tools/gen/uniques/{sid}/")]
    return own_ones + SMOKE_OF_UNIQUE.get(sid, []) + OF_EVERY_UNIQUE


def dest(route, all_items):
    """Server tests required by a changed file: a list, or ALL."""
    if route in all_items:                                           # the test itself
        return [route]
    if route == COMPAT:
        return [p for p in all_items if is_compat(p)]
    parts = route.split("/")
    if route.startswith("tools/gen/uniques/") and len(parts) >= 4 and not parts[3].startswith("_"):
        sid = parts[3][:-3] if len(parts) == 4 and parts[3].endswith(".py") else parts[3]
        if len(parts) > 4 or route.endswith(".py"):
            return for_unique(sid, all_items)
    if route.startswith(JAVA + "uniques/") and len(parts) > 9:      # src/main/java/io/github/albertosa23/heraldia/uniques/<paquete>/...
        pkg = parts[8]
        if pkg in JAVA_UNIQUE:
            return for_unique(JAVA_UNIQUE[pkg], all_items)
        return FULL
    for pattern, tests in MAP:
        if fnmatch.fnmatch(route, pattern):
            return tests
    return FULL


def choose(changed_list, all_items=None):
    """(full, [tests]) for a list of changed paths (relative to the root, with "/"). The compatibility ones
    (COMPAT) only enter if some path is in COMPAT_PATHS, also when what changed requires the full suite."""
    all_items = discover() if all_items is None else all_items
    compat = any(fnmatch.fnmatch(r, pat) for r in changed_list for pat in COMPAT_PATHS)
    chosen_ones = set()
    for r in changed_list:
        p = dest(r, all_items)
        if p == FULL:
            return True, [x for x in all_items if compat or not is_compat(x)]
        chosen_ones.update(x for x in p if x in all_items)
    if compat:
        chosen_ones.update(x for x in all_items if is_compat(x))
    return False, sorted(chosen_ones)


def cost(changed_list):
    """Does the list of changed paths require the generation cost test (COST_PATHS without COST_WITHOUT)?"""
    return any(any(fnmatch.fnmatch(r, p) for p in COST_PATHS) and not any(fnmatch.fnmatch(r, p) for p in COST_WITHOUT)
               for r in changed_list)


def runtime(changed_list):
    """Does the list of changed paths require the play cost test (RUNTIME_PATHS without COST_WITHOUT)?"""
    return any(any(fnmatch.fnmatch(r, p) for p in RUNTIME_PATHS) and not any(fnmatch.fnmatch(r, p) for p in COST_WITHOUT)
               for r in changed_list)


def changed_list(base):
    """Files changed versus `base` (merge-base), plus those of the working tree not yet committed."""
    def git(*a):
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    mb = git("merge-base", base, "HEAD")[0].strip()
    out = git("diff", "--name-only", mb) + git("ls-files", "--others", "--exclude-standard")
    return sorted({l.strip() for l in out if l.strip()})


# Measured duration of each test in CI (s, only the test step; server already cached). Used to distribute them
# into similar groups; a test that is not here counts as DEFAULT_S. Recalibrated (audit, 20 Nov 2026) from the "OK <test>
# (N s)" lines of the two full-suite runs on develop after #119 and #120 (CI runs 44732313111 and 44755065375): the longer
# of the two plus 10 %, rounded up to 5 s; a test that failed in both (caravans, update_path_b, by the two bugs fixed then)
# keeps the higher of its old value and that. The comments after some values are older and may cite older figures.
# Before that, from a full-suite run on develop (CI run 44355003539, Nov 2026): the CI time plus 10 %, rounded up to 5 s. Where that run is no
# reference (the test failed in it, or changed afterwards: village_terrain.py) the higher of the old value and the
# measurement is kept. Before, many values were local guesses far above CI (nether_end 300 vs 41 s, mine_entrances 250 vs
# 79) and two were below (anchored_guardians 450 vs 509, caravans 330 vs 348). A new test: write its real CI time (the
# "OK ... (N s)" line of its group's job), not an estimate. Note that the number of groups is about total / longest test:
# making the longest test shorter means MORE groups (each group is at most as long as the longest test).
DURATION_S = {
    "tools/smoke/village_life.py": 175, "tools/smoke/village_variants.py": 150, "tools/smoke/village_terrain.py": 260,
    "tools/smoke/village_routes.py": 235,          # the 8 villages on a flat world, 14,000 ticks; CI: 159 and 213 s in two runs of PR #130 (Nov 2026): the higher + 10 %
    "tools/gen/uniques/corsair_island/smoke_server.py": 125, "tools/gen/uniques/lost_mine/smoke_server.py": 85,
    "tools/smoke/trophies.py": 100, "tools/smoke/citadel_check.py": 65, "tools/smoke/observatory_smoke.py": 85,
    "tools/smoke/adult_guardians.py": 140, "tools/gen/uniques/sanctuary/smoke_server.py": 70,
    "tools/gen/uniques/cathedral/smoke_game.py": 75, "tools/gen/uniques/jarl_hall/smoke_server.py": 65,
    "tools/gen/uniques/mycelium_lab/smoke_server.py": 75, "tools/smoke/story.py": 60,
    "tools/smoke/palace_redstone.py": 55, "tools/smoke/terralith_biomes.py": 50,
    "tools/gen/uniques/ice_fortress/smoke_server.py": 40, "tools/gen/uniques/monastery/smoke_server.py": 50,
    "tools/gen/uniques/castle/smoke_redstone.py": 50, "tools/gen/uniques/mansion/smoke_server.py": 50,
    "tools/smoke/colosseum_redstone.py": 45, "tools/smoke/compatible_grid.py": 35, "tools/smoke/roads.py": 370,
    "tools/gen/uniques/wizard_tower/smoke_redstone.py": 45,
    "tools/gen/uniques/pyramid/smoke_server.py": 40, "tools/smoke/galleon_test.py": 40,
    "tools/smoke/cleared_spawners.py": 80,               # three starts and a generated castle
    "tools/smoke/boss_phases.py": 65,                     # two starts (the second, with the options disabled)
    # compatibility (Modrinth downloads cached)
    **{f"{COMPAT}::{g}": s for g, s in {"base": 90, "rendimiento": 60, "biomas": 105, "servidor": 70, "distanthorizons": 70,
                                         "estructuras": 115, "terreno": 110, "tectonic": 150, "wwoo": 280}.items()},
    "tools/smoke/anchored_guardians.py": 655,
    "tools/smoke/medium_structures.py": 300,          # 267 s on CI + 10 % and the 8 s the shulkers are given to settle; measured locally (4 cores): 263 s + 10 %, with the inhabitants settling on the first located structure of each kind (6; the other 12 and the three-day stay behind --stay: 639 s)
    "tools/smoke/guide.py": 55,                      # three server starts
    "tools/smoke/search_cache.py": 50,                # three starts, eleven searches
    "tools/smoke/journal.py": 45,                     # one start and a few commands as simulated players (with the end of the Chronicle)
    "tools/smoke/mine_entrances.py": 95,                     # two starts (multiplier 1 and 5), the mines' generation and /locate far away
    "tools/smoke/coast.py": 160,                     # two starts, four /locate with their generation and /place next to beaches
    "tools/smoke/profiles.py": 65,                  # four starts of the same world
    "tools/smoke/light_profile.py": 55,             # three starts and 1,300 sprinted ticks
    "tools/smoke/update.py": 165,                # two starts and a zone of 400 chunks
    "tools/smoke/update_path_b.py": 160,         # five starts, a zone of ~200 chunks, path B and undo
    "tools/smoke/loot_restock.py": 95,             # two starts and a generated hermitage
    "tools/smoke/difficulty.py": 80,                # four starts of the same world
    "tools/smoke/arena.py": 215,                     # two starts, three builds and five waves, and the Herald's House (v2: 18 residents, a market day on its plaza); measured locally (4 cores): 184 s + 10 %
                                                     # (LOCAL measurement, 161 s twice + 10 %: not a CI one; refresh it)
    "tools/smoke/arena_modes.py": 145,               # two starts, one build, seven short waves and the two-week close (+5: the bell's container menu, its refused replies and a mode disabled while it is open; measured locally: +4 s)
    "tools/smoke/admin.py": 65,                      # two starts and two medium structures loaded or generated
    "tools/smoke/update_check.py": 110,              # three starts (with the fake API, without network and disabled)
    "tools/smoke/web_maps.py": 105,                 # three starts (without maps, with squaremap and Carpet, and after restarting)
    "tools/smoke/existing_world.py": 155,           # three starts of the same world
    "tools/smoke/quests.py": 240,                 # two starts of the same world and a generated village (~80 s), then four more starts and a second village for the reputation looks (measured locally: +95 s) (+10: the conversation as a vanilla client's container menu; measured locally: +6 s, the whole test 170 s)
    "tools/smoke/treasure.py": 110,                    # three starts, the whole chain and the chest
    "tools/smoke/nether_end.py": 70,                # T44: one start, /locate and generation in the Nether and the End, /place of 16 styles
    "tools/smoke/wizard_huts.py": 85,               # two starts, four huts and three Evil Wizards
    "tools/smoke/caravans.py": 380,                 # two starts, 387 corridor chunks, 5 caravans and the 9 wayfarers of wayfarers.py
    "tools/smoke/ambience.py": 145,                 # one start, three /locate'd structures, ~11,000 sprinted ticks
    "tools/smoke/spawn_roads.py": 230,            # the Herald's House roads: four starts, two towns, two arenas, three road builds and their audits; CI: 205 s (run 44858433926, Nov 2026, with the dry pass) + 10 %
    "tools/smoke/herald_grounds.py": 245,            # the Herald's House grounds: three starts, two towns, two grounds' builds (one after its roads) and their audits; CI: 222 s (run 44858433926, Nov 2026, with the dry pass) + 10 %
    "tools/smoke/aquatic_dry.py": 170,             # one start, seven /locate'd aquatic structures and their chunks, 200 ticks, the regions read back; measured locally (4 cores): 124-136 s + 10 % (LOCAL: replace with its CI time)
    "tools/smoke/village_events.py": 195,         # measured locally (4 cores): 160 and 156 s of server log in two runs (four starts, one after a kill; ~20,000 sprinted ticks) + 10 % + setup; replace with its CI time
    "tools/smoke/filler_loot.py": 40,             # one start, 17 tables rolled ten times, 7 templates placed and 13 containers unpacked; measured locally (4 cores): 31 and 34 s + 10 % (LOCAL: replace with its CI time)
    "tools/smoke/herald_steep.py": 125,            # one start (the owner's seed, large biomes), a pond, the town, its roads and grounds, the regions read back; CI: 111 s (run 44858433926, Nov 2026, with the dry pass) + 10 %
    "tools/smoke/herald_look.py": 120,            # one start, the town placed (roads and grounds off), two simulated players and ~150 window packets; CI: 108 s (run 44858433926, Nov 2026, with the dry pass) + 10 %
}
DEFAULT_S = 90
# Each CI job pays ~25 s of setup (machine, Java, Python, caches) before the test: short tests are combined
# into one job as long as the group does not exceed the longest one (so CI is not lengthened and fewer machines are used). Free GitHub
# Actions gives 20 concurrent jobs: with the smoke test and the build, the full suite fits in a single batch.
# The real group size is max(GROUP_CAP_S, the longest test): see the trap in groups().
GROUP_CAP_S = 170


def groups(tests, cap=GROUP_CAP_S):
    """Distributes the tests into groups (lists) of duration <= max(cap, the longest): longest first, each into
    the shortest group where it fits (if it fits in none, it opens another). Deterministic.
    Trap: the group size is max(cap, the longest test), so the number of groups is about total / longest test, and
    SHORTENING THE LONGEST TEST RAISES THE NUMBER OF GROUPS (with the table of Nov 2026 before recalibrating,
    anchored_guardians at 450 s gave 16 groups, at 350 s 20, at 300 s 21). It only shortens CI wall-clock time."""
    dur = lambda p: DURATION_S.get(p, DEFAULT_S)
    cap = max([cap] + [dur(p) for p in tests])
    out = []
    for p in sorted(tests, key=lambda p: (-dur(p), p)):
        fits = [g for g in out if sum(map(dur, g)) + dur(p) <= cap]
        if fits:
            min(fits, key=lambda g: sum(map(dur, g))).append(p)
        else:
            out.append([p])
    return out


def name(g):
    """Short name of a group for CI: "isla_corsario + piramide"."""
    def brief(p):
        if "::" in p:
            return "compat " + p.split("::")[1]
        parts = p.split("/")
        return parts[3] if p.startswith("tools/gen/uniques/") else parts[-1][:-3]
    return " + ".join(brief(p) for p in g)


def matrix(full, tests):
    return {"include": [{"name": name(g), "tests": " ".join(g)} for g in groups(tests)]} if tests else {"include": []}


def unit_tests():
    """Quick unit tests of the generator (pytest). The JUnit ones run with ./gradlew test."""
    return subprocess.run([sys.executable, "-m", "pytest", "-q", os.path.join(ROOT, "tools", "gen", "tests")],
                          cwd=ROOT).returncode


def execute(tests, jar, work, logs=None):
    """Runs the server tests serially (all of them, even if one fails) and returns those that fail. Copies the
    logs/latest.log of each one to `logs` (if given) to upload it as an artifact."""
    bad_all = []
    for p in tests:
        t0 = time.monotonic()
        print(f"::group::{p}" if os.environ.get("GITHUB_ACTIONS") else f"== {p}", flush=True)
        r = subprocess.run([sys.executable, *order(p), "--jar", jar, "--work", work], cwd=ROOT).returncode
        if os.environ.get("GITHUB_ACTIONS"):
            print("::endgroup::")
        print(f"{'OK' if r == 0 else 'FAIL'} {p} ({time.monotonic() - t0:.0f} s)", flush=True)
        if logs:
            os.makedirs(logs, exist_ok=True)
            src = os.path.join(work, "logs", "latest.log")
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(logs, p.replace("::", "-").replace("/", "-").replace(".py", "") + ".log"))
        if r:
            bad_all.append(p)
    return bad_all


def default_jar():
    props = dict(l.strip().split("=", 1) for l in open(os.path.join(ROOT, "gradle.properties"), encoding="utf-8")
                 if "=" in l and not l.lstrip().startswith("#"))
    return os.path.join(ROOT, "build", "libs", f"heraldia-{props['mod_version']}.jar")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--affected", action="store_true", help="unit tests + server tests of what changed")
    mode.add_argument("--all", action="store_true", help="full suite (auditing session)")
    mode.add_argument("--list-only", action="store_true", help="only list the chosen server tests")
    mode.add_argument("--unit-tests", action="store_true", help="only the generator's unit tests")
    mode.add_argument("--ci-matrix", action="store_true", help="JSON matrix for CI")
    mode.add_argument("--group", help="run these tests serially (separated by spaces)")
    ap.add_argument("--base", default="origin/develop", help="reference to compare against (default origin/develop)")
    ap.add_argument("--full", action="store_true", help="with --ci-matrix/--list-only: full suite")
    ap.add_argument("--jar", help="the mod's .jar (default: that of the version in gradle.properties)")
    ap.add_argument("--work", default=os.path.join(ROOT, "build", "smoke"), help="folder of the test server")
    ap.add_argument("--logs", help="folder where to copy each test's log")
    ap.add_argument("--no-unit", action="store_true", help="with --affected/--all: skip the unit tests")
    ap.add_argument("--no-cost", action="store_true", help="with --affected/--all: skip the generation cost test")
    ap.add_argument("--no-runtime", action="store_true", help="with --affected/--all: skip the play cost test")
    a = ap.parse_args(argv)
    work = os.path.abspath(a.work)       # the scripts start Java with cwd=--work: absolute path
    jar = os.path.abspath(a.jar or default_jar())

    if a.unit_tests:
        return unit_tests()
    if a.group is not None:
        bad_all = execute(a.group.split(), jar, work, a.logs)
        print("Fallan:" if bad_all else "All pass.", " ".join(bad_all))
        return 1 if bad_all else 0

    if a.all or a.full:
        full, tests, changes, with_cost, with_runtime = True, discover(), [], True, True
    else:
        changes = changed_list(a.base)
        (full, tests), with_cost, with_runtime = choose(changes), cost(changes), runtime(changes)
    if a.ci_matrix:
        print(json.dumps(dict(matrix(full, tests), full=full, cost=with_cost, runtime=with_runtime), ensure_ascii=False))
        return 0
    if a.list_only or a.affected:
        print(f"{len(changes)} ficheros cambiados frente a {a.base}" if changes else "full suite", file=sys.stderr)
        print(("Full suite: " if full else "Affected server tests: ") + (", ".join(tests) or "none"),
              file=sys.stderr)
        print(f"Generation cost ({COST}): {'sí' if with_cost else 'no'}", file=sys.stderr)
        print(f"Play cost ({RUNTIME}): {'sí' if with_runtime else 'no'}", file=sys.stderr)
        if a.list_only:
            print("\n".join(tests + ([COST] if with_cost else []) + ([RUNTIME] if with_runtime else [])))
            return 0
    if with_cost and not a.no_cost:
        tests = tests + [COST]
    if with_runtime and not a.no_runtime:
        tests = tests + [RUNTIME]
    if not a.no_unit and unit_tests():
        return 1
    if not os.path.isfile(jar):
        print(f"The .jar {jar} is missing: build first with ./gradlew build (or pass --jar).", file=sys.stderr)
        return 1
    bad_all = execute(([SMOKE] if a.all else []) + tests, jar, work, a.logs)
    print("Fallan:" if bad_all else "All pass.", " ".join(bad_all))
    return 1 if bad_all else 0


if __name__ == "__main__":
    sys.exit(main())
