package io.github.albertosa23.heraldia.villages;

import java.util.ArrayList;
import java.util.List;
import net.minecraft.world.level.levelgen.structure.BoundingBox;

/**
 * How a village fits the terrain it falls on, decided once when the village is created, from the generation heights
 * only (the same noise for a seed: deterministic, the same with /place and in natural generation).
 * <p>The jigsaw lays each street ({@code terrain_matching}) flat on the generation height of its own anchor column and
 * stands each rigid piece on the generation height of the column of its joint with that street (and only aligns a
 * child to its parent's jigsaw block when both are {@code rigid}: {@code JigsawPlacement}, 26.3). On flat land that is
 * all it takes; on a hillside a street can climb two or more blocks from one column to the next (villagers only step up
 * one), a building can face a street a step or more above or below its door, and a low fenced piece (garden, well) can
 * end up in a pit. Villagers
 * only claim a bed or a workstation they can walk to, and in 26.3 they only look for a path a short way (16 blocks), so
 * every step that cuts a street or a door costs beds and workstations.
 * <p>This pass does the least that fixes it: a street with a step is <b>graded</b> (its centre line gets a profile that
 * climbs at most a block a column, as close to the terrain as possible, and the game's own terrain adaptation shapes
 * the ground to it when the chunks are generated: no fill or cut beyond {@link #MAX_GRADE} blocks, the village is not
 * sunk into a hollow); a building whose door is a step off its street, or a low piece sunk in a pit, is <b>dropped</b>
 * with what is inside it (its villager, its bed): one house less instead of a useless house or a trap. Streets are
 * never dropped: what hangs from a street too steep to grade still works on its own.
 * <p>Pure logic over {@link Part}s (box, kind and parent), with the heights behind {@link Ground}: the game pieces are
 * translated in {@link VillageStructure}.
 */
public final class TerrainFit {
	/** Highest step a villager climbs (and the highest drop it takes back) between two neighbouring columns. */
	public static final int STEP = 1;
	/** Lanes of a street checked side by side (the centre and two to each side): a villager can walk on any of them. */
	static final int[] LANES = {-2, 0, 2};
	/** A low piece (box height up to this) is a pit when the terrain around it rises over its floor by more than {@link #PIT}. */
	static final int LOW = 5;
	static final int PIT = 2;

	private TerrainFit() {
	}

	/** Generation heights: first free height of a column, counting water (a street over water gets planks). */
	@FunctionalInterface
	public interface Ground {
		int surface(int x, int z);
	}

	public enum Kind {
		/** The plaza (first piece): always kept. */
		ROOT,
		/** A street, avenue or street end ({@code terrain_matching}). */
		STREET,
		/** A rigid building hanging from a street: house, filler, special, tower, gate, cemetery, mill. */
		BUILDING,
		/** What goes inside or along another piece (villagers, beds, rugs, golems, lamps, the board): goes with its parent. */
		CONTENT
	}

	/**
	 * A village piece: its box, its kind, the index of the piece it hangs from (-1 if unknown: it is kept with the plaza)
	 * and the column of its joint with that parent (the parent's jigsaw block), or null.
	 */
	public record Part(BoundingBox box, Kind kind, int parent, int jointX, int jointZ) {
		public static Part of(BoundingBox box, Kind kind, int parent, int jointX, int jointZ) {
			return new Part(box, kind, parent, jointX, jointZ);
		}
	}

	/**
	 * What became of a piece: kept as it is, or a street too steep to grade (also kept); or why it was dropped (its
	 * descendants go with it, counted apart).
	 */
	public enum Reason {
		KEPT, STEEP_STREET, DOOR_STEP, PIT, PARENT
	}

	/** Pieces that stay: all the streets, graded or not, and the buildings that a villager can walk into. */
	static boolean kept(Reason r) {
		return r == Reason.KEPT || r == Reason.STEEP_STREET;
	}

	/**
	 * Result: the reason of each piece (KEPT for those kept) and, for each graded street, its grading points {x, y, z}
	 * (the standing height its ground should have at that column; empty for the rest).
	 */
	public record Result(Reason[] reasons, List<List<int[]>> grades) {
		public boolean kept(int i) {
			return TerrainFit.kept(reasons[i]);
		}

		public int count(Reason r) {
			int n = 0;
			for (Reason x : reasons) {
				n += x == r ? 1 : 0;
			}
			return n;
		}

		public String summary() {
			int graded = 0;
			for (List<int[]> g : grades) {
				graded += g.isEmpty() ? 0 : 1;
			}
			int kept = 0;
			for (Reason r : reasons) {
				kept += TerrainFit.kept(r) ? 1 : 0;
			}
			return kept + " of " + reasons.length + " pieces kept, " + graded + " streets and doors graded, " + count(Reason.STEEP_STREET)
					+ " too steep to grade; dropped: " + count(Reason.DOOR_STEP) + " buildings with a step at the door, "
					+ count(Reason.PIT) + " in a pit, " + count(Reason.PARENT) + " pieces inside them";
		}
	}

	/**
	 * Decides every piece in order (a parent always comes before its children, as the jigsaw places them).
	 */
	public static Result fit(List<Part> parts, Ground g) {
		Reason[] out = new Reason[parts.size()];
		List<List<int[]>> grades = new ArrayList<>();
		for (int i = 0; i < parts.size(); i++) {
			Part p = parts.get(i);
			int parent = p.parent();
			if (parent >= i) {
				parent = -1;
			}
			List<int[]> grade = new ArrayList<>();
			grades.add(grade);
			if (p.kind() == Kind.ROOT || (parent < 0 && p.kind() == Kind.CONTENT)) {
				out[i] = Reason.KEPT;
			} else if (parent >= 0 && !kept(out[parent])) {
				out[i] = Reason.PARENT;
			} else if (p.kind() == Kind.CONTENT || parent < 0) {
				out[i] = Reason.KEPT;
			} else {
				out[i] = judge(p, parts.get(parent), g, grade);
				if (!kept(out[i])) {
					grade.clear();
				}
			}
		}
		return new Result(out, grades);
	}

	private static Reason judge(Part p, Part parent, Ground g, List<int[]> grade) {
		return switch (p.kind()) {
			case STREET -> street(p, parent, g, grade);
			case BUILDING -> building(p, parent, g, grade);
			default -> Reason.KEPT;
		};
	}

	/**
	 * A street is kept as it is when, at every step along it (and one column into its neighbours at both ends), one of
	 * its {@link #LANES} climbs at most {@link #STEP}. Otherwise it is graded: the ground under its centre line is given a
	 * profile that climbs at most a step a column and meets both ends where they are (the neighbouring street, or the
	 * floor of the rigid piece it hangs from), as close to the terrain as that allows ({@link #grade}); the game's own
	 * terrain adaptation shapes the ground to it when the chunks are generated. A street that would need more than
	 * {@link #MAX_GRADE} blocks of fill or cut anywhere, or cannot climb from one end to the other at all, is left as it
	 * is ({@link Reason#STEEP_STREET}, kept).
	 */
	static Reason street(Part p, Part parent, Ground g, List<int[]> grades) {
		BoundingBox b = p.box();
		// the way a street runs: away from its joint (a straight, an avenue, a street end); a square crossing, both ways
		int[] d = side(p.jointX(), p.jointZ(), b);
		boolean square = b.getXSpan() == b.getZSpan();
		boolean alongX = square || (d != null ? d[0] != 0 : b.getXSpan() > b.getZSpan());
		boolean alongZ = square || (d != null ? d[1] != 0 : b.getZSpan() > b.getXSpan());
		// hanging from a rigid piece, the column beyond the joint is that piece's floor (standing on its bottom row)
		int[] rigid = parent.kind() == Kind.STREET ? null : d;
		int floor = parent.box().minY() + 1;
		List<int[]> out = new ArrayList<>();
		for (boolean x : new boolean[] {true, false}) {
			if (!(x ? alongX : alongZ) || walkable(b, x, g, rigid, floor)) {
				continue;
			}
			int[] line = line(b, x);
			int[] r = profile(b, x, g, rigid, floor);
			int[] t = grade(r);
			if (t == null || deviation(r, t) > MAX_GRADE) {
				// too steep to grade gently: left as it is (what hangs from it still works on its own, a villager only
				// looks for a bed or a workstation within a short walk)
				return Reason.STEEP_STREET;
			}
			// one point every GRADE_SPACING columns inside the street, at the height the ground should have there
			for (int k = 1; k < t.length - 1; k += GRADE_SPACING) {
				int a = line[0] + k;
				out.add(x ? new int[] {a, t[k], line[2]} : new int[] {line[2], t[k], a});
			}
		}
		grades.addAll(out);
		return Reason.KEPT;
	}

	/** Most blocks of fill or cut a graded street may ask for at any column. */
	public static final int MAX_GRADE = 6;
	/** Highest step between a door and its street that a ramp in front of the door makes up for (more: the house goes). */
	public static final int MAX_DOOR = 3;
	/** Columns between two grading points of a street (the terrain adaptation blends a few blocks around each). */
	static final int GRADE_SPACING = 2;

	/** {first, last, centre}: the columns along the axis from the one before the box to the one after, and the centre line. */
	static int[] line(BoundingBox b, boolean alongX) {
		return new int[] {(alongX ? b.minX() : b.minZ()) - 1, (alongX ? b.maxX() : b.maxZ()) + 1,
				alongX ? (b.minZ() + b.maxZ()) / 2 : (b.minX() + b.maxX()) / 2};
	}

	/**
	 * Standing heights along the centre line, from the column before the box to the one after it; with a rigid parent on
	 * side {@code rigid}, the column beyond that side is the parent's {@code floor}.
	 */
	static int[] profile(BoundingBox b, boolean alongX, Ground g, int[] rigid, int floor) {
		int[] line = line(b, alongX);
		int[] r = new int[line[1] - line[0] + 1];
		for (int k = 0; k < r.length; k++) {
			r[k] = height(g, alongX, line[0] + k, line[2]);
		}
		int s = rigid == null ? 0 : alongX ? rigid[0] : rigid[1];
		if (s < 0) {
			r[0] = floor;
		} else if (s > 0) {
			r[r.length - 1] = floor;
		}
		return r;
	}

	/**
	 * A profile that climbs at most a step a column, equal to {@code r} at both ends and otherwise as close to it as that
	 * allows: the middle of the highest and lowest step-limited profiles under and over {@code r}, clamped to what can
	 * still reach both ends. Null when the ends are further apart in height than in columns.
	 */
	static int[] grade(int[] r) {
		int n = r.length, last = n - 1;
		if (Math.abs(r[last] - r[0]) > last * STEP) {
			return null;
		}
		int[] t = new int[n];
		for (int a = 0; a < n; a++) {
			int over = Integer.MIN_VALUE, under = Integer.MAX_VALUE;
			for (int c = 0; c < n; c++) {
				over = Math.max(over, r[c] - Math.abs(a - c) * STEP);
				under = Math.min(under, r[c] + Math.abs(a - c) * STEP);
			}
			int mid = Math.floorDiv(over + under, 2);
			int lo = Math.max(r[0] - a * STEP, r[last] - (last - a) * STEP);
			int hi = Math.min(r[0] + a * STEP, r[last] + (last - a) * STEP);
			t[a] = Math.max(lo, Math.min(mid, hi));
		}
		return t;
	}

	static int deviation(int[] r, int[] t) {
		int d = 0;
		for (int k = 0; k < r.length; k++) {
			d = Math.max(d, Math.abs(r[k] - t[k]));
		}
		return d;
	}

	/**
	 * Does any lane of the box climb at most a step at each position along the axis (x or z), from the column before it
	 * to the one after it? With a rigid parent on side {@code rigid} (a unit vector, or null), the column beyond that
	 * side is the parent's {@code floor} on every lane.
	 */
	static boolean walkable(BoundingBox b, boolean alongX, Ground g, int[] rigid, int floor) {
		int[] line = line(b, alongX);
		int s = rigid == null ? 0 : alongX ? rigid[0] : rigid[1];
		int[] prev = new int[LANES.length];
		for (int k = 0; k < LANES.length; k++) {
			prev[k] = s < 0 ? floor : height(g, alongX, line[0], line[2] + LANES[k]);
		}
		for (int a = line[0] + 1; a <= line[1]; a++) {
			boolean any = false;
			for (int k = 0; k < LANES.length; k++) {
				int h = s > 0 && a == line[1] ? floor : height(g, alongX, a, line[2] + LANES[k]);
				any |= Math.abs(h - prev[k]) <= STEP;
				prev[k] = h;
			}
			if (!any) {
				return false;
			}
		}
		return true;
	}

	private static int height(Ground g, boolean alongX, int a, int across) {
		return alongX ? g.surface(a, across) : g.surface(across, a);
	}

	/**
	 * A building whose door is more than a step off its street gets a ramp: grading points from the door into the
	 * street, a block a column; more than {@link #MAX_DOOR} off, it is dropped. A low building (a garden, a well) sunk
	 * in a pit it could not be left from is dropped too.
	 * <p>The step is between the two <b>placed boxes</b>, not between two generation heights. {@code JigsawPlacement}
	 * (26.3, read in the bytecode) aligns a child with its parent's jigsaw block only when <b>both</b> are
	 * {@code rigid}; a rigid child of a {@code terrain_matching} parent is placed on
	 * {@code getFirstFreeHeight(joint column, WORLD_SURFACE_WG)} instead. So a building's floor row is the generation
	 * height of <b>its own</b> joint column -- which its box already says, exactly -- while the street it hangs from
	 * was laid flat on the height of <b>the street's own anchor</b> column, up to a piece's length away. On a hillside
	 * those two are blocks apart, and that difference is the step a villager meets at the door.
	 * <p>Reading two neighbouring generation heights instead ({@code g.surface} at the joint and one column out) could
	 * not see it: next to the door the terrain is the same on both columns, so it answered "no step" for a door five
	 * blocks over its street (measured on the test seeds, Nov 2026, #96). What a villager steps on when it walks out is
	 * the row over the parent's paving, {@code parent.box().minY() + 1} -- the same expression {@link #street} already
	 * uses for a rigid parent. No height has to be asked of the generator for this, so the grid of
	 * {@code VillageStructure.Ground} no longer blurs it either: the only reader left here is the pit check.
	 */
	static Reason building(Part p, Part parent, Ground g, List<int[]> grade) {
		BoundingBox b = p.box();
		int jx = p.jointX(), jz = p.jointZ();
		// the row the building's own floor is on: the jigsaw stood the box there, so this is exact
		int floor = b.minY();
		int[] d = side(jx, jz, b);
		if (d != null) {
			// what a villager steps on when it leaves: the row over the parent's paving
			int step = parent.box().minY() + 1 - floor;
			if (Math.abs(step) > MAX_DOOR) {
				return Reason.DOOR_STEP;
			}
			// a ramp from the door into the street: the joint column at the door's height, then a block a column
			for (int k = 0; Math.abs(step) > STEP && k < Math.abs(step); k++) {
				grade.add(new int[] {jx + d[0] * k, floor + Integer.signum(step) * k, jz + d[1] * k});
			}
		}
		if (b.getYSpan() > LOW) {
			return Reason.KEPT;
		}
		int top = Integer.MIN_VALUE;
		for (int[] c : samples(b)) {
			top = Math.max(top, g.surface(c[0], c[1]));
		}
		if (top > b.minY() + PIT) {
			return Reason.PIT;
		}
		return Reason.KEPT;
	}

	/** Columns sampled in a footprint: the corners, the middle of each side and the centre. */
	static List<int[]> samples(BoundingBox b) {
		List<int[]> out = new ArrayList<>();
		int[] xs = {b.minX(), (b.minX() + b.maxX()) / 2, b.maxX()}, zs = {b.minZ(), (b.minZ() + b.maxZ()) / 2, b.maxZ()};
		for (int x : xs) {
			for (int z : zs) {
				out.add(new int[] {x, z});
			}
		}
		return out;
	}

	/** The column one step from the joint away from the box (into the street), or null if the joint is not beside it. */
	static int[] outward(int jx, int jz, BoundingBox b) {
		int[] d = side(jx, jz, b);
		return d == null ? null : new int[] {jx + d[0], jz + d[1]};
	}

	/** The column one step from the joint into the box (the first one of a street hanging from it), or null. */
	static int[] inward(int jx, int jz, BoundingBox b) {
		int[] d = side(jx, jz, b);
		return d == null ? null : new int[] {jx - d[0], jz - d[1]};
	}

	/** Unit vector from the box towards the joint, which lies just outside one of its faces; null otherwise. */
	static int[] side(int jx, int jz, BoundingBox b) {
		boolean inX = jx >= b.minX() && jx <= b.maxX(), inZ = jz >= b.minZ() && jz <= b.maxZ();
		if (inZ && jx == b.minX() - 1) {
			return new int[] {-1, 0};
		}
		if (inZ && jx == b.maxX() + 1) {
			return new int[] {1, 0};
		}
		if (inX && jz == b.minZ() - 1) {
			return new int[] {0, -1};
		}
		if (inX && jz == b.maxZ() + 1) {
			return new int[] {0, 1};
		}
		return null;
	}
}
