package io.github.albertosa23.heraldia.update;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import org.jspecify.annotations.Nullable;

/**
 * A fix to a template already placed in a world, as a list of cells (pure logic over block ids, so it is tested without
 * the game; {@code GenerationMend} reads the world). The cells and their states come from comparing what earlier
 * versions of the generator wrote with what it writes now ({@code tools/repairs/template_patches.py}), in the
 * template's own coordinates:
 * <ul>
 * <li>{@code cells}: each one's block in every earlier version ({@code before}, one per version, in the order of
 * {@code versions}) and today ({@code after}, the full state, placed rotated as the piece);</li>
 * <li>{@code guards}: cells beside them that no version changed, which must still hold the template's block (a
 * player who built against the wall, or broke the window, has made the inn theirs there);</li>
 * <li>{@code moves}: a container whose place changed ({@code from} → {@code to}), carried with all it holds.</li>
 * </ul>
 * The rule ({@link #decide}): the piece is fixed only if every cell and guard is exactly one earlier version's block
 * (all of them the same version's); if every cell is already today's, it is done; anything else is somebody's
 * change and the piece is left as it is, with the first cell that did not match as the reason. Blocks are compared by id
 * (not by their properties: a door that was opened or a wall that joined its neighbour is still the template's).
 */
public record TemplatePatch(String template, List<String> versions, List<Cell> cells, List<Guard> guards, List<Move> moves) {

	public record Cell(int x, int y, int z, List<String> before, String after) {
	}

	public record Guard(int x, int y, int z, String block) {
	}

	public record Move(int[] from, int[] to) {
	}

	public enum Verdict {
		/** One earlier version's blocks, untouched: it can be fixed. */
		FIX,
		/** Already today's blocks (fixed before, or generated after the fix). */
		DONE,
		/** Something else is there: left as it is. */
		CHANGED
	}

	/** What {@link #decide} found: the verdict, the version that matched (FIX) and, for CHANGED, the first cell that did not. */
	public record Decision(Verdict verdict, @Nullable String version, int @Nullable [] at, @Nullable String expected,
			@Nullable String found) {
		static Decision of(Verdict v) {
			return new Decision(v, null, null, null, null);
		}
	}

	/** Blocks that stand for air in a guard: air itself and what settles on open ground by itself (snow, grass). */
	static final Set<String> AIRLIKE = Set.of("minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:snow",
			"minecraft:short_grass");
	private static final Set<String> TRUE_AIR = Set.of("minecraft:air", "minecraft:cave_air", "minecraft:void_air");

	/** The block id of a state string ({@code minecraft:oak_door[half=lower]} → {@code minecraft:oak_door}). */
	public static String block(String state) {
		int i = state.indexOf('[');
		String b = i < 0 ? state : state.substring(0, i);
		int j = b.indexOf('{');
		b = j < 0 ? b : b.substring(0, j);
		return b.indexOf(':') < 0 ? "minecraft:" + b : b;
	}

	static boolean air(String block) {
		return AIRLIKE.contains(block);
	}

	/**
	 * The verdict for one placed piece. {@code world} gives the block id found at a template cell (local coordinates
	 * {x, y, z}), or null where it cannot be seen (a chunk not loaded): then nothing is decided but CHANGED.
	 */
	public Decision decide(Function<int[], @Nullable String> world) {
		Map<Integer, String> found = new java.util.HashMap<>();
		List<int[]> at = new ArrayList<>();
		for (Cell c : cells) {
			at.add(new int[] {c.x, c.y, c.z});
		}
		for (Guard g : guards) {
			at.add(new int[] {g.x, g.y, g.z});
		}
		for (int i = 0; i < at.size(); i++) {
			String b = world.apply(at.get(i));
			if (b == null) {
				int[] p = at.get(i);
				return new Decision(Verdict.CHANGED, null, p, "?", "not loaded");
			}
			found.put(i, b);
		}
		for (int i = 0; i < guards.size(); i++) {
			Guard g = guards.get(i);
			String b = found.get(cells.size() + i);
			if (!same(g.block, b, true)) {
				return new Decision(Verdict.CHANGED, null, new int[] {g.x, g.y, g.z}, g.block, b);
			}
		}
		boolean done = true;
		for (int i = 0; i < cells.size(); i++) {
			if (!same(block(cells.get(i).after), found.get(i), false)) {
				done = false;
				break;
			}
		}
		if (done) {
			return Decision.of(Verdict.DONE);
		}
		for (int v = 0; v < versions.size(); v++) {
			boolean all = true;
			for (int i = 0; i < cells.size() && all; i++) {
				all = same(block(cells.get(i).before.get(v)), found.get(i), false);
			}
			if (all) {
				return new Decision(Verdict.FIX, versions.get(v), null, null, null);
			}
		}
		// the first cell that is neither today's nor any version's
		for (int i = 0; i < cells.size(); i++) {
			Cell c = cells.get(i);
			String b = found.get(i);
			boolean any = same(block(c.after), b, false);
			for (String s : c.before) {
				any |= same(block(s), b, false);
			}
			if (!any) {
				return new Decision(Verdict.CHANGED, null, new int[] {c.x, c.y, c.z}, block(c.before.get(0)), b);
			}
		}
		Cell c = cells.get(0);              // each cell is some version's, but not all the same version's: mixed
		return new Decision(Verdict.CHANGED, null, new int[] {c.x, c.y, c.z}, block(c.before.get(0)), found.get(0));
	}

	private static boolean same(String expected, @Nullable String found, boolean guard) {
		if (found == null) {
			return false;
		}
		String e = block(expected), f = block(found);
		if (e.equals(f)) {
			return true;
		}
		// a guard's air may have caught snow or grass; a cell that is changed must be air itself (what is there would go)
		return air(e) && air(f) && (guard || TRUE_AIR.contains(f) && TRUE_AIR.contains(e));
	}
}
