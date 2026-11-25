package io.github.albertosa23.heraldia.update;

import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.function.LongFunction;
import net.minecraft.core.BlockPos;

/**
 * Running water with no source (pure logic over what each block is, so it is tested without the game; {@code GenerationMend}
 * reads the world). In a world that keeps its fluid ticks, running water with no source never lasts: each block's tick
 * finds nothing feeding it and it dries, and its neighbours after it. It lasts only where the water was put or left
 * without a block update, so it never got a tick: what the Herald's House did before the running-water fix (its build
 * drained a pond and cleared its footprint without updates, and what had already run down the hillside stayed). A
 * player's water always has its tick, so this cannot be a player's.
 * <p>
 * The rule is {@code herald/Shores.dry}'s: a running block is fed if a source (or a waterlogged block) is reached
 * from it through water going sideways or up (water never runs up, so whatever feeds it lies that way); what cannot be
 * seen (a chunk not loaded) or a stream longer than {@link #STREAM} counts as fed. What ran on from an unfed block
 * (sideways or down) is looked at in turn. Nothing is removed here: the caller takes the unfed blocks away, which is what
 * their ticks would have done (no source: each block dries, and so does what ran on from it).
 */
public final class Streams {
	/** What a block is, for this rule. */
	public enum Water { SOURCE, RUNNING, OTHER, UNSEEN }

	/** The most blocks one stream is followed for (Shores.STREAM). */
	public static final int STREAM = 8192;
	private static final int[][] UPSTREAM = {{0, 0, -1}, {0, 0, 1}, {1, 0, 0}, {-1, 0, 0}, {0, 1, 0}};
	private static final int[][] DOWNSTREAM = {{0, 0, -1}, {0, 0, 1}, {1, 0, 0}, {-1, 0, 0}, {0, -1, 0}};

	private Streams() {
	}

	/**
	 * The unfed running blocks reached from {@code seeds} (positions as {@link BlockPos#asLong}), in the order found.
	 * {@code at} says what each position is.
	 */
	public static Set<Long> unfed(Iterable<Long> seeds, LongFunction<Water> at) {
		ArrayDeque<Long> starts = new ArrayDeque<>();
		seeds.forEach(starts::add);
		Set<Long> fed = new HashSet<>(), out = new LinkedHashSet<>();
		while (!starts.isEmpty()) {
			long start = starts.poll();
			if (fed.contains(start) || out.contains(start) || at.apply(start) != Water.RUNNING) {
				continue;
			}
			Set<Long> seen = new HashSet<>();
			ArrayDeque<Long> todo = new ArrayDeque<>();
			seen.add(start);
			todo.add(start);
			boolean source = false;
			while (!todo.isEmpty() && !source) {
				long p = todo.poll();
				for (int[] d : UPSTREAM) {
					long o = BlockPos.offset(p, d[0], d[1], d[2]);
					if (seen.contains(o) || out.contains(o)) {
						continue;              // an unfed block upstream feeds nothing
					}
					Water w = at.apply(o);
					if (w == Water.SOURCE || w == Water.UNSEEN || fed.contains(o) || seen.size() >= STREAM) {
						source = true;
						break;
					}
					if (w == Water.RUNNING) {
						seen.add(o);
						todo.add(o);
					}
				}
			}
			if (source) {
				fed.addAll(seen);
				continue;
			}
			out.addAll(seen);
			for (long p : seen) {                // what ran on from it has lost its water too
				for (int[] d : DOWNSTREAM) {
					long o = BlockPos.offset(p, d[0], d[1], d[2]);
					if (!out.contains(o) && at.apply(o) == Water.RUNNING) {
						starts.add(o);
					}
				}
			}
		}
		return out;
	}
}
