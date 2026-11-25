package io.github.albertosa23.heraldia.herald;

import java.util.function.BiPredicate;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.chunk.LevelChunk;

/**
 * What /heraldia update mend (update/GenerationMend) needs of the Herald's House's shores, so an old town is settled by
 * the very code a town built today uses, never a copy of it: {@link Shores#standing} to count the still water standing in
 * the air and {@link Shores#settle} to drain or bank it. Nothing else: no behaviour of its own.
 */
public final class Repairs {
	private Repairs() {
	}

	/** How many still water blocks of one chunk's columns ({@code in}) stand in the air. Changes nothing. */
	public static int standing(ServerLevel level, LevelChunk chunk, BiPredicate<Integer, Integer> in) {
		return Shores.standing(level, chunk, in).size();
	}

	/** Settles them as the town's build does: {ponds drained, their blocks, water blocks banked}. */
	public static int[] settle(ServerLevel level, LevelChunk chunk, BiPredicate<Integer, Integer> in) {
		Shores.Settled s = Shores.settle(level, chunk, in);
		return new int[] {s.ponds(), s.drained(), s.banked()};
	}
}
