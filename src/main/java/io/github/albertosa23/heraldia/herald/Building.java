package io.github.albertosa23.heraldia.herald;

import io.github.albertosa23.heraldia.command.Texts;
import io.github.albertosa23.heraldia.common.Placing;
import io.github.albertosa23.heraldia.roads.BuiltRoads;
import io.github.albertosa23.heraldia.roads.RoadProfile;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import net.minecraft.ChatFormatting;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.util.ProblemReporter;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntitySpawnRequest;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.ExperienceOrb;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.DyeColor;
import net.minecraft.world.level.ChunkPos;
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
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate;
import net.minecraft.world.level.storage.TagValueInput;
import net.minecraft.world.phys.AABB;
import org.jspecify.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Building the Herald's House, spread over ticks as the arena's works are (arena/Works): each tick handles a single
 * chunk, one kind of bed or a chunk's worth of one road. The steps that used to wait for a chunk on the server thread
 * (loading the ground, and the roads out of the gates, which reach land nothing has generated yet) now ask for theirs
 * {@link #AHEAD} steps ahead and let the worker threads read or generate them, as the grounds do in {@link Outskirts};
 * a step whose chunks are not there yet simply does not run this tick. The rest read what the load phase has already
 * loaded, as they always did: asking for a chunk keeps it loaded, and {@link Shores} banks a body of water instead of
 * draining it when it reaches as far as a loaded chunk, so holding more of them would change the town. Phases:
 * <ol>
 * <li>load (and generate, if needed) the chunks of the footprint and its margin and their neighbours;</li>
 * <li>level: inside the footprint, air above the template up to the top of the terrain and stone under the foundation
 * down to the ground (over water or a hollow); in the {@link Siting#MARGIN} around it, the terrain blended from the
 * house's ground to the natural height (a slope of dirt and grass, not a cliff);</li>
 * <li>template: the chunk's part of the template, with its villagers, horses and golem; placed dry
 * ({@link io.github.albertosa23.heraldia.common.Placing#dry}), so a pond the piece falls into does not leave its
 * walls, stairs and lanterns waterlogged;</li>
 * <li>beds: every bed set again, both halves (a bed across a chunk border is lost when its chunks are placed one by
 * one), one kind of bed per step (reading one kind out of the template is a pass over all its blocks);</li>
 * <li>shores: no still water left standing in the air in the footprint or its margin (a pond the template or the blended
 * margin cut open drains, a bigger body gets a bank: {@link Shores}), and in the footprint no water but the template's
 * (what a pond or a lake beside it let run in when the template's edge was placed);</li>
 * <li>roads: from each gate, a dirt path through the protected ring with a signpost at its end, {@link #ROAD_RUN}
 * blocks of it per step; the first gate that meets water within reach gets the dock instead (a step of its own).</li>
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
	/** A step over this many ms is logged on its own, with the thread's own CPU time beside the clock's (as the grounds do). */
	private static final int SLOW_MS = 40;
	/** How many chunks of the steps to come are asked for ahead, so no step has to wait for one on the server thread. */
	private static final int AHEAD = 6;
	/** After this many ticks waiting for the chunks of a step, it runs anyway (a world that will not hand them over). */
	private static final int MAX_WAIT = 400;
	/** How many blocks of one road a single step walks and paves: a chunk's worth of it. */
	static final int ROAD_RUN = 16;
	/** How many of the margin's columns stand on each kind of land (the town's forecourt takes the commonest). */
	private static final int[] census = new int[RoadProfile.Ground.values().length];

	private enum Phase { LOAD, LEVEL, TEMPLATE, BEDS, SHORE, DRY, ROAD, DOCK, SIGN, FINISH }

	/**
	 * One step of the build. For the phases that work a chunk at a time, {@code a} and {@code b} are its chunk's
	 * coordinates; for {@link Phase#BEDS}, {@code a} is which of the game's kinds of bed ({@link Work#bedKinds});
	 * for {@link Phase#ROAD}, the first and the last block of the stretch out of {@code side}'s gate; for
	 * {@link Phase#DOCK}, the column of the shore the dock is laid from.
	 */
	private record Step(Phase phase, int a, int b, @Nullable String side) {
	}

	/** How far one gate's road has got: the last block it reached, and whether water has stopped it short. */
	private static final class Road {
		int reached = Grounds.RING;
		boolean stopped;
	}

	private record Work(ServerLevel level, Grounds g, @Nullable ServerPlayer who, boolean newWorld, List<Step> steps,
			StructureTemplate template, List<Block> bedKinds, Map<String, Road> roads,
			Map<Long, CompletableFuture<?>> loading) {
	}

	private static @Nullable Work actual;
	private static int index, ticks, waited, bedHalves;
	private static long nanos;
	/** The longest step: the clock's time, the server thread's own CPU time in it, and which step it was. */
	private static long worst, worstCpu;
	private static String worstStep = "";
	// per kind of step: how many, the clock's time and the server thread's own CPU time, in all and of the longest one
	private static final int[] kindSteps = new int[Phase.values().length];
	private static final long[] kindNanos = new long[Phase.values().length], kindCpu = new long[Phase.values().length];
	private static final long[] kindWorst = new long[Phase.values().length], kindWorstCpu = new long[Phase.values().length];
	private static boolean docked;
	/** The height of the shore the dock is laid from (its column is the {@link Phase#DOCK} step's own). */
	private static int dockY;
	private static Shores.Settled settled = Shores.NONE;
	private static int cleared, dried;
	/** The template's own water blocks (world positions), kept by the shores' step. */
	private static Set<BlockPos> ownWater = Set.of();

	private Building() {
	}

	static boolean busy() {
		return actual != null;
	}

	/**
	 * Two villagers made and thrown away, when the server starts. The first villager a server ever makes costs the server
	 * thread 76 ms, and the first one read from a tag 11 ms more (measured one step at a time on the development
	 * container, 4 cores; a second villager costs 1 ms): the classes of the brain and of every behaviour in it are loaded,
	 * the brain is built, and the save format's codecs are read for the first time. Whichever {@link Phase#TEMPLATE} step
	 * placed the town's first villager paid all of that on top of its own work: that chunk's step was the slowest of the
	 * build in four runs of four, 87-120 ms where the other 63 chunks took 26 ms, and a step may take 100 ms. Paid here
	 * instead, in a tick nobody is playing through, the slowest step of the build is 64-73 ms (three passes) and which
	 * chunk it falls on moves from run to run, most of it the collector and not this thread's own work.
	 * <p>
	 * Both are made the way {@code StructureTemplate.placeInWorld} makes the town's: one from nothing, one from a tag,
	 * which is the path every entity of a template takes. Neither is ever added to the world, so nothing is left behind
	 * and no other mod's entity hook sees them (adding and discarding one as well was measured at 2 ms more: not worth
	 * the visit). Every other kind of entity the town holds -- horse, donkey, item frame, cat, iron golem, chicken,
	 * sheep, armour stand -- costs 0-2 ms the first time, so none of them is warmed up; one added later that did cost
	 * would show up as a slow step in the build's own report, not in silence.
	 */
	static void warmUp(ServerLevel level) {
		long t0 = System.nanoTime();
		if (EntityTypes.VILLAGER.create(level, EntitySpawnReason.STRUCTURE) == null) {
			return;
		}
		CompoundTag tag = new CompoundTag();
		tag.putString("id", EntityType.getKey(EntityTypes.VILLAGER).toString());
		EntityType.create(TagValueInput.create(ProblemReporter.DISCARDING, level.registryAccess(), tag), level,
				new EntitySpawnRequest(EntitySpawnReason.STRUCTURE, false));
		LOGGER.info("Heraldia: herald's house: a villager's brain and the save format read once, and thrown away, in {} ms (they would "
				+ "otherwise fall on whichever step of a town's build placed the first villager)", (System.nanoTime() - t0) / 1_000_000);
	}

	/** Starts building {@code g}. False if the template is missing. */
	static boolean start(ServerLevel level, Grounds g, @Nullable ServerPlayer who, boolean newWorld) {
		Identifier id = Identifier.parse(g.plan().template());
		Optional<StructureTemplate> t = level.getStructureTemplateManager().get(id);
		if (t.isEmpty()) {
			LOGGER.error("Heraldia: herald's house: missing template {}", id);
			return false;
		}
		long c0 = cpuNanos(), t0 = System.nanoTime();
		List<Step> steps = new ArrayList<>();
		chunks(steps, Phase.LOAD, g, Siting.MARGIN + 16);
		chunks(steps, Phase.LEVEL, g, Siting.MARGIN);
		chunks(steps, Phase.TEMPLATE, g, 0);
		// one step per kind of bed the game knows, whatever the town holds: both halves of a bed are the same block, so
		// each step still sets whole beds, and reading one kind out of the template is one pass over all its blocks
		List<Block> bedKinds = new ArrayList<>();
		for (Block b : BuiltInRegistries.BLOCK) {
			if (b instanceof BedBlock) {
				bedKinds.add(b);
			}
		}
		for (int i = 0; i < bedKinds.size(); i++) {
			steps.add(new Step(Phase.BEDS, i, 0, null));
		}
		chunks(steps, Phase.SHORE, g, Siting.MARGIN);
		chunks(steps, Phase.DRY, g, Siting.MARGIN);     // once every chunk's water is settled: what ran out of it and has no source
		Map<String, Road> roads = new HashMap<>();
		for (String side : g.plan().gates().keySet()) {
			roads.put(side, new Road());
			for (int from = 1; from <= Grounds.RING; from += ROAD_RUN) {
				steps.add(new Step(Phase.ROAD, from, Math.min(from + ROAD_RUN - 1, Grounds.RING), side));
			}
			steps.add(new Step(Phase.SIGN, 0, 0, side));
		}
		actual = new Work(level, g, who, newWorld, steps, t.get(), List.copyOf(bedKinds), roads, new HashMap<>());
		index = ticks = waited = bedHalves = 0;
		nanos = worst = worstCpu = 0;
		worstStep = "";
		java.util.Arrays.fill(kindSteps, 0);
		java.util.Arrays.fill(kindNanos, 0);
		java.util.Arrays.fill(kindCpu, 0);
		java.util.Arrays.fill(kindWorst, 0);
		java.util.Arrays.fill(kindWorstCpu, 0);
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
		long ns = System.nanoTime() - t0, cpu = c0 < 0 ? -1 : cpuNanos() - c0;
		LOGGER.info("Heraldia: herald's house: {} steps planned in {} ms ({} of them the server thread's own work), {} blocks of water "
				+ "of the template's own", steps.size(), ns / 1_000_000, cpu < 0 ? "? (not measured here)" : cpu / 1_000_000 + " ms",
				ownWater.size());
		return true;
	}

	/** Every chunk of the footprint and {@code m} blocks around it, one step each. */
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
		ticks++;
		if (index < o.steps().size()) {
			Step p = o.steps().get(index);
			prefetch(o);
			if (!ready(o, p)) {
				return;                            // its chunks are being read or generated off the server thread
			}
			waited = 0;
			index++;
			long c0 = cpuNanos(), t0 = System.nanoTime();
			try {
				step(o, p);
			} catch (RuntimeException e) {
				LOGGER.error("Heraldia: herald's house: step {} failed", name(p), e);
			}
			measure(p, System.nanoTime() - t0, c0 < 0 ? -1 : cpuNanos() - c0);
			return;
		}
		long c0 = cpuNanos(), t0 = System.nanoTime();
		actual = null;
		if (bedHalves > 0) {
			LOGGER.info("Heraldia: herald's house: {} bed halves set again (they straddled a chunk border)", bedHalves);
		}
		LOGGER.info("Heraldia: herald's house: shores: {} ponds left open drained ({} blocks of water), {} blocks of water banked; {} "
				+ "blocks of water that ran into the footprint taken away; {} blocks of running water left without a source taken away",
				settled.ponds(), settled.drained(), settled.banked(), cleared, dried);
		finish(o);
		measure(new Step(Phase.FINISH, 0, 0, null), System.nanoTime() - t0, c0 < 0 ? -1 : cpuNanos() - c0);
		LOGGER.info("Heraldia: herald's house: by kind of step: {}", byKind());
		LOGGER.info("Heraldia: herald's house: built in {} ticks ({} ms on the server thread, the slowest step {} ms, {} of it the "
				+ "server thread's own work: {}; one step a tick)", ticks, nanos / 1_000_000, worst / 1_000_000,
				worstCpu < 0 ? "? (not measured here)" : worstCpu / 1_000_000 + " ms", worstStep);
	}

	private static void step(Work o, Step p) {
		switch (p.phase()) {
			case LOAD -> { }                           // nothing: its chunk is there, generated off the server thread
			case LEVEL -> level(o.level(), chunk(o, p), o.g());
			case TEMPLATE -> template(o.level(), p, o.g(), o.template());
			case BEDS -> beds(o, p.a());
			case SHORE -> {
				LevelChunk c = chunk(o, p);
				cleared += Shores.clear(o.level(), c, (x, z) -> o.g().inColumns(x, z), ownWater, o.g().oy(), o.g().maxY());
				settled = settled.plus(Shores.settle(o.level(), c, (x, z) -> outside(o.g(), x, z) <= Siting.MARGIN));
			}
			case DRY -> dried += Shores.dry(o.level(), chunk(o, p));
			case ROAD -> road(o, p);
			case DOCK -> {
				Direction d = Direction.byName(p.side());
				if (d != null) {
					docked = dock(o.level(), o.g(), d, p.a(), dockY, p.b());
				}
			}
			case SIGN -> sign(o, p.side());
			case FINISH -> { }
		}
	}

	private static LevelChunk chunk(Work o, Step p) {
		return o.level().getChunk(p.a(), p.b());
	}

	// --- the chunks every step reads, asked for ahead (never waited for on the server thread) ---

	/**
	 * The chunks a step must have loaded before it runs, as packed {@link ChunkPos}. Only the steps that used to wait for
	 * one on the server thread: the rest read what the {@link Phase#LOAD} phase loaded, as they always did.
	 */
	private static void need(Work o, Step p, List<Long> out) {
		switch (p.phase()) {
			case LOAD -> out.add(ChunkPos.pack(p.a(), p.b()));
			case ROAD -> roadChunks(o.g(), p.side(), p.a(), p.b(), out);
			case SIGN -> {
				Road r = o.roads().get(p.side());
				if (r != null) {
					roadChunks(o.g(), p.side(), r.reached, r.reached, out);
				}
			}
			case DOCK -> {
				int[] size = o.g().plan().dockSize();
				int r = Math.max(size[0], size[2]) + 1;         // whichever way the dock is turned, and its waterline
				box(out, p.a() - r, p.b() - r, p.a() + r, p.b() + r);
			}
			// LEVEL, TEMPLATE, BEDS, SHORE and DRY read chunks the LOAD phase has already loaded, and took 2-48 ms: they
			// are left as they were. Asking for a chunk keeps it loaded, and which chunks are loaded decides what
			// Shores makes of a body of water (Shores.pond gives up at an unloaded chunk and the water is banked
			// instead of drained), so holding more of them than the build used to would change the town itself.
			default -> { }
		}
	}

	/**
	 * The chunks of one road's columns between {@code from} and {@code to} blocks out of the gate, its verges and the
	 * signpost's own column included. Pinned for the four gates by {@code HeraldHouseLogicTest}.
	 */
	static void roadChunks(Grounds g, @Nullable String side, int from, int to, List<Long> out) {
		Direction d = side == null ? null : Direction.byName(side);
		int[] gate = d == null ? null : g.plan().gates().get(side);
		if (d == null || gate == null) {
			return;
		}
		int[] across = g.plan().road();
		int a0 = Math.min(across[0], 0), a1 = Math.max(across[1] + 1, 0);      // + the signpost's own column
		int gx = g.ox() + gate[0], gz = g.oz() + gate[1];
		int x0 = gx + d.getStepX() * from, z0 = gz + d.getStepZ() * from;
		int x1 = gx + d.getStepX() * to, z1 = gz + d.getStepZ() * to;
		boolean sideways = d.getAxis() == Direction.Axis.Z;         // a road along z is widened along x, and the other way
		box(out, Math.min(x0, x1) + (sideways ? a0 : 0), Math.min(z0, z1) + (sideways ? 0 : a0),
				Math.max(x0, x1) + (sideways ? a1 : 0), Math.max(z0, z1) + (sideways ? 0 : a1));
	}

	static void box(List<Long> out, int x0, int z0, int x1, int z1) {
		for (int cx = x0 >> 4; cx <= x1 >> 4; cx++) {
			for (int cz = z0 >> 4; cz <= z1 >> 4; cz++) {
				out.add(ChunkPos.pack(cx, cz));
			}
		}
	}

	/** Asks for a chunk without waiting for it (read or generated on the worker threads), as the grounds' build does. */
	private static void ask(Work o, int cx, int cz) {
		if (o.level().getChunkSource().getChunkNow(cx, cz) != null) {
			return;
		}
		long key = ChunkPos.pack(cx, cz);
		CompletableFuture<?> f = o.loading().get(key);
		if (f == null || f.isDone()) {             // never asked for, or loaded once and unloaded since: asked for again
			o.loading().put(key, o.level().getChunkSource().getChunkFuture(cx, cz, ChunkStatus.FULL, true));
		}
	}

	/** Whether the chunks a step reads are loaded (after {@link #MAX_WAIT} ticks of waiting, it runs anyway). */
	private static boolean ready(Work o, Step p) {
		List<Long> keys = new ArrayList<>();
		need(o, p, keys);
		boolean ok = true;
		for (long key : keys) {
			int cx = ChunkPos.getX(key), cz = ChunkPos.getZ(key);
			if (o.level().getChunkSource().getChunkNow(cx, cz) == null) {
				ask(o, cx, cz);
				ok = false;
			}
		}
		return ok || waited++ >= MAX_WAIT;
	}

	/**
	 * The chunks of the next {@link #AHEAD} steps, asked for ahead: by the time a step runs, its own are already there.
	 * Only those steps: looking further (until some number of chunks had been found) reached the roads' steps while the
	 * shores were being settled and held the whole ring loaded, and {@link Shores} banks a body of water instead of
	 * draining it when it reaches as far as a loaded chunk, so the town itself came out different.
	 */
	private static void prefetch(Work o) {
		List<Long> keys = new ArrayList<>();
		for (int i = index; i < o.steps().size() && i < index + AHEAD; i++) {
			need(o, o.steps().get(i), keys);
		}
		for (long key : keys) {
			ask(o, ChunkPos.getX(key), ChunkPos.getZ(key));
		}
	}

	private static final ThreadMXBean THREADS = ManagementFactory.getThreadMXBean();

	/** The CPU time this thread has used, in nanoseconds (-1 where the JVM does not measure it): work, not waiting. */
	private static long cpuNanos() {
		try {
			return THREADS.isCurrentThreadCpuTimeSupported() ? THREADS.getCurrentThreadCpuTime() : -1;
		} catch (UnsupportedOperationException e) {
			return -1;
		}
	}

	/** Keeps what a step cost, in all and for its kind, and logs it on its own when it took more than {@link #SLOW_MS}. */
	private static void measure(Step p, long ns, long cpu) {
		nanos += ns;
		int k = p.phase().ordinal();
		kindSteps[k]++;
		kindNanos[k] += ns;
		kindCpu[k] += Math.max(cpu, 0);
		if (ns > kindWorst[k]) {
			kindWorst[k] = ns;
			kindWorstCpu[k] = cpu;
		}
		if (ns > worst) {
			worst = ns;
			worstCpu = cpu;
			worstStep = name(p);
		}
		if (ns > SLOW_MS * 1_000_000L) {
			// The clock's time counts whatever stopped the process during the step (a collector's pause, the machine giving the
			// CPU to something else, a chunk waited for); the thread's own CPU time counts only its work. Far apart: the step
			// waited, it did not work. Logged at once, so the line's own time says when.
			LOGGER.info("Heraldia: herald's house: a slow step: {}: {} ms by the clock, {} of them the server thread's own work",
					name(p), ns / 1_000_000, cpu < 0 ? "? (not measured here)" : cpu / 1_000_000 + " ms");
		}
	}

	private static String name(Step p) {
		return (p.side() == null ? p.phase().toString() : p.phase() + " " + p.side()) + " " + p.a() + " " + p.b();
	}

	/** "LOAD 144 steps 940 ms (48 ms of work), the longest 935 ms (45 ms of work); ..." of the kinds that ran. */
	private static String byKind() {
		StringBuilder sb = new StringBuilder();
		for (Phase k : Phase.values()) {
			int i = k.ordinal();
			if (kindSteps[i] == 0) {
				continue;
			}
			sb.append(sb.isEmpty() ? "" : "; ").append(k).append(' ').append(kindSteps[i]).append(" steps ")
					.append(kindNanos[i] / 1_000_000).append(" ms (").append(kindCpu[i] / 1_000_000).append(" ms of work), the longest ")
					.append(kindWorst[i] / 1_000_000).append(" ms (")
					.append(kindWorstCpu[i] < 0 ? "?" : String.valueOf(kindWorstCpu[i] / 1_000_000)).append(" ms of work)");
		}
		return sb.toString();
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

	/**
	 * One chunk's part of the template. A chunk a step on purpose, neither smaller nor larger: {@code placeInWorld} walks
	 * the whole template on every call whatever its bounding box holds (557,056 entries for this one, 20.6 ms of the server
	 * thread at the median and 47.9 at worst, measured with a box that holds nothing), so smaller boxes pay that walk more
	 * often -- four 8 x 8 cells per chunk took the phase from 1.9 to 6.2 s and still left an 86 ms step -- and larger ones
	 * stop the shape-update pass running along the chunk borders inside the town, which can move a block (docs/LESSONS.md).
	 */
	private static void template(ServerLevel level, Step p, Grounds g, StructureTemplate t) {
		BoundingBox bb = new BoundingBox(Math.max(g.ox(), p.a() << 4), g.oy(), Math.max(g.oz(), p.b() << 4),
				Math.min(g.maxX(), (p.a() << 4) + 15), g.maxY(), Math.min(g.maxZ(), (p.b() << 4) + 15));
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
	 * One kind of the game's beds set again from the template, both halves, once all the chunks are placed. Placing a
	 * chunk's part of the template updates the shape of the blocks at its edge against what is beyond it, and a bed whose
	 * other half lies in the next chunk (air yet) is removed, and then its other half too: which beds those are depends
	 * on where the town falls on the chunk grid (seen on seed terrain: the workshop's two beds were missing and its
	 * residents never had one). Set with {@link #FLAGS} (no shape updates), the two halves stay, and their POIs are
	 * registered.
	 * <p>
	 * One kind per step, not all of them in one: reading a kind out of the template is a pass over every block it holds,
	 * and the whole lot in a single step took 164-200 ms of the server thread (the owner's cap is 100). Both halves of a
	 * bed are the same block, so a step still sets whole beds.
	 */
	private static void beds(Work o, int kind) {
		Grounds g = o.g();
		BlockPos origin = new BlockPos(g.ox(), g.oy(), g.oz());
		for (StructureTemplate.StructureBlockInfo info : o.template().filterBlocks(origin, new StructurePlaceSettings(),
				o.bedKinds().get(kind))) {
			if (!o.level().getBlockState(info.pos()).equals(info.state())) {
				o.level().setBlock(info.pos(), info.state(), FLAGS);
				bedHalves++;
			}
		}
	}

	// --- roads and the dock ---

	/** Blocks a road turns into a path (natural ground). */
	private static boolean pathable(BlockState s) {
		return s.is(Blocks.GRASS_BLOCK) || s.is(Blocks.DIRT) || s.is(Blocks.COARSE_DIRT) || s.is(Blocks.PODZOL)
				|| s.is(Blocks.MYCELIUM) || s.is(Blocks.ROOTED_DIRT);
	}

	/**
	 * A stretch of one gate's road: from {@code p.a()} to {@code p.b()} blocks out of the gate, at most {@link #ROAD_RUN}
	 * of them, so a step never walks the whole ring (its chunks are asked for ahead, and reaching them all in one step
	 * cost 168-233 ms of the server thread, nearly all of it waiting for land that was not generated yet). Water stops
	 * the road for good: its {@link Road#reached} is kept and the stretches left do nothing.
	 */
	private static void road(Work o, Step p) {
		ServerLevel level = o.level();
		Grounds g = o.g();
		String side = p.side();
		Direction d = side == null ? null : Direction.byName(side);
		Road r = side == null ? null : o.roads().get(side);
		if (d == null || r == null || r.stopped) {
			return;
		}
		int[] gate = g.plan().gates().get(side);
		int gx = g.ox() + gate[0], gz = g.oz() + gate[1];
		int[] across = g.plan().road();
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		// with the gates' roads on (SpawnRoads, built next) they are the road: a path here would show as a straight stub
		// beside theirs where they bend, and they put the sign by their own end
		boolean paths = !SpawnRoads.enabled();
		for (int step = p.a(); step <= p.b(); step++) {
			int x0 = gx + d.getStepX() * step, z0 = gz + d.getStepZ() * step;
			// the top block (ChunkAccess.getHeight is the highest block itself); the dock is placed from the block under it
			// (its template has y = 1 at the water's surface) and only where that one is water too, as it always was
			int y = level.getChunk(x0 >> 4, z0 >> 4).getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x0 & 15, z0 & 15) - 1;
			if (!level.getBlockState(pos.set(x0, y, z0)).getFluidState().isEmpty()) {
				if (!docked && step <= DOCK_REACH) {
					dockY = y;                 // its own step: the dock's chunks are asked for before it is laid
					o.steps().add(index, new Step(Phase.DOCK, x0, z0, side));
				}
				r.reached = step - 1;
				r.stopped = true;
				return;
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
	}

	/** The signpost by the end of one gate's road, once its stretches are done (nothing where the roads are built). */
	private static void sign(Work o, @Nullable String side) {
		Direction d = side == null ? null : Direction.byName(side);
		Road r = side == null ? null : o.roads().get(side);
		if (d == null || r == null || SpawnRoads.enabled() || r.reached < 4) {
			return;
		}
		int[] gate = o.g().plan().gates().get(side);
		signpost(o.level(), o.g(), d, o.g().ox() + gate[0], o.g().oz() + gate[1], r.reached, o.g().plan().road());
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
