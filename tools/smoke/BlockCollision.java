import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.phys.shapes.VoxelShape;

/**
 * The top of every block's collision box, from the game itself: for each block of the registry, its default state's
 * collision shape (BlockState.getCollisionShape with no level around it), 0 when it has none. It is what
 * tools/smoke/ground_blocks.py regenerates ground_blocks.json from, for village_terrain's ground reader.
 *
 * Usage (single-file source, Java 25), with the deobfuscated 26.3 jar and the server's libraries on the class path:
 *   java -cp "<minecraft-common-deobf-26.3.jar>:<server libraries/**.jar>" tools/smoke/BlockCollision.java > collision.json
 * Prints one JSON object, {"minecraft:stone": 1.0, ...}; the game's own log lines go to stderr.
 */
public final class BlockCollision {
	public static void main(String[] args) {
		SharedConstants.tryDetectVersion();
		Bootstrap.bootStrap();
		StringBuilder out = new StringBuilder("{");
		for (Block b : BuiltInRegistries.BLOCK) {
			VoxelShape v = b.defaultBlockState().getCollisionShape(EmptyBlockGetter.INSTANCE, BlockPos.ZERO);
			out.append(out.length() > 1 ? ", " : "").append('"').append(BuiltInRegistries.BLOCK.getKey(b)).append("\": ")
					.append(v.isEmpty() ? 0.0 : v.max(Direction.Axis.Y));
		}
		// System.out is redirected to the game's logger by the bootstrap: print through the original stream
		new java.io.PrintStream(new java.io.FileOutputStream(java.io.FileDescriptor.out), true).println(out.append("}"));
	}
}
