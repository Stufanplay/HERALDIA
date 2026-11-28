package io.github.albertosa23.heraldia.inhabitants;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.github.albertosa23.heraldia.inhabitants.Inhabitants.Action;
import java.util.Set;
import org.junit.jupiter.api.Test;

class InhabitantsTest {
	private static final String TAG = Inhabitants.TAG;

	@Test
	void notAnInhabitant() {
		assertEquals(Action.NONE, Inhabitants.decide(Set.of(), true));
		assertEquals(Action.NONE, Inhabitants.decide(Set.of("heraldia_mediana", "heraldia_anclado"), false));
	}

	@Test
	void onTheyLive() {
		assertEquals(Action.LIVE, Inhabitants.decide(Set.of(TAG), true));
		assertEquals(Action.LIVE, Inhabitants.decide(Set.of(TAG, Inhabitants.STILL_BEFORE), true));
	}

	@Test
	void offTheOldFiguresStayStillAndTheNewOnesGo() {
		assertEquals(Action.STILL, Inhabitants.decide(Set.of(TAG, Inhabitants.STILL_BEFORE), false));
		assertEquals(Action.REMOVE, Inhabitants.decide(Set.of(TAG), false));
	}

	@Test
	void onceSeenNeverTouchedAgain() {
		for (boolean on : new boolean[] {true, false}) {
			assertEquals(Action.NONE, Inhabitants.decide(Set.of(TAG, Inhabitants.SEEN), on));
			assertEquals(Action.NONE, Inhabitants.decide(Set.of(TAG, Inhabitants.STILL_BEFORE, Inhabitants.SEEN), on));
		}
	}

	@Test
	void lostFurtherThanItsOwnSearchCanReach() {
		// rescue(tags, enabled, alive, sameDimension, stillThere, blocks)
		assertTrue(Inhabitants.rescue(Set.of(TAG), true, true, true, true, 20.0));
		assertTrue(Inhabitants.rescue(Set.of(TAG, Inhabitants.SEEN), true, true, true, true, 16.01));
	}

	@Test
	void withinItsOwnSearchItIsTheBuildingsFaultAndStaysVisible() {
		// a villager that cannot walk to a bed 16 FLAT blocks away or less is what the build's trap audit
		// (mediums/_paths.trap_walk, stranded) and medium_structures.py's settle check are for: never rescued, so one
		// stranded on its own roof, which is a few blocks away on the ground however high it is, still goes red
		assertFalse(Inhabitants.rescue(Set.of(TAG), true, true, true, true, 16.0));
		assertFalse(Inhabitants.rescue(Set.of(TAG), true, true, true, true, 0.0));
		assertEquals(16, Inhabitants.LOST_BLOCKS);
	}

	@Test
	void everythingElseGivesTheBlockUpAsAlways() {
		assertFalse(Inhabitants.rescue(Set.of(), true, true, true, true, 40.0));             // not an inhabitant
		assertFalse(Inhabitants.rescue(Set.of("heraldia_anclado"), true, true, true, true, 40.0));
		assertFalse(Inhabitants.rescue(Set.of(TAG), false, true, true, true, 40.0));          // option off
		assertFalse(Inhabitants.rescue(Set.of(TAG), true, false, true, true, 40.0));          // dead
		assertFalse(Inhabitants.rescue(Set.of(TAG), true, true, false, true, 40.0));          // another dimension
		assertFalse(Inhabitants.rescue(Set.of(TAG), true, true, true, false, 40.0));          // the block is gone
	}

	@Test
	void sameTagsAsTheGenerator() {
		// tools/gen/mediums/_inhabitants.py: TAG, STILL_BEFORE and SEEN
		assertEquals("heraldia_habitante", TAG);
		assertEquals("heraldia_habitante.quieto_antes", Inhabitants.STILL_BEFORE);
		assertEquals("heraldia_habitante.visto", Inhabitants.SEEN);
	}
}
