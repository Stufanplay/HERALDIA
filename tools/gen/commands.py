"""Names of the mod's commands: in English since T35b, with the old Spanish ones as hidden aliases (Java:
comando/Alias.OLD, which test_comandos compares with this). Used to check that no text or button (run_command,
suggest_command) of the mod sends the player to an old name.

Permanent rule (docs/DEVELOPMENT.md): every new command is in English; the texts the player sees stay translated.
"""
import itertools
import re

# canonical path under /heraldia -> old name of its last segment (the same map as comando/Alias.OLD)
OLD = {
    "guide": "guia",
    "key": "llave",
    "info nearby": "cerca",
    "info here": "aqui",
    "arena leave": "salir",
    "arena place": "colocar",
    "arena place confirm": "confirmar",
    "arena move": "mover",
    "arena move confirm": "confirmar",
    "arena remove": "quitar",
    "arena remove confirm": "confirmar",
    "arena start": "empezar",
    "arena stop": "parar",
}
# old argument values: (command path, old, new)
OLD_VALUES = [("key", "todas", "all")]
# the literal subcommands with their canonical name (arguments in <>), to check the Java tree
CANONICAL = [
    "info", "info nearby", "info nearby <radius>", "info here", "guide", "key", "key <players>", "key <players> <key>",
    "arena", "arena leave", "arena place", "arena place confirm", "arena move", "arena move confirm", "arena remove",
    "arena remove confirm", "arena start", "arena stop",
    "arena start coop", "arena start timeattack", "arena start survival",   # T41: arena modes
    "arena leaderboard", "arena leaderboard coop", "arena leaderboard coop <week>", "arena leaderboard timeattack",
    "arena leaderboard timeattack <week>", "arena leaderboard survival", "arena leaderboard survival <week>",
    "arena season", "arena season reset",
    "review", "review next", "review previous", "review skip", "review skip <note>", "review goto", "review goto <id>",
    "review goto <id> generate", "review mark", "review mark checked", "review mark checked <note>", "review mark problem",
    "review mark problem <note>", "review list", "review status", "review reset",
    "status", "status <page>", "reload", "update", "update check",
    "profile",                                   # T36: the play profile
    "webmap", "webmap refresh",
    "treasure", "treasure give", "treasure give <players>", "treasure info",   # T40: treasure hunt (operators)
    "quest", "quest list", "quest accept", "quest accept <number>", "quest abandon", "quest abandon <number>",
    "quest turnin",                              # T38: the board quests
    "talk", "talk more", "talk rumor", "talk trade", "talk bye",   # P9a: the answer buttons of a villager conversation
    "talk with", "talk with <villager>",         # and a conversation started by an operator (preview, tests)
    "choice", "choice click", "choice click <slot>", "choice click <slot> <input>", "choice click <slot> <input> <button>",
    "choice reply", "choice reply <session>", "choice reply <session> <option>",   # the choice windows, as a client (operators, tests)
    "choice send", "choice send button", "choice send button <id>", "choice send slot-state", "choice send slot-state <slot>",
    "choice send slot-state <slot> <on>", "choice send bundle", "choice send bundle <slot>", "choice send bundle <slot> <index>",
    "choice send pick", "choice send pick <x>", "choice send pick <x> <y>", "choice send pick <x> <y> <z>",
    "choice send pick <x> <y> <z> <data>", "choice send recipe", "choice send recipe <recipe>",   # the other window packets (tests)
    "caravan", "caravan spawn", "caravan spawn raid", "caravan spawn peaceful", "caravan raid", "caravan list",
    "caravan clear",                             # T39: the caravans (operators)
    "caravan wayfarer", "caravan wayfarer pilgrim", "caravan wayfarer shepherd", "caravan wayfarer messenger",
    "caravan wayfarer patrol", "caravan wayfarer hunter",   # the wayfarers, on the caravans' engine (operators)
    "wizard", "wizard reveal",                   # T43: the wizard huts (operators)
    # T46: configuration panel in dialogs, each player's language and safe updates
    "config", "config menu", "config menu <menu>", "config profile", "config profile <profile>",
    "config profile <profile> confirm",          # light profile: confirmation in a world already started
    "config save",
    "config save <menu>", "config save <menu> <values>", "config set", "config set <option>", "config set <option> <value>",
    "language", "language <language>",
    "update analyze", "update apply", "update apply confirm", "update apply confirm <id>", "update apply confirm <id> backup",
    "update apply confirm <id> nobackup", "update apply confirm <id> nobackup risk", "update undo", "update undo confirm",
    "update undo confirm <id>", "update repair", "update repair dry-run",
    "update mend", "update mend scan", "update mend apply", "update mend apply water", "update mend apply water confirm", "update mend apply water confirm <id>", "update mend apply streams", "update mend apply streams confirm", "update mend apply streams confirm <id>", "update mend apply wharf", "update mend apply wharf confirm", "update mend apply wharf confirm <id>", "update mend apply inn", "update mend apply inn confirm", "update mend apply inn confirm <id>", "update mend apply all", "update mend apply all confirm", "update mend apply all confirm <id>",
    "journal", "journal villages", "journal uniques", "journal mediums", "journal mines", "journal coast",
    "journal nether", "journal end",             # each player's journal: found and missing, by kind
    "journal chronicle", "journal chronicle book",   # the end of the Chronicle: guardians defeated; a copy of the last leaf
    "herald", "herald place", "herald place here", "herald place confirm",   # the Herald's House (operators place it)
    "herald roads",                              # its roads, huts and the arena road (operators, in a world whose town came first)
    "herald grounds",                            # its levelled grounds, houses and cherry trees (operators, idem)
    "herald stall", "herald stall claim", "herald stall claim <stall>", "herald stall pay", "herald stall pay <stall>",
    "herald stall pay <stall> <periods>", "herald stall leave", "herald stall leave <stall>", "herald stall evict",
    "herald stall evict <stall>",                # its market stalls for rent
    "event", "event list", "event start", "event start market", "event start wedding", "event start funeral",
    "event start festival", "event stop", "event stop all", "event with", "event with <entity>",   # village events (operators)
]


def old_paths():
    """All the paths (without "/heraldia") in which at least one segment uses the old name: "guia", "arena colocar
    confirmar", "arena place confirmar", "arena colocar confirm"..."""
    out = set()
    for route in OLD:
        segments = route.split()
        options = []
        for i in range(len(segments)):
            partial = " ".join(segments[:i + 1])
            options.append([segments[i]] + ([OLD[partial]] if partial in OLD else []))
        for combo in itertools.product(*options):
            if list(combo) != segments:
                out.add(" ".join(combo))
    return sorted(out, key=lambda r: (-len(r), r))


def _pattern():
    routes = "|".join(re.escape(r) for r in old_paths())
    values = "|".join(rf"(?:{re.escape(c)}|{re.escape(OLD.get(c, c))}) \S+ {re.escape(v)}" for c, v, _ in OLD_VALUES)
    return re.compile(rf"\bheraldia (?:{routes})(?!\w|\.\w)|\bheraldia (?:{values})(?!\w|\.\w)")


PATTERN = _pattern()


def old_in(text):
    """The mentions of a command with an old name ("/heraldia guia", "heraldia arena colocar"...) in a text."""
    return [m.group(0) for m in PATTERN.finditer(text)]


def text_errors(texts, where=""):
    """[error] for each text in {key: text} that names an old command."""
    return [f"{where}{k}: «{m}» es un nombre antiguo" for k, t in texts.items() if isinstance(t, str) for m in old_in(t)]


def click_orders(obj):
    """[(action, command)] of all the click_event / clickEvent run_command and suggest_command in a JSON (text
    components of tellraw, books, signs...)."""
    out = []
    if isinstance(obj, dict):
        for k in ("click_event", "clickEvent"):
            ev = obj.get(k)
            if isinstance(ev, dict) and ev.get("action") in ("run_command", "suggest_command"):
                out.append((ev["action"], str(ev.get("command", ev.get("value", "")))))
        for v in obj.values():
            out += click_orders(v)
    elif isinstance(obj, list):
        for v in obj:
            out += click_orders(v)
    elif isinstance(obj, str) and ("run_command" in obj or "suggest_command" in obj):
        # a component written as JSON text inside another (SNBT of the signs, tellraw of the functions)
        for m in re.finditer(r'"(?:command|value)"\s*:\s*"([^"]*)"', obj):
            out.append(("texto", m.group(1)))
    return out


def click_errors(obj, where=""):
    """[error] for each button (run_command / suggest_command) that sends to a command with an old name."""
    return [f"{where}{action} «{order}» usa un nombre antiguo" for action, order in click_orders(obj) if old_in(order)]
