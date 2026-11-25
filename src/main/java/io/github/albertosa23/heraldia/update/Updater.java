package io.github.albertosa23.heraldia.update;

import com.mojang.brigadier.builder.LiteralArgumentBuilder;
import com.mojang.brigadier.context.CommandContext;
import com.mojang.serialization.Codec;
import io.github.albertosa23.heraldia.Heraldia;
import io.github.albertosa23.heraldia.command.Texts;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import net.fabricmc.fabric.api.attachment.v1.AttachmentRegistry;
import net.fabricmc.fabric.api.attachment.v1.AttachmentType;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.core.Holder;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.HoverEvent;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.contents.TranslatableContents;
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
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.item.ItemStack;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Safe updates (T46): the mod version the world was generated with ({@link WorldVersion}), the per-version fixes
 * applied lazily ({@link Fixes}, {@link MobFixes}) and bringing what is new to an existing world
 * ({@link Analysis}, {@link Execution}). Operator commands under /heraldia update (in English, in command/HeraldiaCommands):
 * <ul>
 * <li>{@code analyze}: report of what would be protected, regenerated and placed; it changes nothing;</li>
 * <li>{@code apply}: the same analysis and a dialog to confirm, with or without a backup (without a backup, another
 * confirmation of the risk); on confirming, it warns the players and stops the server, which the administrator starts
 * again by hand: the work is done at startup;</li>
 * <li>{@code undo}: restores the backup of the last apply (also at startup);</li>
 * <li>{@code repair [dry-run]}: forces the fixes on everything loaded (or only says what it would change).</li>
 * </ul>
 * One line in Heraldia.onInitialize.
 */
public final class Updater {
	private static final Logger LOGGER = LoggerFactory.getLogger(Heraldia.MOD_ID);
	/** A world is new (it is treated as generated with this version) if less than this time has passed at its first startup. */
	public static final long NEW_WORLD_TICKS = 1200;
	/** How long an analysis for apply lasts: after this, it has to be repeated. */
	static final long VALIDITY_MS = 15 * 60_000;
	/** Ticks between the warning to the players and the server stopping. */
	static final int NOTICE_TICKS = 200;
	private static final AtomicBoolean ANALYZING = new AtomicBoolean();
	private static volatile Analysis.Report last;
	private static volatile long lastMs;
	private static int stop = -1;

	private Updater() {
	}

	/** Fix mark of each checked mob (the level of {@link MobFixes#LEDGER}); kept apart for the tests. */
	static final class Type {
		static final AttachmentType<Integer> FIXES = AttachmentRegistry.create(Heraldia.id("arreglos"), b -> b.persistent(Codec.INT));

		private Type() {
		}
	}

	public static void register() {
		WorldVersion.Type.VERSION.identifier();
		Type.FIXES.identifier();
		io.github.albertosa23.heraldia.command.Preferences.register();
		ServerEntityEvents.ENTITY_LOAD.register((entity, level) -> onLoad(entity));
		ServerLifecycleEvents.SERVER_STARTING.register(Execution::onBegin);
		ServerLifecycleEvents.SERVER_STARTED.register(Updater::onStart);
		ServerLifecycleEvents.SERVER_STARTED.register(Execution::onStart);
		ServerTickEvents.END_SERVER_TICK.register(Updater::tick);
	}

	// ------------------------------------------------------------------ world version

	static String version() {
		return FabricLoader.getInstance().getModContainer(Heraldia.MOD_ID).map(c -> c.getMetadata().getVersion().getFriendlyString()).orElse("?");
	}

	private static void onStart(MinecraftServer server) {
		ServerLevel ow = server.overworld();
		Optional<WorldVersion> before = Optional.ofNullable(ow.getAttached(WorldVersion.Type.VERSION));
		String actual = version();
		WorldVersion now = WorldVersion.onStart(before, actual, ow.getGameTime(), NEW_WORLD_TICKS, MobFixes.LEDGER.tier());
		if (WorldVersion.backsOff(before, actual)) {
			LOGGER.warn("Heraldia: el mundo se abrió antes con la versión {}, más nueva que esta ({}): lo nuevo de aquella no se deshace",
					before.get().latest(), actual);
		}
		ow.setAttached(WorldVersion.Type.VERSION, now);
		LOGGER.info("Heraldia: mundo generado con la versión {}, abierto antes con {}, ahora con {} (nivel de arreglos {})",
				now.generated(), before.map(WorldVersion::latest).orElse("ninguna"), actual, MobFixes.LEDGER.tier());
	}

	/** The world's saved version (for /heraldia status and the tests). */
	public static Optional<WorldVersion> worldVersion(MinecraftServer server) {
		return Optional.ofNullable(server.overworld().getAttached(WorldVersion.Type.VERSION));
	}

	// ------------------------------------------------------------------ lazy fixes

	/** When an entity loads: if it is a template mob without the current level's mark, its pending fixes. */
	static void onLoad(Entity entity) {
		if (!(entity instanceof Mob mob) || mob.entityTags().isEmpty() && !mob.hasCustomName()) {
			return;                       // early exit: almost all entities
		}
		MobView v = new MobView(mob);
		if (!MobFixes.fromTemplate(v)) {
			return;
		}
		Integer mark = mob.getAttached(Type.FIXES);
		int m = mark == null ? 0 : mark;
		if (!MobFixes.LEDGER.pending(m)) {
			return;
		}
		Map<String, Fixes.Effect> e = MobFixes.LEDGER.execute(v, m, false, false);
		mob.setAttached(Type.FIXES, MobFixes.LEDGER.tier());
		if (!e.isEmpty()) {
			LOGGER.info("Heraldia: arreglos {} en {} ({}) en {} {} {}", e, BuiltInRegistries.ENTITY_TYPE.getKey(mob.getType()),
					mob.getUUID(), mob.getBlockX(), mob.getBlockY(), mob.getBlockZ());
		}
	}

	/** /heraldia update repair: the fixes on all loaded mobs, without looking at the mark. */
	static Fixes.Tally repair(MinecraftServer server, boolean dryRun) {
		Fixes.Tally tally = new Fixes.Tally();
		for (ServerLevel level : server.getAllLevels()) {
			List<Mob> mobs = new ArrayList<>();
			for (Entity e : level.getAllEntities()) {
				if (e instanceof Mob m) {
					mobs.add(m);
				}
			}
			for (Mob mob : mobs) {
				MobView v = new MobView(mob);
				if (!MobFixes.fromTemplate(v)) {
					continue;
				}
				tally.add(MobFixes.LEDGER.execute(v, 0, dryRun, true));
				if (!dryRun) {
					mob.setAttached(Type.FIXES, MobFixes.LEDGER.tier());
				}
			}
		}
		LOGGER.info("Heraldia: update repair{}: {} mobs de plantilla revisados, {} cambios {}", dryRun ? " dry-run" : "",
				tally.checked(), tally.changes(), summary(tally));
		return tally;
	}

	static String summary(Fixes.Tally c) {
		StringBuilder sb = new StringBuilder("{");
		c.byId().forEach((id, v) -> sb.append(sb.length() > 1 ? ", " : "").append(id).append('=').append(v[0]).append('/').append(v[1]));
		return sb.append('}').toString();
	}

	/** {@link MobFixes.Mob} over a real mob. */
	record MobView(Mob mob) implements MobFixes.Mob {
		private static String route(Entity e) {
			return BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).getPath();
		}

		@Override
		public String type() {
			return route(mob);
		}

		@Override
		public Set<String> tags() {
			return mob.entityTags();
		}

		@Override
		public void tagIt(String tag) {
			mob.addTag(tag);
		}

		@Override
		public String nameKey() {
			Component n = mob.getCustomName();
			return n != null && n.getContents() instanceof TranslatableContents t ? t.getKey() : null;
		}

		@Override
		public boolean persistent() {
			return mob.isPersistenceRequired();
		}

		@Override
		public boolean baby() {
			return mob.isBaby();
		}

		@Override
		public void makeAdult() {
			mob.setBaby(false);
		}

		@Override
		public String mount() {
			Entity v = mob.getVehicle();
			return v == null ? null : route(v);
		}

		@Override
		public boolean ownMount() {
			Entity v = mob.getVehicle();
			return v != null && (v.hasCustomName() || v.getPassengers().size() > 1);
		}

		@Override
		public void removeMount() {
			Entity v = mob.getVehicle();
			mob.stopRiding();
			if (v != null) {
				v.discard();
			}
		}

		@Override
		public boolean picksUp() {
			return mob.canPickUpLoot();
		}

		@Override
		public void noPickup() {
			mob.setCanPickUpLoot(false);
		}

		@Override
		public String weapon() {
			ItemStack s = mob.getMainHandItem();
			return s.isEmpty() ? null : BuiltInRegistries.ITEM.getKey(s.getItem()).getPath();
		}

		@Override
		public boolean specialWeapon() {
			ItemStack s = mob.getMainHandItem();
			return s.isEnchanted() || s.has(DataComponents.CUSTOM_NAME);
		}
	}

	// ------------------------------------------------------------------ commands

	/** /heraldia update analyze | apply ... | undo ... | repair [dry-run] (added to VersionNotice's "update"). */
	public static LiteralArgumentBuilder<CommandSourceStack> node() {
		return Commands.literal("update")
				.requires(Commands.hasPermission(Commands.LEVEL_GAMEMASTERS))
				.then(Commands.literal("analyze").executes(c -> analyze(c, false)))
				.then(Commands.literal("apply").executes(c -> analyze(c, true))
						.then(Commands.literal("confirm").then(Commands.argument("id", com.mojang.brigadier.arguments.StringArgumentType.word())
								.then(Commands.literal("backup").executes(c -> confirm(c, true, false)))
								.then(Commands.literal("nobackup").executes(c -> confirm(c, false, false))
										.then(Commands.literal("risk").executes(c -> confirm(c, false, true)))))))
				.then(Commands.literal("undo").executes(Updater::undo)
						.then(Commands.literal("confirm").then(Commands.argument("id", com.mojang.brigadier.arguments.StringArgumentType.word())
								.executes(Updater::confirmUndo))))
				.then(Commands.literal("repair").executes(c -> repair(c, false))
						.then(Commands.literal("dry-run").executes(c -> repair(c, true))))
				.then(GenerationMend.node());
	}

	private static Map<String, String> language(CommandSourceStack src) {
		ServerPlayer p = src.getPlayer();
		return p != null ? Texts.language(p) : Texts.language("es_es");
	}

	private static int analyze(CommandContext<CommandSourceStack> ctx, boolean apply) {
		CommandSourceStack src = ctx.getSource();
		Map<String, String> l = language(src);
		if (apply && !Analysis.protections().isEmpty()) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.protecciones", String.join(", ", Analysis.protections())));
			return 0;
		}
		if (!ANALYZING.compareAndSet(false, true)) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.ocupado"));
			return 0;
		}
		src.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.analizando").withStyle(ChatFormatting.GRAY), true);
		MinecraftServer server = src.getServer();
		Analysis.start(server, m -> LOGGER.info("Heraldia: update analyze: {}", m)).whenComplete((inf, err) -> server.execute(() -> {
			ANALYZING.set(false);
			if (err != null) {
				src.sendFailure(Texts.t(l, "heraldia.actualizar.error", String.valueOf(err.getMessage())));
				return;
			}
			last = inf;
			lastMs = System.currentTimeMillis();
			lines(l, inf).forEach(t -> src.sendSuccess(() -> t, true));
			if (apply) {
				offer(src, l, inf);
			}
		}));
		return 1;
	}

	/** The analysis summary as translatable lines. */
	static List<Component> lines(Map<String, String> l, Analysis.Report i) {
		Detector.Result r = i.result();
		List<Component> out = new ArrayList<>();
		out.add(Texts.t(l, "heraldia.actualizar.titulo", i.chunks(), i.margin()).withStyle(ChatFormatting.GOLD));
		out.add(Texts.t(l, "heraldia.actualizar.protegidos", r.builds().size(), r.tally(Detector.Kind.BUILD),
				r.tally(Detector.Kind.PROTECTED)).withStyle(ChatFormatting.YELLOW));
		out.add(Texts.t(l, "heraldia.actualizar.regenerar", i.regenerate().size(), r.tally(Detector.Kind.PRISTINE), i.cutPristine())
				.withStyle(ChatFormatting.GREEN));
		out.add(Texts.t(l, "heraldia.actualizar.colocar", i.place().size(), i.unsafePlacements()).withStyle(ChatFormatting.AQUA));
		if (!i.protections().isEmpty()) {
			out.add(Texts.t(l, "heraldia.actualizar.protecciones", String.join(", ", i.protections())).withStyle(ChatFormatting.RED));
		}
		out.add(Texts.t(l, "heraldia.actualizar.informe", i.file().toString(), i.mapPng().getFileName().toString()).withStyle(ChatFormatting.GRAY));
		out.add(Texts.t(l, "heraldia.actualizar.nada_cambia").withStyle(ChatFormatting.GRAY));
		return out;
	}

	/** apply: the dialog (or the commands, in the console) to confirm, with or without a backup. */
	private static void offer(CommandSourceStack src, Map<String, String> l, Analysis.Report i) {
		if (i.regenerate().isEmpty() && i.place().isEmpty()) {
			src.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.nada_que_hacer").withStyle(ChatFormatting.GREEN), true);
			return;
		}
		String base = "heraldia update apply confirm " + i.id() + " ";
		ServerPlayer p = src.getPlayer();
		if (p == null) {
			src.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.confirmar_consola", base + "backup", base + "nobackup risk"), false);
			return;
		}
		List<DialogBody> body = new ArrayList<>();
		lines(l, i).forEach(t -> body.add(new PlainMessage(t, 300)));
		body.add(new PlainMessage(Texts.t(l, "heraldia.actualizar.aviso_parada").withStyle(ChatFormatting.RED), 300));
		List<ActionButton> b = List.of(
				button(Texts.t(l, "heraldia.actualizar.boton.copia"), Texts.t(l, "heraldia.actualizar.boton.copia.ayuda"), base + "backup"),
				button(Texts.t(l, "heraldia.actualizar.boton.sin_copia"), Texts.t(l, "heraldia.actualizar.boton.sin_copia.ayuda"), base + "nobackup"));
		p.openDialog(Holder.direct(new MultiActionDialog(new CommonDialogData(Texts.t(l, "heraldia.actualizar.dialogo"), Optional.empty(),
				true, false, DialogAction.CLOSE, body, List.of()), b,
				Optional.of(new ActionButton(new CommonButtonData(Texts.t(l, "heraldia.actualizar.boton.cancelar"), 150), Optional.empty())), 2)));
	}

	private static ActionButton button(Component text, Component help, String cmd) {
		return new ActionButton(new CommonButtonData(text, Optional.of(help), 150), Optional.of(new StaticAction(new ClickEvent.RunCommand(cmd))));
	}

	private static int confirm(CommandContext<CommandSourceStack> ctx, boolean backup, boolean risk) {
		CommandSourceStack src = ctx.getSource();
		Map<String, String> l = language(src);
		String id = com.mojang.brigadier.arguments.StringArgumentType.getString(ctx, "id");
		Analysis.Report i = last;
		if (i == null || !i.id().equals(id) || System.currentTimeMillis() - lastMs > VALIDITY_MS) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.caducado"));
			return 0;
		}
		if (!Analysis.protections().isEmpty()) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.protecciones", String.join(", ", Analysis.protections())));
			return 0;
		}
		if (!backup && !risk) {         // without a backup: another, explicit confirmation
			String cmd = "heraldia update apply confirm " + id + " nobackup risk";
			ServerPlayer p = src.getPlayer();
			if (p == null) {
				src.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.riesgo_consola", cmd).withStyle(ChatFormatting.RED), false);
			} else {
				p.openDialog(Holder.direct(new MultiActionDialog(new CommonDialogData(Texts.t(l, "heraldia.actualizar.riesgo.titulo"),
						Optional.empty(), true, false, DialogAction.CLOSE,
						List.of(new PlainMessage(Texts.t(l, "heraldia.actualizar.riesgo").withStyle(ChatFormatting.RED), 300)),
						List.of()), List.of(button(Texts.t(l, "heraldia.actualizar.boton.riesgo"), Texts.t(l, "heraldia.actualizar.boton.riesgo.ayuda"), cmd)),
						Optional.of(new ActionButton(new CommonButtonData(Texts.t(l, "heraldia.actualizar.boton.cancelar"), 150), Optional.empty())), 1)));
			}
			return 1;
		}
		MinecraftServer server = src.getServer();
		Plan plan = i.plan(backup);
		try {
			plan.save(Execution.plan(server));
		} catch (IOException e) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.error", e.getMessage()));
			return 0;
		}
		last = null;
		LOGGER.info("Heraldia: update apply confirmado por {} ({} copia): {} chunks a regenerar, {} estructuras; el servidor se para en {} s",
				src.getTextName(), backup ? "con" : "sin", plan.regenerate.size(), plan.place.size(), NOTICE_TICKS / 20);
		src.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.confirmado", NOTICE_TICKS / 20).withStyle(ChatFormatting.GOLD), true);
		warnAndStop(server);
		return 1;
	}

	private static void warnAndStop(MinecraftServer server) {
		for (ServerPlayer p : server.getPlayerList().getPlayers()) {
			p.sendSystemMessage(Texts.t(Texts.language(p), "heraldia.actualizar.aviso_jugadores", NOTICE_TICKS / 20).withStyle(ChatFormatting.RED));
		}
		stop = NOTICE_TICKS;
	}

	private static void tick(MinecraftServer server) {
		Execution.tick(server);
		GenerationMend.tick(server);
		if (stop > 0 && --stop == 0) {
			stop = -1;
			LOGGER.warn("Heraldia: update apply: se para el servidor; vuelve a arrancarlo a mano para hacer el trabajo");
			server.halt(false);
		}
	}

	private static int undo(CommandContext<CommandSourceStack> ctx) {
		CommandSourceStack src = ctx.getSource();
		Map<String, String> l = language(src);
		Optional<Plan> p = Execution.lastWithBackup(src.getServer());
		if (p.isEmpty()) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.sin_copia"));
			return 0;
		}
		String cmd = "heraldia update undo confirm " + p.get().id;
		MutableComponent b = Texts.t(l, "heraldia.actualizar.boton.deshacer").withStyle(s -> s.withColor(ChatFormatting.RED)
				.withClickEvent(new ClickEvent.RunCommand(cmd)).withHoverEvent(new HoverEvent.ShowText(Component.literal("/" + cmd))));
		src.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.deshacer", p.get().id, p.get().date, "/" + cmd).append(" ").append(b), false);
		return 1;
	}

	private static int confirmUndo(CommandContext<CommandSourceStack> ctx) {
		CommandSourceStack src = ctx.getSource();
		Map<String, String> l = language(src);
		String id = com.mojang.brigadier.arguments.StringArgumentType.getString(ctx, "id");
		Optional<Plan> p = Execution.lastWithBackup(src.getServer());
		if (p.isEmpty() || !p.get().id.equals(id)) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.sin_copia"));
			return 0;
		}
		Plan d = p.get();
		d.phase = Plan.UNDO;
		try {
			d.save(Execution.undo(src.getServer()));
		} catch (IOException e) {
			src.sendFailure(Texts.t(l, "heraldia.actualizar.error", e.getMessage()));
			return 0;
		}
		LOGGER.info("Heraldia: update undo {} confirmado por {}; el servidor se para", id, src.getTextName());
		src.sendSuccess(() -> Texts.t(l, "heraldia.actualizar.confirmado", NOTICE_TICKS / 20).withStyle(ChatFormatting.GOLD), true);
		warnAndStop(src.getServer());
		return 1;
	}

	private static int repair(CommandContext<CommandSourceStack> ctx, boolean dryRun) {
		CommandSourceStack src = ctx.getSource();
		Map<String, String> l = language(src);
		Fixes.Tally c = repair(src.getServer(), dryRun);
		src.sendSuccess(() -> Texts.t(l, dryRun ? "heraldia.arreglos.prueba" : "heraldia.arreglos.hecho", c.checked(), c.changes())
				.withStyle(ChatFormatting.GOLD), true);
		c.byId().forEach((id, v) -> src.sendSuccess(() -> Texts.t(l, "heraldia.arreglos.linea", Texts.t(l, "heraldia.arreglos." + id), v[0], v[1]), false));
		return c.changes();
	}
}
