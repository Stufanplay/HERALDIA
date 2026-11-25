package io.github.albertosa23.heraldia.update;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.gson.JsonParser;
import io.github.albertosa23.heraldia.update.TemplatePatch.Verdict;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import net.minecraft.core.BlockPos;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.NbtAccounter;
import net.minecraft.nbt.NbtIo;
import net.minecraft.nbt.Tag;
import org.junit.jupiter.api.Test;

/**
 * /heraldia update mend: the rule that decides whether a placed template is repaired ({@link TemplatePatch}), the rule
 * that finds running water with no source ({@link Streams}), and the shipped patches against the templates being built
 * (a later generator change to a patched cell must fail here, not in somebody's world).
 */
class GenerationMendTest {
	// ------------------------------------------------------------------ TemplatePatch.decide

	/** A two-version patch: a window that becomes a door (two cells), a guard beside it. */
	static TemplatePatch door() {
		return new TemplatePatch("heraldia:test", List.of("old", "older"),
				List.of(new TemplatePatch.Cell(0, 1, 0, List.of("minecraft:oak_planks", "minecraft:oak_planks"), "minecraft:oak_door[half=lower]"),
						new TemplatePatch.Cell(0, 2, 0, List.of("minecraft:glass_pane[east=true]", "minecraft:oak_planks"), "minecraft:oak_door[half=upper]")),
				List.of(new TemplatePatch.Guard(1, 1, 0, "minecraft:air")), List.of());
	}

	static Map<String, String> world(String... kv) {
		Map<String, String> m = new HashMap<>();
		for (int i = 0; i < kv.length; i += 2) {
			m.put(kv[i], kv[i + 1]);
		}
		return m;
	}

	static TemplatePatch.Decision decide(TemplatePatch p, Map<String, String> w) {
		return p.decide(c -> w.get(c[0] + "," + c[1] + "," + c[2]));
	}

	@Test
	void anOldVersionUntouchedIsRepaired() {
		var d = decide(door(), world("0,1,0", "minecraft:oak_planks", "0,2,0", "minecraft:glass_pane", "1,1,0", "minecraft:air"));
		assertEquals(Verdict.FIX, d.verdict());
		assertEquals("old", d.version());
		d = decide(door(), world("0,1,0", "minecraft:oak_planks", "0,2,0", "minecraft:oak_planks", "1,1,0", "minecraft:air"));
		assertEquals(Verdict.FIX, d.verdict());
		assertEquals("older", d.version());
	}

	@Test
	void todaysBlocksAreDoneSoASecondRunDoesNothing() {
		var d = decide(door(), world("0,1,0", "minecraft:oak_door", "0,2,0", "minecraft:oak_door", "1,1,0", "minecraft:air"));
		assertEquals(Verdict.DONE, d.verdict());
	}

	@Test
	void anythingElseIsSomebodysAndLeftAlone() {
		// the window broken and replaced by a player's torch
		var d = decide(door(), world("0,1,0", "minecraft:oak_planks", "0,2,0", "minecraft:torch", "1,1,0", "minecraft:air"));
		assertEquals(Verdict.CHANGED, d.verdict());
		assertEquals("minecraft:torch", d.found());
		// a chest put against the wall outside (the guard)
		d = decide(door(), world("0,1,0", "minecraft:oak_planks", "0,2,0", "minecraft:glass_pane", "1,1,0", "minecraft:chest"));
		assertEquals(Verdict.CHANGED, d.verdict());
		assertEquals("minecraft:chest", d.found());
		// half today's, half the old: not one version's whole
		d = decide(door(), world("0,1,0", "minecraft:oak_door", "0,2,0", "minecraft:glass_pane", "1,1,0", "minecraft:air"));
		assertEquals(Verdict.CHANGED, d.verdict());
		// the planks of one version, the window of the other, on cells of the same piece: mixed, not repaired
		var p = new TemplatePatch("t", List.of("a", "b"),
				List.of(new TemplatePatch.Cell(0, 0, 0, List.of("minecraft:stone", "minecraft:dirt"), "minecraft:air"),
						new TemplatePatch.Cell(1, 0, 0, List.of("minecraft:stone", "minecraft:dirt"), "minecraft:air")),
				List.of(), List.of());
		assertEquals(Verdict.CHANGED, decide(p, world("0,0,0", "minecraft:stone", "1,0,0", "minecraft:dirt")).verdict());
	}

	@Test
	void whatCannotBeSeenIsNeverRepaired() {
		var d = decide(door(), world("0,1,0", "minecraft:oak_planks", "0,2,0", "minecraft:glass_pane"));
		assertEquals(Verdict.CHANGED, d.verdict());
	}

	@Test
	void aGuardsAirMayHoldSnowButACellThatGoesMustBeAir() {
		var d = decide(door(), world("0,1,0", "minecraft:oak_planks", "0,2,0", "minecraft:glass_pane", "1,1,0", "minecraft:snow"));
		assertEquals(Verdict.FIX, d.verdict());
		var p = new TemplatePatch("t", List.of("a"), List.of(new TemplatePatch.Cell(0, 0, 0, List.of("minecraft:air"), "minecraft:chest")),
				List.of(), List.of());
		assertEquals(Verdict.CHANGED, decide(p, world("0,0,0", "minecraft:snow")).verdict());
		assertEquals(Verdict.FIX, decide(p, world("0,0,0", "minecraft:cave_air")).verdict());
	}

	// ------------------------------------------------------------------ Streams.unfed

	static long at(int x, int y, int z) {
		return BlockPos.asLong(x, y, z);
	}

	/** A world of a few water blocks; everything else is stone, and x >= 100 is not loaded. */
	static Streams.Water water(Map<Long, Streams.Water> m, long p) {
		if (BlockPos.getX(p) >= 100) {
			return Streams.Water.UNSEEN;
		}
		return m.getOrDefault(p, Streams.Water.OTHER);
	}

	@Test
	void aStreamWithNoSourceIsUnfedAndSoIsWhatRanOnFromIt() {
		Map<Long, Streams.Water> m = new HashMap<>();
		// down a hillside, a block down every two: what lies below is reached only as what ran on from the first
		for (int[] c : new int[][] {{0, 10}, {1, 10}, {1, 9}, {2, 9}, {3, 9}, {3, 8}, {4, 8}}) {
			m.put(at(c[0], c[1], 0), Streams.Water.RUNNING);
		}
		Set<Long> out = Streams.unfed(List.of(at(0, 10, 0)), p -> water(m, p));
		assertEquals(m.size(), out.size(), "every block of the stream");
	}

	@Test
	void aStreamFedFromASourceIsLeft() {
		Map<Long, Streams.Water> m = new HashMap<>();
		m.put(at(0, 10, 0), Streams.Water.SOURCE);
		for (int x = 1; x < 6; x++) {
			m.put(at(x, 10, 0), Streams.Water.RUNNING);
		}
		assertTrue(Streams.unfed(List.of(at(5, 10, 0)), p -> water(m, p)).isEmpty());
		// fed from above (a fall from a source)
		Map<Long, Streams.Water> f = new HashMap<>();
		f.put(at(0, 12, 0), Streams.Water.SOURCE);
		f.put(at(0, 11, 0), Streams.Water.RUNNING);
		f.put(at(0, 10, 0), Streams.Water.RUNNING);
		assertTrue(Streams.unfed(List.of(at(0, 10, 0)), p -> water(f, p)).isEmpty());
	}

	@Test
	void whatAnUnloadedChunkHidesCountsAsASource() {
		Map<Long, Streams.Water> m = new HashMap<>();
		for (int x = 95; x < 100; x++) {
			m.put(at(x, 10, 0), Streams.Water.RUNNING);
		}
		assertTrue(Streams.unfed(List.of(at(95, 10, 0)), p -> water(m, p)).isEmpty());
	}

	// ------------------------------------------------------------------ the shipped patches against today's templates

	/** Today's template: {"x,y,z": state string} (air cells absent) and its entities' {"x,y,z": name key}. */
	record Template(Map<String, String> blocks, Map<String, String> entities) {
	}

	static Template read(String id) throws IOException {
		Path f = Path.of(System.getProperty("heraldia.generated"), "data/heraldia/structure", id.substring("heraldia:".length()) + ".nbt");
		CompoundTag t = NbtIo.readCompressed(f, NbtAccounter.unlimitedHeap());
		List<String> pal = new ArrayList<>();
		for (Tag p : t.getListOrEmpty("palette")) {
			CompoundTag c = (CompoundTag) p;
			StringBuilder sb = new StringBuilder(c.getStringOr("id", c.getStringOr("Name", "?")));
			CompoundTag props = c.contains("id") ? c.getCompoundOrEmpty("properties") : c.getCompoundOrEmpty("Properties");
			if (!props.isEmpty()) {
				sb.append('[').append(String.join(",", props.keySet().stream().sorted().map(k -> k + "=" + props.getStringOr(k, "")).toList())).append(']');
			}
			pal.add(sb.toString());
		}
		Map<String, String> blocks = new HashMap<>(), entities = new HashMap<>();
		for (Tag b : t.getListOrEmpty("blocks")) {
			CompoundTag c = (CompoundTag) b;
			int[] pos = c.getIntArray("pos").orElse(null);
			if (pos == null) {
				ListTag l = c.getListOrEmpty("pos");
				pos = new int[] {l.getIntOr(0, 0), l.getIntOr(1, 0), l.getIntOr(2, 0)};
			}
			blocks.put(pos[0] + "," + pos[1] + "," + pos[2], pal.get(c.getIntOr("state", 0)));
		}
		for (Tag e : t.getListOrEmpty("entities")) {
			CompoundTag c = (CompoundTag) e;
			ListTag bp = c.getListOrEmpty("blockPos");
			CompoundTag n = c.getCompoundOrEmpty("nbt");
			String name = n.getCompoundOrEmpty("CustomName").getStringOr("translate", n.getStringOr("CustomName", ""));
			entities.put(bp.getIntOr(0, 0) + "," + bp.getIntOr(1, 0) + "," + bp.getIntOr(2, 0), n.getStringOr("id", "") + " " + name);
		}
		return new Template(blocks, entities);
	}

	static List<TemplatePatch> shipped(String kind) throws IOException {
		try (InputStream in = GenerationMend.class.getResourceAsStream("/heraldia/mend/" + kind + ".json")) {
			assertNotNull(in, "the " + kind + " patch is in the jar");
			return GenerationMend.parse(JsonParser.parseReader(new InputStreamReader(in, StandardCharsets.UTF_8)).getAsJsonObject());
		}
	}

	@Test
	void eachPatchsAfterIsTodaysTemplate() throws IOException {
		for (String kind : List.of("inn", "wharf")) {
			List<TemplatePatch> ps = shipped(kind);
			assertFalse(ps.isEmpty(), kind + ": no pieces");
			for (TemplatePatch p : ps) {
				Template t = read(p.template());
				for (TemplatePatch.Cell c : p.cells()) {
					String now = t.blocks().getOrDefault(c.x() + "," + c.y() + "," + c.z(), "minecraft:air");
					assertEquals(now, c.after(), p.template() + " " + c + ": the generator changed a patched cell; make the patch again");
					assertTrue(c.before().stream().anyMatch(b -> !b.equals(c.after())), p.template() + " " + c + ": a cell no version changes");
				}
				for (TemplatePatch.Guard g : p.guards()) {
					String now = t.blocks().getOrDefault(g.x() + "," + g.y() + "," + g.z(), "minecraft:air");
					assertEquals(g.block(), TemplatePatch.block(now), p.template() + " guard " + g);
				}
			}
		}
	}

	@Test
	void theInnsPatchOpensTheDoorAndCarriesTheChest() throws IOException {
		Set<String> templates = new HashSet<>();
		for (TemplatePatch p : shipped("inn")) {
			templates.add(p.template());
			assertTrue(p.cells().stream().anyMatch(c -> c.after().contains("_door[") && c.after().contains("half=lower")), p.template());
			assertTrue(p.cells().stream().anyMatch(c -> c.after().contains("_door[") && c.after().contains("half=upper")), p.template());
			assertEquals(1, p.moves().size(), p.template() + ": the room's chest is carried, never emptied");
		}
		assertEquals(6, templates.size(), "three styles, two variants: " + templates);
	}

	@Test
	void theWharfsPatchIsThePostOnlyWhereItWasAWall() throws IOException {
		List<TemplatePatch> ps = shipped("wharf");
		assertEquals(1, ps.size(), "only the midlands style's sentry variant had a wall under its guard");
		TemplatePatch p = ps.get(0);
		assertEquals("heraldia:medianas/embarcadero_shulker/medias/a", p.template());
		assertEquals(1, p.cells().size());
		assertTrue(p.cells().get(0).before().stream().allMatch(b -> b.startsWith("minecraft:end_stone_brick_wall")), p.cells().toString());
		assertTrue(p.cells().get(0).after().startsWith("minecraft:purpur_pillar"));
		Template t = read(p.template());
		TemplatePatch.Cell c = p.cells().get(0);
		String post = c.x() + "," + (c.y() + 1) + "," + c.z();
		assertEquals("minecraft:shulker " + GenerationMend.GUARD_NAME, t.entities().get(post), "the guard stands on the post: " + t.entities());
	}
}
