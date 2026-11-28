# tools/probes: the measuring scripts of the village lofts work (Nov 2026)

**They are not tests and CI never runs them**: `tools/test.py` only discovers `tools/smoke/*.py` and
`tools/gen/uniques/*/smoke_*.py`, so nothing here takes a group. They are kept so that the figures of the village
ladders work can be measured again on another .jar, and so that any later change to the villages can be shown not to
have brought the fault back. Earlier, longer-lived probes of the same family (`loftprobe.py`, `gardenescape.py`,
`player_gate.py`, `closet_experiment.py`, `findlofts.py`) live on the branch `claude/heraldia-camas`, which has no
pull request on purpose; `wlayout.py`, `wlofts.py` and `wdays.py` here are that branch's `layout.py`, `findlofts.py`
and `days.py` with their absolute paths fixed and reading `tools/smoke/saved_world.py` instead of their own copy.

Run them with the generator's requirements installed (`tools/gen/requirements.txt`) and, for the ones that start a
server, with Java 25 on the PATH and `HERALDIA` pointing at the repository (it defaults to `/home/user/heraldia`).

| Script | What it measures | The figure it gave (develop 625616c against this branch) |
|---|---|---|
| `census.py <repo> [out.json]` | Every village template, from the registry built in memory: ladder columns of 4 rungs or more a villager could climb from the ground, and whether the top is a place its path search cannot walk out of. No server. ~90 s. | develop: **536 of 2,796** village templates, and the top of all 536 is such a place (170 houses, 108 mills, 108 town halls, 72 watchtower terminators, 42 churches, 36 smithies). 560 before #149. With the closets: 536 shut, audit clean. |
| `wlayout.py <work> <jar>` | Places the 8 villages of `village_routes` with the world frozen (`tick freeze`) and saves it, so two .jars can be compared block by block. | 8 of 8 placed. develop against this branch: **195 of 1,748,194 blocks differ, all of them a closed fence gate** (194 where there was air, 1 where there was the ladder's lowest rung). |
| `wstranded.py <world>` | **The question itself, on a saved world**: from the natural ground at the edge of each village's box, walking and climbing every ladder it can walk into, which cells can a villager reach that its search finds no way back from? No height criterion. | develop: **98 of 99** ladders it can walk into, **5,727** cells it cannot walk back from. This branch: **0 and 0**. |
| `wlost.py <world A> <world B>` | Which cells of the villagers' walk the closets cost, and what is in them now. | 292: 194 gate cells, 97 ladder feet now out of reach, 1 ladder foot turned into a gate, **and nothing else**. |
| `wlofts.py <world> [out.json]` | `findlofts.py` of the camas branch: ladder columns whose lowest rung is at the ground and whose top the search cannot leave, with the loft cell farthest from the ladder and a free cell at its foot. Writes the `lofts.json` that `wplayer.py` reads. | develop: **85** ladders from the ground, **72** with no way down (92 and 78 on develop 06fd278, before #149's chapels). |
| `wdays.py <work> <jar> <days>` | The 8 villages on a flat world, N game days with the clock running; every night each villager's position, saved, and `village_routes.shut_in` on it, followed by UUID. ~6 min a day. | develop: **2,3,2,4,5,4,5,5,6,6,5,6** (7 villagers, 4 of them up a ladder) and 25-28 without a bed. This branch: **2,1,2,2,1,2,2,2,1,1,2,2** (2 villagers, neither up a ladder) and 23-26. |
| `wplayer.py <work> <jar> <lofts.json>` | Carpet's fake player at each ladder of one village, from the same cell in every .jar: look at the gate, use it, walk toward the ladder, and if walking did not do it, walk and jump. | This branch: gate opened **12 of 12**; reached the top of **4 of 12** by walking. **develop, with no gate: the same 4 of 12, to the same heights.** The other 8 it cannot climb either way: its steering walks it into the wall. Run the control before reading the share. |
| `gates.py <repo> [out.json]` | The shut-in gates census: every village template, its search's walk from the ground round it with the gates as they are and with every gate open; each place only the second reaches, with what puts a villager in it (a `villagers/` jigsaw, a bed, a workstation). The ladder closets' gates are left out. No server. ~6.5 min. | develop 6d9bb6f: **254** templates with a place behind a shut gate, a villager placed in it in **144** (`library_c` 36, `farm`/`_b`/`_c` 108); the other 110 are the cemeteries (108) and `sheep_pen` (2), nobody in them. The build's own audit (`enclosures.py`) with the gates shut again: the same 144. |
| `wcompare.py <world A> <world B>` | Two `wlayout.py` worlds compared block by block over each village's whole box (y -64..80), and each difference counted by its two states. | develop 6d9bb6f against the shut-in gates branch: **19 of 2,030,164** blocks differ, all a gate shut -> open (16 in the 8 farms, 3 in the 3 cloister libraries). Its total is not `wlayout`'s 1,748,194 above: another volume. |
| `wfarmers.py <work> <jar> <days>` | `wdays.py` plus each villager's profession and bed, and a second shut-in reading with a reach of 40 blocks (`penned`), because `village_routes.shut_in` (12) cannot see a villager shut in a farm. Caches each UUID's profession after its first reading: profession changes later in the run are not seen. | develop: **8 of 14** farmers penned all 12 nights, 4-5 of 14 with a bed; `shut in` 1-3 (the librarians only). Shut-in gates branch: **0 of 14** penned, 11-13 of 14 with a bed. |
| `wground.py <work> <jar> [<type> ...]` | Where the ground is round a medium structure in a real world (#86): for one structure of each inhabited family, generated where /locate finds it, the height of its layer 0 and, one to three blocks outside its box, the height of the terrain's top, as a histogram and with literal columns. It is what `mediums/_paths.START_BASE` rests on. ~3 min. | develop ba71056, seed `heraldia`, default configuration: one block outside the box the terrain's top is **level with the layer 0 in 392 of 430 columns** (posada 55 of 74, molino 74 of 76, pescador 71 of 76, cazadores 56 of 68, ermita 76 of 76, torre_vigia 60 of 60); the rest is the hillside the inn stands against (19, 8 to 12 above), a slope down beside the hunters' lodge (12, 1 or 2 below) and sugar cane and blue orchids the reader counts as ground (7). |

Two traps these probes already fell into, both declared in the scripts:

- **Seeding the walk from every standable cell at the street's level** hands it the inside of every building and the
  foot of every ladder, and then a shut ladder reads as open: the first run of `wstranded.py` reported 84 of 99
  climbable and 4,448 stranded cells on a .jar whose templates the audit called clean. It is seeded from the edge of
  the box now. That run is discarded.
- **A 26.3 region palette writes an all-default block state as a bare id**, so `tools/smoke/saved_world.py` gives
  back `minecraft:spruce_fence_gate` with no properties, and `mediums/_paths.Ground`, which only calls a gate solid
  on `open=false`, reads a closed gate as open (23 of 98 in a measured world). `wstranded.py` and `wlost.py` spell
  the defaults out before the model sees them; the real fix is a line in `_paths` and is in LESSONS, "Pending bugs".

And one from the camas branch's README that still holds: **teleporting a villager into a wall suffocates it**, and
**Carpet's `/player` answers nothing on the console** (send it and wait for the join line, and note that Carpet
capitalises the name, so `@a[name=Probe]`, not `probe`).
