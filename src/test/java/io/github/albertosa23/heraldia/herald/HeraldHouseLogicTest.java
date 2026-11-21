package io.github.albertosa23.heraldia.herald;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.github.albertosa23.heraldia.arena.Site;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/**
 * The Herald's House pure logic: the blueprint in the .jar, the protected area (footprint and a ring of at least 50
 * blocks), who may change what, the stall rent (lazy, with warning and grace) and the site choice near spawn.
 */
class HeraldHouseLogicTest {
	private static final HousePlan PLAN = HousePlan.fromJar();
	private static final Grounds G = new Grounds(1000, 60, -2000, PLAN);

	/**
	 * The chunks a stretch of one gate's road needs loaded before it is laid (herald/Building.roadChunks): every chunk the
	 * stretch's own columns fall in, its verges and the signpost's column included, for each of the four gates; and the
	 * stretches of the whole ring leave no chunk of the walk out. Before the road was laid a stretch at a time it walked
	 * the whole ring in one step and generated the land under it on the server thread (168-233 ms there).
	 */
	@Test
	void everyChunkOfARoadStretchIsAskedForBeforeItIsLaid() {
		int[] across = PLAN.road();
		for (String side : PLAN.gates().keySet()) {
			net.minecraft.core.Direction d = net.minecraft.core.Direction.byName(side);
			assertNotNull(d, side);
			int[] gate = PLAN.gates().get(side);
			int gx = G.ox() + gate[0], gz = G.oz() + gate[1];
			java.util.Set<Long> whole = new java.util.HashSet<>();
			for (int from = 1; from <= Grounds.RING; from += Building.ROAD_RUN) {
				int to = Math.min(from + Building.ROAD_RUN - 1, Grounds.RING);
				java.util.List<Long> got = new java.util.ArrayList<>();
				Building.roadChunks(G, side, from, to, got);
				// the columns the stretch really reads: the one straight out of the gate (its height and its water), the
				// road's own width, and the signpost's column one past it
				java.util.Set<Integer> offsets = new java.util.HashSet<>(java.util.List.of(0, across[1] + 1));
				for (int a = across[0]; a <= across[1]; a++) {
					offsets.add(a);
				}
				java.util.Set<Long> want = new java.util.HashSet<>();
				for (int step = from; step <= to; step++) {
					for (int a : offsets) {
						int x = gx + d.getStepX() * step + (d.getAxis() == net.minecraft.core.Direction.Axis.Z ? a : 0);
						int z = gz + d.getStepZ() * step + (d.getAxis() == net.minecraft.core.Direction.Axis.X ? a : 0);
						want.add(net.minecraft.world.level.ChunkPos.pack(x >> 4, z >> 4));
					}
				}
				assertTrue(new java.util.HashSet<>(got).containsAll(want), side + " " + from + "-" + to + ": " + got + " misses one of " + want);
				whole.addAll(got);
			}
			for (int step = 1; step <= Grounds.RING; step++) {
				int x = gx + d.getStepX() * step, z = gz + d.getStepZ() * step;
				assertTrue(whole.contains(net.minecraft.world.level.ChunkPos.pack(x >> 4, z >> 4)),
						side + ": the chunk of the block " + step + " out of the gate is in no stretch");
			}
		}
		java.util.List<Long> one = new java.util.ArrayList<>();
		Building.box(one, -17, -1, -16, 0);                 // a box over four chunks, across x = -16 and z = 0
		assertEquals(4, new java.util.HashSet<>(one).size(), "a box that straddles both chunk borders is four chunks");
	}

	@Test
	void blueprintFromTheJar() {
		assertEquals(128, PLAN.size()[0]);
		assertEquals(128, PLAN.size()[2]);
		assertEquals(2, PLAN.version());
		assertNotNull(PLAN.square(), "the plaza's event square");
		assertEquals(23, PLAN.square()[3], "the same side as a village square (events/Layout.N)");
		assertEquals(8, PLAN.stalls().size());
		assertEquals(12, PLAN.returns().size());
		assertEquals(4, PLAN.gates().size());
		assertNotNull(PLAN.stall(1));
		assertEquals("llanuras_castellana", PLAN.style());
	}

	/**
	 * A world that placed the first town (96 x 96, before there were versions) keeps it exactly as it was: its saved
	 * attachment has no version and reads as 1, and the .jar still carries that blueprint, so its protected area, stalls
	 * and return barrels stay where they were built.
	 */
	@Test
	void aWorldKeepsTheVersionItPlaced() {
		java.util.Map<Integer, HousePlan> all = HousePlan.allFromJar();
		assertEquals(java.util.Set.of(1, 2), all.keySet());
		HousePlan v1 = all.get(1);
		assertEquals(96, v1.size()[0]);
		assertEquals(96, v1.size()[2]);
		assertEquals(null, v1.square(), "no event square in the old town");
		assertEquals(null, v1.exterior(), "the old blueprint names no ground outside its wall");
		// the current one does: the forecourt, the template's rows south of the wall, the whole width
		int[] e = PLAN.exterior();
		assertEquals(0, e[0]);
		assertEquals(PLAN.size()[0] - 1, e[2]);
		assertEquals(PLAN.size()[2] - 1, e[3]);
		assertTrue(e[1] > PLAN.gates().get("south")[1] - 12 && e[1] < e[3], "the forecourt lies outside the south wall");
		Grounds old = new Grounds(1000, 60, -2000, v1);
		assertTrue(old.inArea(1000 + 95 + 50, -2000));
		assertFalse(old.inArea(1000 + 95 + 51, -2000), "the old ring does not grow");
		assertEquals(8, v1.stalls().size());
		assertEquals(12, v1.returns().size());
		// the stall boxes and barrels of version 1, as built by the first release
		assertEquals(java.util.List.of(7, 5, 65), java.util.Arrays.stream(v1.stall(1).min()).boxed().toList());
		assertEquals(java.util.List.of(43, 5, 84), java.util.Arrays.stream(v1.returns().getFirst()).boxed().toList());
		// the attachment: absent version -> 1; a new placement saves the current one
		com.mojang.serialization.Dynamic<com.google.gson.JsonElement> before = new com.mojang.serialization.Dynamic<>(
				com.mojang.serialization.JsonOps.INSTANCE, com.google.gson.JsonParser.parseString(
						"{\"origen\": [1000, 60, -2000], \"decidida\": true}"));
		Saved s = Saved.CODEC.parse(before).getOrThrow();
		assertEquals(1, s.version());
		assertEquals(2, s.withOrigin(net.minecraft.core.BlockPos.ZERO, PLAN.version()).version());
	}

	@Test
	void protectedAreaIsTheFootprintAndFiftyBlocks() {
		assertTrue(Grounds.RING >= 50);
		assertTrue(G.inArea(1000 - 50, -2000 - 50));
		assertFalse(G.inArea(1000 - 51, -2000));
		assertTrue(G.inArea(1000 + 127 + 50, -2000 + 127 + 50));
		assertFalse(G.inArea(1000 + 127 + 51, -2000));
		int side = PLAN.size()[0] + 2 * Grounds.RING;
		assertEquals(228, side, "about 228 x 228 in all");
		// every height: no tunnelling under it, no towering over it
		assertTrue(G.isProtected(1000 - 20, -60, -2000, false, 0));
		assertTrue(G.isProtected(1000 - 20, 300, -2000, false, 0));
	}

	@Test
	void onlyOperatorsAndTenantsInTheirStall() {
		HousePlan.Stall s = PLAN.stall(3);
		int[] in = G.world(s.min());
		assertEquals(3, G.stallAt(in[0], in[1], in[2]));
		assertTrue(G.isProtected(in[0], in[1], in[2], false, 0), "a player without a stall");
		assertTrue(G.isProtected(in[0], in[1], in[2], false, 4), "the tenant of another stall");
		assertFalse(G.isProtected(in[0], in[1], in[2], false, 3), "its tenant");
		assertFalse(G.isProtected(in[0], in[1], in[2], true, 0), "an operator");
		int[] c = G.world(PLAN.bell());
		assertTrue(G.isProtected(c[0], c[1], c[2], false, 3), "the tenant outside their stall");
		assertFalse(G.isProtected(5000, 70, 5000, false, 0), "outside the area");
		// endermen: the pickup goal reaches 2 blocks, so it stops 3 blocks before the area
		assertTrue(G.nearArea(1000 - 50 - 3, -2000, 3));
		assertFalse(G.nearArea(1000 - 50 - 4, -2000, 3));
	}

	@Test
	void portalSignsAndBarrels() {
		int[] a = G.world(PLAN.portal()[0]);
		assertTrue(G.inPortal(a[0], a[1], a[2]));
		assertTrue(G.inPortal(a[0] + 1, a[1] + 1, a[2]), "inside the frame, where the fire would go");
		assertFalse(G.inPortal(a[0] - 1, a[1], a[2]));
		int[] sign = G.world(PLAN.stall(5).sign());
		assertEquals(5, G.signAt(sign[0], sign[1], sign[2]));
		int[] b = G.world(PLAN.returns().get(7));
		assertEquals(7, G.barrelAt(b[0], b[1], b[2]));
		assertEquals(-1, G.barrelAt(b[0], b[1] + 5, b[2]));
	}

	@Test
	void usableBlocks() {
		for (String ok : new String[] {"crimson_door", "spruce_trapdoor", "crimson_fence_gate", "stone_button", "red_bed", "bell",
				"crafting_table", "cartography_table"}) {
			assertTrue(Grounds.usable(ok), ok);
		}
		for (String no : new String[] {"iron_door", "iron_trapdoor", "chest", "barrel", "lectern", "crimson_sign", "anvil",
				"composter", "flower_pot", "obsidian", "furnace", "cauldron"}) {
			assertFalse(Grounds.usable(no), no);
		}
	}

	@Test
	void containerAccess() {
		int[] in = G.world(PLAN.stall(3).min());
		int x = G.centerX(), y = G.groundY(), z = G.centerZ();
		java.util.function.IntPredicate none = n -> false, all = n -> true;
		// the town and its ring: a look, nothing taken (the option off: shut, as before it)
		assertEquals(Grounds.Access.LOOK, G.containerAccess(x, y, z, false, 0, none, true));
		assertEquals(Grounds.Access.SHUT, G.containerAccess(x, y, z, false, 0, none, false));
		assertEquals(Grounds.Access.LOOK, G.containerAccess(G.ox() - Grounds.RING, y, z, false, 0, none, true));
		// outside the area and for an operator: theirs to use
		assertEquals(Grounds.Access.OPEN, G.containerAccess(G.ox() - Grounds.RING - 1, y, z, false, 0, none, true));
		assertEquals(Grounds.Access.OPEN, G.containerAccess(x, y, z, true, 0, all, true));
		assertEquals(Grounds.Access.OPEN, G.containerAccess(in[0], in[1], in[2], true, 0, all, false));
		// a stall: its tenant opens it; someone else's rented stall stays shut; a free one is looked at
		assertEquals(Grounds.Access.OPEN, G.containerAccess(in[0], in[1], in[2], false, 3, all, true));
		assertEquals(Grounds.Access.OPEN, G.containerAccess(in[0], in[1], in[2], false, 3, all, false));
		assertEquals(Grounds.Access.SHUT, G.containerAccess(in[0], in[1], in[2], false, 2, all, true));
		assertEquals(Grounds.Access.SHUT, G.containerAccess(in[0], in[1], in[2], false, 0, all, true));
		assertEquals(Grounds.Access.LOOK, G.containerAccess(in[0], in[1], in[2], false, 0, none, true));
	}

	@Test
	void centeredOnTheSpawn() {
		Grounds g = Grounds.centered(10, -20, 70, PLAN);
		assertEquals(10, g.centerX());
		assertEquals(-20, g.centerZ());
		assertEquals(70, g.groundY());
		assertTrue(g.areaOverlaps(g.maxX() + 50, g.maxZ() + 50, g.maxX() + 60, g.maxZ() + 60));
		assertFalse(g.areaOverlaps(g.maxX() + 51, g.oz(), g.maxX() + 60, g.maxZ()));
	}

	// --- rent ---

	private static final Rent.Terms T = new Rent.Terms(16, 4, 7, 3);
	private static final long D = Rent.DAY;

	@Test
	void rentStatesAreComputedNotCounted() {
		long until = 10 * D;
		assertEquals(Rent.Status.PAID, Rent.status(0, until, T));
		assertEquals(Rent.Status.PAID, Rent.status(9 * D - 1, until, T));
		assertEquals(Rent.Status.DUE_SOON, Rent.status(9 * D, until, T), "a day before: warned");
		assertEquals(Rent.Status.GRACE, Rent.status(10 * D, until, T));
		assertEquals(Rent.Status.GRACE, Rent.status(13 * D - 1, until, T));
		assertEquals(Rent.Status.EXPIRED, Rent.status(13 * D, until, T), "after the grace: lost");
		assertEquals(Rent.Status.PAID, Rent.status(1000 * D, until, new Rent.Terms(16, 0, 7, 3)), "no rent: never expires");
	}

	@Test
	void claimingAndPaying() {
		assertEquals(20, Rent.claimCost(T), "entry fee and the first period");
		long until = Rent.claimUntil(5 * D, T);
		assertEquals(12 * D, until);
		assertEquals(3, Rent.payable(5 * D, until, T), "up to four periods from now");
		assertEquals(12 * D + 3 * 7 * D, Rent.pay(until, 3, T));
		assertEquals(0, Rent.payable(5 * D, Rent.pay(until, 3, T), T));
		// in the grace, paying settles the arrears: the new period starts where the old one ended
		long late = 13 * D;
		assertEquals(Rent.Status.GRACE, Rent.status(late, until, T));
		assertEquals(until + 7 * D, Rent.pay(until, 1, T));
		assertEquals(0, Rent.payable(16 * D, until, T), "expired: nothing to pay, the stall is lost");
		assertTrue(Rent.affordable(20, 20));
		assertFalse(Rent.affordable(19, 20));
		assertEquals(3, Rent.daysLeft(9 * D + 1, 12 * D));
		assertEquals(0, Rent.daysLeft(12 * D, 12 * D));
	}

	// --- site ---

	private record Terrain(java.util.function.IntBinaryOperator high, java.util.function.BiPredicate<Integer, Integer> water)
			implements Site.Heights {
		@Override
		public int surface(int x, int z) {
			return high.applyAsInt(x, z) + 1 + (water.test(x, z) ? 3 : 0);
		}

		@Override
		public int depth(int x, int z) {
			return high.applyAsInt(x, z) + 1;
		}
	}

	private static Optional<Siting.Choice> choose(Site.Heights h, Siting.Forbidden f) {
		return Siting.choose(0, 0, PLAN.size()[0], PLAN.ground(), PLAN.size()[1] - PLAN.ground(), -64, 320, h, f);
	}

	@Test
	void flatSpawnIsTheSpawn() {
		Siting.Choice c = choose(new Terrain((x, z) -> 70, (x, z) -> false), (a, b, c2, d) -> false).orElseThrow();
		assertEquals(0, c.x());
		assertEquals(0, c.z());
		assertEquals(70, c.ground());
	}

	@Test
	void avoidsWaterAndTheArena() {
		// a lake east of spawn: the house moves west
		Siting.Choice c = choose(new Terrain((x, z) -> 70, (x, z) -> x > 30), (a, b, c2, d) -> false).orElseThrow();
		assertTrue(c.x() < 0, "x " + c.x());
		assertEquals(0, c.water());
		// all of it water: still a site (the house brings its foundation)
		assertTrue(choose(new Terrain((x, z) -> 50, (x, z) -> true), (a, b, c2, d) -> false).isPresent());
		// an arena everywhere: none
		assertTrue(choose(new Terrain((x, z) -> 70, (x, z) -> false), (a, b, c2, d) -> true).isEmpty());
		// never further than RADIUS, so the ring stays clear of the arena's search (200-300 blocks)
		assertTrue(Siting.RADIUS + PLAN.size()[0] / 2 + Grounds.RING < Site.RADIUS_MIN - 57 / 2);
	}

	@Test
	void prefersLessDrop() {
		Siting.Choice c = choose(new Terrain((x, z) -> x > 0 ? 70 + x / 2 : 70, (x, z) -> false), (a, b, c2, d) -> false).orElseThrow();
		assertTrue(c.x() < 0, "the flat side");
	}

	@Test
	void blendingIsASlope() {
		assertEquals(70, Building.blend(70, 70, 3));
		assertEquals(70, Building.blend(70, 79, 0));
		assertEquals(79, Building.blend(70, 79, Siting.MARGIN + 1));
		int prev = 70;
		for (int k = 1; k <= Siting.MARGIN; k++) {
			int y = Building.blend(70, 88, k);
			assertTrue(y >= prev && y - prev <= 2, "step " + k);
			prev = y;
		}
	}
}
