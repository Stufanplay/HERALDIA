package io.github.albertosa23.heraldia.mixin;

import io.github.albertosa23.heraldia.inhabitants.Inhabitants;
import net.minecraft.core.GlobalPos;
import net.minecraft.world.entity.ai.memory.MemoryModuleType;
import net.minecraft.world.entity.npc.villager.Villager;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Mixin (last resort: there is no event when a villager gives up a point of interest): at the head of
 * {@code Villager.releasePoi}, which the game calls when a villager lets a remembered bed or workstation go
 * ({@code SetWalkTargetFromBlockMemory}, after the 1,200 ticks it gives it to reach the block, or at once when the
 * block is further than its memory's limit -- 150 blocks of Manhattan distance for the bed, 100 for the workstation --
 * and 1,000 tries find no step toward it), an inhabitant of a medium structure that is lost further away than its own search can ever reach is put back at it
 * ({@link Inhabitants#givingUp}). The release itself is not cancelled: freeing the point of interest's ticket is what
 * lets the villager claim it again from where it has been put.
 * <p>
 * Nothing runs every tick: {@code releasePoi} is called when a villager gives something up, and
 * {@link Inhabitants#givingUp} leaves on one set lookup for every villager that is not an inhabitant.
 */
@Mixin(Villager.class)
abstract class VillagerLostPoiMixin {
	@Inject(method = "releasePoi", at = @At("HEAD"))
	private void heraldia$lostInhabitant(MemoryModuleType<GlobalPos> memory, CallbackInfo ci) {
		Inhabitants.givingUp((Villager) (Object) this, memory);
	}
}
