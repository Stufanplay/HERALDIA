package io.github.albertosa23.heraldia.common;

import net.minecraft.world.level.levelgen.structure.templatesystem.LiquidSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;

/**
 * How the mod's own builds put a template into the world where water already stands.
 * <p>
 * {@code StructureTemplate.placeInWorld} keeps the water that was in a cell by default
 * ({@link LiquidSettings#APPLY_WATERLOGGING}): after setting the template's block it reads the fluid that was there and,
 * if the block can hold water (a wall, a stair, a slab, a fence, a lantern, a trapdoor...), puts the water back inside
 * it, {@code waterlogged=true}, whatever the template says; and the blocks whose water was not a source are then
 * waterlogged again from any source next to them, so it spreads along the piece's edge. A build that places a piece
 * inside a pond therefore ends up with its own walls full of water.
 * <p>
 * And it does not do it quietly. {@code SimpleWaterloggedBlock.placeLiquid} sets the block with
 * {@code setBlockAndUpdate} (neighbour updates and all, which a build spread over ticks takes care never to do) and
 * calls {@code scheduleTick} for the fluid: the wall starts pouring there and then, while the town is still being
 * built. herald/Shores takes that water away afterwards, so the finished town
 * looks dry — and what is left is the waterlogged blocks themselves, which no measure of water counts and which pour
 * again at the first block update beside them.
 * <p>
 * Our builds place a piece on ground they have already shaped, and the water they want is the water their template
 * carries: {@link #dry} says so. The template's own water blocks are placed exactly as before (the setting only governs
 * the world's water, not the template's; in 26.3 the fluid of a cell is only read, and the waterlogging pass only run,
 * when {@code shouldApplyWaterlogging()}), so this takes work away and never adds any.
 * <p>
 * A piece that is meant to stand in the water keeps the default: the dock's posts (herald/Building.dock) go down into
 * the water and are waterlogged on purpose.
 */
public final class Placing {
	private Placing() {
	}

	/** {@code settings} with the water already in a cell left out: no block of the piece ends up waterlogged by it. */
	public static StructurePlaceSettings dry(StructurePlaceSettings settings) {
		return settings.setLiquidSettings(LiquidSettings.IGNORE_WATERLOGGING);
	}
}
