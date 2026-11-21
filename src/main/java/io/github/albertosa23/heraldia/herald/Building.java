package io.github.albertosa23.heraldia.herald;

import io.github.albertosa23.heraldia.command.Texts;
import io.github.albertosa23.heraldia.common.Placing;
import io.github.albertosa23.heraldia.roads.BuiltRoads;
import io.github.albertosa23.heraldia.roads.RoadProfile;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.ExperienceOrb;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.DyeColor;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.block.BedBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.Mirror;
import net.minecraft.world.level.block.Rotation;
import net.minecraft.world.level.block.StandingSignBlock;
import net.minecraft.world.level.block.entity.SignBlockEntity;
import net.minecraft.world.level.block.entity.SignText;
import net.minecraft.world.level.block.entity.SignTextSlot;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate;
import net.minecraft.world.phys.AABB;
import org.jspecify.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Building the Herald's House, spread over ticks as the arena's works are (arena/Works): each tick handles a single
 * chunk or a single road. Phases:
 * <ol>
 * <li>load (and generate, if needed) the chunks of the footprint and its margin and their neighbours;</li>
 * <li>level: inside the footprint, air above the template up to the top of the terrain and stone under the foundation
 * down to the ground (over water or a hollow); in the {@link Siting#MARGIN} around it, the terrain blended from the
 * house's ground to the natural height (a slope of dirt and grass, not a cliff);</li>
 * <li>template: the chunk's part of the template, with its villagers, horses and golem; placed dry
 * ({@link io.github.albertosa23.heraldia.common.Placing#dry}), so a pond the piece falls into does not leave its
 * walls, stairs and lanterns waterlogged;</li>
 * <li>beds: every bed set again, both halves (a bed across a chunk border is lost when its chunks are placed one by
 * one);</li>
 * <li>shores: no still water left standing in the air in the footprint or its margin (a pond the template or the blended
 * margin cut open drains, a bigger body gets a bank: {@link Shores}), and in the footprint no water but the template's
 * (what a pond or a lake beside it let run in when the template's edge was placed);</li>
 * <li>roads: from each gate, a dirt path through the protected ring with a signpost at its end; the first gate that
 * meets water within reach gets the dock instead.</li>
 * </ol>
 * When done, loose items in the box are removed, players and other people's animals in the box go to the plaza, the
 * house is saved in the world and starts being protected. Never per tick when nothing is being built (one field check).
 */
final class Building {
	private static final Logger LOGGER = LoggerFactory.getLogger("heraldia");
	/** As in arena/Works: no neighbour updates and no drops. */
	private static final int FLAGS = Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE | Block.UPDATE_SUPPRESS_DROPS;
	/** How deep the foundation may go to reach the ground (a deeper hollow is left as it is). */
	private static final int FOUNDATION = 48;
	/** The dock only if the water starts this close to the wall (its far end stays inside the protected ring). */
	private static final int DOCK_REACH = 32;
	/** How far down the land's own ground is looked for under what stands on it (a cactus is three blocks). */
	private static final int LOOK_DOWN = 4;
	/** The foundation's outermost columns built as masonry (the wall's thickness). */
	private static final int EDGE = 4;
	/** How many of the margin's columns stand on each kind of land (the town's forecourt takes the commonest). */
	private static final int[] census = new int[RoadProfile.Ground.values().length];

	private enum Phase { LOAD, LEVEL, TEMPLATE, BEDS, SHORE, DRY, ROAD }

	private record Step(Phase phase, int cx, int cz, @Nullable String side) {
	}

	private record Work(ServerLevel level, Grounds g, @Nullable ServerPlayer who, boolean newWorld, List<Step> steps,
			StructureTemplate template) {
	}

	private static @Nullable Work actual;
	private static int index, ticks;
	private static long nanos;
	private static boolean docked;
	private static Shores.Settled settled = Shores.NONE;
	private static int cleared, dried;
	/** The template's own water blocks (world positions), kept by the shores' step. */
	private static Set<BlockPos> ownWater = Set.of();

	private Building() {
	}

	static boolean busy() {
		return actual != null;
	}

	/** Starts building {@code g}. False if the template is missing. */
	static boolean start(ServerLevel level, Grounds g, @Nullable ServerPlayer who, boolean newWorld) {
		Identifier id = Identifier.parse(g.plan().template());
		Optional<StructureTemplate> t = level.getStructureTemplateManager().get(id);
		if (t.isEmpty()) {
			LOGGER.error("Heraldia: herald's house: missing template {}", id);
			return false;
		}
		List<Step> steps = new ArrayList<>();
		chunks(steps, Phase.LOAD, g, Siting.MARGIN + 16);
		chunks(steps, Phase.LEVEL, g, Siting.MARGIN);
		chunks(steps, Phase.TEMPLATE, g, 0);
		steps.add(new Step(Phase.BEDS, 0, 0, null));
		chunks(steps, Phase.SHORE, g, Siting.MARGIN);
		chunks(steps, Phase.DRY, g, Siting.MARGIN);     // once every chunk's water is settled: what ran out of it and has no source
		for (String side : g.plan().gates().keySet()) {
			steps.add(new Step(Phase.ROAD, 0, 0, side));
		}
		actual = new Work(level, g, who, newWorld, steps, t.get());
		index = ticks = 0;
		nanos = 0;
		docked = false;
		settled = Shores.NONE;
		cleared = dried = 0;
		java.util.Arrays.fill(census, 0);
		Set<BlockPos> own = new HashSet<>();
		BlockPos origin = new BlockPos(g.ox(), g.oy(), g.oz());
		for (StructureTemplate.StructureBlockInfo info : t.get().filterBlocks(origin, new StructurePlaceSettings(), Blocks.WATER)) {
			own.add(info.pos());
		}
		ownWater = Set.copyOf(own);
		return true;
	}

	private static void chunks(List<Step> steps, Phase phase, Grounds g, int m) {
		for (int cx = (g.ox() - m) >> 4; cx <= (g.maxX() + m) >> 4; cx++) {
			for (int cz = (g.oz() - m) >> 4; cz <= (g.maxZ() + m) >> 4; cz++) {
				steps.add(new Step(phase, cx, cz, null));
			}
		}
	}

	static void tick(MinecraftServer server) {
		Work o = actual;
		if (o == null) {
			return;
		}
		long t0 = System.nanoTime();
		ticks++;
		if (index < o.steps().size()) {
			Step p = o.steps().get(index++);
			switch (p.phase()) {
				case LOAD -> o.level().getChunk(p.cx(), p.cz());
				case LEVEL -> level(o.level(), o.level().getChunk(p.cx(), p.cz()), o.g());
				case TEMPLATE -> template(o.level(), p, o.g(), o.template());
				case BEDS -> beds(o.level(), o.g(), o.template());
				case SHORE -> {
					LevelChunk c = o.level().getChunk(p.cx(), p.cz());
					cleared += Shores.clear(o.level(), c, (x, z) -> o.g().inColumns(x, z), ownWater, o.g().oy(), o.g().maxY());
					settled = settled.plus(Shores.settle(o.level(), c, (x, z) -> outside(o.g(), x, z) <= Siting.MARGIN));
				}
				case DRY -> dried += Shores.dry(o.level(), o.level().getChunk(p.cx(), p.cz()));
				case ROAD -> road(o.level(), o.g(), p.side());
			}
			nanos += System.nanoTime() - t0;
			return;
		}
		actual = null;
		LOGGER.info("Heraldia: herald's house: shores: {} ponds left open drained ({} blocks of water), {} blocks of water banked; {} "
				+ "blocks of water that ran into the footprint taken away; {} blocks of running water left without a source taken away",
				settled.ponds(), settled.drained(), settled.banked(), cleared, dried);
		finish(o);
		nanos += System.nanoTime() - t0;
		LOGGER.info("Heraldia: herald's house: built in {} ticks ({} ms on the server thread, at most a chunk per tick)",
				ticks, nanos / 1_000_000);
	}

	// --- terrain ---

	/** Chebyshev distance from the column to the footprint (0 inside). */
	static int outside(Grounds g, int x, int z) {
		int dx = Math.max(Math.max(g.ox() - x, x - g.maxX()), 0), dz = Math.max(Math.max(g.oz() - z, z - g.maxZ()), 0);
		return Math.max(dx, dz);
	}

	/** Height of the blended margin {@code k} blocks out (1..MARGIN), between the house's ground and the natural one. */
	static int blend(int ground, int natural, int k) {
		return ground + Math.round((natural - ground) * (float) k / (Siting.MARGIN + 1));
	}

	/**
	 * The land's own ground at a column, looking down from {@code y} through what grows or stands on it (a cactus, a dead
	 * bush, snow): the block and its kind, or null if there is none within {@link #LOOK_DOWN} blocks (water, a structure).
	 */
	static @Nullable BlockState land(ServerLevel level, BlockPos.MutableBlockPos pos, int x, int y, int z) {
		for (int k = 0; k <= LOOK_DOWN; k++) {
			BlockState s = level.getBlockState(pos.set(x, y - k, z));
			if (!s.getFluidState().isEmpty()) {
				return null;
			}
			if (BuiltRoads.kind(s) != null) {
				return s;
			}
		}
		return null;
	}

	/** The surface a kind of land shows where the town lays bare ground of its own. */
	static BlockState surface(RoadProfile.Ground kind) {
		return (switch (kind) {
			case MUD -> Blocks.MUD;
			case DIRT -> Blocks.GRASS_BLOCK;
			case RED -> Blocks.RED_SAND;
			case SAND -> Blocks.SAND;
			case STONE -> Blocks.GRAVEL;
		}).defaultBlockState();
	}

	/** The kind of land most of the margin's columns stand on (grassland until the margin has been read). */
	static RoadProfile.Ground dominant() {
		RoadProfile.Ground best = RoadProfile.Ground.DIRT;
		for (RoadProfile.Ground k : RoadProfile.Ground.values()) {
			if (census[k.ordinal()] > census[best.ordinal()]) {
				best = k;
			}
		}
		return best;
	}

	/** The masonry of the foundation under the town's edge, where it shows over lower land: the wall's own stone. */
	static BlockState masonry(int x, int y, int z) {
		int h = (x * 73856093 ^ y * 19349663 ^ z * 83492791) & 0xFFFF;
		int v = h % 20;
		return (v < 3 ? Blocks.MOSSY_STONE_BRICKS : v < 6 ? Blocks.COBBLESTONE : v < 8 ? Blocks.CRACKED_STONE_BRICKS
				: v < 9 ? Blocks.MOSSY_COBBLESTONE : Blocks.STONE_BRICKS).defaultBlockState();
	}

	private static void level(ServerLevel level, LevelChunk chunk, Grounds g) {
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		BlockState air = Blocks.AIR.defaultBlockState(), dirt = Blocks.DIRT.defaultBlockState(),
				grass = Blocks.GRASS_BLOCK.defaultBlockState(), stone = Blocks.STONE.defaultBlockState();
		int m = Siting.MARGIN, ground = g.groundY();
		for (int x = Math.max(g.ox() - m, chunk.getPos().getMinBlockX()); x <= Math.min(g.maxX() + m, chunk.getPos().getMaxBlockX()); x++) {
			for (int z = Math.max(g.oz() - m, chunk.getPos().getMinBlockZ()); z <= Math.min(g.maxZ() + m, chunk.getPos().getMaxBlockZ()); z++) {
				int k = outside(g, x, z);
				int top = chunk.getHeight(Heightmap.Types.WORLD_SURFACE, x & 15, z & 15);
				if (k == 0) {
					for (int y = g.maxY() + 1; y <= top + 1; y++) {
						if (!level.getBlockState(pos.set(x, y, z)).isAir()) {
							level.setBlock(pos, air, FLAGS);
						}
					}
					// under the town's edge the foundation shows wherever the land is lower: masonry there, not bare stone
					boolean edge = Math.min(Math.min(x - g.ox(), g.maxX() - x), Math.min(z - g.oz(), g.maxZ() - z)) < EDGE;
					for (int y = g.oy() - 1; y > g.oy() - FOUNDATION && y > level.getMinY(); y--) {
						BlockState s = level.getBlockState(pos.set(x, y, z));
						if (!s.isAir() && s.getFluidState().isEmpty() && !s.canBeReplaced()) {
							break;
						}
						level.setBlock(pos, edge ? masonry(x, y, z) : stone, FLAGS);
					}
					continue;
				}
				// the natural ground's top block (ChunkAccess.getHeight is the highest block itself, not the air over it)
				int natural = chunk.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x & 15, z & 15);
				if (!level.getBlockState(pos.set(x, natural, z)).getFluidState().isEmpty()) {
					continue;                       // water around the house stays (the dock may need it)
				}
				// the margin keeps the land's own ground (sand on sand, terracotta on badlands): grass only on grassland
				BlockState own = land(level, pos, x, natural, z), surface = grass, fill = dirt;
				if (own != null) {
					RoadProfile.Ground kind = BuiltRoads.kind(own);
					census[kind.ordinal()]++;
					if (kind != RoadProfile.Ground.DIRT) {
						surface = own.is(Blocks.FARMLAND) || own.is(Blocks.DIRT_PATH) ? surface(kind) : own;
						fill = BuiltRoads.fill(kind);
					}
				}
				int target = blend(ground, natural, k);
				for (int y = target + 1; y <= Math.max(top, natural) + 1; y++) {
					if (!level.getBlockState(pos.set(x, y, z)).isAir()) {
						level.setBlock(pos, air, FLAGS);
					}
				}
				for (int y = target; y > Math.min(natural, target) - 1; y--) {
					BlockState s = level.getBlockState(pos.set(x, y, z));
					if (y < target && !s.isAir() && s.getFluidState().isEmpty() && !s.canBeReplaced()) {
						break;
					}
					level.setBlock(pos, y == target ? surface : fill, FLAGS);
				}
			}
		}
	}

	private static void template(ServerLevel level, Step p, Grounds g, StructureTemplate t) {
		BoundingBox bb = new BoundingBox(Math.max(g.ox(), p.cx() << 4), g.oy(), Math.max(g.oz(), p.cz() << 4),
				Math.min(g.maxX(), (p.cx() << 4) + 15), g.maxY(), Math.min(g.maxZ(), (p.cz() << 4) + 15));
		BlockPos origin = new BlockPos(g.ox(), g.oy(), g.oz());
		t.placeInWorld(level, origin, origin, Placing.dry(new StructurePlaceSettings().setBoundingBox(bb).setIgnoreEntities(false)
				.setFinalizeEntities(false)), level.getRandom(), FLAGS);
		exterior(level, g, bb);
		interior(level, g, bb);
	}

	/**
	 * Inside the wall too, the town stands on the land's own ground: off grassland the template's lawn takes the land's
	 * surface (sand in a desert, red sand on badlands, gravel on stone, mud in a swamp), wherever nothing that grows
	 * stands on it. The crops keep their farmland. On sand a flower has no soil to live on: its bed becomes a dry garden
	 * (a dead bush in one bed of three, bare sand in the others). On grassland nothing changes.
	 */
	private static void interior(ServerLevel level, Grounds g, BoundingBox bb) {
		RoadProfile.Ground kind = dominant();
		if (kind == RoadProfile.Ground.DIRT) {
			return;
		}
		boolean dry = kind == RoadProfile.Ground.SAND || kind == RoadProfile.Ground.RED;
		BlockState surface = surface(kind), air = Blocks.AIR.defaultBlockState(), bush = Blocks.DEAD_BUSH.defaultBlockState();
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		int y = g.groundY();
		for (int x = bb.minX(); x <= bb.maxX(); x++) {
			for (int z = bb.minZ(); z <= bb.maxZ(); z++) {
				if (!level.getBlockState(pos.set(x, y, z)).is(Blocks.GRASS_BLOCK)) {
					continue;
				}
				BlockState over = level.getBlockState(pos.set(x, y + 1, z));
				if (over.is(BlockTags.FLOWERS) || over.is(BlockTags.SAPLINGS) || over.is(BlockTags.CROPS)) {
					if (!dry || !over.is(BlockTags.SMALL_FLOWERS)) {
						continue;       // it keeps its soil
					}
					level.setBlock(pos, Math.floorMod(x * 73856093 ^ z * 83492791, 3) == 0 ? bush : air, FLAGS);
				}
				level.setBlock(pos.set(x, y, z), surface, FLAGS);
			}
		}
	}

	/**
	 * Outside the wall (the forecourt) the template's bare grass takes the land's own surface, so the town does not lay a
	 * lawn on a desert: only grass with nothing on it (the gardens' beds keep their soil), and only off grassland.
	 */
	private static void exterior(ServerLevel level, Grounds g, BoundingBox bb) {
		int[] e = g.plan().exterior();
		RoadProfile.Ground kind = dominant();
		if (e == null || kind == RoadProfile.Ground.DIRT) {
			return;
		}
		BlockState surface = surface(kind);
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		int y = g.groundY();
		for (int x = Math.max(bb.minX(), g.ox() + e[0]); x <= Math.min(bb.maxX(), g.ox() + e[2]); x++) {
			for (int z = Math.max(bb.minZ(), g.oz() + e[1]); z <= Math.min(bb.maxZ(), g.oz() + e[3]); z++) {
				if (level.getBlockState(pos.set(x, y, z)).is(Blocks.GRASS_BLOCK) && level.getBlockState(pos.set(x, y + 1, z)).isAir()) {
					level.setBlock(pos.set(x, y, z), surface, FLAGS);
				}
			}
		}
	}

	/**
	 * Every bed of the template again, both halves, once all the chunks are placed. Placing a chunk's part of the
	 * template updates the shape of the blocks at its edge against what is beyond it, and a bed whose other half lies in
	 * the next chunk (air yet) is removed, and then its other half too: which beds those are depends on where the
	 * town falls on the chunk grid (seen on seed terrain: the workshop's two beds were missing and its residents never
	 * had one). Set with {@link #FLAGS} (no shape updates), the two halves stay, and their POIs are registered.
	 */
	private static void beds(ServerLevel level, Grounds g, StructureTemplate t) {
		BlockPos origin = new BlockPos(g.ox(), g.oy(), g.oz());
		StructurePlaceSettings settings = new StructurePlaceSettings();
		int n = 0;
		for (Block b : BuiltInRegistries.BLOCK) {
			if (!(b instanceof BedBlock)) {
				continue;
			}
			for (StructureTemplate.StructureBlockInfo info : t.filterBlocks(origin, settings, b)) {
				if (!level.getBlockState(info.pos()).equals(info.state())) {
					level.setBlock(info.pos(), info.state(), FLAGS);
					n++;
				}
			}
		}
		if (n > 0) {
			LOGGER.info("Heraldia: herald's house: {} bed halves set again (they straddled a chunk border)", n);
		}
	}

	// --- roads and the dock ---

	/** Blocks a road turns into a path (natural ground). */
	private static boolean pathable(BlockState s) {
		return s.is(Blocks.GRASS_BLOCK) || s.is(Blocks.DIRT) || s.is(Blocks.COARSE_DIRT) || s.is(Blocks.PODZOL)
				|| s.is(Blocks.MYCELIUM) || s.is(Blocks.ROOTED_DIRT);
	}

	private static void road(ServerLevel level, Grounds g, String side) {
		Direction d = Direction.byName(side);
		if (d == null) {
			return;
		}
		int[] gate = g.plan().gates().get(side);
		int gx = g.ox() + gate[0], gz = g.oz() + gate[1];
		int[] across = g.plan().road();
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		// with the gates' roads on (SpawnRoads, built next) they are the road: a path here would show as a straight stub
		// beside theirs where they bend, and they put the sign by their own end
		boolean paths = !SpawnRoads.enabled();
		int reached = Grounds.RING;
		for (int step = 1; step <= Grounds.RING; step++) {
			int x0 = gx + d.getStepX() * step, z0 = gz + d.getStepZ() * step;
			// the top block (ChunkAccess.getHeight is the highest block itself); the dock is placed from the block under it
			// (its template has y = 1 at the water's surface) and only where that one is water too, as it always was
			int y = level.getChunk(x0 >> 4, z0 >> 4).getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x0 & 15, z0 & 15) - 1;
			if (!level.getBlockState(pos.set(x0, y, z0)).getFluidState().isEmpty()) {
				if (!docked && step <= DOCK_REACH) {
					docked = dock(level, g, d, x0, y, z0);
				}
				reached = step - 1;
				break;
			}
			for (int a = across[0]; paths && a <= across[1]; a++) {
				int x = x0 + (d.getAxis() == Direction.Axis.Z ? a : 0), z = z0 + (d.getAxis() == Direction.Axis.X ? a : 0);
				// the top block itself (it was the one under it: the path went under the grass and never showed)
				int yy = level.getChunk(x >> 4, z >> 4).getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x & 15, z & 15);
				BlockState s = level.getBlockState(pos.set(x, yy, z));
				if (pathable(s)) {
					BlockState above = level.getBlockState(pos.set(x, yy + 1, z));
					if (above.canBeReplaced() && above.getFluidState().isEmpty()) {
						level.setBlock(pos, Blocks.AIR.defaultBlockState(), FLAGS);
					}
					level.setBlock(pos.set(x, yy, z), Blocks.DIRT_PATH.defaultBlockState(), FLAGS);
				}
			}
		}
		if (paths && reached >= 4) {
			signpost(level, g, d, gx, gz, reached, across);
		}
	}

	/** A signpost by the end of the road, facing whoever comes towards the house. */
	private static void signpost(ServerLevel level, Grounds g, Direction d, int gx, int gz, int step, int[] across) {
		int a = across[1] + 1;
		int x = gx + d.getStepX() * step + (d.getAxis() == Direction.Axis.Z ? a : 0);
		int z = gz + d.getStepZ() * step + (d.getAxis() == Direction.Axis.X ? a : 0);
		// over the top block (ChunkAccess.getHeight is that block: the post stood in the grass and was never placed)
		int y = level.getChunk(x >> 4, z >> 4).getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x & 15, z & 15) + 1;
		BlockPos post = new BlockPos(x, y, z);
		if (!level.getBlockState(post).canBeReplaced() || !level.getBlockState(post.above()).canBeReplaced()
				|| !level.getBlockState(post.below()).isFaceSturdy(level, post.below(), Direction.UP)) {
			return;
		}
		level.setBlock(post, Blocks.CRIMSON_FENCE.defaultBlockState(), Block.UPDATE_ALL);
		int rotation = switch (d) {          // the text faces outwards, along the road
			case SOUTH -> 0;
			case WEST -> 4;
			case NORTH -> 8;
			default -> 12;
		};
		level.setBlock(post.above(), Blocks.CRIMSON_SIGN.defaultBlockState().setValue(StandingSignBlock.ROTATION, rotation),
				Block.UPDATE_ALL);
		if (level.getBlockEntity(post.above()) instanceof SignBlockEntity sign) {
			int blocks = (int) Math.round(Math.hypot(x - g.centerX(), z - g.centerZ()));
			Map<String, String> l = Texts.texts("es_es");
			List<Component> lines = List.of(Texts.t(l, HeraldHouse.K + "camino.cartel"),
					Texts.t(l, HeraldHouse.K + "camino.cartel2", blocks), Component.empty(), Component.empty());
			sign.setText(new SignText(lines, lines, DyeColor.BLACK, false), SignTextSlot.FRONT);
			sign.setWaxed(true);
			sign.setChanged();
		}
	}

	/** Places the dock from the shore at (x, y, z) out over the water along {@code d}. */
	private static boolean dock(ServerLevel level, Grounds g, Direction d, int x, int y, int z) {
		Optional<StructureTemplate> t = level.getStructureTemplateManager().get(Identifier.parse(g.plan().dockTemplate()));
		if (t.isEmpty()) {
			return false;
		}
		Rotation rot = switch (d) {          // the template runs along +z (south)
			case SOUTH -> Rotation.NONE;
			case NORTH -> Rotation.CLOCKWISE_180;
			case WEST -> Rotation.CLOCKWISE_90;
			default -> Rotation.COUNTERCLOCKWISE_90;
		};
		int w = g.plan().dockSize()[0];
		BlockPos near = StructureTemplate.transform(new BlockPos(w / 2, 1, 0), Mirror.NONE, rot, BlockPos.ZERO);
		BlockPos origin = new BlockPos(x, y + 1, z).subtract(near);
		t.get().placeInWorld(level, origin, origin, new StructurePlaceSettings().setRotation(rot), level.getRandom(), Block.UPDATE_ALL);
		LOGGER.info("Heraldia: herald's house: dock at {} {} {} towards the {}", x, y, z, d.getName());
		return true;
	}

	// --- end ---

	private static void finish(Work o) {
		Grounds g = o.g();
		AABB box = new AABB(g.ox(), g.oy(), g.oz(), g.maxX() + 1, g.maxY() + 1, g.maxZ() + 1);
		int[] s = g.spawn();
		for (Entity e : o.level().getEntities((Entity) null, box.inflate(Siting.MARGIN + 4, 16, Siting.MARGIN + 4),
				e -> e instanceof ItemEntity || e instanceof ExperienceOrb)) {
			e.discard();
		}
		for (Entity e : o.level().getEntities((Entity) null, box, e -> !(e instanceof Player))) {
			if (e.entityTags().contains(HeraldHouse.TAG)) {
				continue;                          // the house's own villagers, horses and golem
			}
			if (e instanceof Mob m && !m.isPersistenceRequired()) {
				e.discard();
			} else {
				e.teleportTo(s[0] + 0.5, s[1], s[2] + 0.5);
			}
		}
		for (ServerPlayer p : o.level().players()) {
			if (g.inFootprint(p.getBlockX(), p.getBlockY(), p.getBlockZ())) {
				p.teleportTo(s[0] + 0.5, s[1], s[2] + 0.5);
			}
		}
		HeraldHouse.placed(o.level(), g, o.newWorld());
		SpawnRoads.townPlaced(o.level(), g, o.who());       // its roads out of the gates, the huts and the arena road
		LOGGER.info("Heraldia: herald's house: placed at {} {} {} (box {} {} {} to {} {} {})", g.centerX(), g.groundY(),
				g.centerZ(), g.ox(), g.oy(), g.oz(), g.maxX(), g.maxY(), g.maxZ());
		if (o.who() != null && !o.who().hasDisconnected()) {
			o.who().sendSystemMessage(Texts.t(HeraldHouse.K + "colocada", s[0], s[1], s[2]).withStyle(ChatFormatting.GOLD));
			if (!o.newWorld()) {
				String cmd = "/setworldspawn " + s[0] + " " + s[1] + " " + s[2];
				o.who().sendSystemMessage(Texts.t(HeraldHouse.K + "spawn", Component.literal(cmd).withStyle(st -> st
						.withColor(ChatFormatting.GREEN).withUnderlined(true)
						.withClickEvent(new net.minecraft.network.chat.ClickEvent.SuggestCommand(cmd)))));
			}
		}
	}
}
