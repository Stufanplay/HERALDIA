# Heraldia: installation, commands and configuration

**English** · [Español](CONFIGURACION.md)

Back to the [README](../README.md).

## Installation

Requirements: Minecraft 26.3, Fabric Loader 0.20.1 or later and Fabric API (tested with 0.166.2+26.3). Optional on the client: Mod Menu (built against 21.0.1), for the [configuration screen](#configuration-screen-client).

1. Build `heraldia-<version>.jar` (see below).
2. Copy it into the server's `mods` folder. On clients it is optional: a vanilla client plays the same (texts it does not know show in Spanish, except the Guide, which arrives in each player's language); with the mod everything shows in its language and the configuration screen is available.
3. Start the server. `logs/latest.log` should show `Heraldia: 180 estructuras registradas`.

In an existing world, structures only appear in chunks that have not been generated yet.
`/reload` does not reload world generation: you must restart the server (or leave and re-enter the world in single player).

## Test commands

- Place a village where you stand: `/place structure heraldia:llanuras_castellana` (or `..._grande`). It works even outside its biome.
- Find the nearest one: `/locate structure heraldia:llanuras_castellana`
- Place a single piece: `/place template heraldia:llanuras_castellana/specials/church`
- `/function heraldia:muestrario`: places all 72 villages in a grid starting where you stand (each row, heading south, is a family; in each row go the 3 styles and then their large versions, heading east, 300 blocks apart). It puts you in spectator mode and takes you from one to the next, one every 8 s (about 10 min). When it finishes you return to creative.
- `/function heraldia:familia/<family>` (`llanuras`, `bosque`, `oscuro`, `taiga`, `nieve`, `desierto`, `sabana`, `jungla`, `pantano`, `cerezos`, `badlands`, `costa`): the same with the 6 villages of one family, in a row heading east.
- `/function heraldia:muestrario/parar`: stops it.
- `/heraldia key <players> <key>` (operators, level 2): gives the keys of the locked chests of the unique structures, the same item you get in the game. `<key>` autocompletes: `all`, a structure (`atlantida`: its four keys) or a single key (`atlantida.arsenal`, `atlantida.academia`, `atlantida.anfiteatro`, `atlantida.poseidon`). If the inventory is full, the key drops on the ground for that player.
- `/heraldia info` (operators, level 2): summary of the configuration in use (villages, enabled unique structures and their spacing, minimum distance, per-player chest, whether Lootr is installed, medium structures, mine entrances and the vanilla mineshaft multiplier) and how many structures are registered.
- `/heraldia info nearby [radius]`: the nearest unique structure and medium structure of each type, mine entrance of each size and the nearest Heraldia village, with distance, direction and coordinates (click them to get a `/tp` command). It uses the same check as `/locate`, so it never points to a structure that the minimum distance discards, but it neither loads nor generates chunks: what has not been generated yet is shown as "predicted" (for a predicted village only its family is known). Default radius 3,000 blocks, maximum 10,000; the message says how long the search took.
- `/heraldia wizard [reveal]` (operators, level 2): the [wizard's huts](CONTENT.md#wizards-huts). On its own, the wizards within 32 blocks with their state (benign, evil and unrevealed, not decided yet); `reveal` reveals the nearest unrevealed one even if he is benign (to test the Evil Wizard and his loot).
- `/heraldia caravan [spawn [raid | peaceful] | raid | list | clear]` (operators, level 2): the [caravans](CONTENT.md#caravans). `spawn` sends one off next to you (within 80 blocks of a Heraldia road, with its start in loaded chunks and the road really there in the world; without waiting for the `caravanas.frecuencia` draw, but with `caravanas.activado` and `caravanas.max_activas`); `spawn raid` sends it with a certain ambush and `spawn peaceful`, without one. `raid` forces the ambush of the nearest one right away; `list`, those on the road (from which village to which, whether it is under attack, which waypoint it is heading for and where the merchant is); `clear` removes them all, with their entities (the wayfarers too).
- `/heraldia caravan wayfarer [pilgrim | shepherd | messenger | patrol | hunter]` (operators, level 2): brings a [wayfarer](CONTENT.md#wayfarers) next to you, on the road within 80 blocks, without waiting for the `viajeros.frecuencia` draw (with `viajeros.activado`, the kind's option and `viajeros.max_activos`). Without a kind, the draw chooses one that fits the area and the hour; with a kind, it comes whatever the area and the hour (a pilgrim, only with a monastery or cathedral within 3,000 blocks). Handy to see each encounter (and take screenshots) whenever you want; `/heraldia caravan list` shows them under the caravans and `/heraldia caravan clear` removes them.
- `/heraldia event [list | start <market | wedding | funeral | festival> | stop [all] | with <entity>]` (operators, level 2): the [village events](CONTENT.md#village-events). `start` begins one in the Heraldia village you are in, without waiting for the `eventos.frecuencia` draw and whatever the hour, the weather and the village's rest (but with `eventos.activado`, `eventos.max_activos`, one per village and only where it fits in the square); `stop` ends the one of the village you are in (`all`: every one), taking its figures and its blocks away; `list` shows the running ones (kind, village, seconds, figures, blocks, where the square is); `with <entity>` deals with a figure as your right click would (to preview the lines and take screenshots).
- `/heraldia guide` (any player, no permissions needed): gives you an up-to-date copy of the [Herald's Guide](CONTENT.md#heralds-guide) (if you carry one in your inventory, it is replaced by the new one).
- `/heraldia journal [villages | uniques | mediums | mines | coast | nether | end | chronicle]` (any player, no permissions needed): your own [journal](CONTENT.md#your-journal-heraldia-journal) in chat, what you have found and what is still missing, by kind. On its own, one line per kind with a progress bar and the count (each line opens its kind; hovering over it lists what is missing) and the overall total; with a kind, the names found and missing. No coordinates or clues. `chronicle`: the guardians defeated towards the [end of the Chronicle](CONTENT.md#end-of-the-chronicle); `/heraldia journal chronicle book` gives a Herald of Atlantis a copy of the last leaf.
- `/heraldia quest [list | accept <number> | abandon <number> | turnin]` (any player, no permissions needed): inside a Heraldia village, without arguments, its [job board](CONTENT.md#village-life) (the same as touching the lectern); elsewhere, your quests. `accept <number>` takes quest number N from the board of the village you are in; `list`, your quests (up to 5), their state and your reputation with each village; `abandon <number>` drops one of yours; `turnin` hands in, at the village that gave them, the ones that are done (the bring quests, if you carry the items). The board's buttons run these same commands.
- `/heraldia talk [more | rumor | trade | bye]` (any player, no permissions needed): the answer buttons of a [villager conversation](CONTENT.md#villager-conversations) (right click on a Heraldia villager inside its village; sneak + right click trades directly). `/heraldia talk with <villager>` (operators, level 2) opens a conversation with that villager as a click would, whatever the hand or the item held: handy to preview the lines and take screenshots.
- `/heraldia profile` (operators, level 2): the [gameplay profile](#gameplay-profiles) in use (the effective one and the one chosen in the file) and the value it gives to each of its options, marking the ones set by hand in the file that override it; with `ligero`, the reminder that it changes world generation only in new chunks.
- `/heraldia info here`: which Heraldia structure you are standing in (name and id) and, in a unique structure, whether its guardian is alive (only answered when the whole structure is loaded).

Use the showcase only in a test world: whatever it places stays.

Every command and subcommand of the mod has an English name, so the same commands work on every server whatever its
language (what the player reads is still translated). The Spanish names used up to now (`/heraldia guia`, `llave`,
`info cerca`, `info aqui`, `arena colocar`/`mover`/`quitar` [`confirmar`], `arena empezar`/`parar`/`salir` and the
`todas` key) still work as hidden aliases: they do the same, do not show up in autocompletion and warn that they are
deprecated, giving the new name. They will be removed in a future version.

| Old name | New name |
|---|---|
| `/heraldia guia` | `/heraldia guide` |
| `/heraldia llave <jugadores> <todas\|...>` | `/heraldia key <players> <all\|...>` |
| `/heraldia info cerca [radio]` | `/heraldia info nearby [radius]` |
| `/heraldia info aqui` | `/heraldia info here` |
| `/heraldia arena colocar [confirmar]` | `/heraldia arena place [confirm]` |
| `/heraldia arena mover [confirmar]` | `/heraldia arena move [confirm]` |
| `/heraldia arena quitar [confirmar]` | `/heraldia arena remove [confirm]` |
| `/heraldia arena empezar` | `/heraldia arena start` |
| `/heraldia arena parar` | `/heraldia arena stop` |
| `/heraldia arena salir` | `/heraldia arena leave` |

## Admin tools

### Review route: `/heraldia review`

For operators (level 2). A guided route to check all the visual content of the mod in one afternoon, stop by stop: a village of each family, every unique structure (Atlantis and the Corsair's Isle included), each type of medium structure, a mine entrance of each size, a coastal lighthouse and a shipwreck, the arena (if enabled) and a stretch of road (if there are roads). The Herald's House, its roads and its grounds are not on the route. Whatever is disabled in the configuration is left out.

- `/heraldia review`: goes to the stop you are at (the first one, the first time). At each stop you get an on-screen title, the list of what to check in the chat (translated, like everything else) and buttons to mark it: **Checked**, **+ Note** (checked, with a note) and **Problem** (type what is wrong after the command), plus **Skip**, **Previous**, **Next** and **List**.
- `/heraldia review next`, `previous`, `skip [note]` (marks it as skipped and goes to the next one), `goto <id>` (e.g. `goto unica/castillo`; it autocompletes), `list` (every stop with its status; click one to go there), `reset` (clears your marks) and `status` (the summary: how many are checked, with a problem, skipped and pending, and the list of problems).
- `/heraldia review mark checked [note]` and `/heraldia review mark problem [note]`: what the buttons do.
- The search runs off the server thread, with the same rules as `/heraldia info nearby` (from the world spawn, up to 10,000 blocks; Atlantis, anywhere in the world), and never loads or generates chunks: it prefers a structure that is already generated, even if farther away, to a predicted one. If the nearest one has not been generated yet, it warns you that going there generates new terrain and waits until you click **Go and generate** (`goto <id> generate`).
- The teleport loads the destination without blocking the server and leaves you above ground, with no suffocation: feet and head free, solid ground or water below (floating on the sea at Atlantis or the isle), never in lava, fire, magma, cactus or powder snow, searching in a spiral up to 8 blocks around. If there is no safe spot, you are not moved.
- Progress is per player and saved in `heraldia_revision.json`, in the world folder (it survives restarts). Every change also writes `heraldia_revision.md` in the same folder: per player, every stop with its status, its note and the date, those with a problem first.

### Server status: `/heraldia status [page]`

For any player, translated and paged (8 lines per page, with buttons to turn the page): the Heraldia version, how many structures of each kind some player has discovered out of the total (villages, one of each family; unique structures; medium structures, by type; mines, by size), the guardians defeated, the state of the arena with the server record, the job board quests handed in by everyone and by you (with how many villages are friends of yours and of how many you are the hero), the caravans on the road (with their maximum and chances) and how many have arrived or been lost since startup, whether restocking loot is enabled and whether Lootr is installed. Operators also see the difficulty, the key generation, boss and Guide options, what is still undiscovered of each kind and the other mods loaded. Discoveries come from advancements: those of online players, from memory; the rest, from their files in the world folder (read off the server thread). This is the server's summary (by anyone); a player's own progress is in [`/heraldia journal`](CONTENT.md#your-journal-heraldia-journal), which the report links to. A medium structure of the Nether or the End counts with its own walker advancement (`medianas/nether`, `medianas/end`).

### New version notice: `/heraldia update check`

When the server starts and every 24 hours, in a thread of its own (it never slows down the start or the server), the
mod asks the GitHub Releases API of the project (where releases are published, together with CurseForge) whether there
is a newer version of Heraldia for the server's Minecraft version: semantic version comparison, pre-releases ignored
(unless `update_check.prereleases`), and the Minecraft version of each release read from the `gradle.properties` of its
tag. If there is one, it says so in the console and, in the chat, to each operator when they join (once per server
session), in their language, with a clickable download link and the recommendation to **back up the server before
updating**. `/heraldia update check` (operators, level 2) checks right away and answers in the chat.

No telemetry: one GET request with a generic `User-Agent` and no data about the server or its players, with short
timeouts (5 s to connect, 10 s to answer). With no network or an odd answer it only writes one line in the log. Turn it
off with `update_check.activado = false`.

### Web maps: `/heraldia webmap refresh`

If the server has [BlueMap](https://modrinth.com/plugin/bluemap), [Dynmap](https://modrinth.com/plugin/dynmap) or [squaremap](https://modrinth.com/plugin/squaremap) (optional dependencies: without any of them nothing changes), Heraldia puts its structures on the web map, each kind on its own layer that can be hidden: unique structures, villages, medium structures, mine entrances and the wave arena. Each marker has its layer's icon, the structure's name in the language of `mapas_web.idioma` and a short description. Details and tested versions in [Compatibility](COMPATIBILITY.md#web-maps-bluemap-dynmap-and-squaremap).

- What is shown: the Heraldia structures in the chunks that have been loaded at least once since there is a web map (they are noted down as each chunk loads and saved in `heraldia_mapas_web.json`, in the world folder) and the placed arena. With `mapas_web.solo_descubiertas` (the default), only those of a kind some player has already discovered, with the same advancements [`/heraldia status`](#server-status-heraldia-status-page) counts: a village, once someone has its family's advancement; a unique structure, the one for discovering it; a medium structure, its type's criterion; a mine entrance, the one for its size. The arena is always shown.
- When it is updated: at startup, as soon as someone earns a Heraldia advancement, when a new structure appears, after [`/heraldia reload`](#live-reload-heraldia-reload) (the `mapas_web.*` options are reloadable) and with `/heraldia webmap refresh` (operators, level 2: reads every player's advancements again and says how many markers it placed). Everything runs on its own thread, at most one update every 2 s; on the server thread it only looks at the list of structure starts of each chunk that loads.

### Treasure hunt: `/heraldia treasure`

For operators (level 2), to test the [treasure hunt](CONTENT.md#treasure-hunt):

- `/heraldia treasure give [players]`: gives an undeciphered treasure map fragment (the `heraldia:tesoro/fragmento` table) to the players (with no argument, to whoever runs it).
- `/heraldia treasure info`: the chain of the map in your main hand: seed, current mark and each destination (type, clickable coordinates, structure or biome, generated or predicted) and, once placed, where the chest was buried. It is also written to the log ("Heraldia: tesoro: info {…}").

Players need no commands: they use the fragment and the map with a right-click. The log says how long each chain took to choose (off the server thread) and how long each chest's spot took to find.

### Live reload: `/heraldia reload`

For operators (level 2). Reads `config/heraldia.json` again without restarting the server (and without rewriting it) and applies whatever does not affect generation:

- `dificultad.*`: the health and damage modifiers of the Heraldia mobs already loaded are recalculated (the rest, when they load), keeping the proportion of their current health.
- `jefes.*`, `botin.*`, `guia.*`, `aldeas.vida.tratos_estilo`, `aldeas.vida.asedios` (trades are rolled when a villager levels up), `unicas.atlantida.cofre_unico_por_jugador`, `mapas_web.*` (the markers are rebuilt on reload), `tesoro.*` (when loot is rolled and when a clue is used), `encargos.*`, `reputacion.*`, `dialogos.*` (read on every click), `chozas_mago.*` (when each hut is decided), `actualizar.margen_bloques` (on each `/heraldia update analyze`) `caravanas.*` (with `caravanas.activado` set to `false`, the caravan on the road leaves) and `viajeros.*` (likewise with the wayfarers, the general switch or a kind's), `eventos.*` (with `eventos.activado` set to `false`, or the light profile, the running events end within a second): read every time they are used.
- `perfil` (the [gameplay profile](#gameplay-profiles)): applied whole, with whatever is set by hand on top (all its options are among these).
- `golems.*`: the limits are published again to the golem functions.
- `arena.*` (except `arena.generar_en_mundos_nuevos`, which only counts when a new world starts): increments, maximum alive, experience, modes and whether it is enabled. With a match running they do not change until it ends (reload again then), except `arena.temporada.*`, which always applies (the history is trimmed at once; the day and hour count from then on).

Everything else (grids and spacings, villages, families and styles, the job board, roads, unique structures, medium structures, mines, compatibility and the minimum distance) affects generation: if it changed halfway, two neighbouring chunks would be generated with different rules and `/locate` and maps would no longer match what was generated. Those options are not applied: the answer lists them with their value in use and the one in the file, and they apply on restart. A new option of the mod belongs to this group unless it is declared reloadable.

### In-game configuration panel: `/heraldia config`

For operators (level 2), **without the mod on the client**: it opens a vanilla dialog (the server Dialog API). At the top, the gameplay profile in use and a button per profile (casual, standard, hardcore, light; the light one, in a world already started, asks for confirmation first: see [Light profile](#light-profile)); below, seven sections with 5 to 8 options each: **World and generation**, **Villages and roads**, **Combat and bosses**, **Loot**, **Arena**, **Players and Guide** and **Advanced**. Each option has a sentence that explains it, the recommended value (the chosen profile's or the default) and, when it is not applied live, the note “[applies after a restart]”. **Save** writes `config/heraldia.json` and applies through the same path as [`/heraldia reload`](#live-reload-heraldia-reload): reloadable options at once, the rest is saved and flagged as waiting for a restart. Anything not in the sections (the Herald's House `casa_heraldo.*`, village events, conversations, ambience...) is changed with `/heraldia config set` or in the file (the Mod Menu screen shows every option).

From the console, `/heraldia config` lists the same as text and `/heraldia config set <option> <value>` changes any option (same reload path).

### Each player's language: `/heraldia language`

For everyone. `/heraldia language` says which language Heraldia writes to you in and gives a button per language (the mod's 8); `/heraldia language <code>` (`es_es`, `en_us`, `fr_fr`, `de_de`, `it_it`, `pt_br`, `ca_es`, `gl_es`) sets it and `/heraldia language auto` goes back to your game's. It is saved with the player and overrides the client's language for the mod's texts (Guide, quests, arena, caravans, notices). A client without the mod sees them in the chosen language; one with the mod translates the keys with its own language. Known limitation: some messages are still built without the player's language (about 290 call sites of `Texts.t(key)` in the Java: parts of the arena, the caravans, the Herald's House and its market, `/heraldia status`, `review` and `info`); a client without the mod sees those in Spanish whatever is chosen (with the mod, in its own language).

### The Herald's House: `/heraldia herald`

Operators: `/heraldia herald place` proposes a site near spawn (or `place here`, centred on you) and marks the corners with columns of light for five minutes; `/heraldia herald place confirm` builds it (a chunk per tick). In an existing world it never appears on its own and the world spawn is not moved (the message offers the `/setworldspawn` command). `/heraldia herald` (anyone) says where it is. Market: `/heraldia herald stall` lists the stalls; players use `stall claim <n>`, `stall pay <n> [periods]` and `stall leave <n>`; operators `stall evict <n>` (the tenant's things go to a return barrel). Options: `casa_heraldo.activado`, `casa_heraldo.generar_en_mundos_nuevos`, `casa_heraldo.contenedores_solo_ver` (on: a player who is not an operator opens the area's containers to look but cannot take or put anything; off, they stay shut), `casa_heraldo.mercado.activado` (off by default), `casa_heraldo.mercado.entrada_esmeraldas`, `casa_heraldo.mercado.alquiler_esmeraldas`, `casa_heraldo.mercado.periodo_dias` and `casa_heraldo.mercado.gracia_dias`, also in game with `/heraldia config set` (they apply at once, except `generar_en_mundos_nuevos`, read at startup). See [The Herald's House](CONTENT.md#the-heralds-house). Roads: a new placement builds a road out of each gate with its huts, and the road to the arena (now or when the arena is placed); in a world whose town was already there, `/heraldia herald roads` (operators) builds them, only what is missing. Options `casa_heraldo.caminos.activado` (on) and `casa_heraldo.caminos.aldeanos` (villagers in the huts in all, the guide included: 5 by default, 0 to 8; each villager with its AI costs some server time while a player is near). See [The Herald's House roads](CONTENT.md#the-heralds-house-roads). Grounds: a new placement then levels the protected ring into gentle, walkable ground with a few cherry trees and small houses with a loot chest (no villagers); in a world whose town was already there, `/heraldia herald grounds` (operators) builds them. Options `casa_heraldo.alrededores.activado` (on) and `casa_heraldo.alrededores.casas` (8 by default, 0 to 12). See [The Herald's House grounds](CONTENT.md#the-heralds-house-grounds).

## Updating a server

Guide for admins (permanent policy: no version changes what has already been built without your permission).

1. **Before updating**: stop the server and back up the world and `config/`. Swap the Heraldia `.jar` and start.
2. **On start-up** with the new version nothing changes in what is already generated: new generation content appears in new chunks. The mod stores in the world which version generated it and which one last opened it (the log says “mundo generado con la versión …”; a world older than this is recorded as `anterior`), migrates `config/heraldia.json` if its format changed (leaving `heraldia.json.v<version>.bak` with the old one) and applies, once per mob when it loads, the **fixes** for already-corrected bugs that may remain from older versions: 0.1.0 guardians without marks (they get anchored so they do not wander out of their room, stop picking up items and become bosses), babies, drowned riding zombie nautiluses. The changed-weapon one only warns (the original is unknown). `/heraldia update repair dry-run` says what it would change in loaded entities; `/heraldia update repair` forces it.
3. **`/heraldia update analyze`** (operators): report of what bringing the new content to already-generated land would do. **It changes nothing.** It reads the overworld region files on its own thread (a few minutes on a large world) and leaves in `<world>/heraldia/actualizar/` the report (`analisis-<date>.txt`), a text map and an image (`mapa-<date>.txt` and `.png`: `#` build, `P` protected, `R` regenerated, `v` kept virgin, `E` new structure, `.` generated, `S` spawn). It detects player builds by combining:
   - typical player blocks (beds, chests, barrels, signs, tables, furnaces, rails, fences, doors, torches, planks, glass…) outside the pieces of saved structures;
   - differences from a regeneration with the same seed (the top of 16 columns per chunk against the generator's terrain, not counting trees, snow, fluids or plants) in chunks someone has been to;
   - InhabitedTime (from 1 hour of players nearby the chunk counts as a build);
   - the world spawn, players' beds and respawn points and each player's last position (offline ones too);
   - areas claimed with protection mods: if a known one is installed (Flan, GOML, FTB Chunks, Open Parties and Claims…), they cannot be read, the report says so and `apply` will not run.
   Around every build there is a **50-block margin** (`actualizar.margen_bloques`, 16 to 256): nothing is deleted or placed there.
   - **Route A**: **virgin** chunks (fully generated, with less than 1 minute of players nearby and no builds or margin) are deleted so they generate again with the new content when someone comes near. Only those that would not leave a cut structure: if what would now appear in that chunk (or what was there) reaches a chunk that stays, the chunk is kept.
   - **Route B**: new Heraldia structures that would appear today in an already-generated chunk are placed only in safe spots: their whole box outside any protected chunk and not overlapping another structure.
4. **`/heraldia update apply`**: the same analysis and a dialog (on the console, the commands) to confirm:
   - **Back up and apply**: first copies the affected region, entity and POI files to `heraldia/actualizar/copia-<id>/`.
   - **Apply without backup**: asks for a second, explicit confirmation of the risk (it cannot be undone).
   On confirming, players are warned and **the server stops** after 10 s. **Start it again by hand**: on start-up, before the world loads, the backup is made and the virgin chunks are deleted (one someone has visited since the analysis is kept); with the server running the new structures are placed and the report `informe-<id>.txt` is left.
5. **Undo**: `/heraldia update undo` (if there was a backup) asks for confirmation, stops the server and, when you start it by hand, restores the backed-up regions. Whatever changed in them since the apply is lost.
6. **`/heraldia update mend`** (operators): repairs what an earlier version **built** wrong and its fix cannot reach (Heraldia builds each structure once: a fixed generator only helps new chunks). `mend scan` reports, per repair, how many it found, how many are fine and how many it leaves alone, with coordinates (the first few in chat, all of them in `heraldia/actualizar/mend-<id>-scan.txt`). **It changes nothing.** `mend apply <water|streams|wharf|inn|all>` scans again and asks for confirmation (a dialog; on the console, the command), within 15 minutes; the repair runs a little each tick with the server running (at most 8 ms a tick, one place per step), and the report says how long the slowest step took. The repairs:
   - `water`: **still water standing in the air with no source** beside the town, left by a Herald's House build that drained a pond without block updates: it is settled the way a town built today settles it, which **changes blocks in your world** -- each body is either drained or banked. This is one of the repairs `all` runs, and like every repair it **cannot be undone**. Water that runs because something feeds it is a different thing and is left alone: a source, or a waterlogged block of the town's own walls, feeds it by the game's rules, so it is not this fault and `water` does not touch it.
   - `streams`: running water with no source left by the Herald's House beside a pond it drained (towns built before the running-water fix): taken away, as a town built today does. Running water with no source only lasts if it never got a block update; a player's water always gets one, so this is never a player's. The road's plank walkways over it are left.
   - `wharf`: on the Fallen Shulker Wharfs of the End midlands and barrens, the guard's post (an end stone brick wall a shulker cannot hold) becomes a purpur pillar and the guard, if alive and away, goes back on it. A dead guard is only reported: none is made.
   - `inn`: the Roadside Inn's bedroom gets its door to the yard, and the room's chest, which stood where the door opens, moves to the corner **with everything in it**.
   **Nothing somebody changed is touched**: a structure is repaired only if every block the repair changes, and every block beside them, is still exactly what an earlier version placed; otherwise it is listed as left alone, with the block that did not match. Running it again finds nothing to do. Not repaired (on purpose): the Herald's House grounds' old "rice terraces" (rebuilding the terrain round a town people live in cannot tell the generator's earth from a player's) and the water that runs because a source or a waterlogged block feeds it (by the game's rules it has a source: a separate fault).

Limitations: overworld only; structures placed in already-generated chunks do not adjust the terrain around them (like `/place structure`); if the world was generated with another Minecraft version, regenerated chunks may not match the terrain next to them.

## Configuration

File `config/heraldia.json` on the server (in a single-player world, the one in the game folder). It is created at startup with all default values
and rewritten on every startup with the values in use and a help text (`_ayuda`) in Spanish and English (the options of the [gameplay profile](#gameplay-profiles) only if they were set by hand; the `_perfil` block, informative, shows the effective profile and its values). An invalid value (out of range or of another type)
is reported in the log and replaced by its default; an unknown option is reported and ignored. The `version` field allows migrating the file
when its format changes. It is read when the server starts and affects chunks generated afterwards (not what is already generated); whatever does not affect generation can be applied without restarting with [`/heraldia reload`](#live-reload-heraldia-reload).

| Option | Default | Range | What it does |
| --- | --- | --- | --- |
| `perfil` | `estandar` | `casual`, `estandar`, `hardcore`, `ligero`, `personalizado` | [Gameplay profile](#gameplay-profiles): sets difficulty, reinforcements, restocking loot and the arena in one go; only `ligero` (the [light profile](#light-profile)) also touches world generation. |
| `aldeas.separacion_bloques` | 1500 | 1000-10000 | Average spacing between villages; the minimum keeps the 62/94 ratio of the grid. |
| `aldeas.maximo` | 100 | 0-100 | Maximum villages per world: only the grid cells closest to 0,0 count (deterministic, no saved data). |
| `aldeas.porcentaje_grandes` | 25 | 0-100 | Percentage of large villages; the rest are standard. |
| `aldeas.distancia_aldeas_vanilla_bloques` | 160 | 0-256 | Minimum distance to a vanilla village (rounded to chunks); 0 disables it. |
| `aldeas.familias.<family>` | `true` | `true`/`false` | Enables a whole family (its 3 styles). |
| `aldeas.estilos.<style>` | `true` | `true`/`false` | Enables a style (standard and large). If a cell picks a disabled one, another style of its biome is tried. |
| `aldeas.vida.tratos_estilo` | `true` | `true`/`false` | Style trades and the map of the area's unique structure at each family's cartographers ([Village life](CONTENT.md#village-life)). |
| `aldeas.vida.tablon` | `true` | `true`/`false` | Job board and bailiff on the square of new villages. |
| `aldeas.vida.rastros` | `true` | `true`/`false` | Traces of work in progress on a few plots of new villages (a house half built, laundry, a meal half eaten, a work yard, a loaded cart, fish drying, a cooking fire): blocks only; off, the plots stay empty. |
| `aldeas.vida.asedios` | `false` | `true`/`false` | The weaponsmith of fortified villages sells an ominous bottle to trigger a raid. |
| `aldeas.caminos.activado` | `true` | `true`/`false` | Roads between nearby villages, with bridges, lamp posts and signs ([Roads between villages](CONTENT.md#roads-between-villages)); new chunks only. When off, the feature is not even added to the biomes. |
| `aldeas.caminos.distancia_maxima_bloques` | 2000 | 500-4000 | Only villages closer than this are joined. Two villages are never closer than about 670 blocks (with the minimum spacing, 1000), so below that there would be no roads at all. |
| `aldeas.caminos.ancho` | 3 | 1-5 | Road width, in blocks. |
| `golems.limpieza` | `true` | `true`/`false` | Enables the periodic removal of natural golems. |
| `golems.limite_estandar` | 8 | 1-64 | At this many natural golems or more, a standard village removes one every 30 s. |
| `golems.limite_grande` | 9 | 1-64 | Same for large villages. |
| `unicas.<id>.activada` | `true` | `true`/`false` | Enables a unique structure. There is one entry for each unique structure in the mod. |
| `unicas.<id>.separacion_bloques` | the structure's own (4000; 1600 for the Ashen Citadel in the Nether and 2000 for the Sanctum of the Void in the End) | 1000-10000 | Average spacing between structures of that type (by default, one every 3000-5000 blocks). Each type spreads over its whole grid cell (grid origin shifted per type), and two of the same type are never closer than `unicas.distancia_minima.bloques`. For the Mycologist's Laboratory (mushroom fields, a very rare biome) the candidate of each cell is not random: it is the spot of the cell deepest inside that biome, so it appears on a good share of mushroom islands (at most one per cell). The Lost Mine does the same with lush and dripstone caves, looking at cavern height (y = 26) instead of sea level, and the Corsair's Isle with its oceans (the spot deepest in open sea). |
| `unicas.rejilla_compatible` | `false` | `true`/`false` | **Set it to `true` in a world created with an earlier Heraldia version (0.1.0)**; leave it `false` in a new world. Placement grids of unique structures changed after 0.1.0 (each type's grid origin is now shifted and the internal separation is the minimum distance), so in an old world `/locate`, treasure maps, the Chronicle folios, `/heraldia info nearby` and the minimum distance no longer find the unique structures already generated in explored areas (they are still there). Turned on, the 14 unique structures that existed in 0.1.0 (aqueduct, castle, cathedral, citadel, colosseum, lighthouse, ice fortress, galleon, mansion, monastery, observatory, palace, pyramid, wizard tower) use that version's grid again, bit for bit, for the same seed and configuration, at the same cost. The ones added later (Jarl's Hall, Druidic Sanctuary, Mycologist's Laboratory, Lost Mine, Corsair's Isle, and the Ashen Citadel and the Sanctum of the Void beyond the portals) keep the new grid, and the old ones take precedence over them: a new one is discarded if it falls within the minimum distance of an old one that spawns, so it never appears on top of one already generated. Villages and Atlantis are not affected (their placement did not change; Atlantis keeps its saved position). |
| `unicas.distancia_minima.activada` | `true` | `true`/`false` | Keeps two different unique structures (Atlantis included) from spawning closer than the minimum distance. |
| `unicas.distancia_minima.bloques` | 1000 | 100-3000 | Minimum distance between the start chunks of two different unique structures. When two candidates are too close, a deterministic draw (seed and position) keeps one; if the winner cannot spawn there (wrong biome or terrain), the other one is kept. `/locate` and treasure maps follow the same rule. |
| `unicas.atlantida.cofre_unico_por_jugador` | `false` | `true`/`false` | Per-player Atlantis premium chest. The first opening turns its contents into a template stored in the chest itself (the chest is left empty, so breaking or emptying it duplicates nothing) and each player opens their own copy: the whole contents the first time, and afterwards whatever they left. The Poseidon key is still needed. It works the same with or without Lootr (Lootr does not convert this chest because it has no loot table). Turning it off later puts the contents back in the chest once (the first time someone uses it), and it behaves as before. |
| `jefes.fases.activado` | `true` | `true`/`false` | Guardian phases below 66 % and 33 % health: effects, particles, sound and an action-bar notice ([Guardian fights](CONTENT.md#guardian-fights)); also for structures already generated. |
| `jefes.refuerzos.activado` | `true` | `true`/`false` | Guardian reinforcements: 2 or 3 mobs of its structure once per phase, at most `jefes.refuerzos.maximo_vivos` alive at once; they do not drop the guardian's loot. Works even with phases off (then without effects and with another notice). |
| `jefes.refuerzos.porcentaje` | 100 | 0-300 | How many reinforcements per phase, as a % of the guardian's own (rounded; above 100 its list repeats): 150 = one or two more. |
| `jefes.refuerzos.maximo_vivos` | 4 | 1-12 | Maximum reinforcements alive at once near a guardian. |
| `jefes.barra.activado` | `true` | `true`/`false` | Boss bar with the guardian's name for players within 32 blocks while the fight lasts. |
| `jefes.apagar_generadores` | `true` | `true`/`false` | When the guardian of a unique structure falls, the spawners of that structure turn off for good (the structure is left clean and safe; [Cleared uniques](CONTENT.md#cleared-uniques)). `false` keeps them working as before. Uniques beaten before this version are not affected. |
| `medianas.activadas` | `true` | `true`/`false` | Enables the [medium structures](CONTENT.md#medium-structures). |
| `medianas.frecuencia_porcentaje` | 100 | 25-400 | Frequency of all medium structures, as a % of each type's own spacing (each type's spacing is divided by the square root): **100 = each type at its own spacing** (one every ~550 blocks among all types), 200 = twice that, 50 = the light profile's (see [Medium structures density](#medium-structures-density)). |
| `medianas.distancia_minima.bloques` | 192 | 64-1024 | Minimum distance between two medium structures of different types (and between two of the same type, at most half a grid cell). |
| `medianas.distancia_aldeas_unicas_bloques` | 256 | 128-1024 | A medium structure does not spawn closer than this to the start of a Heraldia village or unique structure that spawns there. |
| `medianas.habitantes` | `true` | `true`/`false` | [Inhabitants](CONTENT.md#medium-structures) of the medium structures: the innkeeper, the miller, the fisher, the hunters, the lookout and the hermit live in their building (bed, workstation, vanilla AI) and the inn has its pigs. Applied when each one first loads: off, the new ones do not appear and the old still figures stay still; an inhabitant that has already loaded is never changed. Off in the light profile. |
| `medianas.<id>.activada` | `true` | `true`/`false` | Enables a type of medium structure (`torre_vigia`, `posada`, `campamento`, `ermita`, `molino`, `pescador`, `cazadores`, `templete`, `choza_mago`; Nether: `puesto_piglin`, `altar_magma`, `atalaya_basalto`, `santuario_hongos`; End: `observatorio_vacio`, `mausoleo_purpura`, `embarcadero_shulker`). |
| `medianas.<id>.separacion_bloques` | the type's own (576-1024) | 256-4000 | Average spacing between two of that type (at 100 % frequency); each grid cell looks for its candidate inside the type's biomes. |
| `minas.entradas.activado` | `true` | `true`/`false` | Enables the [mine entrances](CONTENT.md#mine-entrances) (new chunks only). |
| `minas.entradas.separacion_bloques` | 768 | 256-4000 | Average spacing between two small mine entrances; medium and large ones keep the ratio (x1.5 and x2.5). |
| `minas.vanilla.multiplicador` | 2.0 | 1-5 | Multiplies how often vanilla abandoned mineshafts appear in new chunks (1 = vanilla; decimals allowed, e.g. 1.5). Does not change chunks already generated or other structures. |
| `faros.activado` | `true` | `true`/`false` | Turns on the coastal [lighthouses](CONTENT.md#lighthouses-and-wrecks) (new chunks only). |
| `faros.separacion_bloques` | 1024 | 256-4000 | Average spacing between two lighthouses (they only spawn where there is coast: fewer in practice). |
| `naufragios.activado` | `true` | `true`/`false` | Turns on the [wrecked galleons](CONTENT.md#lighthouses-and-wrecks) (new chunks only). |
| `naufragios.separacion_bloques` | 768 | 256-4000 | Average spacing between two wrecked galleons (they only spawn where there is coast: fewer in practice). |
| `guia.entregar_al_entrar` | `true` | `true`/`false` | Gives the [Herald's Guide](CONTENT.md#heralds-guide) to each player the first time they join with each mod version. When off, nobody gets it on joining, but `/heraldia guide` still hands it out. |
| `guia.final_cronica` | `true` | `true`/`false` | [End of the Chronicle](CONTENT.md#end-of-the-chronicle): whoever defeats (or sees fall within 64 blocks) the guardians of every unique structure of the main world gets the advancement and title Herald of Atlantis, the last leaf and the Standard of the Heralds, once per player. Guardian advancements earned before this version count. `false` gives nothing (participation is still recorded, so turning it on later gives the end on the next join). |
| `update_check.activado` | `true` | `true`/`false` | [New version notice](#new-version-notice-heraldia-update-check): checks GitHub Releases at startup and every 24 h and tells operators when they join. Applies on restart. |
| `update_check.prereleases` | `false` | `true`/`false` | Also announce pre-releases (alpha, beta, release candidates). |
| `actualizar.margen_bloques` | `50` | 16-256 | Safety margin (blocks) around every build that [`/heraldia update analyze`](#updating-a-server) detects: nothing is regenerated or placed there. |
| `compatibilidad.zona_estructuras_ajenas_bloques` | 224 | 0-512 | Structures from other mods that show above ground do not spawn closer than this to the start of a Heraldia village or unique structure that spawns there; 0 disables it ([Compatibility with other mods](COMPATIBILITY.md#compatibility-with-other-mods)). |
| `botin.reponer.activado` | `false` | `true`/`false` | [Restocking loot](CONTENT.md#restocking-loot-and-difficulty): Heraldia chests and barrels are refilled on opening after the given days, with no other player nearby and when empty or almost empty; also chests already generated. Nothing with Lootr. |
| `botin.reponer.dias` | 7 | 1-60 | In-game days (24,000 ticks of the world clock) after a looting before a chest is restocked. |
| `botin.reponer.premium_vencido_modesto` | `true` | `true`/`false` | [Premium chest of a cleared unique](CONTENT.md#premium-chest-of-a-cleared-unique): once the guardian of a unique has fallen, its premium chest restocks with a modest table (1-2 emeralds 40 % of the time, a modest enchanted book 8 %); its first opening is the real premium. `false`: it restocks with its full premium, as before. Only matters with `botin.reponer.activado`. |
| `dificultad.nivel` | `normal` | `facil`, `normal`, `dificil`, `heroica` | [Difficulty](CONTENT.md#restocking-loot-and-difficulty) of Heraldia guardians and template mobs (health and damage); also those already generated, when they load. `normal` is the previous behaviour. |
| `dificultad.escalar_por_jugadores` | `false` | `true`/`false` | +25 % health per extra player within 32 blocks (up to +100 %), when hit. |
| `dificultad.escalar_botin` | `true` | `true`/`false` | With `facil`, `dificil` or `heroica`, plain stackable items of Heraldia chest loot come in x0.75, x1.25 or x1.5 amounts (nothing changes with `normal`). |
| `arena.activado` | `true` | `true`/`false` | [Wave arena](CONTENT.md#wave-arena) near spawn. When disabled, no matches and no protection (a placed arena stays as it is). |
| `arena.generar_en_mundos_nuevos` | `true` | `true`/`false` | In a new world, the arena is built on its own 200-300 blocks from spawn; in an existing one, never (an operator places it). |
| `arena.oleada.mobs_incremento` | 50 | 10-200 | Extra enemies in each wave, as a % of the first wave's (4, 6, 8, 10... with 50), rounded up. |
| `arena.oleada.stats_incremento` | 10 | 1-100 | Extra health and damage in each wave, in %; if it exceeds `mobs_incremento`, that one is used (enemies grow faster than their strength). |
| `arena.max_mobs_vivos` | 20 | 4-64 | Enemies alive at once in the ring; if a wave brings more, they come in batches. |
| `arena.experiencia_porcentaje` | 15 | 0-100 | Experience of arena enemies, as a % of the normal amount (after the game's own scaling); they drop no items. |
| `arena.modos.cooperativo` | `true` | `true`/`false` | Co-op [arena mode](CONTENT.md#wave-arena) (the usual one). |
| `arena.modos.contrarreloj` | `true` | `true`/`false` | Time attack mode: `arena.modos.oleadas_contrarreloj` waves against the clock. |
| `arena.modos.supervivencia` | `true` | `true`/`false` | Survival mode: waves with no break until everyone falls. |
| `arena.modos.oleadas_contrarreloj` | 10 | 1-50 | Waves in a time attack (its advancements need at least 10). |
| `arena.temporada.dia_reinicio` | `lunes` | `lunes`, `martes`, `miercoles`, `jueves`, `viernes`, `sabado`, `domingo` | Day the arena's weekly leaderboard closes (server time): champions announced, signs and Guide updated. |
| `arena.temporada.hora_reinicio` | 0 | 0-23 | Hour (server time) at which it closes. |
| `arena.temporada.historico` | 8 | 1-52 | Closed weeks kept in the world (`/heraldia arena leaderboard <mode> <week>`); lowering it trims them at once. |
| `encargos.activado` | `true` | `true`/`false` | [Job board quests](CONTENT.md#village-life) (`/heraldia quest`), in every Heraldia village (also those already generated). When disabled, the lectern only opens its book and the commands say so; what each player carries is kept. |
| `encargos.rotacion_dias` | 3 | 1-30 | In-game days each board lasts before its quests change (accepted ones are kept). |
| `caravanas.activado` | `true` | `true`/`false` | [Caravans](CONTENT.md#caravans) along the roads between villages, only with players nearby and in loaded chunks. When disabled, none sets off and the one on the road leaves. |
| `caravanas.frecuencia` | 10 | 0-100 | Chance (%) of a caravan setting off at each draw (one per minute, next to a player within 80 blocks of a road, at least 2 min after the previous one). 0: only with `/heraldia caravan spawn`. |
| `caravanas.prob_asalto` | 35 | 0-100 | Chance (%) of bandits ambushing it halfway. Set by the [profile](#gameplay-profiles). |
| `caravanas.max_activas` | 1 | 1-3 | Caravans on the road at once on the whole server. |
| `viajeros.activado` | `true` | `true`/`false` | [Wayfarers](CONTENT.md#wayfarers) along the roads (pilgrim, shepherd, messenger, pair of guards, hunter), only with a player nearby and in loaded chunks; 1 to 6 entities for a minute or two. When disabled, none passes and the one on the road leaves. |
| `viajeros.frecuencia` | 30 | 0-100 | Chance (%) of someone passing at each draw (one per minute, next to a player within 80 blocks of a road, at least 2 min after the previous one). 0: only with `/heraldia caravan wayfarer`. |
| `viajeros.max_activos` | 1 | 1-3 | Wayfarers on the road at once on the whole server (besides the caravans). |
| `viajeros.peregrino.activado` | `true` | `true`/`false` | Pilgrims (towards a monastery or cathedral within 3,000 blocks). |
| `viajeros.pastor.activado` | `true` | `true`/`false` | Shepherds with their flock (they trade). |
| `viajeros.mensajero.activado` | `true` | `true`/`false` | Messengers. |
| `viajeros.guardias.activado` | `true` | `true`/`false` | Pairs of guards (two iron golems; also at night). |
| `viajeros.cazador.activado` | `true` | `true`/`false` | Hunters with their dog (they trade). |
| `chozas_mago.prob_malvado` | 20 | 0-100 | Chance (%) that the wizard of a [wizard's hut](CONTENT.md#wizards-huts) is evil; per hut, always the same, and stored in the wizard when it loads. 0: all of them trade. Set by the [profile](#gameplay-profiles). |
| `chozas_mago.prob_botin_premium` | 30 | 0-100 | Chance (%) that the Evil Wizard also carries the prize (Mending, hard potions, a totem or a high-level book); per hut, when he reveals himself. |
| `ambiente.activado` | `true` | `true`/`false` | [Ambient effects](CONTENT.md#ambience) with the game's own sounds and particles (also in existing worlds). Off, none plays. |
| `ambiente.campanas` | `true` | `true`/`false` | Village bell at sunrise and nightfall for the players inside a Heraldia village (at most twice a day per player). |
| `ambiente.sirena_faro` | `true` | `true`/`false` | Lighthouse siren in rain or a thunderstorm, for players in the open within 160 blocks (at most every 3 min per player). |
| `ambiente.minas` | `true` | `true`/`false` | Drips (every 20-45 s) and, rarely, the cave's echo in the galleries of Heraldia's mines. |
| `reputacion.activado` | `true` | `true`/`false` | Reputation per village: it rises with quests and falls when you attack its villagers or golems; known, friend and village hero lower its trades by 10, 20 and 30 % (not stacking with Hero of the Village). When disabled, no discounts or changes (the reputation earned is kept). |
| `reputacion.aldea_visible` | `true` | `true`/`false` | [Reputation you can see](CONTENT.md#village-life): the village shows the best reputation any player has with it (flowers, banners, lanterns, a carpet; shutters closed if everyone is in negative reputation), only on air and never on a player's block. Disabled (or with `reputacion.activado` off), each village takes down what the mod put up as it loads. Reloads with `/heraldia reload`. |
| `dialogos.activado` | `true` | `true`/`false` | [Villager conversations](CONTENT.md#villager-conversations): a right click on a Heraldia villager inside its village first opens a conversation in the middle of the screen (or in chat, with `dialogos.en_pantalla` set to `false`), with buttons to keep talking, ask for news, trade and say goodbye. Sneak + right click, vanilla villagers and those of other mods trade as always. When disabled, every click trades; what villagers and players remember is kept. |
| `dialogos.espera_segundos` | 60 | 0-600 | Seconds each villager rests between conversations (meanwhile it says it is busy and offers its trades). 0: no wait. |
| `dialogos.viajeros_porcentaje` | 10 | 0-100 | Percentage of Heraldia villagers who are wayfarers and, once in their life, tell the direction and approximate distance of a real Heraldia structure near their village (never coordinates). 0: none. |
| `dialogos.pista_reputacion` | 20 | 0-300 | Reputation with the village a wayfarer asks for before telling its hint (20: known). Ignored with `reputacion.activado` set to `false`. |
| `dialogos.en_pantalla` | `true` | `true`/`false` | Conversations and the arena bell's mode menu [in the middle of the screen](CONTENT.md#in-the-middle-of-the-screen): a panel with buttons for whoever has Heraldia on the client (the same version) and a chest window whose slots are the options for any other client (vanilla). `false`: clickable buttons in chat for everyone, as before (for instance on a server of vanilla clients that prefers them). |
| `mapas_web.activado` | `true` | `true`/`false` | [Markers on the web maps](#web-maps-heraldia-webmap-refresh) (BlueMap, Dynmap or squaremap); without any of them it does nothing. Disabled, it removes Heraldia's layers from the map. |
| `mapas_web.solo_descubiertas` | `true` | `true`/`false` | Only those of a kind some player has discovered are shown (the `/heraldia status` advancements); with `false`, every one already generated in chunks that have been loaded. |
| `mapas_web.idioma` | `auto` | `auto`, `es_es`, `en_us`, `fr_fr`, `de_de`, `it_it`, `pt_br`, `ca_es`, `gl_es` | Language of the names, descriptions and layers; `auto` uses the server system's (the JVM's). |
| `mapas_web.capas.<capa>` | `true` | `true`/`false` | One per layer (`unicas`, `aldeas`, `medianas`, `minas`, `costa`, `arena`): when off, the layer is not shown. |
| `tesoro.activado` | `true` | `true`/`false` | [Treasure hunt](CONTENT.md#treasure-hunt): map fragments in the loot that lead through several real structures to a buried chest. Disabled, no fragments appear and existing ones do nothing. |
| `tesoro.probabilidad` | 3.0 | 0-100 (decimals allowed) | Chance, in %, of a fragment in each chest of medium structures and mines; half that in unique structures' chests; five times that in job-board feat rewards. |
| `tesoro.radio_max` | 1500 | 300-4000 | Maximum distance from each mark of the map to the previous one (or to where the fragment is deciphered), in blocks. |
| `eventos.activado` | `true` | `true`/`false` | [Village events](CONTENT.md#village-events): now and then a market day, a wedding, a funeral or a festival in the square of the Heraldia village a player is in (also in villages already generated); 10 to 15 villagers without AI and a few props for 3 to 6 minutes, then everything goes. Off (and with `ligero`), none starts and the running ones end. |
| `eventos.frecuencia` | 20 | 0-100 | Chance (%) of an event starting at each draw (every 30 s, per village with a player inside and more than 24 blocks from its square). 0: only with `/heraldia event start`. |
| `eventos.espera_minutos` | 20 | 5-240 | Minutes of play each village rests between one event and the next: raise it to make them rarer. |
| `eventos.max_activos` | 2 | 1-4 | Events at once on the whole server (each one up to 18 entities while it lasts). |
| `casa_heraldo.activado` | `true` | `true`/`false` | [The Herald's House](CONTENT.md#the-heralds-house): the walled spawn town (128 × 128) and its 50-block protected ring. Disabled, it is neither built nor protected. |
| `casa_heraldo.generar_en_mundos_nuevos` | `true` | `true`/`false` | Built on its own at spawn in a new world (never in an existing one: `/heraldia herald place`). Read at startup. |
| `casa_heraldo.contenedores_solo_ver` | `true` | `true`/`false` | A player who is not an operator opens the area's containers to look, not to take or put; off, they stay shut. |
| `casa_heraldo.mercado.activado` | `false` | `true`/`false` | Market stalls for rent, paid in emeralds. |
| `casa_heraldo.mercado.entrada_esmeraldas` | 16 | 0-256 | Entry fee to take a free stall (once, with the first rent). |
| `casa_heraldo.mercado.alquiler_esmeraldas` | 4 | 0-256 | Rent per period (0: the stall never runs out). |
| `casa_heraldo.mercado.periodo_dias` | 7 | 1-60 | Length of a rent period, in game days. |
| `casa_heraldo.mercado.gracia_dias` | 3 | 0-30 | Game days of grace after the rent runs out before the stall is lost. |
| `casa_heraldo.caminos.activado` | `true` | `true`/`false` | [The Herald's House roads](CONTENT.md#the-heralds-house-roads) with their huts and the arena road. |
| `casa_heraldo.caminos.aldeanos` | 5 | 0-8 | Villagers in the roadside huts, in all (the guide included). |
| `casa_heraldo.alrededores.activado` | `true` | `true`/`false` | The grounds: the protected ring levelled, with cherry trees and small houses. |
| `casa_heraldo.alrededores.casas` | 8 | 0-12 | Small houses in the grounds (none where the ground does not allow it). |

Atlantis has no placement options: there is always exactly one per world.

### Gameplay profiles

The `perfil` option sets a group of options in one go. `casual`, `estandar` and `hardcore` only set gameplay options (never world generation: where and how structures spawn, or the arena that builds itself in a new world, are never touched by them); `ligero` is the [light profile](#light-profile), the `estandar` game with lighter world generation for modest machines. `estandar`, the default, is exactly the previous behaviour.

| Option | `casual` | `estandar` | `hardcore` |
| --- | --- | --- | --- |
| `dificultad.nivel` | `facil` | `normal` | `heroica` |
| `dificultad.escalar_por_jugadores` | `false` | `false` | `true` |
| `dificultad.escalar_botin` | `false` | `true` | `true` |
| `botin.reponer.activado` | `true` | `false` | `false` |
| `botin.reponer.dias` | 3 | 7 | 14 |
| `jefes.fases.activado` | `true` | `true` | `true` |
| `jefes.refuerzos.activado` | `true` | `true` | `true` |
| `jefes.refuerzos.porcentaje` | 50 | 100 | 150 |
| `jefes.refuerzos.maximo_vivos` | 2 | 4 | 6 |
| `arena.oleada.mobs_incremento` | 30 | 50 | 75 |
| `arena.oleada.stats_incremento` | 5 | 10 | 20 |
| `arena.max_mobs_vivos` | 12 | 20 | 28 |
| `arena.experiencia_porcentaje` | 30 | 15 | 5 |
| `caravanas.prob_asalto` | 15 | 35 | 60 |
| `chozas_mago.prob_malvado` | 10 | 20 | 35 |

- **An option written in the file overrides the profile** (it is "set by hand"). If its value is not the profile's, the profile becomes **custom** (`personalizado`): the log says so at startup, listing which options differ and what the profile would give, and so do `/heraldia profile` and the `_perfil` block of the file. The other options keep the profile's values.
- The options a profile sets are only written to the file when they are set by hand; that way changing `perfil` in the file actually changes them. To go back to the profile's value, delete the option from the file.
- `personalizado` sets nothing: each option takes its value from the file or, if it is not there, its default.
- Files from 0.1.0 (`version` 1) are migrated without changing anything: the mod used to write every option, so the profile options that had their default are removed (with `estandar` they give the same) and the ones with another value stay as set by hand.
- Files of version 2 (before the light profile) are migrated the same way: the options of `ligero` that had their default are removed (with any other profile they give the same) and those with another value stay as set by hand; a backup `heraldia.json.v2.bak` is kept.
- It is applied whenever the file is read (at startup and with `/heraldia reload`), never in the middle of a chunk; mobs already generated take the difficulty when they load, as before. The generation options of `ligero` wait for the restart, like any other generation option.
- Changing the profile from the [panel](#in-game-configuration-panel-heraldia-config) or the [screen](#configuration-screen-client) moves the options that had the previous profile's value to the new one's and keeps the ones set by hand (before, the panel left the previous profile's values written as set by hand, so the new profile came out as `personalizado`).

### Light profile

`"perfil": "ligero"`: the same game as `estandar` (difficulty, bosses, loot, arena... the gameplay options of the table above take `estandar`'s values) with lighter world generation, for modest machines and servers with little RAM. It is the only profile that touches generation, and it does it only with these options (an option of this list written in the file with another profile is just an option: it does not make that profile `personalizado`):

| Option | Default (every other profile) | `ligero` | Why |
| --- | --- | --- | --- |
| `aldeas.porcentaje_grandes` | 25 | 10 | a large village has about twice the pieces of a standard one: the village zone is where Heraldia weighs most (+10 % per chunk) |
| `aldeas.caminos.activado` | `true` | `false` | the road feature looks at its route in every chunk it crosses |
| `medianas.frecuencia_porcentaje` | 100 | 50 | fewer medium structures than the default (the common kinds thin out; see [Medium structures density](#medium-structures-density)) |
| `medianas.distancia_minima.bloques` | 192 | 320 | more room between two medium structures |
| `minas.vanilla.multiplicador` | 2.0 | 1.0 | vanilla abandoned mineshafts, the long galleries, as in vanilla (the default doubles them) |
| `caravanas.activado` | `true` | `false` | no caravan entities walking between villages (server ticks) |
| `eventos.activado` | `true` | `false` | no [village events](CONTENT.md#village-events) (10 to 15 entities in a square while one lasts: on a machine half as fast per core, an event costs about twice what [docs/DEVELOPMENT.md](DEVELOPMENT.md) measures) |
| `medianas.habitantes` | `true` | `false` | no villagers with AI in the medium structures (server ticks); the traders that were still figures before stay still, as they were |

The [wayfarers](CONTENT.md#wayfarers) (`viajeros.activado`) are not part of it: they cost less than a caravan (one encounter of 1 to 6 entities with simple AI for a minute or two) and adding an option to a profile changes the file format; on a very modest machine, set `viajeros.activado` to `false` by hand.

What it saves (measured with `tools/smoke/generation_cost.py --profile ligero`, 3 passes on 4 cores, same seed and areas as the cost test, when `ligero` had `medianas.frecuencia_porcentaje` 60 and the default was 100; the medium frequency itself turned out not to be a measurable cost, see [Medium structures density](#medium-structures-density)): against vanilla, the CPU per chunk goes from +9.6 % with `estandar` to **−0.7 %** with `ligero` (within the noise: as light as without Heraldia); in the village's zone, from +9 % to +2 %; the chunks over a tick (50 ms), from +3.3 points to −1.2 points; the server tick while generating (MSPT p99), from 17.7 to **5.1 ms** (max 21.8 → 6.3 ms; vanilla 6.8-8.8 ms); the continuous strip, already like vanilla with `estandar`, stays so (worst stretch −0 % and −7 %); `/locate` of a medium structure 71 → 49 ms and of a mine 925 → 816 ms. What it does **not** lower: the slowest single chunk (the start of a village, 230-290 ms: the village is still there) and the memory after each GC (441 and 461 MB at most, against 401-403 MB without Heraldia: that is noise). The light profile saves CPU and server ticks, not RAM; the memory is used for the first-start suggestion because hosting plans with little RAM usually come with few, slow cores.

What it does **not** change, on purpose: the grids of villages (`aldeas.separacion_bloques`, `aldeas.maximo`) and of unique structures, and the mine entrances. In a world already started, moving a grid would make new villages or unique structures spawn next to old ones and `/locate` and the maps would stop finding those already generated; and the mine entrances cost little to generate (each one is a single template, about 6 ms in all for the 12 candidates of the test) and their galleries are part of that template, so the "shorter galleries" are the vanilla mineshafts going back to vanilla frequency.

**In a world already started** (the main thing to know): what is already generated **does not change**. Only the chunks generated after the restart follow the light profile, so next to the land already explored there are **seams**: a zone dense with medium structures next to an emptier one, roads that end at the edge of what was generated, and `/locate` and maps may no longer find medium structures generated with the previous frequency. That is why:

- In the [panel](#in-game-configuration-panel-heraldia-config), choosing `ligero` in a world already played (more than a minute of game time) first opens a dialog that explains it, with **Apply anyway** (`/heraldia config profile ligero confirm`) and **Back**; from the console, `/heraldia config profile ligero` explains it and gives the `confirm` command. On the [client screen](#configuration-screen-client), choosing it shows the same warning (and the profile's tooltip keeps it).
- At startup, the mod saves the generation options in use in the world (new attachment `heraldia:generacion_mundo`). If they changed since the previous start in a world already played (by the profile or by hand), it writes a warning in the log with what changed (for example `medianas.frecuencia_porcentaje 60 → 50`) and tells each operator in the chat on joining. A world from before this version, without that record, is warned if it starts with `ligero` or if a generation default it was using has changed since and the file does not set that option by hand (such a world was generated with `medianas.frecuencia_porcentaje` 100, the default again today, so nothing to warn there; a world started with the 60 of a few hours of development has the record and is warned with `medianas.frecuencia_porcentaje 60 → 100`: see [Medium structures density](#medium-structures-density)).
- `/heraldia profile` reminds it when the profile in use is `ligero`.

Why warn and let the owner decide instead of only allowing it in a new world: a generation profile only takes effect after a restart, so even in a brand-new world the area around spawn is already generated with the previous options when it is chosen in game: "only in a new world" can only mean "chosen in the file before the world exists", which is what the first-start suggestion (below) is for. And for an existing world on a modest machine the lighter generation of the new land is exactly what the owner may want: the seams are a visual and gameplay cost they can accept knowingly, nothing breaks (nothing already built or generated changes, and switching back to `estandar` restores the old frequencies in the chunks generated afterwards).

**First-start suggestion**: when `config/heraldia.json` does not say which profile to use (a first start, or a file without `perfil`), the mod looks at the memory given to Java (`-Xmx`) and the cores, and writes one line in the log: with less than 3.5 GB (a server started with `-Xmx3G` or less) or 2 cores or fewer it suggests `ligero`; otherwise it says the current profile is fine. If it suggests `ligero`, each operator who joins during that session gets it in the chat, with a **[Apply the light profile]** button (it runs `/heraldia config profile ligero`, with the confirmation above in a world already started). It never applies anything on its own, and once a profile is in the file (the mod writes it at startup) it stays quiet.

### Medium structures density

The default is **100** (`medianas.frecuencia_porcentaje`: each type at its own spacing): among all overworld types, one medium structure every **~550 blocks**, and on a walk in a straight line you pass by one (within 80 blocks of the path) every **~1.9 km**. Heraldia aims at a world full of structures, activity and life, also at short range, and the density costs nothing measurable (below), so the default is the dense one. The medium-density session lowered it to 60 for a few hours (one every ~610 blocks, ~2.3 km on a walk) and it went back to 100. Fewer are still an option: `"medianas": {"frecuencia_porcentaje": 60}` in `config/heraldia.json` (or *Frequency (%)* in the [panel](#in-game-configuration-panel-heraldia-config) or the [screen](#configuration-screen-client)); lowering it thins out the common kinds (roadside inns one every ~1,330 blocks at 60 instead of ~1,070, bandit camps ~1,380 instead of ~1,220, mills ~1,840 instead of ~1,590), while the ones tied to a scarce biome (hermitages, hunters' lodges, watchtowers, fisher's huts, ruined shrines) keep practically the same number. The [light profile](#light-profile) uses 50.

What each frequency gives (measured, 18-11-2026):

| Frequency | One every (blocks) | Passed per km walked | Rarest type (one every) | CPU per chunk vs vanilla | Chunks > 50 ms (vanilla 15.3 %) | p99 per chunk (vanilla 145.7 ms) | Worst stretch of the strip (vanilla 58.2 ms/chunk) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **100 (default)** | **551** | **0.53** | hermitage (2,954) | +5.5 % | 17.0 % | 143.1 ms | 60.4 |
| 85 | 573 | 0.49 | hermitage (2,954) | +1.1 % | 14.0 % | 142.1 ms | 56.0 |
| 70 | 598 | 0.45 | hermitage (2,889) | +3.8 % | 16.6 % | 148.7 ms | 55.6 |
| 60 (the default for a few hours) | 609 | 0.43 | hermitage (2,799) | +3.5 % | 15.7 % | 147.2 ms | 54.3 |
| 50 (`ligero`) | 630 | 0.40 | hermitage (2,654) | not measured | — | — | — |
| 25 | 745 | 0.29 | hermitage (2,938) | not measured | — | — | — |

- Game feel (`MediumDensityComparisonTest`, the simulation of `MediumFrequencyTest`: placement grids on the real 26.3 overworld biome noise with villages, unique structures and vanilla structures around them, 3 seeds of 16 × 16 km). The frequency option thins out mostly the common kinds: for a kind tied to a scarce biome the limit is how many patches of its biome there are, not the size of the grid cell, so lowering the frequency below ~60 % gains little (25 % still gives one every 745 blocks). At every frequency down to 25 % every type still spawns in every seed (31 times or more per 256 km² seed at 60 %).
- Generation cost (`tools/smoke/generation_cost.py --zones medianas --variant ...`, 2 passes per configuration against the same vanilla passes, 4 cores: four squares of 51 × 51 chunks on open land at the four diagonals, 10,404 chunks, plus the continuous strip; the standard zones are centred on a village and next to a castle, where no medium structure spawns). **The density of medium structures is not a measurable generation cost**: the differences between frequencies (+1 % to +5.5 % against vanilla) are inside the noise of two identical passes (±3 %), the placement rule of the mediums adds up to 0.15-0.38 s in the whole pass (0.02-0.03 ms per chunk) and starting them 27-44 ms in all (11-14 in the measured land). The default is therefore a gameplay decision, not a performance one: a world full of structures, so 100; the light profile keeps a lower value (50) and its other savings (roads, large villages, mineshafts, caravans).

**In a world already started with the 60** (during the few hours it was the default): what is already generated does not change; only new chunks follow the default 100, so between the land explored with 60 and the new one there may be a seam (a zone with fewer medium structures next to a denser one). That world has the record of its generation options, so the mod warns about it at startup (log and chat of each operator) with `medianas.frecuencia_porcentaje 60 → 100`. To keep 60 in such a world, write `"medianas": {"frecuencia_porcentaje": 60}` in the file before generating new land: a value written by hand never changes with an update, and there is no warning. A world from before the record was generated with 100, so it has no seam from this. A file from before the light profile (format 1 or 2), where the mod wrote 100 on its own, is not "set by hand" (the mod wrote every option then): it takes the default, which is 100 too.

### Search memory

`/locate`, the treasure maps (cartographers and chests), the Chronicle folios and `/heraldia info nearby` all ask the same expensive question about the same grid cells: would this structure start here (biome, terrain of the hillside or the shore, Heraldia's placement rules)? The game already remembers those answers, but only until the server stops: after every restart the first search paid all of it again, **on the server thread** (every player notices the stall). Since this version the answers are kept **in the world** (attachment `heraldia:busquedas`) and served from there, with nothing to configure.

- **The result does not change**: only answers of pure functions are kept (with the same seed and configuration they always give the same value), and what depends on what is already generated (the saved chunks) is still read every time. With the same world, the same positions as before, exactly (checked in `tools/smoke/search_cache.py` and comparing 112 answers against the previous `.jar`: 56 searches from 7 points, in a new world and after a restart).
- **Discarded on its own when something that decides placement changes**: at startup a stamp is computed from the seed, the generation options **with their values in use** (the same ones as the seam record `heraldia:generacion_mundo`; a value not written in the file counts with its default, so a changed default, like `medianas.frecuencia_porcentaje` 100 → 60 → 100, also discards it), the mods and their versions, the datapacks (and the files of the world's `datapacks` folder), the `.jar` itself and the registered structures and structure_sets. If it differs from the saved one, the whole memory is thrown away (the log says `Heraldia: búsquedas: la memoria guardada (...) es de otra configuración, mods o versión: se descarta`). "There is nothing here" is an answer too, and it is discarded with the rest.
- **Bounded**: at most 16,384 answers; the structures of a structure_set that share a cell (the 10 styles and variants of a mine size, the lighthouses, the wrecks) go together in one. The 4 searches of `generation_cost.py` store about 950 and 56 varied searches from 7 points about 5,100; when full, the oldest that nobody asks for again go. Worst case in the save: 141 KB uncompressed, 113 KB compressed; usually a few KB. It is written with the world (`save-all`, autosave, stop), only if something changed.
- A search that finds nothing walks the whole grid (some 40,000 cells) and asked the disk about each one; for a chunk that was never generated, the answer ("no data") is now given without the round trip to the storage thread when its region file does not exist and nothing of that region was written in this session (the same answer: a region file copied in by hand while the server runs is not seen until the next start, as with the game's own region cache).

Measured (4 cores, seed `heraldia`, default configuration, the same cases as `tools/smoke/generation_cost.py`: `/locate` from 8000, -8000; ms as the game reports them, on the server thread; two rounds each, the range):

| Search | Before: first search | Before: after a restart | Now: first search | Now: after a restart |
| --- | --- | --- | --- | --- |
| `#heraldia:minas` | 773-834 | 1,114-1,465 | 735-828 | **34-51** |
| `#heraldia:aldeas` | 250-425 | 164-179 | 358-394 | **26-35** |
| `heraldia:unicas/castillo` | 315-326 | 126-136 | 266-360 | **1-2** |
| `#heraldia:medianas` | 64-70 | 168-183 | 69-79 | **4-6** |
| Nothing found (`#heraldia:aldeas` from 200000, 200000; wall time) | 1,660-1,714 | 1,573-1,613 | **286-307** | **403-547** |

The first search from a new place still computes what nobody asked before (except the one that finds nothing); repeating it in the same session already cost 0-24 ms before (the game's memory; 261-274 the one that finds nothing) and now 0-5 ms (154-194). With 56 varied searches (villages, castle, cathedral, all the uniques, mediums, mines, lighthouses and wrecks and vanilla villages, from 7 points between 0, 0 and 100000, -50000): 45.1 s → 33.1 s in total the first time and **41.1 s → 0.64 s** after a restart (the slowest, `#heraldia:costa` from 3000, 3000: 9.0 s → 17 ms), with the same 112 answers; the memory kept 5,674 answers.

### Configuration screen (client)

On the client the file can also be edited from a screen inside the game. With [Mod Menu](https://modrinth.com/mod/modmenu) installed (optional; the mod works the same without it, the screen just has no button) it opens from the configuration button of Heraldia in the mod list. It is built from the same option list as the file, so new options appear on their own:

- Sections: Gameplay profile, Villages, Village families, Village styles, Village life, Roads between villages, Golems, Unique structures, Minimum distance between unique structures, Atlantis, Guardians (bosses), Medium structures, Mines, Lighthouses and wrecks, Compatibility with other mods, Loot, Difficulty, Herald's Guide, Wave arena, Quests and reputation, Caravans, Wizard's huts, Updates, Web maps and Treasure hunt, with a search box (by name, key, help or section).
- Each option shows its value (on/off button, number box, or a button that cycles through the values of a list option such as `dificultad.nivel`). Its tooltip shows the key, the help text (the same as `_ayuda`) and the default and range. An invalid number turns red, its tooltip says why and **Save** stays disabled until it is fixed.
- Gameplay profile: choosing `ligero` shows a warning (in a world already started, only new chunks follow it and seams are left; see [Light profile](#light-profile)). Changing it moves the options that had the previous profile's value to the new one's; the ones with another value (set by hand) stay as they are, with their name in gold, and their tooltip shows the profile's value and that they override it. The tooltip of the profile itself shows the effective profile and which options differ. On saving, only the options whose value is not the profile's are written as set by hand.
- **Save** writes `config/heraldia.json` in the same format as at startup (with `version` and `_ayuda`); **Reset to defaults** puts every option back to its default (nothing is written until you save); **Cancel** discards the changes.
- Changes apply when the world is opened again or the server is restarted, and only to chunks generated afterwards; the screen says so. With no world open they are used from the next world you open (no need to restart the game). With a single-player world open, saving reloads live whatever does not affect generation, the same way as [`/heraldia reload`](#live-reload-heraldia-reload) (the report shows in the chat); the rest, after leaving and re-entering it.
- When connected to a server the screen edits **the client's local file** (your single-player worlds), not the server's: the screen warns about it. The server's configuration is still edited in its own `config/heraldia.json`. Nothing is sent over the network.
