# tools/probes: the measuring scripts of the ladders and gardens work (Nov 2026)

**Unpolished, kept so the figures can be measured again.** These are the scripts that produced the figures in PRs #140,
#145 and #148 and in `docs/LESSONS.md` ("A villager gets by physics to places its path search cannot leave" and the
village ladders entry of "Pending bugs"). They were never cleaned up:
- **absolute paths** (`/home/user/HERALDIA/...`, the scratchpad of the session that wrote them): fix them before use;
- they import `tools/smoke/server_smoke.py`, `village_routes.py` and `medium_structures.py`, and each other;
- they are **not tests**: `tools/test.py` only discovers `tools/smoke/*.py` and `tools/gen/uniques/*/smoke_*.py`, so nothing
  here runs in CI or takes a group.

**`world.py` duplicates `tools/smoke/saved_world.py`** of PR #145 (the region-file reader, 26.3 palette formats included).
If #145 is merged, **`saved_world.py` is the canonical one** and `world.py` is only this copy: use the other, and delete
this one when these scripts are next touched.

| Script | What it measures | The figure it gave (re-run it: this is what should come out) |
|---|---|---|
| `vr_strand.py` | From a saved world: can a villager's path search walk 12 blocks away from where it stands (the mediums/_paths model on the real blocks)? `classify` and `component`. | The two CI positions on top of the old hunters' lookout: shut in, reach 2.2 and 1.4; their bed and the slope beside them: free. The same criterion is `village_routes.shut_in` in #145. |
| `days.py` | The 8 villages of `village_routes` on a flat world, N in-game days with the clock running; every night every villager's position, saved, and shut in or not, followed by UUID. | develop: shut in per day 2, 1, 3, 3, 2, 4, 6, 5, 8, 6, 9, 7 (12 days, 12 different villagers, 8 on lofts, 4 in gardens). Experimental closet jar: 1, 0, 0, 2, 1, 1, 0, 1, 0, 1, 1, 1 (3 villagers, none on a loft). About 3 minutes per game day on 4 cores. |
| `layout.py` | Places the 8 villages with the world frozen (`tick freeze`) and saves: run it with two jars, then compare the saved worlds block by block within ±110 of each village (the comparison is a short loop over `world.blocks`, in the PRs). | Experimental closet vs develop: 276 of 1,740,873 blocks differ, all air turned into the closet (92 gates, 184 posts). Open garden gate vs develop: 14 differ, all a gate from shut to open. |
| `findlofts.py` | From a saved `village_routes` world: every ladder column from the ground whose top lands on a cell the search cannot leave, with the loft's farthest floor cell and a free cell at the ladder's foot. Writes `lofts.json`. | 92 ladders from the ground in the 8 villages, 78 of them onto a loft with no way down. |
| `loftprobe.py` | Villagers with a bed taken at nightfall to the loft nearest their bed (`loft`, as far from the ladder as it goes) or to the foot of the same ladder (`foot`), 2,400 ticks: back in bed? | loft: 0 of 15 back, 15 lost their bed; foot: 13 of 15 back (one climbed the ladder by itself and stayed up). Right beside the hole (an earlier version): 16 of 16 came down. Watch for villagers teleported into a wall: they suffocate (6 did in early versions; counted apart). |
| `gardenescape.py` | Two villagers per garden per round taken inside a fenced garden at nightfall; still inside 2,400 ticks later? "Inside" is judged on the shut-gate geometry (a develop world: `REF`) for both jars. Reads `gardens.json`. | Gate shut: 31 of 60 still inside; open: 1 of 60. |
| `player_gate.py` | Carpet's fake player in front of a closet's gate: looks at it, uses it, walks into the ladder's cell and pushes against the block the ladder hangs from. | Gate opened 4 of 4; the player climbed 3 of 4 (the 4th walked out to the south: probably the crude closet put its gate on the ladder's own side; not verified). Carpet's `/player` commands answer nothing on the console: send them, do not wait for a reply. |
| `closet_experiment.py` | The experimental closet patch (it was pasted into `tools/gen/pack.py`, never committed). | It walls off part of the building in 30 church templates (162 ground cells each): the crude closet is NOT the fix. |

Data: `lofts.json` (from `findlofts.py` on a develop 06fd278 world) and `gardens.json` (the 10 gardens of the 8 villages,
develop 5bd9aba). Both depend on the layout of the 8 `village_routes` villages at their coordinates on a flat world with
the tests' seed: regenerate them after any change to the villages.

What a real closet still needs (agreed, not started): its sides chosen on purpose, and three checks in the build — nothing
left without a way out (`mediums/_paths.stranded`), no cell lost that was reachable from the piece's entrance (the case
of the 30 churches), and the player still reaching the ladder.
