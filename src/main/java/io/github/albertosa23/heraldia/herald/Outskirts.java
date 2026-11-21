package io.github.albertosa23.heraldia.herald;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.brigadier.context.CommandContext;
import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import io.github.albertosa23.heraldia.Heraldia;
import io.github.albertosa23.heraldia.arena.Arena;
import io.github.albertosa23.heraldia.command.Texts;
import io.github.albertosa23.heraldia.common.Placing;
import io.github.albertosa23.heraldia.config.HeraldiaConfig;
import io.github.albertosa23.heraldia.roads.BuiltRoads;
import io.github.albertosa23.heraldia.roads.RoadLayout;
import io.github.albertosa23.heraldia.roads.RoadProfile;
import io.github.albertosa23.heraldia.roads.SpawnRoadLayout;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import net.fabricmc.fabric.api.attachment.v1.AttachmentRegistry;
import net.fabricmc.fabric.api.attachment.v1.AttachmentType;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.Registries;
import net.minecraft.data.worldgen.features.TreeFeatures;
import net.minecraft.resources.Identifier;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.BlockTags;
import net.minecraft.util.RandomSource;
import net.minecraft.util.Util;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.FallingBlock;
import net.minecraft.world.level.block.FlowerBedBlock;
import net.minecraft.world.level.block.Rotation;
import net.minecraft.world.level.block.entity.RandomizableContainerBlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate;
import org.jspecify.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The Herald's House grounds (casa_heraldo.alrededores.*; the houses and numbers in tools/gen/herald_grounds.py): the
 * protected ring around the town ({@link Grounds#RING} blocks on each side) levelled into gentle, walkable ground that
 * blends into the natural terrain at its edge, with a few cherry trees and a few small houses, each with a loot chest
 * and no villager. BUILT, not generated, in chunks that already exist, spread over ticks as the town and its roads are.
 * <ul>
 * <li>When: right after the town is placed, once its roads are done (or at once with the roads off): the roads own
 * their columns, and the ground is shaped round them, never the other way. In a world whose town came before this
 * feature, only with /heraldia herald grounds (an operator): a town already standing is never touched on its own. What
 * was built is saved ({@link Saved}, a new attachment): never built twice.</li>
 * <li>Steps (a few per tick, within {@link #BUDGET_MS} ms; a slow one gives the server {@link #REST} ticks): the arena
 * road's plan if there is an arena (off the server thread), each chunk read ({@link #survey}: the natural ground's
 * height under trees and plants, and what must not move), the plan ({@link OutskirtsPlan}, off the server thread),
 * each chunk levelled ({@link #level}: each terrace's riser faced with a retaining wall, {@link #wall}) and its trees
 * felled whole, each chunk's shores settled ({@link Shores}: no still water left standing in the air), each house, each
 * cherry tree, and each chunk looked at again ({@link #audit}: the ramps of one-block steps, the steps left bare, the
 * loose columns and holes, the water standing in the air, the chests' loot, the doors, the trees; in the log, which the
 * server test reads). The chunks are asked for ahead ({@link #AHEAD}) so the server thread never waits
 * for one to be generated.</li>
 * <li>What it keeps: the roads that were built, their huts, lamps and signs, structures, players' blocks, water, the
 * town. Houses: the roads never touch them ({@link #inHouse}, through SpawnRoads.skip) and the arena road goes round
 * their chunks as it goes round any structure ({@link #houseChunks}).</li>
 * </ul>
 * No per-tick work when nothing is being built (one field check, from {@link HeraldHouse}'s tick).
 */
public final class Outskirts {
	private static final Logger LOGGER = LoggerFactory.getLogger("heraldia");
	public static final String ENABLED = "casa_heraldo.alrededores.activado", HOUSES = "casa_heraldo.alrededores.casas";
	static final String K = HeraldHouse.K + "alrededores.";
	static final int BUDGET_MS = 8, SLOW_MS = 40, REST = 2, AHEAD = 6, MAX_WAIT = 400, MAX_OBJECT = 24, FIRE_REACH = 6;
	/** The outermost rows, where the ground meets the natural one beyond (which keeps its own steps): counted apart. */
	static final int EDGE_BLEND = 4;
	/** A narrow pit's lid: this many blocks of fill under its surface (the air under it stays), over a pit at most LID_MAX deep. */
	static final int LID = 3, LID_MAX = 160;

	private static @Nullable Blueprint blueprint;
	private static @Nullable Work work;
	private static @Nullable Pending pending;
	/** The plots (world columns, inclusive) of the houses this world has, or null until read. */
	private static volatile @Nullable List<int[]> built;

	private Outskirts() {
	}

	// --- what the generator wrote (heraldia/alrededores_casa.json) ---

	record House(String name, String template, int[] size) {
	}

	/** A slot: its house, rotation, template origin, plot, walls and door (relative to the town template's corner). */
	record Slot(String name, int group, String house, Rotation rotation, int[] origin, int[] plot, int[] walls, int[] door, String facing) {
	}

	record Blueprint(OutskirtsPlan.Params params, int ring, int defaultHouses, int cherries, Map<String, House> houses, List<Slot> slots,
			List<int[]> sites) {
		static Blueprint read(JsonObject o) {
			Map<String, House> houses = new java.util.LinkedHashMap<>();
			for (JsonElement e : o.getAsJsonArray("casas")) {
				JsonObject c = e.getAsJsonObject();
				houses.put(c.get("nombre").getAsString(), new House(c.get("nombre").getAsString(), c.get("plantilla").getAsString(),
						ints(c.getAsJsonArray("tamano"))));
			}
			List<Slot> slots = new ArrayList<>();
			for (JsonElement e : o.getAsJsonArray("huecos")) {
				JsonObject s = e.getAsJsonObject();
				Rotation rot = switch (s.get("giro").getAsString()) {
					case "clockwise_90" -> Rotation.CLOCKWISE_90;
					case "clockwise_180" -> Rotation.CLOCKWISE_180;
					case "counterclockwise_90" -> Rotation.COUNTERCLOCKWISE_90;
					default -> Rotation.NONE;
				};
				slots.add(new Slot(s.get("hueco").getAsString(), s.get("grupo").getAsInt(), s.get("casa").getAsString(), rot,
						ints(s.getAsJsonArray("origen")),
						ints(s.getAsJsonArray("parcela")), ints(s.getAsJsonArray("muros")), ints(s.getAsJsonArray("puerta")),
						s.get("mira").getAsString()));
			}
			List<int[]> sites = new ArrayList<>();
			for (JsonElement e : o.getAsJsonArray("sitios_cerezo")) {
				sites.add(ints(e.getAsJsonArray()));
			}
			OutskirtsPlan.Params p = new OutskirtsPlan.Params(o.get("corte").getAsInt(), o.get("relleno").getAsInt(),
					o.get("suavizado").getAsInt(), o.get("borde").getAsInt(), o.get("llano").getAsInt());
			return new Blueprint(p, o.get("anillo").getAsInt(), o.get("casas_por_defecto").getAsInt(), o.get("cerezos").getAsInt(),
					Map.copyOf(houses), List.copyOf(slots), List.copyOf(sites));
		}

		private static int[] ints(com.google.gson.JsonArray a) {
			int[] out = new int[a.size()];
			for (int i = 0; i < out.length; i++) {
				out[i] = a.get(i).getAsInt();
			}
			return out;
		}

		static Blueprint fromJar() {
			String path = "/heraldia/alrededores_casa.json";
			try (InputStream in = Outskirts.class.getResourceAsStream(path)) {
				if (in == null) {
					throw new IllegalStateException("Missing " + path + " in the Heraldia .jar");
				}
				return read(JsonParser.parseReader(new InputStreamReader(in, StandardCharsets.UTF_8)).getAsJsonObject());
			} catch (IOException e) {
				throw new IllegalStateException("Could not read " + path, e);
			}
		}
	}

	static Blueprint blueprint() {
		Blueprint b = blueprint;
		if (b == null) {
			b = blueprint = Blueprint.fromJar();
		}
		return b;
	}

	// --- what is saved (a new attachment, heraldia:casa_heraldo_alrededores) ---

	/** Whether this world's grounds were built, and the houses standing (by slot). */
	public record Saved(boolean built, List<String> houses) {
		public static final Codec<Saved> CODEC = RecordCodecBuilder.create(i -> i.group(
				Codec.BOOL.optionalFieldOf("construidos", false).forGetter(Saved::built),
				Codec.STRING.listOf().optionalFieldOf("casas", List.of()).forGetter(Saved::houses)).apply(i, Saved::new));
		public static final Saved EMPTY = new Saved(false, List.of());
	}

	static final class Type {
		static final AttachmentType<Saved> GROUNDS = AttachmentRegistry.create(Heraldia.id("casa_heraldo_alrededores"),
				b -> b.persistent(Saved.CODEC));

		private Type() {
		}
	}

	static Saved saved(ServerLevel level) {
		return Optional.ofNullable(level.getAttached(Type.GROUNDS)).orElse(Saved.EMPTY);
	}

	// --- registration, triggers and what the roads ask ---

	/** From HeraldHouse.register. */
	static void register() {
		Type.GROUNDS.identifier();
		ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
			work = null;
			pending = null;
			built = null;
		});
	}

	static boolean enabled() {
		return HeraldiaConfig.get().getBool(ENABLED);
	}

	static boolean busy() {
		return work != null;
	}

	private record Pending(ServerLevel level, Grounds g, @Nullable ServerPlayer who) {
	}

	/** The town was just placed: its grounds, once its roads are done (SpawnRoads calls {@link #roadsDone}). */
	static void queue(ServerLevel level, Grounds g, @Nullable ServerPlayer who) {
		if (!enabled()) {
			LOGGER.info("Heraldia: herald's house grounds: disabled ({} = false)", ENABLED);
			return;
		}
		pending = new Pending(level, g, who);
	}

	/** The roads' work ended (or there was none): the grounds of a town just placed, if any is waiting. */
	static void roadsDone(ServerLevel level) {
		Pending p = pending;
		if (p == null || p.level() != level || work != null) {
			return;
		}
		pending = null;
		if (!saved(level).built()) {
			start(level, p.g(), p.who());
		}
	}

	/** Is the column in a house's plot (the roads never touch it)? Cheap: a field check, then a few rectangles. */
	static boolean inHouse(int x, int z) {
		List<int[]> b = plots();
		for (int[] r : b) {
			if (x >= r[0] && x <= r[2] && z >= r[1] && z <= r[3]) {
				return true;
			}
		}
		return false;
	}

	/** The chunks the houses' plots touch (packed), for the arena road's plan: it goes round them as round a structure. */
	static Set<Long> houseChunks() {
		Set<Long> out = new HashSet<>();
		for (int[] r : plots()) {
			chunksOf(r, out);
		}
		return out;
	}

	private static void chunksOf(int[] r, Set<Long> out) {
		for (int cx = r[0] >> 4; cx <= r[2] >> 4; cx++) {
			for (int cz = r[1] >> 4; cz <= r[3] >> 4; cz++) {
				out.add(RoadLayout.pack(cx, cz));
			}
		}
	}

	private static List<int[]> plots() {
		List<int[]> b = built;
		if (b != null) {
			return b;
		}
		Grounds g = HeraldHouse.grounds();
		ServerLevel level = HeraldHouse.level();
		if (g == null || level == null) {
			return List.of();
		}
		List<int[]> out = new ArrayList<>();
		Set<String> names = new HashSet<>(saved(level).houses());
		for (Slot s : blueprint().slots()) {
			if (names.contains(s.name())) {
				out.add(world(g, s.plot()));
			}
		}
		built = b = List.copyOf(out);
		return b;
	}

	private static int[] world(Grounds g, int[] r) {
		return new int[] {g.ox() + r[0], g.oz() + r[1], g.ox() + r[2], g.oz() + r[3]};
	}

	// --- the work ---

	enum Kind { SURVEY, PLAN, LEVEL, FELL, SHORE, DRY, HOUSE, CHERRY, AUDIT, CHECK, TREE_CHECK, FINISH }

	record Step(Kind kind, int a, int b) {
	}

	static final class Work {
		final ServerLevel level;
		final Grounds g;
		final @Nullable ServerPlayer who;
		final int x0, z0, n, houses;
		final byte[] kind;
		final int[] h;
		final boolean[] avoid;
		final List<Step> steps = new ArrayList<>();
		final List<Long> chunks = new ArrayList<>();
		final Map<Long, CompletableFuture<?>> loading = new HashMap<>();
		final List<List<BlockPos>> felling = new ArrayList<>();
		final List<RoadLayout.Route> kept = new ArrayList<>();   // the roads built: their columns (and shoulders) are kept
		final List<RoadLayout.Route> avoided = new ArrayList<>(); // and those that will be: no house or tree on them
		final RoadLayout layout;
		Set<Long> huts = Set.of();
		OutskirtsPlan.@Nullable Result plan;
		final List<String> placed = new ArrayList<>();
		final List<int[]> trees = new ArrayList<>();               // {x, y, z} of the trunk's foot
		boolean waiting;
		int index, rest, ticks, waited, levelled, left, felled, burning, lids, notGrown;
		int audited, steps2, edgeSteps, pillars, holes, chests, looted, doorsBlocked, floating, faced, bare, standing, walled;
		Shores.Settled settled = Shores.NONE;
		int dried;
		final int[] seen;                                          // the audited ground's height (MIN_VALUE: not audited)
		long nanos, worst, worstCpu, planMs;
		String worstStep = "";
		// per kind of step: how many, the clock's time and the server thread's own CPU time, in all and of the longest one
		final int[] kindSteps = new int[Kind.values().length];
		final long[] kindNanos = new long[Kind.values().length], kindCpu = new long[Kind.values().length];
		final long[] kindWorst = new long[Kind.values().length], kindWorstCpu = new long[Kind.values().length];

		Work(ServerLevel level, Grounds g, @Nullable ServerPlayer who, int houses) {
			this.level = level;
			this.g = g;
			this.who = who;
			this.houses = houses;
			int ring = blueprint().ring();
			this.x0 = g.ox() - ring;
			this.z0 = g.oz() - ring;
			this.n = Math.max(g.plan().size()[0], g.plan().size()[2]) + 2 * ring;
			this.kind = new byte[n * n];
			this.h = new int[n * n];
			this.avoid = new boolean[n * n];
			this.seen = new int[n * n];
			java.util.Arrays.fill(seen, Integer.MIN_VALUE);
			this.layout = new RoadLayout(level.getSeed(), 16, 0, (x, z) -> RoadLayout.NONE, RoadLayout.Milestones.NO_MILESTONES);
		}

		boolean in(int x, int z) {
			return x >= x0 && z >= z0 && x < x0 + n && z < z0 + n;
		}

		int index(int x, int z) {
			return (x - x0) * n + (z - z0);
		}
	}

	/** Starts building this world's grounds. False if there is nothing to build (or something else is being built). */
	static boolean start(ServerLevel level, Grounds g, @Nullable ServerPlayer who) {
		if (work != null || Building.busy() || SpawnRoads.busy()) {
			return false;
		}
		Blueprint bp = blueprint();
		int groups = (int) bp.slots().stream().mapToInt(Slot::group).distinct().count();
		int houses = Math.clamp(HeraldiaConfig.get().getInt(HOUSES), 0, groups);
		Work w = new Work(level, g, who, houses);
		for (int cx = w.x0 >> 4; cx <= (w.x0 + w.n - 1) >> 4; cx++) {
			for (int cz = w.z0 >> 4; cz <= (w.z0 + w.n - 1) >> 4; cz++) {
				int ax = cx << 4, az = cz << 4;
				if (ax >= g.ox() && az >= g.oz() && ax + 15 <= g.maxX() && az + 15 <= g.maxZ()) {
					continue;                          // all the town's: nothing to read or to level
				}
				w.chunks.add(RoadLayout.pack(cx, cz));
			}
		}
		for (long c : w.chunks) {
			w.steps.add(new Step(Kind.SURVEY, RoadLayout.px(c), RoadLayout.pz(c)));
		}
		w.steps.add(new Step(Kind.PLAN, 0, 0));
		w.huts = hutColumns(w);
		work = w;
		roads(w);
		LOGGER.info("Heraldia: herald's house grounds: building ({} chunks, up to {} houses)", w.chunks.size(), houses);
		if (who != null) {
			who.sendSystemMessage(Texts.t(K + "construyendo").withStyle(ChatFormatting.GOLD));
		}
		return true;
	}

	/**
	 * The roads this world has or will have: the gates' roads (kept if built, avoided anyway) and, with an arena, the
	 * arena road (its plan off the server thread, as SpawnRoads makes it: with the houses' chunks as structures if it is
	 * yet to be built, so the houses chosen now are the ones it will go round).
	 */
	private static void roads(Work w) {
		SpawnRoads.Saved rs = SpawnRoads.saved(w.level);
		SpawnRoadLayout.Params p = SpawnRoads.blueprint().params();
		Map<String, int[]> gates = SpawnRoads.gates(w.g);
		for (Map.Entry<String, int[]> e : gates.entrySet()) {
			RoadLayout.Route r = SpawnRoadLayout.toRoute(SpawnRoadLayout.normal(e.getValue(), e.getKey(), w.level.getSeed(), p));
			w.avoided.add(r);
			if (rs.built()) {
				w.kept.add(r);
			}
		}
		SpawnRoadLayout.Box arena = SpawnRoads.arenaBox();
		if (arena == null) {
			return;
		}
		boolean builtRoad = rs.arena().isPresent();
		Set<Long> slots = new HashSet<>();
		if (!builtRoad) {
			for (Slot s : blueprint().slots()) {
				chunksOf(world(w.g, s.plot()), slots);
			}
		}
		ServerLevel level = w.level;
		Map<Long, Boolean> memo = new java.util.concurrent.ConcurrentHashMap<>();
		SpawnRoadLayout.Structures structures = (cx, cz) -> slots.contains(RoadLayout.pack(cx, cz))
				|| memo.computeIfAbsent(RoadLayout.pack(cx, cz), k -> Arena.structureAt(level, cx, cz));
		SpawnRoadLayout.Box town = SpawnRoads.town(w.g);
		long seed = level.getSeed();
		w.waiting = true;
		CompletableFuture.supplyAsync(() -> SpawnRoadLayout.arenaPlan(gates, arena, seed, structures, town, p), Util.backgroundExecutor())
				.whenCompleteAsync((plan, err) -> {
					if (work != w) {
						return;
					}
					w.waiting = false;
					if (err == null && plan != null && plan.arena() != null) {
						RoadLayout.Route r = SpawnRoadLayout.toRoute(plan.arena().pts());
						w.avoided.add(r);
						if (builtRoad) {
							w.kept.add(r);
						}
					}
				}, level.getServer());
	}

	/** A few steps per tick (from HeraldHouse's tick), within the budget; none when nothing is being built. */
	static void tick(MinecraftServer server) {
		Work w = work;
		if (w == null) {
			return;
		}
		w.ticks++;
		if (w.rest > 0) {
			w.rest--;
			return;
		}
		long start = System.nanoTime();
		while (work == w && !w.waiting && w.index < w.steps.size() && System.nanoTime() - start < BUDGET_MS * 1_000_000L) {
			Step st = w.steps.get(w.index);
			prefetch(w);
			if (!ready(w, st)) {
				return;                                // its chunks are being loaded or generated off the server thread
			}
			w.waited = 0;
			w.index++;
			long c0 = cpuNanos(), t0 = System.nanoTime();
			try {
				step(w, st);
			} catch (RuntimeException e) {
				LOGGER.error("Heraldia: herald's house grounds: step {} failed", st, e);
			}
			long ns = System.nanoTime() - t0, cpu = c0 < 0 ? -1 : cpuNanos() - c0;
			w.nanos += ns;
			int k = st.kind().ordinal();
			w.kindSteps[k]++;
			w.kindNanos[k] += ns;
			w.kindCpu[k] += Math.max(cpu, 0);
			if (ns > w.kindWorst[k]) {
				w.kindWorst[k] = ns;
				w.kindWorstCpu[k] = cpu;
			}
			if (ns > w.worst) {
				w.worst = ns;
				w.worstCpu = cpu;
				w.worstStep = st.kind() + " " + st.a() + " " + st.b();
			}
			if (ns > SLOW_MS * 1_000_000L) {
				// The clock's time counts whatever stopped the process during the step (a collector's pause, the machine giving
				// the CPU to something else); the thread's own CPU time counts only its work. Far apart: the step waited, it did
				// not work. Logged at once, so the line's own time says when.
				LOGGER.info("Heraldia: herald's house grounds: a slow step: {} {} {}: {} ms by the clock, {} of them the server "
						+ "thread's own work", st.kind(), st.a(), st.b(), ns / 1_000_000, cpu < 0 ? "? (not measured here)" : cpu / 1_000_000 + " ms");
				w.rest = REST;                         // a slow step (a chunk loaded from disk): let the server breathe
				return;
			}
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

	/** "SURVEY 192 steps 45 ms (40 ms of work), the longest 3 ms (3 ms of work); ..." of the kinds that ran. */
	private static String byKind(Work w) {
		StringBuilder sb = new StringBuilder();
		for (Kind k : Kind.values()) {
			int i = k.ordinal();
			if (w.kindSteps[i] == 0) {
				continue;
			}
			sb.append(sb.isEmpty() ? "" : "; ").append(k).append(' ').append(w.kindSteps[i]).append(" steps ")
					.append(w.kindNanos[i] / 1_000_000).append(" ms (").append(w.kindCpu[i] / 1_000_000).append(" ms of work), the longest ")
					.append(w.kindWorst[i] / 1_000_000).append(" ms (")
					.append(w.kindWorstCpu[i] < 0 ? "?" : String.valueOf(w.kindWorstCpu[i] / 1_000_000)).append(" ms of work)");
		}
		return sb.toString();
	}

	private static boolean chunkStep(Step st) {
		return st.kind() == Kind.SURVEY || st.kind() == Kind.LEVEL || st.kind() == Kind.SHORE || st.kind() == Kind.DRY
				|| st.kind() == Kind.AUDIT;
	}

	/** The chunks of the next steps that read one, asked for without waiting (generated on the worker threads). */
	private static void prefetch(Work w) {
		int found = 0;
		for (int i = w.index; i < w.steps.size() && found < AHEAD; i++) {
			Step st = w.steps.get(i);
			if (chunkStep(st)) {
				found++;
				ask(w, st.a(), st.b());
			}
		}
	}

	private static void ask(Work w, int cx, int cz) {
		long key = RoadLayout.pack(cx, cz);
		if (w.level.getChunkSource().getChunkNow(cx, cz) == null) {
			CompletableFuture<?> f = w.loading.get(key);
			if (f == null || f.isDone()) {         // never asked, or loaded once and unloaded since: asked for (again)
				w.loading.put(key, w.level.getChunkSource().getChunkFuture(cx, cz, ChunkStatus.FULL, true));
			}
		}
	}

	/** Whether the chunks a step reads are loaded (at most {@link #MAX_WAIT} ticks of waiting for them). */
	private static boolean ready(Work w, Step st) {
		List<long[]> need = new ArrayList<>();
		switch (st.kind()) {
			case SURVEY, LEVEL -> need.add(new long[] {st.a(), st.b()});
			case AUDIT, SHORE, DRY -> {
				need.add(new long[] {st.a(), st.b()});
				need.add(new long[] {st.a() + 1, st.b()});
				need.add(new long[] {st.a(), st.b() + 1});
				need.add(new long[] {st.a() - 1, st.b()});
				need.add(new long[] {st.a(), st.b() - 1});
			}
			case HOUSE, CHERRY, CHECK, TREE_CHECK -> {
				int[] c = st.kind() == Kind.HOUSE || st.kind() == Kind.CHECK ? plotOf(w, st.a()) : treeBox(w, st.a());
				for (int cx = c[0] >> 4; cx <= c[2] >> 4; cx++) {
					for (int cz = c[1] >> 4; cz <= c[3] >> 4; cz++) {
						need.add(new long[] {cx, cz});
					}
				}
			}
			default -> {
				return true;
			}
		}
		boolean ok = true;
		for (long[] c : need) {
			if (w.level.getChunkSource().getChunkNow((int) c[0], (int) c[1]) == null) {
				ask(w, (int) c[0], (int) c[1]);
				ok = false;
			}
		}
		return ok || w.waited++ >= MAX_WAIT;
	}

	private static void step(Work w, Step st) {
		switch (st.kind()) {
			case SURVEY -> survey(w, chunk(w, st.a(), st.b()));
			case PLAN -> plan(w);
			case LEVEL -> {
				List<BlockPos> logs = new ArrayList<>();
				level(w, chunk(w, st.a(), st.b()), logs);
				if (!logs.isEmpty()) {
					w.felling.add(logs);
					w.steps.add(w.index, new Step(Kind.FELL, st.a(), st.b()));   // its trees, next
				}
			}
			case FELL -> {
				if (!w.felling.isEmpty()) {
					w.felled += BuiltRoads.fell(w.level, w.felling.remove(0), (x, z) -> w.g.inColumns(x, z));
				}
			}
			case SHORE -> w.settled = w.settled.plus(Shores.settle(w.level, chunk(w, st.a(), st.b()),
					(x, z) -> w.in(x, z) && !w.g.inColumns(x, z)));
			case DRY -> w.dried += Shores.dry(w.level, chunk(w, st.a(), st.b()));
			case HOUSE -> house(w, st.a());
			case CHERRY -> cherry(w, st.a());
			case AUDIT -> audit(w, chunk(w, st.a(), st.b()));
			case CHECK -> check(w, st.a());
			case TREE_CHECK -> treeCheck(w, st.a());
			case FINISH -> finish(w);
		}
	}

	private static LevelChunk chunk(Work w, int cx, int cz) {
		return w.level.getChunk(cx, cz);
	}

	// --- reading the ground ---

	/**
	 * The natural ground under a column's growth (trees, plants, snow) and under anything nobody grew (a lamp post, a sign,
	 * a hut, a player's block: {@code object[0]} true then): its top block's y. At most {@link #MAX_OBJECT} blocks down.
	 */
	static int ground(LevelChunk c, int x, int z, int minY, BlockPos.MutableBlockPos pos, boolean[] object) {
		int y = c.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, x & 15, z & 15), floor = y - MAX_OBJECT;
		object[0] = false;
		while (y > minY && y > floor) {
			BlockState s = c.getBlockState(pos.set(x, y, z));
			if (s.isAir() || BuiltRoads.growth(s)) {
				y--;
				continue;
			}
			if (!s.getFluidState().isEmpty() || BuiltRoads.kind(s) != null || BuiltRoads.terrain(s)) {
				break;
			}
			object[0] = true;
			y--;
		}
		return y;
	}

	private static boolean frozen(BlockState s) {
		return s.is(Blocks.ICE) || s.is(Blocks.PACKED_ICE) || s.is(Blocks.BLUE_ICE) || s.is(Blocks.FROSTED_ICE);
	}

	/** One chunk's columns of the protected area: their kind and ground height. */
	private static void survey(Work w, LevelChunk chunk) {
		var cp = chunk.getPos();
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		boolean[] object = new boolean[1];
		List<BoundingBox> boxes = BuiltRoads.boxes(w.level, chunk);
		RoadLayout.Cell[] road = w.kept.isEmpty() ? null : w.layout.paint(w.kept, cp.x(), cp.z(), SpawnRoads.blueprint().params().width() + 2, false);
		RoadLayout.Cell[] near = w.layout.paint(w.avoided, cp.x(), cp.z(), SpawnRoads.blueprint().params().width() + 8, false);
		Set<Long> huts = w.huts;
		for (int lx = 0; lx < 16; lx++) {
			for (int lz = 0; lz < 16; lz++) {
				int x = cp.getMinBlockX() + lx, z = cp.getMinBlockZ() + lz;
				if (!w.in(x, z)) {
					continue;
				}
				int i = w.index(x, z);
				if (w.g.inColumns(x, z)) {
					w.kind[i] = OutskirtsPlan.TOWN;
					w.h[i] = w.g.groundY();
					continue;
				}
				int y = ground(chunk, x, z, w.level.getMinY(), pos, object);
				BlockState s = chunk.getBlockState(pos.set(x, y, z));
				w.h[i] = y;
				w.avoid[i] = near[lx * 16 + lz] != null;
				boolean structure = false;
				for (BoundingBox b : boxes) {
					if (b.isInside(x, y, z) || b.isInside(x, y + 1, z)) {
						structure = true;
						break;
					}
				}
				if (object[0] || structure || frozen(s) || s.getFluidState().isEmpty() == false && !s.is(Blocks.WATER)
						|| road != null && road[lx * 16 + lz] != null || huts.contains(RoadLayout.pack(x, z))) {
					w.kind[i] = OutskirtsPlan.KEPT;
					w.avoid[i] = true;
				} else if (!s.getFluidState().isEmpty()) {
					w.kind[i] = OutskirtsPlan.WATER;
				} else {
					w.kind[i] = OutskirtsPlan.LAND;
				}
			}
		}
	}

	/** The columns of the roadside huts this world has, and a block round them (kept as they are), packed. */
	private static Set<Long> hutColumns(Work w) {
		Set<Long> out = new HashSet<>();
		SpawnRoads.Blueprint bp = SpawnRoads.blueprint();
		Map<String, int[]> gates = SpawnRoads.gates(w.g);
		for (String key : SpawnRoads.saved(w.level).huts()) {
			String side = key.substring(0, key.indexOf(':')), name = key.substring(key.indexOf(':') + 1);
			SpawnRoads.Slot slot = name.equals(bp.guide().name()) ? bp.guide()
					: bp.slots().stream().filter(s -> s.name().equals(name)).findFirst().orElse(null);
			int[] gate = gates.get(side);
			if (slot == null || gate == null) {
				continue;
			}
			for (int lx = -1; lx <= bp.size()[0]; lx++) {
				for (int lz = -1; lz <= bp.size()[2]; lz++) {
					int[] q = SpawnRoadLayout.hutCell(gate, side, slot.side(), slot.along(), bp.size()[0], bp.edge(), lx, lz);
					out.add(RoadLayout.pack(q[0], q[1]));
				}
			}
		}
		return out;
	}

	// --- the plan ---

	private static void plan(Work w) {
		long p0 = System.nanoTime();
		Blueprint bp = blueprint();
		List<OutskirtsPlan.Slot> slots = new ArrayList<>();
		for (int i = 0; i < bp.slots().size(); i++) {
			int[] r = world(w.g, bp.slots().get(i).plot());
			slots.add(new OutskirtsPlan.Slot(i, r[0], r[1], r[2], r[3], bp.slots().get(i).group()));
		}
		List<int[]> sites = new ArrayList<>();
		for (int[] c : bp.sites()) {
			sites.add(new int[] {w.g.ox() + c[0], w.g.oz() + c[1]});
		}
		long t0 = System.nanoTime();
		w.waiting = true;                              // the plan, its reference heights included, off the server thread
		CompletableFuture.supplyAsync(() -> new OutskirtsPlan(w.x0, w.z0, w.n, w.kind, w.h, w.g.groundY(), bp.params())
						.plan(slots, w.houses, sites, bp.cherries(), w.avoid), Util.backgroundExecutor())
				.whenCompleteAsync((res, err) -> {
					if (work != w) {
						return;
					}
					w.waiting = false;
					w.planMs = (System.nanoTime() - t0) / 1_000_000;
					if (err != null || res == null) {
						LOGGER.error("Heraldia: herald's house grounds: the plan failed", err);
						w.steps.add(new Step(Kind.FINISH, 0, 0));
						return;
					}
					w.plan = res;
					LOGGER.info("Heraldia: herald's house grounds: plan in {} ms: {} columns to level (cut up to {}, filled up to {}), "
									+ "{} too steep to level within {} blocks, {} narrow pits to cover; steps of more than one block: {} before, {} in the "
									+ "plan ({} of them terraces' walls); one-block steps in ramps: {} before, {} in the plan; {} houses, {} cherry trees",
							w.planMs, res.changed(), res.maxCut(), res.maxFill(), res.steep(),
							Math.max(bp.params().cut(), bp.params().fill()), res.lids(), res.before(), res.steps(), res.walls(), res.rampsBefore(),
							res.ramps(), res.houses().size(), res.cherries().size());
					for (long c : w.chunks) {
						w.steps.add(new Step(Kind.LEVEL, RoadLayout.px(c), RoadLayout.pz(c)));
					}
					for (long c : w.chunks) {
						w.steps.add(new Step(Kind.SHORE, RoadLayout.px(c), RoadLayout.pz(c)));
					}
					for (long c : w.chunks) {             // once all are settled: what ran out and has no source left
						w.steps.add(new Step(Kind.DRY, RoadLayout.px(c), RoadLayout.pz(c)));
					}
					for (int k = 0; k < res.houses().size(); k++) {
						w.steps.add(new Step(Kind.HOUSE, k, 0));
					}
					for (int k = 0; k < res.cherries().size(); k++) {
						w.steps.add(new Step(Kind.CHERRY, k, 0));
					}
					for (long c : w.chunks) {
						w.steps.add(new Step(Kind.AUDIT, RoadLayout.px(c), RoadLayout.pz(c)));
					}
					for (int k = 0; k < res.houses().size(); k++) {
						w.steps.add(new Step(Kind.CHECK, k, 0));
					}
					for (int k = 0; k < res.cherries().size(); k++) {
						w.steps.add(new Step(Kind.TREE_CHECK, k, 0));
					}
					w.steps.add(new Step(Kind.FINISH, 0, 0));
				}, w.level.getServer());
		// what this step does on the server thread, in its two halves: if it is ever slow, which one (or neither: a pause)
		LOGGER.info("Heraldia: herald's house grounds: the plan handed to the background pool: {} ms getting it ready, {} ms handing it over",
				(t0 - p0) / 1_000_000, (System.nanoTime() - t0) / 1_000_000);
	}

	// --- levelling ---

	/** The surface a levelled column gets: its own top block (grass, sand, a path...), never farmland or snow over it. */
	private static BlockState surface(BlockState top) {
		if (top.is(Blocks.FARMLAND)) {
			return Blocks.DIRT.defaultBlockState();
		}
		return top.hasProperty(BlockStateProperties.SNOWY) ? top.setValue(BlockStateProperties.SNOWY, false) : top;
	}

	private static BlockState filling(BlockState top) {
		RoadProfile.Ground k = BuiltRoads.kind(top);
		return k == null ? Blocks.DIRT.defaultBlockState() : BuiltRoads.fill(k);
	}

	/** One chunk's columns brought to the plan's height: cut or filled, their growth cleared, trees felled after. */
	private static void level(Work w, LevelChunk chunk, List<BlockPos> logs) {
		OutskirtsPlan.Result plan = w.plan;
		if (plan == null) {
			return;
		}
		var cp = chunk.getPos();
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		boolean[] object = new boolean[1];
		BlockState air = Blocks.AIR.defaultBlockState();
		for (int lx = 0; lx < 16; lx++) {
			for (int lz = 0; lz < 16; lz++) {
				int x = cp.getMinBlockX() + lx, z = cp.getMinBlockZ() + lz;
				if (!w.in(x, z)) {
					continue;
				}
				int i = w.index(x, z);
				int t = plan.target()[i];
				if (w.kind[i] != OutskirtsPlan.LAND) {
					continue;
				}
				int g = ground(chunk, x, z, w.level.getMinY(), pos, object);
				BlockState top = chunk.getBlockState(pos.set(x, g, z));
				if (object[0] || !top.getFluidState().isEmpty()) {
					continue;
				}
				if (t == g) {
					wall(w, chunk, x, z, t, top, pos);   // as planned already: its riser faced, if it has one
					continue;
				}
				Blueprint bp = blueprint();
				boolean lid = t > g + bp.params().fill();      // a narrow pit (the plan says so): a lid, not a full fill
				if (t < g - bp.params().cut() || t > g + LID_MAX) {
					w.left++;
					continue;
				}
				boolean ok = true;
				for (int y = Math.min(t, g) + 1; y <= Math.max(t, g) && ok; y++) {
					BlockState s = chunk.getBlockState(pos.set(x, y, z));
					ok = s.isAir() || BuiltRoads.growth(s) || (y <= g && BuiltRoads.terrain(s));
				}
				if (!ok) {
					w.left++;                      // something nobody grew in the way (a buried structure): left as it is
					continue;
				}
				BlockState surface = surface(top), fill = filling(top);
				if (t < g) {
					for (int y = t + 1; y <= g; y++) {
						set(w, chunk, pos.set(x, y, z), air, logs);
					}
					clearGrowth(w, chunk, x, g + 1, z, pos, logs);
				} else {
					for (int y = lid ? t - LID : g; y < t; y++) {
						set(w, chunk, pos.set(x, y, z), fill.getBlock() instanceof FallingBlock ? Blocks.DIRT.defaultBlockState() : fill, logs);
					}
					w.lids += lid ? 1 : 0;
				}
				set(w, chunk, pos.set(x, t, z), surface, logs);
				clearGrowth(w, chunk, x, t + 1, z, pos, logs);
				if (surface.getBlock() instanceof FallingBlock) {
					BlockState below = chunk.getBlockState(pos.set(x, t - 1, z));
					if (below.isAir() || !below.getFluidState().isEmpty() || BuiltRoads.growth(below)) {
						w.level.setBlock(pos, fill.getBlock() instanceof FallingBlock ? Blocks.DIRT.defaultBlockState() : fill, BuiltRoads.FLAGS);
					}
				}
				wall(w, chunk, x, z, t, top, pos);
				w.levelled++;
			}
		}
	}

	private static void set(Work w, LevelChunk chunk, BlockPos.MutableBlockPos pos, BlockState s, List<BlockPos> logs) {
		BlockState old = chunk.getBlockState(pos);
		if (old.is(BlockTags.LOGS)) {
			logs.add(pos.immutable());             // a tree on a levelled column: felled whole afterwards
		}
		if (old != s) {
			w.level.setBlock(pos, s, BuiltRoads.FLAGS);
		}
	}

	/** The plants and trunks standing on a column from y up (not leaves: a felled tree takes its own with it). */
	private static void clearGrowth(Work w, LevelChunk chunk, int x, int y0, int z, BlockPos.MutableBlockPos pos, List<BlockPos> logs) {
		for (int y = y0; y < y0 + 40; y++) {
			BlockState s = chunk.getBlockState(pos.set(x, y, z));
			if (s.isAir() || s.is(BlockTags.LEAVES) || !s.getFluidState().isEmpty() || !BuiltRoads.growth(s)) {
				return;
			}
			set(w, chunk, pos, Blocks.AIR.defaultBlockState(), logs);
		}
	}

	/**
	 * A terrace's riser: the side of the column (top at {@code t}) that faces a lower neighbour two or more blocks down (as
	 * planned: natural ground, or a kept column such as a road's cut) made a retaining wall of stone, from the neighbour's
	 * height up to under the column's surface, so the step reads as built and not as bare earth. The town's side and the
	 * water's are left as they are; so is anything that is not ground (a lid's air under it, a buried structure).
	 */
	private static void wall(Work w, LevelChunk chunk, int x, int z, int t, BlockState top, BlockPos.MutableBlockPos pos) {
		OutskirtsPlan.Result plan = w.plan;
		RoadProfile.Ground kind = BuiltRoads.kind(top);
		if (plan == null || kind == null) {
			return;
		}
		int low = t;
		for (int[] d : new int[][] {{1, 0}, {-1, 0}, {0, 1}, {0, -1}}) {
			int nx = x + d[0], nz = z + d[1];
			if (!w.in(nx, nz)) {
				continue;
			}
			int j = w.index(nx, nz);
			if (w.kind[j] == OutskirtsPlan.LAND) {
				low = Math.min(low, plan.target()[j]);
			} else if (w.kind[j] == OutskirtsPlan.KEPT) {
				low = Math.min(low, w.h[j]);
			}
		}
		for (int y = low + 1; y <= t - 1 && t - low >= 2; y++) {
			BlockState s = chunk.getBlockState(pos.set(x, y, z));
			if (BuiltRoads.terrain(s) && !wallBlock(s)) {
				w.level.setBlock(pos, wallBlock(kind, x, y, z), BuiltRoads.FLAGS);
				w.walled++;
			}
		}
	}

	/** A retaining wall's block for ground of this kind: two materials mixed (a quarter of the second), by position. */
	static BlockState wallBlock(RoadProfile.Ground kind, int x, int y, int z) {
		boolean second = Math.floorMod(x * 7 + y * 13 + z * 5, 4) == 0;
		return (switch (kind) {
			case DIRT -> second ? Blocks.MOSSY_COBBLESTONE : Blocks.COBBLESTONE;
			case SAND -> second ? Blocks.SMOOTH_SANDSTONE : Blocks.CUT_SANDSTONE;
			case RED -> second ? Blocks.SMOOTH_RED_SANDSTONE : Blocks.CUT_RED_SANDSTONE;
			case MUD -> second ? Blocks.PACKED_MUD : Blocks.MUD_BRICKS;
			case STONE -> second ? Blocks.MOSSY_STONE_BRICKS : Blocks.STONE_BRICKS;
		}).defaultBlockState();
	}

	/** Is it a retaining wall's block (what the audit takes for a faced riser)? */
	static boolean wallBlock(BlockState s) {
		for (RoadProfile.Ground g : RoadProfile.Ground.values()) {
			if (s.is(wallBlock(g, 0, 0, 0).getBlock()) || s.is(wallBlock(g, 0, 0, 1).getBlock())) {
				return true;
			}
		}
		return false;
	}

	// --- the houses and the trees ---

	private static int[] plotOf(Work w, int k) {
		OutskirtsPlan.Result plan = w.plan;
		return plan == null ? new int[4] : new int[] {plan.houses().get(k).slot().x0() - 1, plan.houses().get(k).slot().z0() - 1,
				plan.houses().get(k).slot().x1() + 1, plan.houses().get(k).slot().z1() + 1};
	}

	private static int[] treeBox(Work w, int k) {
		OutskirtsPlan.Result plan = w.plan;
		if (plan == null) {
			return new int[4];
		}
		int[] c = plan.cherries().get(k);
		return new int[] {c[0] - 8, c[1] - 8, c[0] + 8, c[1] + 8};
	}

	/** A house on its pad: whatever grew on the plot felled, then its template (its chest's loot is drawn when opened). */
	private static void house(Work w, int k) {
		OutskirtsPlan.Result plan = w.plan;
		if (plan == null) {
			return;
		}
		OutskirtsPlan.House hs = plan.houses().get(k);
		Slot slot = blueprint().slots().get(hs.slot().index());
		House house = blueprint().houses().get(slot.house());
		Optional<StructureTemplate> t = w.level.getStructureTemplateManager().get(Identifier.parse(house.template()));
		if (house == null || t.isEmpty()) {
			LOGGER.error("Heraldia: herald's house grounds: missing template {}", house == null ? slot.house() : house.template());
			return;
		}
		int y = hs.y();
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		List<BlockPos> logs = new ArrayList<>();
		for (int x = hs.slot().x0(); x <= hs.slot().x1(); x++) {
			for (int z = hs.slot().z0(); z <= hs.slot().z1(); z++) {
				for (int yy = y + 1; yy <= y + house.size()[1] + 16; yy++) {
					BlockState s = w.level.getBlockState(pos.set(x, yy, z));
					if (s.is(BlockTags.LOGS)) {
						logs.add(pos.immutable());
						w.level.setBlock(pos, Blocks.AIR.defaultBlockState(), BuiltRoads.FLAGS);
					}
				}
			}
		}
		// the pad's own surface (sand, terracotta, mud...), read before the template covers it with its grass
		int sx = hs.slot().x1() - hs.slot().x0() + 1;
		BlockState[] pad = new BlockState[sx * (hs.slot().z1() - hs.slot().z0() + 1)];
		for (int x = hs.slot().x0(); x <= hs.slot().x1(); x++) {
			for (int z = hs.slot().z0(); z <= hs.slot().z1(); z++) {
				pad[(z - hs.slot().z0()) * sx + x - hs.slot().x0()] = w.level.getBlockState(pos.set(x, y, z));
			}
		}
		BlockPos origin = new BlockPos(w.g.ox() + slot.origin()[0], y, w.g.oz() + slot.origin()[1]);
		StructurePlaceSettings settings = Placing.dry(new StructurePlaceSettings().setRotation(slot.rotation()).setIgnoreEntities(true));
		t.get().placeInWorld(w.level, origin, origin, settings, w.level.getRandom(), BuiltRoads.FLAGS);
		// off grassland the plot's bare grass goes back to that surface: a house on the sand, not on a green doormat
		for (int x = hs.slot().x0(); x <= hs.slot().x1(); x++) {
			for (int z = hs.slot().z0(); z <= hs.slot().z1(); z++) {
				BlockState was = pad[(z - hs.slot().z0()) * sx + x - hs.slot().x0()];
				RoadProfile.Ground kind = BuiltRoads.kind(was);
				if (kind != null && kind != RoadProfile.Ground.DIRT && w.level.getBlockState(pos.set(x, y, z)).is(Blocks.GRASS_BLOCK)
						&& w.level.getBlockState(pos.set(x, y + 1, z)).isAir()) {
					w.level.setBlock(pos.set(x, y, z), surface(was), BuiltRoads.FLAGS);
				}
			}
		}
		w.felled += BuiltRoads.fell(w.level, logs, (x, z) -> w.g.inColumns(x, z));
		w.placed.add(slot.name());
		LOGGER.info("Heraldia: herald's house grounds: house {} ({}) at {} {} {}", slot.name(), slot.house(), origin.getX(), y, origin.getZ());
	}

	/** Is there a fire source (lava, fire, a lit campfire, magma) within {@link #FIRE_REACH} blocks of the tree's place? */
	private static boolean fireNear(ServerLevel level, int x, int y, int z) {
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		for (int dx = -FIRE_REACH; dx <= FIRE_REACH; dx++) {
			for (int dz = -FIRE_REACH; dz <= FIRE_REACH; dz++) {
				for (int dy = -3; dy <= 12; dy++) {
					BlockState s = level.getBlockState(pos.set(x + dx, y + dy, z + dz));
					if (s.is(Blocks.LAVA) || s.is(BlockTags.FIRE) || s.is(Blocks.MAGMA_BLOCK) || s.is(BlockTags.CAMPFIRES)) {
						return true;
					}
				}
			}
		}
		return false;
	}

	/** A cherry tree (vanilla's own) on its site, with a few petals round it; none on a fire source's reach or off grass. */
	private static void cherry(Work w, int k) {
		OutskirtsPlan.Result plan = w.plan;
		if (plan == null) {
			return;
		}
		int[] c = plan.cherries().get(k);
		int x = c[0], z = c[1];
		LevelChunk chunk = w.level.getChunk(x >> 4, z >> 4);
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		boolean[] object = new boolean[1];
		int y = ground(chunk, x, z, w.level.getMinY(), pos, object);
		BlockState s = chunk.getBlockState(pos.set(x, y, z));
		if (object[0] || BuiltRoads.kind(s) != RoadProfile.Ground.DIRT || s.is(Blocks.DIRT_PATH) || s.is(Blocks.FARMLAND)) {
			w.notGrown++;                              // not on grass or dirt (sand, stone, a path)
			return;
		}
		if (fireNear(w.level, x, y, z)) {
			w.burning++;
			return;
		}
		if (!s.is(Blocks.GRASS_BLOCK)) {
			w.level.setBlock(pos, Blocks.GRASS_BLOCK.defaultBlockState(), BuiltRoads.FLAGS);
		}
		BlockPos foot = new BlockPos(x, y + 1, z);
		if (!w.level.getBlockState(foot).isAir() && !BuiltRoads.growth(w.level.getBlockState(foot))) {
			w.notGrown++;
			return;
		}
		w.level.setBlock(foot, Blocks.AIR.defaultBlockState(), BuiltRoads.FLAGS);
		RandomSource random = RandomSource.create(w.level.getSeed() ^ foot.asLong());
		boolean grown = w.level.registryAccess().lookupOrThrow(Registries.FEATURE).get(TreeFeatures.CHERRY)
				.map(f -> f.value().place(w.level, w.level.getChunkSource().getGenerator(), random, foot)).orElse(false);
		if (!grown) {
			w.notGrown++;                              // no room for it (vanilla's own check)
			return;
		}
		w.trees.add(new int[] {x, y + 1, z});
		for (int p = 0; p < 7; p++) {                  // a few petals on the grass round the trunk
			int px = x + random.nextInt(7) - 3, pz = z + random.nextInt(7) - 3;
			if (px == x && pz == z) {
				continue;
			}
			LevelChunk pc = w.level.getChunk(px >> 4, pz >> 4);
			int py = pc.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, px & 15, pz & 15);
			if (pc.getBlockState(pos.set(px, py, pz)).is(Blocks.GRASS_BLOCK) && pc.getBlockState(pos.set(px, py + 1, pz)).isAir()) {
				w.level.setBlock(pos, Blocks.PINK_PETALS.defaultBlockState().setValue(FlowerBedBlock.AMOUNT, 1 + random.nextInt(4))
						.setValue(FlowerBedBlock.FACING, Direction.Plane.HORIZONTAL.getRandomDirection(random)), Block.UPDATE_CLIENTS);
			}
		}
	}

	// --- the audit ---

	/**
	 * One chunk's columns of the ring as they stand: the pairs of side by side columns of natural ground (neither water
	 * nor under something nobody grew, nor the town's) more than a block apart, the loose columns (two or more over all
	 * four neighbours) and the holes (two or more under all four). Reads loaded chunks only.
	 */
	private static void audit(Work w, LevelChunk chunk) {
		var cp = chunk.getPos();
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		boolean[] object = new boolean[1];
		int[] tops = new int[18 * 18];
		java.util.Arrays.fill(tops, Integer.MIN_VALUE);
		for (int ix = 0; ix < 18; ix++) {
			for (int iz = 0; iz < 18; iz++) {
				int x = cp.getMinBlockX() - 1 + ix, z = cp.getMinBlockZ() - 1 + iz;
				if (!w.in(x, z) || w.g.inColumns(x, z) || inPlots(w, x, z)) {
					continue;
				}
				LevelChunk c = (x >> 4) == cp.x() && (z >> 4) == cp.z() ? chunk : w.level.getChunkSource().getChunkNow(x >> 4, z >> 4);
				if (c == null) {
					continue;
				}
				int y = ground(c, x, z, w.level.getMinY(), pos, object);
				BlockState s = c.getBlockState(pos.set(x, y, z));
				if (object[0] || !s.getFluidState().isEmpty() || frozen(s) || w.kind[w.index(x, z)] == OutskirtsPlan.KEPT) {
					continue;
				}
				tops[ix * 18 + iz] = y;
			}
		}
		for (int ix = 1; ix <= 16; ix++) {
			for (int iz = 1; iz <= 16; iz++) {
				int y = tops[ix * 18 + iz];
				if (y == Integer.MIN_VALUE) {
					continue;
				}
				w.audited++;
				int x = cp.getMinBlockX() - 1 + ix, z = cp.getMinBlockZ() - 1 + iz;
				boolean blend = Math.min(Math.min(x - w.x0, w.x0 + w.n - 2 - x), Math.min(z - w.z0, w.z0 + w.n - 2 - z)) < EDGE_BLEND;
				if (!blend) {
					w.seen[w.index(x, z)] = y;
				}
				int e = tops[(ix + 1) * 18 + iz], s = tops[ix * 18 + iz + 1];
				int found = (e != Integer.MIN_VALUE && Math.abs(e - y) > 1 ? 1 : 0) + (s != Integer.MIN_VALUE && Math.abs(s - y) > 1 ? 1 : 0);
				int faced = (e != Integer.MIN_VALUE && Math.abs(e - y) > 1 && faced(w, x, y, z, x + 1, e, z, pos) ? 1 : 0)
						+ (s != Integer.MIN_VALUE && Math.abs(s - y) > 1 && faced(w, x, y, z, x, s, z + 1, pos) ? 1 : 0);
				w.steps2 += found;
				w.edgeSteps += blend ? found : 0;
				w.faced += faced;
				w.bare += blend ? 0 : found - faced;
				int[] nb = {tops[(ix - 1) * 18 + iz], e, tops[ix * 18 + iz - 1], s};
				boolean pillar = true, hole = true;
				for (int o : nb) {
					pillar &= o != Integer.MIN_VALUE && o <= y - 2;
					hole &= o != Integer.MIN_VALUE && o >= y + 2;
				}
				w.pillars += pillar && !blend ? 1 : 0;
				w.holes += hole && !blend ? 1 : 0;
				if ((pillar || hole) && !blend && w.pillars + w.holes <= 4) {
					OutskirtsPlan.Result plan = w.plan;
					LOGGER.info("Heraldia: herald's house grounds: audit: a {} at {} {} {} (planned {}, natural {}; round it {} {} {} {})",
							pillar ? "loose column" : "hole", x, y, z, plan == null ? "?" : plan.target()[w.index(x, z)], w.h[w.index(x, z)],
							nb[0], nb[1], nb[2], nb[3]);
				}
			}
		}
		w.standing += Shores.standing(w.level, chunk, (x, z) -> w.in(x, z)).size();
	}

	/** A step between (x, y, z) and its neighbour (nx, ny, nz) faced: the higher one's side over the lower one is a wall's block. */
	private static boolean faced(Work w, int x, int y, int z, int nx, int ny, int nz, BlockPos.MutableBlockPos pos) {
		int hx = y > ny ? x : nx, hz = y > ny ? z : nz, low = Math.min(y, ny);
		return wallBlock(w.level.getBlockState(pos.set(hx, low + 1, hz)));
	}

	private static boolean inPlots(Work w, int x, int z) {
		OutskirtsPlan.Result plan = w.plan;
		if (plan == null) {
			return false;
		}
		for (OutskirtsPlan.House hs : plan.houses()) {
			OutskirtsPlan.Slot s = hs.slot();
			if (x >= s.x0() && x <= s.x1() && z >= s.z0() && z <= s.z1()) {
				return true;
			}
		}
		return false;
	}

	/** A house's chests (a loot table each, until opened) and its door (room in front), its chunks loaded. */
	private static void check(Work w, int k) {
		OutskirtsPlan.Result plan = w.plan;
		if (plan == null) {
			return;
		}
		{
			OutskirtsPlan.House hs = plan.houses().get(k);
			Slot slot = blueprint().slots().get(hs.slot().index());
			if (!w.placed.contains(slot.name())) {
				return;
			}
			House house = blueprint().houses().get(slot.house());
			StructureTemplate t = w.level.getStructureTemplateManager().get(Identifier.parse(house.template())).orElse(null);
			BlockPos origin = new BlockPos(w.g.ox() + slot.origin()[0], hs.y(), w.g.oz() + slot.origin()[1]);
			if (t != null) {
				for (StructureTemplate.StructureBlockInfo info : t.filterBlocks(origin, new StructurePlaceSettings().setRotation(slot.rotation()),
						Blocks.CHEST)) {
					w.chests++;
					if (w.level.getBlockEntity(info.pos()) instanceof RandomizableContainerBlockEntity r && r.getLootTable() != null) {
						w.looted++;
					}
				}
			}
			int[] d = SpawnRoadLayout.outward(slot.facing());
			BlockPos door = new BlockPos(w.g.ox() + slot.door()[0], hs.y() + 1, w.g.oz() + slot.door()[1]);
			boolean free = w.level.getBlockState(door).getBlock() instanceof DoorBlock;
			for (int out = 1; out <= 3 && free; out++) {
				BlockPos f = door.offset(d[0] * out, 0, d[1] * out);
				free = w.level.getBlockState(f).getCollisionShape(w.level, f).isEmpty()
						&& w.level.getBlockState(f.above()).getCollisionShape(w.level, f.above()).isEmpty();
			}
			if (!free) {
				w.doorsBlocked++;
			}
		}
	}

	/** A cherry tree's foot: its trunk on grass or dirt (none floating). */
	private static void treeCheck(Work w, int k) {
		OutskirtsPlan.Result plan = w.plan;
		if (plan == null) {
			return;
		}
		int[] site = plan.cherries().get(k);
		for (int[] c : w.trees) {
			if (c[0] != site[0] || c[2] != site[1]) {
				continue;
			}
			BlockPos foot = new BlockPos(c[0], c[1], c[2]);
			BlockState under = w.level.getBlockState(foot.below());
			if (!w.level.getBlockState(foot).is(BlockTags.LOGS) || !under.is(BlockTags.DIRT) && !under.is(Blocks.GRASS_BLOCK)) {
				w.floating++;
			}
		}
	}

	private static void finish(Work w) {
		work = null;
		ServerLevel level = w.level;
		List<String> houses = new ArrayList<>(saved(level).houses());
		for (String s : w.placed) {
			if (!houses.contains(s)) {
				houses.add(s);
			}
		}
		level.setAttached(Type.GROUNDS, new Saved(true, List.copyOf(houses)));
		built = null;
		OutskirtsPlan.Result plan = w.plan;
		LOGGER.info("Heraldia: herald's house grounds: the slowest step: {} ({} ms by the clock, {} of them the server thread's own work)",
				w.worstStep, w.worst / 1_000_000, w.worstCpu < 0 ? "?" : w.worstCpu / 1_000_000 + " ms");
		LOGGER.info("Heraldia: herald's house grounds: by kind of step: {}", byKind(w));
		boolean[] in = new boolean[w.n * w.n];
		for (int i = 0; i < in.length; i++) {
			in[i] = w.seen[i] != Integer.MIN_VALUE;
		}
		int ramps = OutskirtsPlan.ramps(w.n, w.seen, in);
		LOGGER.info("Heraldia: herald's house grounds: audit: {} columns on land, {} steps of more than one block ({} before; {} of them in "
						+ "the outermost {} rows, where the natural ground keeps its own; {} faced with a retaining wall, {} bare further in), {} one-block "
						+ "steps in ramps ({} before), {} loose columns, {} holes (further in), {} blocks of water standing in the air; {} houses, {} of {} chests "
						+ "with loot, {} doors blocked; {} cherry trees, {} floating, {} left out by a fire source, {} that did not fit (not on grass, no room)",
				w.audited, w.steps2, plan == null ? 0 : plan.before(), w.edgeSteps, EDGE_BLEND, w.faced, w.bare, ramps,
				plan == null ? 0 : plan.rampsBefore(), w.pillars, w.holes, w.standing, w.placed.size(), w.looted,
				w.chests, w.doorsBlocked, w.trees.size(), w.floating, w.burning, w.notGrown);
		LOGGER.info("Heraldia: herald's house grounds: shores: {} ponds left open drained ({} blocks of water), {} blocks of water banked; "
				+ "{} blocks of retaining wall; {} blocks of running water left without a source taken away", w.settled.ponds(),
				w.settled.drained(), w.settled.banked(), w.walled, w.dried);
		LOGGER.info("Heraldia: herald's house grounds: built in {} ticks ({} ms on the server thread, the slowest step {} ms; the plan {} ms "
						+ "off it): {} columns levelled ({} narrow pits covered with a lid), {} left, {} too steep to level fully, {} trees felled, {} houses, "
						+ "{} cherry trees", w.ticks, w.nanos / 1_000_000, w.worst / 1_000_000, w.planMs, w.levelled, w.lids, w.left,
				plan == null ? 0 : plan.steep(), w.felled, w.placed.size(), w.trees.size());
		if (w.who != null && !w.who.hasDisconnected()) {
			w.who.sendSystemMessage(Texts.t(K + "hechos", w.levelled, w.placed.size(), w.trees.size()).withStyle(ChatFormatting.GOLD));
		}
		SpawnRoads.arenaPlaced(level);                 // an arena placed meanwhile: its road, now
	}

	// --- /heraldia herald grounds ---

	static int command(CommandContext<CommandSourceStack> ctx) {
		CommandSourceStack src = ctx.getSource();
		if (!enabled()) {
			src.sendFailure(Texts.t(K + "desactivados"));
			return 0;
		}
		Grounds g = HeraldHouse.grounds();
		ServerLevel level = HeraldHouse.level();
		if (g == null || level == null) {
			src.sendFailure(Texts.t(HeraldHouse.K + "no_existe"));
			return 0;
		}
		if (work != null || Building.busy() || SpawnRoads.busy()) {
			src.sendFailure(Texts.t(K + "ocupado"));
			return 0;
		}
		if (saved(level).built() || !start(level, g, src.getPlayer())) {
			src.sendSuccess(() -> Texts.t(K + "nada"), false);
			return 0;
		}
		src.sendSuccess(() -> Texts.t(K + "construyendo"), true);
		return 1;
	}
}
