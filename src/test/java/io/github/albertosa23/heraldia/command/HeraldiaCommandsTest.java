package io.github.albertosa23.heraldia.command;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.ParseResults;
import com.mojang.brigadier.context.ParsedCommandNode;
import com.mojang.brigadier.tree.ArgumentCommandNode;
import com.mojang.brigadier.tree.CommandNode;
import com.mojang.brigadier.tree.LiteralCommandNode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import net.minecraft.SharedConstants;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.server.Bootstrap;
import net.minecraft.server.permissions.LevelBasedPermissionSet;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * The real /heraldia tree (HeraldiaCommands.tree, without a server): all canonical names in English and ASCII (the same
 * as tools/gen/commands.py), each old name resolves to the same node with the same permissions and warns, and no alias
 * shows in the tree the client receives (the suggestions).
 */
class HeraldiaCommandsTest {
	private static CommandDispatcher<CommandSourceStack> d;
	private static CommandSourceStack op, player;

	@BeforeAll
	static void game() {
		SharedConstants.tryDetectVersion();
		Bootstrap.bootStrap();
		d = new CommandDispatcher<>();
		HeraldiaCommands.tree(d);
		op = Commands.createCompilationContext(LevelBasedPermissionSet.OWNER);
		player = Commands.createCompilationContext(LevelBasedPermissionSet.ALL);
	}

	private static CommandNode<CommandSourceStack> root() {
		return d.getRoot().getChild("heraldia");
	}

	/** Paths of the visible nodes (without aliases) under /heraldia: literals by their name, arguments as &lt;name&gt;. */
	private static Set<String> canonical(CommandNode<CommandSourceStack> n, String route, Set<String> out) {
		for (CommandNode<CommandSourceStack> h : n.getChildren()) {
			if (!Alias.visible(h)) {
				continue;
			}
			String name = h instanceof ArgumentCommandNode ? "<" + h.getName() + ">" : h.getName();
			String r = route.isEmpty() ? name : route + " " + name;
			out.add(r);
			canonical(h, r, out);
		}
		return out;
	}

	/** CANONICAL from tools/gen/commands.py (the list the generator's tests also check). */
	private static Set<String> fromCommandsPy() throws IOException {
		String py = Files.readString(Path.of("tools/gen/commands.py"), StandardCharsets.UTF_8);
		Matcher m = Pattern.compile("CANONICAL = \\[(.*?)\\]", Pattern.DOTALL).matcher(py);
		assertTrue(m.find(), "CANONICAL in commands.py");
		Set<String> out = new TreeSet<>();
		Matcher s = Pattern.compile("\"([^\"]+)\"").matcher(m.group(1));
		while (s.find()) {
			out.add(s.group(1));
		}
		return out;
	}

	@Test
	void canonicalNamesInEnglishAndAscii() throws IOException {
		Set<String> routes = canonical(root(), "", new TreeSet<>());
		assertEquals(fromCommandsPy(), routes);
		for (String r : routes) {
			for (String segment : r.split(" ")) {
				assertTrue(segment.matches("<?[a-z]+(-[a-z]+)?>?"), r);
			}
		}
		Set<String> legacyNames = new TreeSet<>(Alias.LEGACY.values());
		for (String r : routes) {
			for (String segment : r.split(" ")) {
				assertFalse(legacyNames.contains(segment), "nombre antiguo visible: " + r);
			}
		}
	}

	private static CommandNode<CommandSourceStack> node(String route) {
		CommandNode<CommandSourceStack> n = root();
		for (String t : route.split(" ")) {
			n = n.getChild(t);
			assertNotNull(n, route);
		}
		return n;
	}

	@Test
	void eachAliasResolvesToSameNodeWithSamePermissions() {
		for (Map.Entry<String, String> e : Alias.LEGACY.entrySet()) {
			String route = e.getKey();
			int i = route.lastIndexOf(' ');
			String parent = i < 0 ? "" : route.substring(0, i);
			CommandNode<CommandSourceStack> p = parent.isEmpty() ? root() : node(parent);
			CommandNode<CommandSourceStack> alias = p.getChild(e.getValue()), canon = node(route);
			Alias.Hidden<?> o = assertInstanceOf(Alias.Hidden.class, alias, route);
			assertSame(canon, o.destination(), route);
			assertSame(canon.getRequirement(), alias.getRequirement(), route);
			assertEquals(canon.getCommand() == null, alias.getCommand() == null, route);
			assertEquals(names(canon), names(alias), route);
		}
	}

	/** The children with their canonical name (those of the copy, translated with the map). */
	private static Set<String> names(CommandNode<CommandSourceStack> n) {
		Set<String> out = new TreeSet<>();
		Map<String, String> inverse = new java.util.HashMap<>();
		Alias.LEGACY.forEach((k, v) -> inverse.put(v, k.substring(k.lastIndexOf(' ') + 1)));
		for (CommandNode<CommandSourceStack> h : n.getChildren()) {
			if (h instanceof LiteralCommandNode && !Alias.visible(h)) {
				continue;
			}
			out.add(inverse.getOrDefault(h.getName(), h.getName()));
		}
		return out;
	}

	private static void parses(String order, CommandSourceStack src) {
		ParseResults<CommandSourceStack> p = d.parse(order, src);
		assertFalse(p.getReader().canRead(), order + ": " + p.getExceptions());
		assertNotNull(p.getContext().getCommand(), order);
	}

	@Test
	void oldCommandsAreUnderstoodWhole() {
		for (String order : List.of("heraldia guia", "heraldia info cerca", "heraldia info cerca 500", "heraldia info aqui",
				"heraldia llave @a todas", "heraldia llave @a atlantida", "heraldia arena salir", "heraldia arena colocar",
				"heraldia arena colocar confirmar", "heraldia arena place confirmar", "heraldia arena mover confirmar",
				"heraldia arena quitar confirmar", "heraldia arena empezar", "heraldia arena parar")) {
			parses(order, op);
		}
		for (String order : List.of("heraldia guide", "heraldia info nearby 500", "heraldia info here", "heraldia key @a all",
				"heraldia arena leave", "heraldia arena place confirm", "heraldia arena move confirm", "heraldia arena remove confirm",
				"heraldia arena start", "heraldia arena stop", "heraldia update check", "heraldia review next", "heraldia status 2",
				"heraldia reload")) {
			parses(order, op);
		}
		// without permissions, only what already belonged to everyone
		parses("heraldia journal", player);
		parses("heraldia journal uniques", player);
		parses("heraldia guia", player);
		parses("heraldia arena salir", player);
		assertTrue(d.parse("heraldia arena colocar", player).getReader().canRead());
		assertTrue(d.parse("heraldia update check", player).getReader().canRead());
	}

	@Test
	void arenaModeCommands() {
		for (String order : List.of("heraldia arena start coop", "heraldia arena start timeattack", "heraldia arena start survival",
				"heraldia arena leaderboard", "heraldia arena leaderboard timeattack", "heraldia arena leaderboard survival 3",
				"heraldia arena season", "heraldia arena season reset", "heraldia arena empezar timeattack")) {
			parses(order, op);
		}
		for (String order : List.of("heraldia arena start", "heraldia arena start survival", "heraldia arena leaderboard",
				"heraldia arena leaderboard coop 1")) {
			parses(order, player);
		}
		// the season is for operators; the week has a cap
		assertTrue(d.parse("heraldia arena season reset", player).getReader().canRead());
		assertTrue(d.parse("heraldia arena leaderboard coop 99", op).getExceptions().size() > 0
				|| d.parse("heraldia arena leaderboard coop 99", op).getReader().canRead());
		assertTrue(d.parse("heraldia arena start contrarreloj", op).getReader().canRead(), "los modos, en inglés");
	}

	@Test
	void lastNodeOfOldCommandIsACopy() {
		List<ParsedCommandNode<CommandSourceStack>> n = d.parse("heraldia arena colocar confirmar", op).getContext().getNodes();
		assertEquals(List.of("heraldia", "arena", "colocar", "confirmar"), n.stream().map(x -> x.getNode().getName()).toList());
		assertFalse(Alias.visible(n.get(2).getNode()));
	}

	@Test
	void noAliasInClientTree() {
		var client = new CommandDispatcher<>(AliasTest.fromClient(d.getRoot(), op));
		List<String> root = AliasTest.suggestions(client, "heraldia ", op);
		assertEquals(List.of("arena", "caravan", "choice", "config", "event", "guide", "herald", "info", "journal", "key", "language", "profile", "quest", "reload", "review", "status", "talk", "treasure", "update", "webmap", "wizard"), root);
		assertEquals(List.of("grounds", "place", "roads", "stall"), AliasTest.suggestions(client, "heraldia herald ", op));
		assertEquals(List.of("confirm", "here"), AliasTest.suggestions(client, "heraldia herald place ", op));
		assertEquals(List.of("claim", "evict", "leave", "pay"), AliasTest.suggestions(client, "heraldia herald stall ", op));
		assertEquals(List.of("chronicle", "coast", "end", "mediums", "mines", "nether", "uniques", "villages"), AliasTest.suggestions(client, "heraldia journal ", op));
		assertEquals(List.of("clear", "list", "raid", "spawn", "wayfarer"), AliasTest.suggestions(client, "heraldia caravan ", op));
		assertEquals(List.of("hunter", "messenger", "patrol", "pilgrim", "shepherd"), AliasTest.suggestions(client, "heraldia caravan wayfarer ", op));
		assertEquals(List.of("peaceful", "raid"), AliasTest.suggestions(client, "heraldia caravan spawn ", op));
		assertEquals(List.of("abandon", "accept", "list", "turnin"), AliasTest.suggestions(client, "heraldia quest ", op));
		assertEquals(List.of("bye", "more", "rumor", "trade", "with"), AliasTest.suggestions(client, "heraldia talk ", op));
		assertEquals(List.of("click", "reply", "send"), AliasTest.suggestions(client, "heraldia choice ", op));
		assertEquals(List.of("give", "info"), AliasTest.suggestions(client, "heraldia treasure ", op));
		assertEquals(List.of("leaderboard", "leave", "move", "place", "remove", "season", "start", "stop"),
				AliasTest.suggestions(client, "heraldia arena ", op));
		assertEquals(List.of("coop", "survival", "timeattack"), AliasTest.suggestions(client, "heraldia arena start ", op));
		assertEquals(List.of("reset"), AliasTest.suggestions(client, "heraldia arena season ", op));
		assertEquals(List.of("here", "nearby"), AliasTest.suggestions(client, "heraldia info ", op));
		assertEquals(List.of("analyze", "apply", "check", "mend", "repair", "undo"), AliasTest.suggestions(client, "heraldia update ", op));
		assertEquals(List.of("list", "start", "stop", "with"), AliasTest.suggestions(client, "heraldia event ", op));
		assertEquals(List.of("festival", "funeral", "market", "wedding"), AliasTest.suggestions(client, "heraldia event start ", op));
		// a player without permissions only sees their own
		var playerSource = new CommandDispatcher<>(AliasTest.fromClient(d.getRoot(), player));
		assertEquals(List.of("arena", "guide", "herald", "journal", "language", "quest", "status", "talk"), AliasTest.suggestions(playerSource, "heraldia ", player));
		assertEquals(List.of("stall"), AliasTest.suggestions(playerSource, "heraldia herald ", player));
		assertEquals(List.of("claim", "leave", "pay"), AliasTest.suggestions(playerSource, "heraldia herald stall ", player));
		assertEquals(List.of("abandon", "accept", "list", "turnin"), AliasTest.suggestions(playerSource, "heraldia quest ", player));
		assertEquals(List.of("bye", "more", "rumor", "trade"), AliasTest.suggestions(playerSource, "heraldia talk ", player));
		// T41: anyone sees the leaderboard and start (the mode menu buttons; the Java requires being in the ring)
		assertEquals(List.of("leaderboard", "leave", "start"), AliasTest.suggestions(playerSource, "heraldia arena ", player));
		assertEquals(List.of("coop", "survival", "timeattack"), AliasTest.suggestions(playerSource, "heraldia arena leaderboard ", player));
		// all the aliases are on the server
		List<String> hidden = new ArrayList<>();
		collect(root(), hidden);
		assertEquals(Alias.LEGACY.size(), hidden.size(), hidden.toString());
	}

	private static void collect(CommandNode<CommandSourceStack> n, List<String> out) {
		for (CommandNode<CommandSourceStack> h : n.getChildren()) {
			if (!Alias.visible(h)) {
				out.add(h.getName());
			} else {
				collect(h, out);
			}
		}
	}

	@Test
	void keyAllIsAll() {
		assertEquals("all", KeyCommand.option("todas"));
		assertEquals("all", KeyCommand.option("all"));
		assertEquals("atlantida", KeyCommand.option("atlantida"));
	}
}
