package io.github.albertosa23.heraldia.inhabitants;

import io.github.albertosa23.heraldia.config.HeraldiaConfig;
import io.github.albertosa23.heraldia.update.MobFixes;
import java.util.List;
import java.util.Set;
import java.util.function.BiPredicate;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.minecraft.core.BlockPos;
import net.minecraft.core.GlobalPos;
import net.minecraft.core.Holder;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.ai.memory.MemoryModuleType;
import net.minecraft.world.entity.ai.village.poi.PoiType;
import net.minecraft.world.entity.npc.villager.Villager;
import net.minecraft.world.phys.Vec3;
import org.jspecify.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Inhabitants of the medium structures (tools/gen/mediums/_inhabitants.py): the villagers who live in the inn, the mill,
 * the fisher's hut, the hunters' lodge, the watchtower and the hermitage, and the inn's pigs. They come in the templates
 * (the game spawns them when the structure generates) and live with vanilla AI: this class does nothing every tick.
 * <p>
 * The option {@link #OPTION} (on by default, off in the light profile) is applied once per inhabitant, the first time it
 * loads ({@code ENTITY_LOAD}, early exit when it has no {@link #TAG}): on, it is marked {@link #SEEN} and lives; off,
 * the inhabitants that were still figures in earlier versions ({@link #STILL_BEFORE}) become still again ({@code NoAI})
 * and the new ones are removed. Once seen, an inhabitant is never touched again: changing the option does not change what
 * a world already has.
 * <p>
 * The one other thing it does is {@link #givingUp}: it is called only from inside {@code Villager.releasePoi}, when the
 * game is about to make a villager give up a bed or a workstation it remembers, and puts a LOST inhabitant back at it.
 */
public final class Inhabitants {
	private static final Logger LOGGER = LoggerFactory.getLogger("heraldia");
	public static final String OPTION = "medianas.habitantes";
	public static final String TAG = MobFixes.INHABITANT;
	public static final String STILL_BEFORE = "heraldia_habitante.quieto_antes", SEEN = "heraldia_habitante.visto";
	/**
	 * Blocks from the remembered block beyond which an inhabitant that is about to give it up counts as lost instead of
	 * badly housed. It is a villager's own {@code follow_range} in 26.3: its path search opens no node whose walked
	 * distance reaches 16, so from further away than that there was never a path home to find, whatever the building
	 * looks like (mediums/_paths). Within that reach a failure IS the building's fault and must stay visible — the
	 * build's trap audit ({@code mediums/_paths.trap_walk}, {@code stranded}) and medium_structures.py's settle check
	 * are what catch it — so {@link #givingUp} never touches it.
	 * <p>
	 * Measured <b>flat</b>, as {@code trap_walk} measures its own (it only looks at cells within
	 * {@code hypot(dx, dz) <= FOLLOW_RANGE} of the bed): a villager stranded on a roof or a tower top of its own
	 * structure is a few blocks away on the ground however high it is, so it is never rescued and the settle check
	 * still goes red on it. Only the terrain outside, which no audit models, is far enough out.
	 */
	public static final int LOST_BLOCKS = 16;
	/**
	 * The two blocks an inhabitant needs and the only two {@code SetWalkTargetFromBlockMemory} makes it give up: its
	 * bed and its workstation. {@code Villager.releaseAllPois} lets go of every one of them at once in two other
	 * places — when the villager dies (it is not alive then, so nothing is done) and when lightning turns it into a
	 * witch; in that second case a hermit struck while lost would be moved to his bed and the witch would appear
	 * there instead of where the bolt fell. That is cosmetic, needs a thunderbolt to land on a lost inhabitant, and
	 * there is no way to tell the conversion apart at this point: it is left as it is on purpose.
	 */
	private static final Set<MemoryModuleType<GlobalPos>> OWN = Set.of(MemoryModuleType.HOME, MemoryModuleType.JOB_SITE);

	/** What to do with an entity when it loads. */
	enum Action { NONE, LIVE, STILL, REMOVE }

	private Inhabitants() {
	}

	public static void register() {
		ServerEntityEvents.ENTITY_LOAD.register((entity, level) -> onLoad(entity));
		ServerLifecycleEvents.SERVER_STARTED.register(server -> LOGGER.info("Heraldia: habitantes de las medianas: {}",
				enabled() ? "activados" : "desactivados"));
	}

	static boolean enabled() {
		HeraldiaConfig c = HeraldiaConfig.get();
		return !c.has(OPTION) || c.getBool(OPTION);
	}

	/** The decision (pure logic, tested in InhabitantsTest). */
	static Action decide(Set<String> tags, boolean enabled) {
		if (tags.isEmpty() || !tags.contains(TAG) || tags.contains(SEEN)) {
			return Action.NONE;
		}
		if (enabled) {
			return Action.LIVE;
		}
		return tags.contains(STILL_BEFORE) ? Action.STILL : Action.REMOVE;
	}

	static void onLoad(Entity e) {
		Set<String> tags = e.entityTags();
		if (tags.isEmpty() || !tags.contains(TAG)) {
			return;                                   // almost every entity: one set lookup
		}
		switch (decide(tags, enabled())) {
			case LIVE -> e.addTag(SEEN);
			case STILL -> {
				if (e instanceof Mob m) {
					m.setNoAi(true);
				}
				e.addTag(SEEN);
			}
			case REMOVE -> e.discard();
			case NONE -> {
			}
		}
	}

	/**
	 * Is this villager a lost inhabitant, to be put back at the block it is about to give up? (pure logic, tested in
	 * InhabitantsTest). `blocks` is the distance from the villager to that block and `stillThere` says the block is
	 * still a point of interest of the kind the memory is for: a bed a player broke, or a profession the villager has
	 * lost, is given up as always.
	 */
	static boolean rescue(Set<String> tags, boolean enabled, boolean alive, boolean sameDimension, boolean stillThere,
			double blocks) {
		return enabled && alive && sameDimension && stillThere && !tags.isEmpty() && tags.contains(TAG)
				&& blocks > LOST_BLOCKS;
	}

	/**
	 * The game is about to make a villager give up a bed or a workstation it remembers
	 * ({@code Villager.releasePoi}, which {@code SetWalkTargetFromBlockMemory} calls after the 1,200 ticks it gives it
	 * to reach the block, and also at once when the block is further than its memory's limit and 1,000 tries find no
	 * step toward it; the constants are the game's own, read with javap on 26.3's {@code VillagerGoalPackages}: bed
	 * close-enough 1, limit 150, 1,200 ticks; workstation 9, 100, 1,200. A lost inhabitant is 12 to 25 blocks from its
	 * block, far inside those limits, so it is always the 1,200 ticks that take the memory). An inhabitant of a medium structure that is further from it than {@link #LOST_BLOCKS} is put
	 * back at it; the release and the memory still go, which is what frees the point of interest's ticket, and from
	 * beside its bed the villager claims it again on one of the next ticks.
	 * <p>
	 * Why an inhabitant needs it and a village villager does not: the structure stands alone on the seed's real
	 * terrain, and a villager walks DOWN a drop of three blocks and only climbs UP one. A hillside, a leaf canopy or an
	 * open cave shaft inside its day's stroll is a one-way street with no path home out of it, and the templates are
	 * audited standing on flat ground, so no audit of the build sees it (docs/LESSONS.md, "A villager gets by physics
	 * to places its path search cannot leave"). Measured on the test seed: the hermit of the dark-forest hermitage at
	 * -128, -1664 and the natural shaft nine blocks east of it, where he lost his bed AND his lectern 2 times in 2.
	 * It is not one structure's fault: the farmer of the roadside inn at -896, -192 ended six blocks below its own bed
	 * 12.4 blocks away, never moved again, and lost its bed 431 ticks later while the bed was still a bed.
	 * <p>
	 * Cost: nothing per tick. It runs only inside {@code releasePoi}, which the game calls when a villager gives a
	 * point of interest up (not every tick, and not at all for most villagers), and for every villager that is not an
	 * inhabitant it leaves on one set lookup.
	 */
	public static void givingUp(Villager v, MemoryModuleType<GlobalPos> memory) {
		Set<String> tags = v.entityTags();
		if (tags.isEmpty() || !tags.contains(TAG)) {
			return;                                   // every other villager in the world: one set lookup
		}
		if (!OWN.contains(memory) || !(v.level() instanceof ServerLevel level)) {
			return;
		}
		GlobalPos at = v.getBrain().getMemory(memory).orElse(null);
		if (at == null) {
			return;
		}
		BlockPos pos = at.pos();
		double dx = v.getX() - (pos.getX() + 0.5), dz = v.getZ() - (pos.getZ() + 0.5);
		double blocks = Math.sqrt(dx * dx + dz * dz);          // flat: see LOST_BLOCKS
		if (!rescue(tags, enabled(), v.isAlive(), at.dimension().equals(level.dimension()), stillThere(level, v, memory, pos),
				blocks)) {
			return;
		}
		Vec3 back = landing(level, v, pos);
		if (back == null) {
			LOGGER.info("Heraldia: habitante perdido a {} bloques de {} en {}: no hay sitio libre donde devolverlo",
					Math.round(blocks), memory.toString(), pos.toShortString());
			return;
		}
		v.snapTo(back.x(), back.y(), back.z(), v.getYRot(), 0.0f);
		LOGGER.info("Heraldia: habitante perdido a {} bloques de {} en {}: devuelto a {}", Math.round(blocks),
				memory.toString(), pos.toShortString(), BlockPos.containing(back).toShortString());
	}

	/** Is the remembered block still a point of interest of the kind the memory is for? (the game's own test) */
	private static boolean stillThere(ServerLevel level, Villager v, MemoryModuleType<GlobalPos> memory, BlockPos pos) {
		BiPredicate<Villager, Holder<PoiType>> ofThisMemory = Villager.POI_MEMORIES.get(memory);
		if (ofThisMemory == null) {
			return false;
		}
		Holder<PoiType> type = level.getPoiManager().getType(pos).orElse(null);
		return type != null && ofThisMemory.test(v, type);
	}

	/**
	 * A free cell to put the villager back in: beside the block first (where the side of its bed is), then on top of
	 * it. A cell with something under it is preferred over one hanging over a drop, so an outdoor workstation does not
	 * hand the villager a fall; with none of either, nothing is moved.
	 */
	private static @Nullable Vec3 landing(ServerLevel level, Villager v, BlockPos pos) {
		Vec3 hanging = null;
		for (BlockPos p : List.of(pos.north(), pos.south(), pos.east(), pos.west(), pos.above(), pos)) {
			Vec3 spot = new Vec3(p.getX() + 0.5, p.getY(), p.getZ() + 0.5);
			if (!level.noCollision(v, v.getType().getSpawnAABB(spot))) {
				continue;
			}
			if (!level.getBlockState(p.below()).isAir()) {
				return spot;
			}
			if (hanging == null) {
				hanging = spot;
			}
		}
		return hanging;
	}
}
