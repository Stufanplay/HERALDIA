package io.github.albertosa23.heraldia.update;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.builder.LiteralArgumentBuilder;
import com.mojang.brigadier.context.CommandContext;
import io.github.albertosa23.heraldia.Heraldia;
import io.github.albertosa23.heraldia.command.Texts;
import io.github.albertosa23.heraldia.herald.Grounds;
import io.github.albertosa23.heraldia.herald.HeraldHouse;
import io.github.albertosa23.heraldia.herald.Repairs;
import io.github.albertosa23.heraldia.roads.BuiltRoads;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.contents.TranslatableContents;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.dialog.ActionButton;
import net.minecraft.server.dialog.CommonButtonData;
import net.minecraft.server.dialog.CommonDialogData;
import net.minecraft.server.dialog.DialogAction;
import net.minecraft.server.dialog.MultiActionDialog;
import net.minecraft.server.dialog.action.StaticAction;
import net.minecraft.server.dialog.body.DialogBody;
import net.minecraft.server.dialog.body.PlainMessage;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.level.TicketType;
import net.minecraft.world.Container;
import net.minecraft.world.entity.monster.Shulker;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.dimension.DimensionType;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.PoolElementStructurePiece;
import net.minecraft.world.level.levelgen.structure.StructurePiece;
import net.minecraft.world.level.levelgen.structure.StructureStart;
import net.minecraft.world.level.levelgen.structure.pools.SinglePoolElement;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate;
import net.minecraft.world.level.material.FluidState;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.world.phys.AABB;
import org.jspecify.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * /heraldia update mend: repairs, with the operator's confirmation, what an earlier version of the generator built wrong
 * in a world that already has it. Heraldia builds each structure once, so when a generator bug is fixed new worlds come
 * out right and what was already built stays as it was. The repairs (each one asked for by itself, or {@code all}):
 * <ul>
 * <li>{@code water}: still water left standing in the air with no source around the Herald's House (the same build
 * drained a pond without block updates): settled by the very code a town built today uses ({@link Repairs#settle},
 * herald/Shores), so each body is drained or banked. It writes blocks in the world and {@code all} includes it. Water
 * that something feeds is not this fault and is left: by the game's rules a source, or a waterlogged block of the
 * town's own walls, is a source.</li>
 * <li>{@code streams}: running water left with no source around the Herald's House (its build drained a pond without block
 * updates before the running-water fix; what had run down the hillside stayed, a stream from nowhere): taken away, as
 * herald/Shores.dry does in a town built today ({@link Streams}). A player's water always has its tick, so it never
 * stays running with no source: this cannot be a player's. The road walkways laid over it are left (a player's planks
 * and the road's cannot be told apart there).</li>
 * <li>{@code wharf}: the Wharf Guard's post on the Fallen Shulker Wharfs of the End midlands and barrens (an end stone
 * brick wall a shulker cannot hold, made a full block by the fix) and the guard, if alive and away, put back on it.</li>
 * <li>{@code inn}: the Roadside Inn's bedroom door (the innkeeper's bed was out of his reach with the street door alone);
 * the room's chest, which stood where the door's way in is, is carried to the corner with everything in it.</li>
 * </ul>
 * The rules, the reason for this command at all (a repair that breaks someone's house is worse than the bug it fixes):
 * <ul>
 * <li>{@code scan} reports what it found, per repair, with where; it changes nothing. {@code apply <repair>} scans
 * again and asks for confirmation with what it found (a dialog; the console gets the command); only the confirmation
 * repairs, within {@link #VALIDITY_MS} of the scan, and every target is looked at again at that moment.</li>
 * <li>A template repair ({@link TemplatePatch}) touches a piece only if every cell it changes and every cell beside them
 * is still exactly what an earlier version of the generator placed; any other block there is somebody's, and the piece
 * is left alone and listed with the cell that did not match. Done once, the cells are today's and the next run finds
 * nothing to do: idempotent by construction.</li>
 * <li>Off the server thread: reading the saved regions to find the structures. On it: one target per step, a few steps a
 * tick within {@link #BUDGET_MS} ms, chunks asked for ahead and loaded off the thread (a loading ticket, no simulation),
 * the slowest step in the log and in the report; a step over {@link #SLOW_MS} ms is logged as slow.</li>
 * </ul>
 * Left out on purpose (docs/LESSONS.md): the grounds' "rice terraces" (rebuilding the terrain round a town people live in
 * cannot tell the generator's earth from a player's), the water that runs because something feeds it (by the game's
 * rules it has a source: a separate fault), and the welcome decorations on mossy supports (they are put up at run time, so they come on their own
 * once the support check is fixed; nothing in the world records them as declined).
 */
public final class GenerationMend {
	private static final Logger LOGGER = LoggerFactory.getLogger(Heraldia.MOD_ID);
	static final int BUDGET_MS = 8, SLOW_MS = 100, MAX_WAIT = 400, SHOWN = 5;
	static final long VALIDITY_MS = 15 * 60_000;
	/** Structure ids (path prefixes) of each template repair, and its dimension. */
	static final String INN_ID = "medianas/posada/", WHARF_ID = "medianas/embarcadero_shulker/";
	/** The Wharf Guard's tag (mediums.MARK + ".embarcadero_shulker") and its name's key. */
	static final String WHARF_TAG = "heraldia_mediana.embarcadero_shulker", GUARD_NAME = "heraldia.medianas.embarcadero_shulker.guardia";
	/** How far a guard that left its post may be (a shulker teleports up to 8 blocks). */
	static final int GUARD_REACH = 8;

	public enum Kind {
		/** In this order: the water standing in the air is settled before the running water is looked at (as the build). */
		WATER("water", true), STREAMS("streams", true), WHARF("wharf", true), INN("inn", true),
		/** Only reported: the one-block steps in ramps left round an old town (see the class comment). */
		RING("ring", false);

		final String word;
		final boolean repairs;

		Kind(String word, boolean repairs) {
			this.word = word;
			this.repairs = repairs;
		}

		/** Done on the Herald's House's area, chunk by chunk. */
		boolean area() {
			return this == WATER || this == STREAMS || this == RING;
		}

		static @Nullable Kind of(String w) {
			for (Kind k : values()) {
				if (k.word.equals(w)) {
					return k;
				}
			}
			return null;
		}
	}

	/** What was found at one target. */
	public enum Outcome {
		/** Wrong, and it can be repaired (scan) / it was repaired (apply). */
		REPAIR,
		/** Nothing to do. */
		FINE,
		/** Someone changed it, or it could not be seen: left as it is. */
		LEFT,
		/** Wrong, and not repairable by this command (a guard that died). */
		NOTICE
	}

	record Target(Kind kind, ResourceKey<Level> dimension, int cx, int cz) {
	}

	/**
	 * One place the command looked at. {@code blocks} is how many blocks of the world the finding is about, where that
	 * is what the operator needs to judge the size of the change (the water and the streams); 0 where the unit is the
	 * piece itself (an inn, a wharf), so a total of 0 means "not counted in blocks", never "nothing".
	 */
	record Finding(Kind kind, Outcome outcome, BlockPos at, String detail, int blocks) {
		Finding(Kind kind, Outcome outcome, BlockPos at, String detail) {
			this(kind, outcome, at, detail, 0);
		}
	}

	/** A scan or an apply in progress (one at a time). */
	static final class Job {
		final String id;
		final boolean apply;
		final Set<Kind> kinds;
		final List<Target> targets;
		final CommandSourceStack source;
		final Map<String, String> lang;
		final List<Finding> findings = new ArrayList<>();
		final Set<Long> streamSeen = new HashSet<>();
		/** The chunks the current target asked for: kept loaded (their loading tickets renewed) until it is done. */
		final Set<Long> held = new HashSet<>();
		int index, waited, steps;
		long nanos, worst, worstCpu, started = System.currentTimeMillis();
		String worstStep = "-";
		@Nullable Runnable onDone;
		int @Nullable [] ringY;
		boolean @Nullable [] ringIn;
		int ringX, ringZ, ringN;
		/** The step left the target half done on purpose (it goes on, within the tick's budget); the column it is at. */
		boolean more;
		int column;
		/** What the columns of the chunk being settled have come to so far: reported as one finding when it is done. */
		int ponds, drained, banked;

		Job(String id, boolean apply, Set<Kind> kinds, List<Target> targets, CommandSourceStack source, Map<String, String> lang) {
			this.id = id;
			this.apply = apply;
			this.kinds = kinds;
			this.targets = targets;
			this.source = source;
			this.lang = lang;
		}
	}

	/** A finished scan, kept for the confirmation. */
	record Scan(String id, long at, Set<Kind> kinds, List<Target> targets, List<Finding> findings) {
		long count(Kind k, Outcome o) {
			return findings.stream().filter(f -> f.kind == k && f.outcome == o).count();
		}
	}

	private static @Nullable Job job;
	private static volatile boolean discovering;
	private static @Nullable Scan last;
	private static final Map<Kind, List<TemplatePatch>> PATCHES = new EnumMap<>(Kind.class);
	private static final Map<String, List<int[]>> GUARD_POSTS = new LinkedHashMap<>();
	private static final DateTimeFormatter DATE = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss", Locale.ROOT);
	private static final ThreadMXBean THREADS = ManagementFactory.getThreadMXBean();

	private GenerationMend() {
	}

	// ------------------------------------------------------------------ the patches (resources heraldia/mend/<kind>.json)

	static synchronized List<TemplatePatch> patches(Kind k) {
		return PATCHES.computeIfAbsent(k, kind -> {
			try (InputStream in = GenerationMend.class.getResourceAsStream("/heraldia/mend/" + kind.word + ".json")) {
				if (in == null) {
					return List.of();
				}
				return parse(JsonParser.parseReader(new InputStreamReader(in, StandardCharsets.UTF_8)).getAsJsonObject());
			} catch (IOException | RuntimeException e) {
				LOGGER.error("Heraldia: update mend: the {} patch could not be read", kind.word, e);
				return List.of();
			}
		});
	}

	/** The pieces of one patch file (also read by the tests). */
	static List<TemplatePatch> parse(JsonObject o) {
		List<TemplatePatch> out = new ArrayList<>();
		for (JsonElement e : o.getAsJsonArray("pieces")) {
			JsonObject p = e.getAsJsonObject();
			List<String> versions = new ArrayList<>();
			p.getAsJsonArray("versions").forEach(v -> versions.add(v.getAsString()));
			List<TemplatePatch.Cell> cells = new ArrayList<>();
			for (JsonElement c : p.getAsJsonArray("cells")) {
				JsonObject co = c.getAsJsonObject();
				int[] pos = ints(co.getAsJsonArray("pos"));
				List<String> before = new ArrayList<>();
				co.getAsJsonArray("before").forEach(b -> before.add(b.getAsString()));
				cells.add(new TemplatePatch.Cell(pos[0], pos[1], pos[2], before, co.get("after").getAsString()));
			}
			List<TemplatePatch.Guard> guards = new ArrayList<>();
			for (JsonElement g : p.getAsJsonArray("guards")) {
				JsonObject go = g.getAsJsonObject();
				int[] pos = ints(go.getAsJsonArray("pos"));
				guards.add(new TemplatePatch.Guard(pos[0], pos[1], pos[2], go.get("block").getAsString()));
			}
			List<TemplatePatch.Move> moves = new ArrayList<>();
			for (JsonElement m : p.getAsJsonArray("moves")) {
				JsonObject mo = m.getAsJsonObject();
				moves.add(new TemplatePatch.Move(ints(mo.getAsJsonArray("from")), ints(mo.getAsJsonArray("to"))));
			}
			String template = p.get("template").getAsString();
			if (p.has("posts")) {
				List<int[]> posts = new ArrayList<>();
				p.getAsJsonArray("posts").forEach(x -> posts.add(ints(x.getAsJsonArray())));
				synchronized (GUARD_POSTS) {
					GUARD_POSTS.put(template, posts);
				}
			}
			out.add(new TemplatePatch(template, versions, cells, guards, moves));
		}
		return List.copyOf(out);
	}

	private static int[] ints(JsonArray a) {
		int[] r = new int[a.size()];
		for (int i = 0; i < r.length; i++) {
			r[i] = a.get(i).getAsInt();
		}
		return r;
	}

	// ------------------------------------------------------------------ commands

	/** /heraldia update mend scan | apply <repair|all> [confirm <id>] (added to Updater.node()). */
	public static LiteralArgumentBuilder<CommandSourceStack> node() {
		LiteralArgumentBuilder<CommandSourceStack> apply = Commands.literal("apply");
		for (String w : words()) {
			apply.then(Commands.literal(w).executes(c -> scan(c, kinds(w), true))
					.then(Commands.literal("confirm").then(Commands.argument("id", StringArgumentType.word())
							.executes(c -> confirm(c, kinds(w))))));
		}
		return Commands.literal("mend")
				.then(Commands.literal("scan").executes(c -> scan(c, Set.of(Kind.values()), false)))
				.then(apply);
	}

	static List<String> words() {
		List<String> l = new ArrayList<>();
		for (Kind k : Kind.values()) {
			if (k.repairs) {
				l.add(k.word);
			}
		}
		l.add("all");
		return l;
	}

	static Set<Kind> kinds(String w) {
		Kind k = Kind.of(w);
		if (k != null) {
			return Set.of(k);
		}
		Set<Kind> all = java.util.EnumSet.noneOf(Kind.class);
		for (Kind x : Kind.values()) {
			if (x.repairs) {
				all.add(x);
			}
		}
		return all;
	}

	private static Map<String, String> language(CommandSourceStack src) {
		ServerPlayer p = src.getPlayer();
		return p != null ? Texts.language(p) : Texts.language("es_es");
	}

	private static int scan(CommandContext<CommandSourceStack> ctx, Set<Kind> kinds, boolean offer) {
		CommandSourceStack src = ctx.getSource();
		Map<String, String> l = language(src);
		if (job != null || discovering) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.reparar.ocupado"));
			return 0;
		}
		discovering = true;
		src.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.reparar.buscando").withStyle(ChatFormatting.GRAY), true);
		MinecraftServer server = src.getServer();
		String id = LocalDateTime.now().format(DATE);
		discover(server, kinds, m -> LOGGER.info("Heraldia: update mend: {}", m)).whenComplete((targets, err) -> server.execute(() -> {
			discovering = false;
			if (err != null) {
				LOGGER.error("Heraldia: update mend: the search failed", err);
				src.sendFailure(Texts.t(l, "heraldia.actualizar.reparar.error", String.valueOf(err.getMessage())));
				return;
			}
			Job j = new Job(id, false, kinds, targets, src, l);
			j.onDone = offer ? () -> offer(j) : null;
			job = j;
			LOGGER.info("Heraldia: update mend scan {}: {} targets ({})", id, targets.size(), kinds);
		}));
		return 1;
	}

	private static int confirm(CommandContext<CommandSourceStack> ctx, Set<Kind> kinds) {
		CommandSourceStack src = ctx.getSource();
		Map<String, String> l = language(src);
		String id = StringArgumentType.getString(ctx, "id");
		Scan s = last;
		if (s == null || !s.id.equals(id) || System.currentTimeMillis() - s.at > VALIDITY_MS || !s.kinds.containsAll(kinds)) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.reparar.caducado"));
			return 0;
		}
		if (job != null || discovering) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.reparar.ocupado"));
			return 0;
		}
		// only the targets the scan found to repair: everything else stays exactly as it is
		List<Target> todo = new ArrayList<>();
		Set<String> seen = new HashSet<>();
		for (Target t : s.targets) {
			if (kinds.contains(t.kind) && seen.add(t.toString())) {
				todo.add(t);
			}
		}
		last = null;
		job = new Job(id, true, kinds, todo, src, l);
		LOGGER.info("Heraldia: update mend apply {} confirmed by {}: {} targets ({})", id, src.getTextName(), todo.size(), kinds);
		src.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.reparar.reparando", todo.size()).withStyle(ChatFormatting.GOLD), true);
		return 1;
	}

	/** After a scan for apply: the dialog (or, in the console, the command) to confirm, with what was found. */
	private static void offer(Job j) {
		Scan s = last;
		if (s == null) {
			return;
		}
		Map<String, String> l = j.lang;
		long n = 0;
		for (Kind k : j.kinds) {
			n += s.count(k, Outcome.REPAIR);
		}
		if (n == 0) {
			j.source.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.reparar.nada").withStyle(ChatFormatting.GREEN), true);
			return;
		}
		String word = j.kinds.size() == 1 ? j.kinds.iterator().next().word : "all";
		String cmd = "heraldia update mend apply " + word + " confirm " + s.id;
		ServerPlayer p = j.source.getPlayer();
		if (p == null) {
			j.source.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.reparar.confirmar_consola", cmd), false);
			return;
		}
		List<DialogBody> body = new ArrayList<>();
		summary(l, s.kinds, s.findings, false).forEach(t -> body.add(new PlainMessage(t, 300)));
		body.add(new PlainMessage(Texts.t(l, "heraldia.actualizar.reparar.aviso").withStyle(ChatFormatting.YELLOW), 300));
		ActionButton yes = new ActionButton(new CommonButtonData(Texts.t(l, "heraldia.actualizar.reparar.boton.reparar"),
				Optional.of(Texts.t(l, "heraldia.actualizar.reparar.boton.reparar.ayuda")), 150), Optional.of(new StaticAction(new ClickEvent.RunCommand(cmd))));
		p.openDialog(Holder.direct(new MultiActionDialog(new CommonDialogData(Texts.t(l, "heraldia.actualizar.reparar.dialogo"), Optional.empty(),
				true, false, DialogAction.CLOSE, body, List.of()), List.of(yes),
				Optional.of(new ActionButton(new CommonButtonData(Texts.t(l, "heraldia.actualizar.boton.cancelar"), 150), Optional.empty())), 1)));
	}

	/** The report as translatable lines: per repair, how many of each outcome, and where (the first few). */
	static List<Component> summary(Map<String, String> l, Set<Kind> kinds, List<Finding> findings, boolean applied) {
		List<Component> out = new ArrayList<>();
		for (Kind k : Kind.values()) {
			if (!kinds.contains(k)) {
				continue;
			}
			if (k == Kind.RING) {
				// reported, never repaired: the reason is in the text itself, so no operator takes it for something forgotten
				findings.stream().filter(f -> f.kind == Kind.RING).findFirst().ifPresent(f ->
						out.add(Texts.t(l, "heraldia.actualizar.reparar.anillo", f.detail).withStyle(ChatFormatting.GRAY)));
				continue;
			}
			long[] n = new long[Outcome.values().length];
			long blocks = 0;
			for (Finding f : findings) {
				if (f.kind == k) {
					n[f.outcome.ordinal()]++;
					blocks += f.blocks();
				}
			}
			out.add(Texts.t(l, "heraldia.actualizar.reparar.linea" + (applied ? ".hecho" : ""), Texts.t(l, "heraldia.actualizar.reparar." + k.word),
					n[Outcome.REPAIR.ordinal()], n[Outcome.FINE.ordinal()], n[Outcome.LEFT.ordinal()], n[Outcome.NOTICE.ordinal()])
					.withStyle(ChatFormatting.YELLOW));
			// how many blocks of the world: the places are the command's unit, the blocks are what a person can judge
			if (blocks > 0) {
				out.add(Texts.t(l, "heraldia.actualizar.reparar.bloques", Texts.t(l, "heraldia.actualizar.reparar." + k.word), blocks)
						.withStyle(ChatFormatting.YELLOW));
			}
			int shown = 0;
			for (Finding f : findings) {
				if (f.kind == k && f.outcome != Outcome.FINE && shown++ < SHOWN) {
					out.add(Texts.t(l, "heraldia.actualizar.reparar.donde." + f.outcome.name().toLowerCase(Locale.ROOT), f.at.getX(), f.at.getY(),
							f.at.getZ(), f.detail).withStyle(ChatFormatting.GRAY));
				}
			}
		}
		return out;
	}

	// ------------------------------------------------------------------ finding the targets

	/**
	 * The targets of a scan: for {@code streams}, the chunks of the Herald's House's protected area (none without a house);
	 * for {@code wharf} and {@code inn}, the chunks whose saved data starts one of those structures, read from the
	 * dimension's region files off the server thread once its chunks are written out.
	 */
	static CompletableFuture<List<Target>> discover(MinecraftServer server, Set<Kind> kinds, Consumer<String> progress) {
		List<Target> area = new ArrayList<>();
		Grounds g = HeraldHouse.grounds();
		for (Kind k : Kind.values()) {
			if (!k.area() || !kinds.contains(k) || g == null) {
				continue;
			}
			int r = Grounds.RING;
			for (int cx = (g.ox() - r) >> 4; cx <= (g.maxX() + r) >> 4; cx++) {
				for (int cz = (g.oz() - r) >> 4; cz <= (g.maxZ() + r) >> 4; cz++) {
					if (g.areaOverlaps(cx << 4, cz << 4, (cx << 4) + 15, (cz << 4) + 15)) {
						area.add(new Target(k, Level.OVERWORLD, cx, cz));
					}
				}
			}
		}
		Map<ResourceKey<Level>, List<Kind>> dims = new LinkedHashMap<>();
		if (kinds.contains(Kind.INN)) {
			dims.computeIfAbsent(Level.OVERWORLD, d -> new ArrayList<>()).add(Kind.INN);
		}
		if (kinds.contains(Kind.WHARF)) {
			dims.computeIfAbsent(Level.END, d -> new ArrayList<>()).add(Kind.WHARF);
		}
		server.saveEverything(true, false, true);     // written out without waiting on the server thread (no flush)
		List<CompletableFuture<Void>> written = new ArrayList<>();
		Map<ResourceKey<Level>, Path> folders = new LinkedHashMap<>();
		for (ResourceKey<Level> d : dims.keySet()) {
			ServerLevel level = server.getLevel(d);
			if (level != null) {
				written.add(level.getChunkSource().chunkMap.synchronize(true));
				folders.put(d, DimensionType.getStorageFolder(d, server.getWorldPath(LevelResource.ROOT)).resolve("region"));
			}
		}
		CompletableFuture<List<Target>> out = new CompletableFuture<>();
		CompletableFuture.allOf(written.toArray(CompletableFuture[]::new)).whenComplete((v, e) -> {
			Thread t = new Thread(() -> {
				try {
					List<Target> l = new ArrayList<>(area);
					for (var en : folders.entrySet()) {
						l.addAll(starts(en.getValue(), en.getKey(), dims.get(en.getKey()), progress));
					}
					out.complete(l);
				} catch (IOException | RuntimeException ex) {
					out.completeExceptionally(ex);
				}
			}, "Heraldia update mend");
			t.setDaemon(true);
			t.setPriority(Thread.MIN_PRIORITY);
			t.start();
		});
		return out;
	}

	/** The chunks of a region folder that start a structure of one of {@code kinds} (off the server thread). */
	static List<Target> starts(Path region, ResourceKey<Level> dim, List<Kind> kinds, Consumer<String> progress) throws IOException {
		List<Target> out = new ArrayList<>();
		if (!Files.isDirectory(region)) {
			return out;
		}
		List<Path> files = new ArrayList<>();
		try (DirectoryStream<Path> ds = Files.newDirectoryStream(region, "r.*.mca")) {
			ds.forEach(files::add);
		}
		files.sort(null);
		int i = 0;
		for (Path f : files) {
			if (Region.coordinatesOf(f).isEmpty()) {
				continue;
			}
			for (int idx : Region.present(Region.header(f))) {
				try {
					Optional<CompoundTag> nbt = Region.read(f, idx);
					if (nbt.isEmpty()) {
						continue;
					}
					CompoundTag starts = nbt.get().getCompoundOrEmpty("structures").getCompoundOrEmpty("starts");
					for (String id : starts.keySet()) {
						Kind k = kindOf(id);
						if (k != null && kinds.contains(k) && !"INVALID".equals(starts.getCompoundOrEmpty(id).getStringOr("id", "INVALID"))) {
							out.add(new Target(k, dim, nbt.get().getIntOr("xPos", 0), nbt.get().getIntOr("zPos", 0)));
						}
					}
				} catch (IOException | RuntimeException e) {
					LOGGER.warn("Heraldia: update mend: a chunk of {} could not be read ({}); not looked at", f.getFileName(), e.getMessage());
				}
			}
			if (++i % 16 == 0) {
				progress.accept(i + "/" + files.size() + " regions of " + dim.identifier());
			}
		}
		return out;
	}

	static @Nullable Kind kindOf(String structureId) {
		String path = structureId.startsWith("heraldia:") ? structureId.substring("heraldia:".length()) : null;
		if (path == null) {
			return null;
		}
		return path.startsWith(INN_ID) ? Kind.INN : path.startsWith(WHARF_ID) ? Kind.WHARF : null;
	}

	// ------------------------------------------------------------------ the steps (server thread)

	/** Called each server tick (from Updater's tick): a few steps of the job within the budget; nothing without a job. */
	static void tick(MinecraftServer server) {
		Job j = job;
		if (j == null) {
			return;
		}
		long start = System.nanoTime();
		while (job == j && j.index < j.targets.size() && System.nanoTime() - start < BUDGET_MS * 1_000_000L) {
			Target t = j.targets.get(j.index);
			ServerLevel level = server.getLevel(t.dimension);
			if (level == null) {
				j.index++;
				continue;
			}
			for (int k = j.index; k < Math.min(j.targets.size(), j.index + 4); k++) {
				Target a = j.targets.get(k);
				ServerLevel al = server.getLevel(a.dimension);
				if (al != null) {
					ask(al, a.cx, a.cz, 1);           // ahead: loaded off the thread while the steps before it run
				}
			}
			ask(level, t.cx, t.cz, 1);
			for (long c : j.held) {
				ask(level, ChunkPos.getX(c), ChunkPos.getZ(c), 0);
			}
			if (!loaded(level, t.cx, t.cz, 1)) {
				if (++j.waited > MAX_WAIT) {
					j.findings.add(new Finding(t.kind, Outcome.LEFT, new BlockPos(t.cx << 4, 0, t.cz << 4), "not loaded"));
					j.index++;
					j.waited = 0;
					j.held.clear();
				}
				return;
			}
			long c0 = cpu(), t0 = System.nanoTime();
			boolean done;
			try {
				done = step(j, level, t);
			} catch (RuntimeException e) {
				LOGGER.error("Heraldia: update mend: step {} failed", t, e);
				j.findings.add(new Finding(t.kind, Outcome.LEFT, new BlockPos(t.cx << 4, 0, t.cz << 4), "error: " + e.getMessage()));
				done = true;
			}
			long ns = System.nanoTime() - t0, cpuNs = c0 < 0 ? -1 : cpu() - c0;
			if (j.more) {                              // a step of a target done in several (one column at a time)
				j.more = false;
				j.steps++;
				j.nanos += ns;
				if (ns > j.worst) {
					j.worst = ns;
					j.worstCpu = cpuNs;
					j.worstStep = t.kind.word + " " + t.cx + " " + t.cz + " (part)";
				}
				continue;
			}
			if (!done) {
				if (++j.waited > MAX_WAIT) {
					j.findings.add(new Finding(t.kind, Outcome.LEFT, new BlockPos(t.cx << 4, 0, t.cz << 4), "not loaded"));
					done = true;
				} else {
					return;                            // a piece's other chunks are still being loaded
				}
			}
			j.index++;
			j.waited = 0;
			j.held.clear();
			j.steps++;
			j.nanos += ns;
			if (ns > j.worst) {
				j.worst = ns;
				j.worstCpu = cpuNs;
				j.worstStep = t.kind.word + " " + t.cx + " " + t.cz;
			}
			if (ns > SLOW_MS * 1_000_000L) {
				LOGGER.info("Heraldia: update mend: a slow step: {} {} {}: {} ms by the clock, {} ms of work", t.kind.word, t.cx, t.cz,
						ns / 1_000_000, cpuNs < 0 ? "?" : cpuNs / 1_000_000);
				return;
			}
		}
		if (job == j && j.index >= j.targets.size()) {
			finish(server, j);
		}
	}

	private static long cpu() {
		try {
			return THREADS.isCurrentThreadCpuTimeSupported() ? THREADS.getCurrentThreadCpuTime() : -1;
		} catch (UnsupportedOperationException e) {
			return -1;
		}
	}

	/** Keeps the chunks round (cx, cz) loaded for a while (a loading ticket: no simulation), asking for them if needed. */
	private static void ask(ServerLevel level, int cx, int cz, int radius) {
		level.getChunkSource().addTicketWithRadius(TicketType.PLAYER_SPAWN, new ChunkPos(cx, cz), radius);
	}

	private static boolean loaded(ServerLevel level, int cx, int cz, int radius) {
		for (int x = cx - radius; x <= cx + radius; x++) {
			for (int z = cz - radius; z <= cz + radius; z++) {
				if (level.getChunkSource().getChunkNow(x, z) == null) {
					ask(level, cx, cz, radius);
					return false;
				}
			}
		}
		return true;
	}

	/** One target. False if it must wait for more chunks (it is run again). */
	static boolean step(Job j, ServerLevel level, Target t) {
		return switch (t.kind) {
			case WATER -> water(j, level, t);
			case STREAMS -> streams(j, level, t);
			case WHARF, INN -> pieces(j, level, t);
			case RING -> ring(j, level, t);
		};
	}

	// ------------------------------------------------------------------ water standing in the air

	/**
	 * Still water standing in the air in the area (the town cut a pond or a lake open before the shores fix): settled by
	 * herald/Shores itself, as a town built today ({@link Repairs}): a small pond drained to where it would have run out, a
	 * bigger body banked. A source with air beside or under it only stays so if it never had a fluid tick, which a player's
	 * water always has: this is never a player's.
	 */
	private static boolean water(Job j, ServerLevel level, Target t) {
		LevelChunk chunk = level.getChunkSource().getChunkNow(t.cx, t.cz);
		Grounds g = HeraldHouse.grounds();
		if (chunk == null || g == null) {
			return chunk != null;
		}
		if (!j.apply) {                                // counting is cheap: the whole chunk at once
			int n = Repairs.standing(level, chunk, g::inArea);
			if (n > 0) {
				j.findings.add(new Finding(Kind.WATER, Outcome.REPAIR, new BlockPos(t.cx << 4, g.groundY(), t.cz << 4),
						String.valueOf(n), n));
			}
			return true;
		}
		// settling is not: a column per step (Shores.settle looks for each standing block's pond, up to 4,096 blocks; a
		// whole chunk at once took 132 ms of the server thread, read in the log of a world from an earlier jar)
		if (j.column == 0 && Repairs.standing(level, chunk, g::inArea) == 0) {
			return true;                               // nothing standing in this chunk: no column to settle
		}
		int c = j.column, x = (t.cx << 4) + (c & 15), z = (t.cz << 4) + (c >> 4);
		java.util.function.BiPredicate<Integer, Integer> in = (a, b) -> a == x && b == z && g.inArea(a, b);
		if (g.inArea(x, z) && Repairs.standing(level, chunk, in) > 0) {
			int[] s = Repairs.settle(level, chunk, in);
			j.ponds += s[0];
			j.drained += s[1];
			j.banked += s[2];
		}
		if (++j.column < 256) {
			j.more = true;
			return false;
		}
		j.column = 0;
		// one finding for the chunk, at the cell the scan named and counting the blocks the scan counted: the offer the
		// operator confirmed and what was done are then the same figure, in the same unit
		if (j.drained + j.banked > 0) {
			j.findings.add(new Finding(Kind.WATER, Outcome.REPAIR, new BlockPos(t.cx << 4, g.groundY(), t.cz << 4),
					j.ponds + " ponds drained (" + j.drained + " blocks), " + j.banked + " banked", j.drained + j.banked));
		}
		j.ponds = j.drained = j.banked = 0;
		return true;
	}

	// ------------------------------------------------------------------ the ring's old "rice terraces" (reported only)

	/** Each chunk's ground heights (no leaves) into the job's grid of the area; counted when the job ends. */
	private static boolean ring(Job j, ServerLevel level, Target t) {
		LevelChunk chunk = level.getChunkSource().getChunkNow(t.cx, t.cz);
		Grounds g = HeraldHouse.grounds();
		if (chunk == null || g == null) {
			return chunk != null;
		}
		if (j.ringY == null) {
			j.ringX = g.ox() - Grounds.RING;
			j.ringZ = g.oz() - Grounds.RING;
			j.ringN = Math.max(g.maxX() - g.ox(), g.maxZ() - g.oz()) + 1 + 2 * Grounds.RING;
			j.ringY = new int[j.ringN * j.ringN];
			j.ringIn = new boolean[j.ringN * j.ringN];
		}
		for (int lx = 0; lx < 16; lx++) {
			for (int lz = 0; lz < 16; lz++) {
				int x = (t.cx << 4) + lx, z = (t.cz << 4) + lz, u = x - j.ringX, v = z - j.ringZ;
				if (u < 0 || v < 0 || u >= j.ringN || v >= j.ringN) {
					continue;
				}
				int i = v * j.ringN + u;
				j.ringIn[i] = g.inArea(x, z) && !g.inColumns(x, z);
				j.ringY[i] = chunk.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, lx, lz);
			}
		}
		return true;
	}

	// ------------------------------------------------------------------ streams

	private static boolean streams(Job j, ServerLevel level, Target t) {
		LevelChunk chunk = level.getChunkSource().getChunkNow(t.cx, t.cz);
		Grounds g = HeraldHouse.grounds();
		if (chunk == null || g == null) {
			return chunk != null;
		}
		List<Long> seeds = new ArrayList<>();
		BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
		for (int lx = 0; lx < 16; lx++) {
			for (int lz = 0; lz < 16; lz++) {
				int x = (t.cx << 4) + lx, z = (t.cz << 4) + lz;
				if (!g.inArea(x, z)) {
					continue;
				}
				int top = chunk.getHeight(Heightmap.Types.WORLD_SURFACE, lx, lz);
				for (int y = top; y > top - 64 && y > level.getMinY(); y--) {
					BlockState s = chunk.getBlockState(pos.set(x, y, z));
					if (s.is(Blocks.WATER) && !s.getFluidState().isSource()) {
						seeds.add(pos.asLong());
					} else if (!s.isAir() && !s.canBeReplaced()) {
						break;
					}
				}
			}
		}
		seeds.removeIf(j.streamSeen::contains);
		if (seeds.isEmpty()) {
			return true;
		}
		// What lies in a chunk that is not loaded counts as feeding the stream, so a stream across more chunks than are
		// loaded round this one would always look fed (read back from a real world: 35 of 193 blocks found). The chunks of
		// the area (and a chunk round it) that it reaches are asked for and the step is run again once they are all loaded;
		// beyond them nothing is loaded or generated, and what lies there counts as fed.
		Set<Long> unseen = new HashSet<>();
		Set<Long> unfed = Streams.unfed(seeds, p -> {
			Streams.Water w = water(level, p);
			if (w == Streams.Water.UNSEEN) {
				int x = BlockPos.getX(p), z = BlockPos.getZ(p);
				if (g.areaOverlaps(x - 16, z - 16, x + 16, z + 16)) {
					unseen.add(ChunkPos.pack(x >> 4, z >> 4));
				}
			}
			return w;
		});
		if (!unseen.isEmpty()) {
			for (long c : unseen) {
				ask(level, ChunkPos.getX(c), ChunkPos.getZ(c), 0);
			}
			j.held.addAll(unseen);
			return false;
		}
		// what an earlier chunk's step already found is not counted (nor taken away) twice; this chunk's own seeds are
		// marked only after that (marking them first dropped them from their own stream: 35 of 193 blocks, read back)
		unfed.removeIf(j.streamSeen::contains);
		j.streamSeen.addAll(seeds);
		j.streamSeen.addAll(unfed);
		if (unfed.isEmpty()) {
			return true;
		}
		BlockPos first = BlockPos.of(unfed.iterator().next());
		if (j.apply) {
			for (long p : unfed) {
				// what its tick would have done, as Shores.dry does in a town built today (without updates, as the build)
				level.setBlock(BlockPos.of(p), Blocks.AIR.defaultBlockState(), BuiltRoads.FLAGS);
			}
		}
		j.findings.add(new Finding(Kind.STREAMS, Outcome.REPAIR, first, String.valueOf(unfed.size()), unfed.size()));
		return true;
	}

	private static Streams.Water water(ServerLevel level, long p) {
		BlockPos b = BlockPos.of(p);
		LevelChunk c = level.getChunkSource().getChunkNow(b.getX() >> 4, b.getZ() >> 4);
		if (c == null) {
			return Streams.Water.UNSEEN;
		}
		BlockState s = c.getBlockState(b);
		FluidState f = s.getFluidState();
		if (f.is(Fluids.WATER) || f.is(Fluids.FLOWING_WATER)) {
			return f.isSource() ? Streams.Water.SOURCE : s.is(Blocks.WATER) ? Streams.Water.RUNNING : Streams.Water.SOURCE;
		}
		return Streams.Water.OTHER;
	}

	// ------------------------------------------------------------------ template pieces (wharf, inn)

	private static boolean pieces(Job j, ServerLevel level, Target t) {
		LevelChunk chunk = level.getChunkSource().getChunkNow(t.cx, t.cz);
		if (chunk == null) {
			return false;
		}
		List<TemplatePatch> patches = patches(t.kind);
		for (Map.Entry<net.minecraft.world.level.levelgen.structure.Structure, StructureStart> e : chunk.getAllStarts().entrySet()) {
			Identifier sid = level.registryAccess().lookupOrThrow(Registries.STRUCTURE).getKey(e.getKey());
			if (sid == null || kindOf(sid.toString()) != t.kind || !e.getValue().isValid()) {
				continue;
			}
			BoundingBox box = e.getValue().getBoundingBox();
			int reach = t.kind == Kind.WHARF ? GUARD_REACH : 0;
			boolean ready = true;
			for (int x = (box.minX() - reach) >> 4; x <= (box.maxX() + reach) >> 4; x++) {
				for (int z = (box.minZ() - reach) >> 4; z <= (box.maxZ() + reach) >> 4; z++) {
					if (level.getChunkSource().getChunkNow(x, z) == null
							|| t.kind == Kind.WHARF && !level.areEntitiesLoaded(ChunkPos.pack(x, z))) {
						ask(level, x, z, 0);
						j.held.add(ChunkPos.pack(x, z));
						ready = false;
					}
				}
			}
			if (!ready) {
				return false;
			}
			for (StructurePiece piece : e.getValue().getPieces()) {
				if (!(piece instanceof PoolElementStructurePiece pe) || !(pe.getElement() instanceof SinglePoolElement el)) {
					continue;
				}
				String template = el.getTemplateLocation().toString();
				for (TemplatePatch p : patches) {
					if (p.template().equals(template)) {
						piece(j, level, t.kind, pe, p);
					}
				}
			}
		}
		return true;
	}

	private static BlockPos world(PoolElementStructurePiece pe, int x, int y, int z) {
		StructurePlaceSettings s = new StructurePlaceSettings().setRotation(pe.getRotation());
		return StructureTemplate.calculateRelativePosition(s, new BlockPos(x, y, z)).offset(pe.getPosition());
	}

	private static String id(BlockState s) {
		return BuiltInRegistries.BLOCK.getKey(s.getBlock()).toString();
	}

	/** One placed piece of a patched template: looked at, and (apply) repaired. */
	private static void piece(Job j, ServerLevel level, Kind kind, PoolElementStructurePiece pe, TemplatePatch p) {
		TemplatePatch.Decision d = p.decide(c -> {
			BlockPos w = world(pe, c[0], c[1], c[2]);
			LevelChunk ch = level.getChunkSource().getChunkNow(w.getX() >> 4, w.getZ() >> 4);
			return ch == null ? null : id(ch.getBlockState(w));
		});
		TemplatePatch.Cell c0 = p.cells().get(0);
		BlockPos at = world(pe, c0.x(), c0.y(), c0.z());
		switch (d.verdict()) {
			case CHANGED -> {
				BlockPos w = d.at() == null ? at : world(pe, d.at()[0], d.at()[1], d.at()[2]);
				j.findings.add(new Finding(kind, Outcome.LEFT, w, d.expected() + " → " + d.found()));
				return;
			}
			case DONE -> j.findings.add(new Finding(kind, Outcome.FINE, at, ""));
			case FIX -> {
				if (j.apply) {
					apply(level, pe, p);
				}
				j.findings.add(new Finding(kind, Outcome.REPAIR, at, String.valueOf(d.version())));
			}
		}
		if (kind == Kind.WHARF) {
			guard(j, level, pe, p, d.verdict() == TemplatePatch.Verdict.FIX && !j.apply);
		}
	}

	/** Today's blocks on the patched cells, the containers carried with what they hold. */
	private static void apply(ServerLevel level, PoolElementStructurePiece pe, TemplatePatch p) {
		var blocks = level.registryAccess().lookupOrThrow(Registries.BLOCK);
		var rotation = pe.getRotation();
		Set<String> carried = new HashSet<>();
		int flags = Block.UPDATE_CLIENTS;              // no block updates (a template is placed so), shapes kept in step
		for (TemplatePatch.Move m : p.moves()) {
			BlockPos from = world(pe, m.from()[0], m.from()[1], m.from()[2]), to = world(pe, m.to()[0], m.to()[1], m.to()[2]);
			BlockEntity be = level.getBlockEntity(from);
			TemplatePatch.Cell dest = cell(p, m.to());
			if (be == null || dest == null) {
				continue;
			}
			CompoundTag tag = be.saveWithFullMetadata(level.registryAccess());     // with its id: loadStatic needs it
			BlockState now = parse(blocks, dest.after()).rotate(rotation);
			level.setBlock(to, now, flags);
			BlockEntity nb = BlockEntity.loadStatic(to, now, tag, level.registryAccess());
			if (nb != null) {
				level.setBlockEntity(nb);
			}
			if (be instanceof Container c) {
				c.clearContent();                      // it is all in the new place now: nothing to drop from the old one
			}
			carried.add(key(m.from()));
			carried.add(key(m.to()));
			TemplatePatch.Cell src = cell(p, m.from());
			level.setBlock(from, src == null ? Blocks.AIR.defaultBlockState() : parse(blocks, src.after()).rotate(rotation),
					flags | Block.UPDATE_SKIP_BLOCK_ENTITY_SIDEEFFECTS);
		}
		for (TemplatePatch.Cell c : p.cells()) {
			if (carried.contains(key(new int[] {c.x(), c.y(), c.z()}))) {
				continue;
			}
			level.setBlock(world(pe, c.x(), c.y(), c.z()), parse(blocks, c.after()).rotate(rotation), flags);
		}
	}

	private static String key(int[] p) {
		return p[0] + "," + p[1] + "," + p[2];
	}

	private static TemplatePatch.@Nullable Cell cell(TemplatePatch p, int[] at) {
		for (TemplatePatch.Cell c : p.cells()) {
			if (c.x() == at[0] && c.y() == at[1] && c.z() == at[2]) {
				return c;
			}
		}
		return null;
	}

	static BlockState parse(net.minecraft.core.HolderLookup<Block> blocks, String state) {
		try {
			return BlockStateParser.parseForBlock(blocks, state, false).blockState();
		} catch (com.mojang.brigadier.exceptions.CommandSyntaxException e) {
			throw new IllegalStateException("bad block state in a patch: " + state, e);
		}
	}

	/**
	 * The Wharf Guard: if it is alive and away from its post, and the post holds today's full block with room on it, it is
	 * put back (it attaches to the post's top: the first face a shulker tries). A guard that is not found is only reported:
	 * a player may have killed it, and none is made.
	 */
	private static void guard(Job j, ServerLevel level, PoolElementStructurePiece pe, TemplatePatch p, boolean postToBeFixed) {
		List<int[]> posts;
		synchronized (GUARD_POSTS) {
			posts = GUARD_POSTS.getOrDefault(p.template(), List.of());
		}
		BoundingBox box = pe.getBoundingBox();
		AABB around = new AABB(box.minX() - GUARD_REACH, box.minY() - GUARD_REACH, box.minZ() - GUARD_REACH,
				box.maxX() + 1 + GUARD_REACH, box.maxY() + 1 + GUARD_REACH, box.maxZ() + 1 + GUARD_REACH);
		List<Shulker> guards = level.getEntitiesOfClass(Shulker.class, around, s -> s.entityTags().contains(WHARF_TAG) && guardName(s));
		for (int[] post : posts) {
			BlockPos at = world(pe, post[0], post[1], post[2]);
			if (guards.stream().anyMatch(s -> s.blockPosition().equals(at))) {
				continue;                               // at its post
			}
			Shulker s = guards.stream().filter(g -> posts.stream().noneMatch(q -> world(pe, q[0], q[1], q[2]).equals(g.blockPosition())))
					.findFirst().orElse(null);
			if (s == null) {
				j.findings.add(new Finding(Kind.WHARF, Outcome.NOTICE, at, "no guard"));
				continue;
			}
			BlockPos under = at.below();
			// in a scan the post may still be the old wall: it will be today's full block by the time the guard goes back
			boolean room = level.getBlockState(at).isAir()
					&& (postToBeFixed || level.getBlockState(under).isFaceSturdy(level, under, net.minecraft.core.Direction.UP));
			if (!room) {
				j.findings.add(new Finding(Kind.WHARF, Outcome.LEFT, at, "post " + id(level.getBlockState(under)) + " / " + id(level.getBlockState(at))));
				continue;
			}
			if (j.apply) {
				s.teleportTo(at.getX() + 0.5, at.getY(), at.getZ() + 0.5);
				// held by the post's top from now: a shulker only looks at its hold when it ticks, and in a chunk nobody is
				// near it would keep the face it had where it was (under the pier, read back: AttachFace 1, "up")
				var out = net.minecraft.world.level.storage.TagValueOutput.createWithContext(net.minecraft.util.ProblemReporter.DISCARDING,
						level.registryAccess());
				s.saveWithoutId(out);
				CompoundTag tag = out.buildResult();
				tag.putByte("AttachFace", (byte) net.minecraft.core.Direction.DOWN.get3DDataValue());
				s.load(net.minecraft.world.level.storage.TagValueInput.create(net.minecraft.util.ProblemReporter.DISCARDING,
						level.registryAccess(), tag));
			}
			j.findings.add(new Finding(Kind.WHARF, Outcome.REPAIR, at, "guard at " + s.getBlockX() + " " + s.getBlockY() + " " + s.getBlockZ()));
			guards.remove(s);
		}
	}

	private static boolean guardName(Shulker s) {
		return s.getCustomName() != null && s.getCustomName().getContents() instanceof TranslatableContents tc && GUARD_NAME.equals(tc.getKey());
	}

	// ------------------------------------------------------------------ the end of a job

	private static void finish(MinecraftServer server, Job j) {
		job = null;
		if (j.ringY != null) {
			// grid index v * n + u: OutskirtsPlan.ramps walks both axes, so the orientation does not matter
			int ramps = io.github.albertosa23.heraldia.herald.OutskirtsPlan.ramps(j.ringN, j.ringY, j.ringIn);
			Grounds g = HeraldHouse.grounds();
			j.findings.add(new Finding(Kind.RING, Outcome.NOTICE, g == null ? BlockPos.ZERO : new BlockPos(g.centerX(), g.groundY(), g.centerZ()),
					String.valueOf(ramps)));
		}
		long ms = System.currentTimeMillis() - j.started;
		String slowest = j.worstStep + " " + j.worst / 1_000_000 + " ms (" + (j.worstCpu < 0 ? "?" : j.worstCpu / 1_000_000) + " ms of work)";
		LOGGER.info("Heraldia: update mend {} {}: {} steps, {} ms on the server thread, the slowest {}; {}", j.apply ? "apply" : "scan", j.id,
				j.steps, j.nanos / 1_000_000, slowest, counts(j));
		for (Finding f : j.findings) {
			if (f.outcome != Outcome.FINE) {
				LOGGER.info("Heraldia: update mend {} {}: {} {} at {} {} {} {}", j.apply ? "apply" : "scan", j.id, f.kind.word,
						f.outcome.name().toLowerCase(Locale.ROOT), f.at.getX(), f.at.getY(), f.at.getZ(), f.detail);
			}
		}
		Path file = Analysis.folder(server).resolve("mend-" + j.id + (j.apply ? "-apply" : "-scan") + ".txt");
		try {
			Files.createDirectories(file.getParent());
			StringBuilder sb = new StringBuilder();
			sb.append("Heraldia update mend ").append(j.apply ? "apply" : "scan").append(' ').append(j.id).append('\n')
					.append(j.steps).append(" steps, ").append(j.nanos / 1_000_000).append(" ms on the server thread, the slowest ")
					.append(slowest).append(", ").append(ms).append(" ms in all\n");
			for (Finding f : j.findings) {
				sb.append(f.kind.word).append(' ').append(f.outcome.name().toLowerCase(Locale.ROOT)).append(' ')
						.append(f.at.getX()).append(' ').append(f.at.getY()).append(' ').append(f.at.getZ()).append(' ').append(f.detail).append('\n');
			}
			Files.writeString(file, sb.toString());
		} catch (IOException e) {
			LOGGER.warn("Heraldia: update mend: the report could not be written ({})", e.getMessage());
		}
		Map<String, String> l = j.lang;
		j.source.sendSuccess(() -> Texts.t(l, j.apply ? "heraldia.actualizar.reparar.titulo.hecho" : "heraldia.actualizar.reparar.titulo", j.steps,
				j.worst / 1_000_000).withStyle(ChatFormatting.GOLD), true);
		summary(l, j.kinds, j.findings, j.apply).forEach(c -> j.source.sendSuccess(() -> c, false));
		j.source.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.reparar.informe", file.toString()).withStyle(ChatFormatting.GRAY), false);
		if (!j.apply) {
			last = new Scan(j.id, System.currentTimeMillis(), j.kinds, targetsToRepair(j), List.copyOf(j.findings));
			if (j.onDone != null) {
				j.onDone.run();
			} else {
				j.source.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.reparar.nada_cambia").withStyle(ChatFormatting.GRAY), false);
			}
		}
	}

	/** The targets with something to repair (the confirmation looks at these again, and only these). */
	private static List<Target> targetsToRepair(Job j) {
		List<Target> out = new ArrayList<>();
		for (Target t : j.targets) {
			boolean any = j.findings.stream().anyMatch(f -> f.kind == t.kind && f.outcome == Outcome.REPAIR && within(f.at, t));
			// the streams are looked at again over the whole area if anything there is repaired: draining a pond that stood in
			// the air leaves running water with no source that was fed when the scan ran (read back from a world of an
			// earlier jar: 739 blocks), as a town built today dries after it settles its shores
			boolean area = t.kind == Kind.STREAMS && j.findings.stream().anyMatch(f -> (f.kind == Kind.STREAMS || f.kind == Kind.WATER)
					&& f.outcome == Outcome.REPAIR);
			if (any || area) {
				out.add(t);
			}
		}
		return out;
	}

	private static boolean within(BlockPos at, Target t) {
		return Math.abs((at.getX() >> 4) - t.cx) <= 4 && Math.abs((at.getZ() >> 4) - t.cz) <= 4;
	}

	private static String counts(Job j) {
		StringBuilder sb = new StringBuilder();
		for (Kind k : j.kinds) {
			long[] n = new long[Outcome.values().length];
			j.findings.stream().filter(f -> f.kind == k).forEach(f -> n[f.outcome.ordinal()]++);
			long blocks = j.findings.stream().filter(f -> f.kind == k).mapToLong(Finding::blocks).sum();
			sb.append(sb.isEmpty() ? "" : "; ").append(k.word).append(": ").append(n[0]).append(j.apply ? " repaired, " : " to repair, ")
					.append(n[1]).append(" fine, ").append(n[2]).append(" left alone, ").append(n[3]).append(" notices");
			if (blocks > 0) {
				sb.append(" (").append(blocks).append(" blocks)");
			}
		}
		return sb.toString();
	}

	/** Is a job running? (for /heraldia status and the tests) */
	public static boolean busy() {
		return job != null || discovering;
	}
}
