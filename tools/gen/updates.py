"""Texts for the safe updates (T46, Java: comando/PanelConfig, comando/Preferencias and actualizar/): the configuration
panel in dialogs (/heraldia config), each player's language (/heraldia language), per-version fixes
(/heraldia update repair) and bringing new content to an existing world (/heraldia update analyze, apply and undo).

Each text goes in all 8 languages in this module, in the order of LANGUAGES: es_es and en_us come from lang(); the others are copied
to idiomas/<code>.json with `python3 tools/gen/updates.py` (checked by tests/test_updates.py).
"""
import json
import os

NS = "heraldia"
LANGUAGES = ("es_es", "en_us", "fr_fr", "de_de", "it_it", "pt_br", "ca_es", "gl_es")
# name of each language in its own language (the same in all languages)
LANGUAGE_NAMES = {"es_es": "Español", "en_us": "English", "fr_fr": "Français", "de_de": "Deutsch", "it_it": "Italiano",
                  "pt_br": "Português (Brasil)", "ca_es": "Català", "gl_es": "Galego"}
# panel submenus (config/Menus.MENUS, in the same order): id -> (title, help) per language
MENUS = ("mundo", "aldeas", "combate", "botin", "arena", "jugadores", "avanzado")
PROFILES = ("casual", "estandar", "hardcore", "ligero")
# generator options in arreglos/ArreglosMobs.REGISTRY (heraldia.arreglos.<id>)
FIXES = ("marcas", "bebes", "nautilos", "recoger", "armas")

_T = {
    # ---------------- configuration panel (/heraldia config)
    "panel.titulo": ("Configuración de Heraldia", "Heraldia configuration", "Configuration de Heraldia",
                     "Heraldia-Einstellungen", "Configurazione di Heraldia", "Configuração do Heraldia",
                     "Configuració de Heraldia", "Configuración de Heraldia"),
    "panel.perfil": ("Perfil de juego en uso: %s", "Gameplay profile in use: %s", "Profil de jeu actuel : %s",
                     "Aktuelles Spielprofil: %s", "Profilo di gioco attuale: %s", "Perfil de jogo em uso: %s",
                     "Perfil de joc en ús: %s", "Perfil de xogo en uso: %s"),
    "panel.ayuda": ("Elige un perfil (fija la dificultad, los jefes, el botín y la arena) o entra en un apartado. "
                    "Lo técnico está en Avanzado o en config/heraldia.json.",
                    "Pick a profile (it sets difficulty, bosses, loot and the arena) or open a section. "
                    "Technical settings are under Advanced or in config/heraldia.json.",
                    "Choisis un profil (il règle la difficulté, les boss, le butin et l'arène) ou ouvre une section. "
                    "Les réglages techniques sont dans Avancé ou dans config/heraldia.json.",
                    "Wähle ein Profil (es legt Schwierigkeit, Bosse, Beute und Arena fest) oder öffne einen Bereich. "
                    "Technisches steht unter Erweitert oder in config/heraldia.json.",
                    "Scegli un profilo (imposta difficoltà, boss, bottino e arena) o apri una sezione. "
                    "Le impostazioni tecniche sono in Avanzate o in config/heraldia.json.",
                    "Escolha um perfil (define a dificuldade, os chefes, o saque e a arena) ou abra uma seção. "
                    "O que é técnico fica em Avançado ou em config/heraldia.json.",
                    "Tria un perfil (fixa la dificultat, els caps, el botí i l'arena) o entra en un apartat. "
                    "El que és tècnic és a Avançat o a config/heraldia.json.",
                    "Escolle un perfil (fixa a dificultade, os xefes, o botín e a area) ou entra nun apartado. "
                    "O técnico está en Avanzado ou en config/heraldia.json."),
    "panel.perfil.casual": ("Más fácil, con el botín que se repone", "Easier, with restocking loot", "Plus facile, avec le butin qui se renouvelle",
                            "Leichter, mit nachgefüllter Beute", "Più facile, con il bottino che si rigenera", "Mais fácil, com saque que se repõe",
                            "Més fàcil, amb el botí que es reposa", "Máis doado, co botín que se repón"),
    "panel.perfil.estandar": ("El juego de siempre (recomendado)", "The usual game (recommended)", "Le jeu habituel (recommandé)",
                              "Das übliche Spiel (empfohlen)", "Il gioco di sempre (consigliato)", "O jogo de sempre (recomendado)",
                              "El joc de sempre (recomanat)", "O xogo de sempre (recomendado)"),
    "panel.perfil.hardcore": ("Más difícil y con más refuerzos", "Harder, with more reinforcements", "Plus difficile, avec plus de renforts",
                              "Schwerer, mit mehr Verstärkung", "Più difficile, con più rinforzi", "Mais difícil e com mais reforços",
                              "Més difícil i amb més reforços", "Máis difícil e con máis reforzos"),
    "panel.perfil.ligero": ("Para equipos modestos: generación más ligera", "For modest machines: lighter generation",
                            "Pour machines modestes : génération plus légère", "Für bescheidene Rechner: leichtere Generierung",
                            "Per macchine modeste: generazione più leggera", "Para máquinas modestas: geração mais leve",
                            "Per a equips modestos: generació més lleugera", "Para equipos modestos: xeración máis lixeira"),
    "panel.ligero.titulo": ("Perfil ligero en un mundo ya empezado", "Light profile in a world already started",
                            "Profil léger dans un monde déjà commencé", "Leichtes Profil in einer schon begonnenen Welt",
                            "Profilo leggero in un mondo già iniziato", "Perfil leve num mundo já começado",
                            "Perfil lleuger en un món ja començat", "Perfil lixeiro nun mundo xa comezado"),
    "panel.ligero.aviso": (
        "El perfil ligero cambia la generación del mundo: menos estructuras medianas y más separadas, aldeas grandes más raras, "
        "sin caminos ni caravanas y las minas vanilla como en vanilla. Lo ya generado no cambia: solo los chunks nuevos, después "
        "de reiniciar. Junto al terreno ya explorado quedarán costuras (una zona densa junto a otra más vacía, caminos que "
        "acaban en el borde) y /locate y los mapas pueden dejar de encontrar estructuras medianas ya generadas.",
        "The light profile changes world generation: fewer, more spread-out medium structures, rarer large villages, no roads "
        "or caravans and vanilla mineshafts as in vanilla. What is already generated does not change: only new chunks, after a "
        "restart. Next to the land already explored there will be seams (a dense zone next to an emptier one, roads ending at "
        "the edge) and /locate and maps may no longer find medium structures already generated.",
        "Le profil léger change la génération du monde : moins de structures moyennes et plus espacées, grands villages plus "
        "rares, ni chemins ni caravanes et les puits de mine vanilla comme en vanilla. Ce qui est déjà généré ne change pas : "
        "seulement les nouveaux chunks, après un redémarrage. À côté des terres déjà explorées il restera des coutures (une zone "
        "dense à côté d'une plus vide, des chemins qui s'arrêtent au bord) et /locate et les cartes peuvent ne plus trouver des "
        "structures moyennes déjà générées.",
        "Das leichte Profil ändert die Weltgenerierung: weniger und weiter verteilte mittlere Bauwerke, seltenere große Dörfer, "
        "keine Wege und Karawanen und Vanilla-Minen wie in Vanilla. Bereits Generiertes ändert sich nicht: nur neue Chunks, nach "
        "einem Neustart. Neben dem schon erkundeten Land bleiben Nähte (eine dichte Zone neben einer leereren, Wege, die am Rand "
        "enden), und /locate und Karten finden schon generierte mittlere Bauwerke womöglich nicht mehr.",
        "Il profilo leggero cambia la generazione del mondo: strutture medie più rare e distanti, villaggi grandi più rari, "
        "niente sentieri né carovane e le miniere vanilla come in vanilla. Ciò che è già generato non cambia: solo i chunk nuovi, "
        "dopo un riavvio. Accanto alle terre già esplorate resteranno cuciture (una zona densa accanto a una più vuota, sentieri "
        "che finiscono sul bordo) e /locate e le mappe potrebbero non trovare più strutture medie già generate.",
        "O perfil leve muda a geração do mundo: menos estruturas médias e mais espaçadas, aldeias grandes mais raras, sem "
        "caminhos nem caravanas e as minas vanilla como no vanilla. O que já foi gerado não muda: só os chunks novos, depois de "
        "reiniciar. Junto ao terreno já explorado ficarão costuras (uma zona densa ao lado de outra mais vazia, caminhos que "
        "acabam na borda) e o /locate e os mapas podem deixar de encontrar estruturas médias já geradas.",
        "El perfil lleuger canvia la generació del món: menys estructures mitjanes i més separades, viles grans més rares, "
        "sense camins ni caravanes i les mines vanilla com a vanilla. El que ja s'ha generat no canvia: només els chunks nous, "
        "després de reiniciar. Al costat del terreny ja explorat quedaran costures (una zona densa al costat d'una més buida, "
        "camins que acaben a la vora) i /locate i els mapes poden deixar de trobar estructures mitjanes ja generades.",
        "O perfil lixeiro cambia a xeración do mundo: menos estruturas medianas e máis separadas, aldeas grandes máis raras, "
        "sen camiños nin caravanas e as minas vanilla coma en vanilla. O xa xerado non cambia: só os chunks novos, despois de "
        "reiniciar. Xunto ao terreo xa explorado quedarán costuras (unha zona densa xunto a outra máis baleira, camiños que "
        "rematan no bordo) e /locate e os mapas poden deixar de atopar estruturas medianas xa xeradas."),
    "panel.ligero.aplicar": ("Aplicar igualmente", "Apply anyway", "Appliquer quand même", "Trotzdem anwenden",
                             "Applica comunque", "Aplicar mesmo assim", "Aplica igualment", "Aplicar igualmente"),
    "panel.ligero.aplicar.ayuda": ("Guarda el perfil ligero; la generación cambia al reiniciar", "Saves the light profile; generation changes after a restart",
                                   "Enregistre le profil léger ; la génération change au redémarrage",
                                   "Speichert das leichte Profil; die Generierung ändert sich nach einem Neustart",
                                   "Salva il profilo leggero; la generazione cambia al riavvio",
                                   "Salva o perfil leve; a geração muda ao reiniciar",
                                   "Desa el perfil lleuger; la generació canvia en reiniciar",
                                   "Garda o perfil lixeiro; a xeración cambia ao reiniciar"),
    "panel.cerrar": ("Cerrar", "Close", "Fermer", "Schließen", "Chiudi", "Fechar", "Tanca", "Pechar"),
    "panel.guardar": ("Guardar", "Save", "Enregistrer", "Speichern", "Salva", "Salvar", "Desa", "Gardar"),
    "panel.guardar.ayuda": ("Escribe config/heraldia.json y aplica lo que se puede sin reiniciar",
                            "Writes config/heraldia.json and applies what can be applied without a restart",
                            "Écrit config/heraldia.json et applique ce qui peut l'être sans redémarrer",
                            "Schreibt config/heraldia.json und wendet an, was ohne Neustart geht",
                            "Scrive config/heraldia.json e applica ciò che si può senza riavviare",
                            "Grava config/heraldia.json e aplica o que for possível sem reiniciar",
                            "Escriu config/heraldia.json i aplica el que es pot sense reiniciar",
                            "Escribe config/heraldia.json e aplica o que se pode sen reiniciar"),
    "panel.volver": ("Volver", "Back", "Retour", "Zurück", "Indietro", "Voltar", "Torna", "Volver"),
    "panel.volver.ayuda": ("Vuelve al panel sin guardar", "Back to the panel without saving", "Retour au panneau sans enregistrer",
                           "Zurück zum Menü, ohne zu speichern", "Torna al pannello senza salvare", "Volta ao painel sem salvar",
                           "Torna al tauler sense desar", "Volve ao panel sen gardar"),
    "panel.opcion": ("%s: %s. Recomendado: %s.", "%s: %s. Recommended: %s.", "%s : %s. Recommandé : %s.",
                     "%s: %s. Empfohlen: %s.", "%s: %s. Consigliato: %s.", "%s: %s. Recomendado: %s.",
                     "%s: %s. Recomanat: %s.", "%s: %s. Recomendado: %s."),
    "panel.reinicio": ("[se aplica al reiniciar]", "[applies after a restart]", "[s'applique au redémarrage]",
                       "[gilt nach einem Neustart]", "[si applica al riavvio]", "[aplica-se ao reiniciar]",
                       "[s'aplica en reiniciar]", "[aplícase ao reiniciar]"),
    "panel.si": ("sí", "yes", "oui", "ja", "sì", "sim", "sí", "si"),
    "panel.no": ("no", "no", "non", "nein", "no", "não", "no", "non"),
    "panel.resultado": ("Configuración guardada", "Configuration saved", "Configuration enregistrée", "Einstellungen gespeichert",
                        "Configurazione salvata", "Configuração salva", "Configuració desada", "Configuración gardada"),
    "panel.sin_cambios": ("No has cambiado nada.", "Nothing was changed.", "Rien n'a changé.", "Nichts wurde geändert.",
                          "Non hai cambiato nulla.", "Nada foi alterado.", "No has canviat res.", "Non cambiaches nada."),
    "panel.guardada": ("✔ %s = %s (ya aplicado)", "✔ %s = %s (applied now)", "✔ %s = %s (appliqué)", "✔ %s = %s (sofort angewendet)",
                       "✔ %s = %s (applicato ora)", "✔ %s = %s (aplicado agora)", "✔ %s = %s (aplicat ara)", "✔ %s = %s (aplicado xa)"),
    "panel.guardada_reinicio": ("⟳ %s = %s (guardado; se aplica al reiniciar el servidor)",
                                "⟳ %s = %s (saved; applies when the server restarts)",
                                "⟳ %s = %s (enregistré ; s'applique au redémarrage du serveur)",
                                "⟳ %s = %s (gespeichert; gilt nach dem Serverneustart)",
                                "⟳ %s = %s (salvato; si applica al riavvio del server)",
                                "⟳ %s = %s (salvo; aplica-se ao reiniciar o servidor)",
                                "⟳ %s = %s (desat; s'aplica en reiniciar el servidor)",
                                "⟳ %s = %s (gardado; aplícase ao reiniciar o servidor)"),
    "panel.invalida": ("Valor no válido para %s: %s", "Invalid value for %s: %s", "Valeur non valide pour %s : %s",
                       "Ungültiger Wert für %s: %s", "Valore non valido per %s: %s", "Valor inválido para %s: %s",
                       "Valor no vàlid per a %s: %s", "Valor non válido para %s: %s"),
    "panel.no_existe": ("No existe: %s", "Does not exist: %s", "N'existe pas : %s", "Gibt es nicht: %s", "Non esiste: %s",
                        "Não existe: %s", "No existeix: %s", "Non existe: %s"),
    "panel.error": ("No se pudo guardar la configuración: %s", "Could not save the configuration: %s",
                    "Impossible d'enregistrer la configuration : %s", "Einstellungen konnten nicht gespeichert werden: %s",
                    "Impossibile salvare la configurazione: %s", "Não foi possível salvar a configuração: %s",
                    "No s'ha pogut desar la configuració: %s", "Non se puido gardar a configuración: %s"),
    "panel.consola": ("Desde la consola: /heraldia config set <opción> <valor> (o abre /heraldia config en el juego).",
                      "From the console: /heraldia config set <option> <value> (or open /heraldia config in game).",
                      "Depuis la console : /heraldia config set <option> <valeur> (ou ouvre /heraldia config en jeu).",
                      "Über die Konsole: /heraldia config set <Option> <Wert> (oder öffne /heraldia config im Spiel).",
                      "Dalla console: /heraldia config set <opzione> <valore> (o apri /heraldia config nel gioco).",
                      "Pelo console: /heraldia config set <opção> <valor> (ou abra /heraldia config no jogo).",
                      "Des de la consola: /heraldia config set <opció> <valor> (o obre /heraldia config al joc).",
                      "Desde a consola: /heraldia config set <opción> <valor> (ou abre /heraldia config no xogo)."),
    "panel.menu.mundo": ("Mundo y generación", "World and generation", "Monde et génération", "Welt und Generierung",
                         "Mondo e generazione", "Mundo e geração", "Món i generació", "Mundo e xeración"),
    "panel.menu.mundo.ayuda": ("Estructuras medianas, minas, faros y distancia entre únicas (solo en chunks nuevos)",
                               "Medium structures, mines, lighthouses and distance between unique ones (new chunks only)",
                               "Structures moyennes, mines, phares et distance entre uniques (nouveaux chunks seulement)",
                               "Mittlere Bauwerke, Minen, Leuchttürme und Abstand der einzigartigen (nur neue Chunks)",
                               "Strutture medie, miniere, fari e distanza tra le uniche (solo chunk nuovi)",
                               "Estruturas médias, minas, faróis e distância entre únicas (só chunks novos)",
                               "Estructures mitjanes, mines, fars i distància entre úniques (només chunks nous)",
                               "Estruturas medianas, minas, faros e distancia entre únicas (só chunks novos)"),
    "panel.menu.aldeas": ("Aldeas y caminos", "Villages and roads", "Villages et chemins", "Dörfer und Wege",
                          "Villaggi e sentieri", "Aldeias e caminhos", "Llogarets i camins", "Aldeas e camiños"),
    "panel.menu.aldeas.ayuda": ("Separación y tamaño de las aldeas, caminos, tratos, tablón y gólems",
                                "Village spacing and size, roads, trades, job board and golems",
                                "Espacement et taille des villages, chemins, échanges, tableau et golems",
                                "Abstand und Größe der Dörfer, Wege, Handel, Auftragstafel und Golems",
                                "Distanza e dimensione dei villaggi, sentieri, scambi, bacheca e golem",
                                "Distância e tamanho das aldeias, caminhos, trocas, quadro e golens",
                                "Separació i mida dels llogarets, camins, tractes, tauler i gòlems",
                                "Separación e tamaño das aldeas, camiños, tratos, taboleiro e gólems"),
    "panel.menu.combate": ("Combate y jefes", "Combat and bosses", "Combat et boss", "Kampf und Bosse", "Combattimento e boss",
                           "Combate e chefes", "Combat i caps", "Combate e xefes"),
    "panel.menu.combate.ayuda": ("Dificultad de los mobs de Heraldia y combates contra los guardianes",
                                 "Difficulty of Heraldia mobs and guardian fights",
                                 "Difficulté des mobs de Heraldia et combats contre les gardiens",
                                 "Schwierigkeit der Heraldia-Mobs und Kämpfe gegen die Wächter",
                                 "Difficoltà dei mob di Heraldia e combattimenti con i guardiani",
                                 "Dificuldade dos mobs do Heraldia e combates contra os guardiões",
                                 "Dificultat dels mobs de Heraldia i combats contra els guardians",
                                 "Dificultade dos mobs de Heraldia e combates contra os gardiáns"),
    "panel.menu.botin": ("Botín", "Loot", "Butin", "Beute", "Bottino", "Saque", "Botí", "Botín"),
    "panel.menu.botin.ayuda": ("Botín que se repone, búsqueda del tesoro y premios", "Restocking loot, treasure hunt and rewards",
                               "Butin qui se renouvelle, chasse au trésor et récompenses", "Nachfüllende Beute, Schatzsuche und Belohnungen",
                               "Bottino che si rigenera, caccia al tesoro e premi", "Saque que se repõe, caça ao tesouro e prêmios",
                               "Botí que es reposa, cerca del tresor i premis", "Botín que se repón, busca do tesouro e premios"),
    "panel.menu.arena": ("Arena", "Arena", "Arène", "Arena", "Arena", "Arena", "Arena", "Area"),
    "panel.menu.arena.ayuda": ("La arena de oleadas: si está activa, sus modos y sus límites",
                               "The wave arena: whether it is on, its modes and its limits",
                               "L'arène de vagues : activée ou non, ses modes et ses limites",
                               "Die Wellenarena: ob sie aktiv ist, ihre Modi und Grenzen",
                               "L'arena a ondate: se è attiva, le sue modalità e i suoi limiti",
                               "A arena de ondas: se está ativa, seus modos e limites",
                               "L'arena d'onades: si està activa, els seus modes i els seus límits",
                               "A area de vagas: se está activa, os seus modos e os seus límites"),
    "panel.menu.jugadores": ("Jugadores y Guía", "Players and Guide", "Joueurs et Guide", "Spieler und Leitfaden",
                             "Giocatori e Guida", "Jogadores e Guia", "Jugadors i Guia", "Xogadores e Guía"),
    "panel.menu.jugadores.ayuda": ("Guía del Heraldo, encargos, reputación y caravanas",
                                   "Herald's Guide, quests, reputation and caravans",
                                   "Guide du Héraut, missions, réputation et caravanes",
                                   "Leitfaden des Herolds, Aufträge, Ruf und Karawanen",
                                   "Guida dell'Araldo, incarichi, reputazione e carovane",
                                   "Guia do Arauto, encargos, reputação e caravanas",
                                   "Guia de l'Herald, encàrrecs, reputació i caravanes",
                                   "Guía do Heraldo, encargos, reputación e caravanas"),
    "panel.menu.avanzado": ("Avanzado", "Advanced", "Avancé", "Erweitert", "Avanzate", "Avançado", "Avançat", "Avanzado"),
    "panel.menu.avanzado.ayuda": ("Compatibilidad, avisos de versión, mapas web y margen de las actualizaciones",
                                  "Compatibility, version notices, web maps and update margin",
                                  "Compatibilité, avis de version, cartes web et marge des mises à jour",
                                  "Kompatibilität, Versionshinweise, Webkarten und Abstand bei Updates",
                                  "Compatibilità, avvisi di versione, mappe web e margine degli aggiornamenti",
                                  "Compatibilidade, avisos de versão, mapas web e margem das atualizações",
                                  "Compatibilitat, avisos de versió, mapes web i marge de les actualitzacions",
                                  "Compatibilidade, avisos de versión, mapas web e marxe das actualizacións"),
    # ---------------- each player's language (/heraldia language)
    "idioma.actual": ("Idioma de Heraldia: %s (elegido por ti).", "Heraldia language: %s (your choice).",
                      "Langue de Heraldia : %s (ton choix).", "Heraldia-Sprache: %s (deine Wahl).",
                      "Lingua di Heraldia: %s (scelta da te).", "Idioma do Heraldia: %s (escolhido por você).",
                      "Idioma de Heraldia: %s (triat per tu).", "Idioma de Heraldia: %s (escollido por ti)."),
    "idioma.actual_cliente": ("Idioma de Heraldia: %s (el de tu juego). Elige otro:", "Heraldia language: %s (your game's). Pick another:",
                              "Langue de Heraldia : %s (celle de ton jeu). Choisis-en une autre :",
                              "Heraldia-Sprache: %s (die deines Spiels). Wähle eine andere:",
                              "Lingua di Heraldia: %s (quella del tuo gioco). Scegline un'altra:",
                              "Idioma do Heraldia: %s (o do seu jogo). Escolha outro:",
                              "Idioma de Heraldia: %s (el del teu joc). Tria'n un altre:",
                              "Idioma de Heraldia: %s (o do teu xogo). Escolle outro:"),
    "idioma.auto": ("[Automático]", "[Automatic]", "[Automatique]", "[Automatisch]", "[Automatico]", "[Automático]",
                    "[Automàtic]", "[Automático]"),
    "idioma.fijado": ("Los textos de Heraldia te saldrán en %s.", "Heraldia texts will now be in %s.",
                      "Les textes de Heraldia seront désormais en %s.", "Heraldia-Texte erscheinen jetzt auf %s.",
                      "I testi di Heraldia ora saranno in %s.", "Os textos do Heraldia agora aparecerão em %s.",
                      "Els textos de Heraldia et sortiran en %s.", "Os textos de Heraldia sairanche en %s."),
    "idioma.automatico": ("Heraldia vuelve a usar el idioma de tu juego (%s).", "Heraldia uses your game's language again (%s).",
                          "Heraldia utilise de nouveau la langue de ton jeu (%s).", "Heraldia nutzt wieder die Sprache deines Spiels (%s).",
                          "Heraldia usa di nuovo la lingua del tuo gioco (%s).", "O Heraldia volta a usar o idioma do seu jogo (%s).",
                          "Heraldia torna a fer servir l'idioma del teu joc (%s).", "Heraldia volve usar o idioma do teu xogo (%s)."),
    "idioma.no_existe": ("No hay idioma «%s». Los que hay: %s", "There is no language “%s”. Available: %s",
                         "La langue « %s » n'existe pas. Disponibles : %s", "Die Sprache „%s“ gibt es nicht. Verfügbar: %s",
                         "La lingua «%s» non esiste. Disponibili: %s", "Não há o idioma “%s”. Disponíveis: %s",
                         "No hi ha l'idioma «%s». N'hi ha: %s", "Non hai o idioma «%s». Hai estes: %s"),
    "idioma.solo_jugadores": ("Solo un jugador puede elegir su idioma.", "Only a player can choose their language.",
                              "Seul un joueur peut choisir sa langue.", "Nur ein Spieler kann seine Sprache wählen.",
                              "Solo un giocatore può scegliere la propria lingua.", "Só um jogador pode escolher seu idioma.",
                              "Només un jugador pot triar el seu idioma.", "Só un xogador pode escoller o seu idioma."),
    # ---------------- arreglos (/heraldia update repair)
    "arreglos.hecho": ("Arreglos: %s mobs de plantilla revisados, %s cambios.", "Fixes: %s template mobs checked, %s changes.",
                       "Correctifs : %s mobs de structure vérifiés, %s changements.", "Korrekturen: %s Bauwerks-Mobs geprüft, %s Änderungen.",
                       "Correzioni: %s mob di struttura controllati, %s modifiche.", "Correções: %s mobs de estrutura revisados, %s mudanças.",
                       "Arranjaments: %s mobs de plantilla revisats, %s canvis.", "Arranxos: %s mobs de modelo revisados, %s cambios."),
    "arreglos.prueba": ("Prueba (no se cambia nada): %s mobs de plantilla revisados, %s cambios pendientes.",
                        "Dry run (nothing changed): %s template mobs checked, %s pending changes.",
                        "Essai (rien n'est modifié) : %s mobs de structure vérifiés, %s changements en attente.",
                        "Probelauf (nichts geändert): %s Bauwerks-Mobs geprüft, %s ausstehende Änderungen.",
                        "Prova (nulla cambia): %s mob di struttura controllati, %s modifiche in sospeso.",
                        "Teste (nada é alterado): %s mobs de estrutura revisados, %s mudanças pendentes.",
                        "Prova (no es canvia res): %s mobs de plantilla revisats, %s canvis pendents.",
                        "Proba (non se cambia nada): %s mobs de modelo revisados, %s cambios pendentes."),
    "arreglos.linea": (" - %s: %s cambios, %s avisos", " - %s: %s changes, %s warnings", " - %s : %s changements, %s avertissements",
                       " - %s: %s Änderungen, %s Hinweise", " - %s: %s modifiche, %s avvisi", " - %s: %s mudanças, %s avisos",
                       " - %s: %s canvis, %s avisos", " - %s: %s cambios, %s avisos"),
    "arreglos.marcas": ("marcas de los guardianes antiguos (anclados, adultos y jefes)",
                        "marks for old guardians (anchored, adult and bosses)",
                        "marques des anciens gardiens (ancrés, adultes et boss)",
                        "Markierungen alter Wächter (verankert, erwachsen, Bosse)",
                        "marcature dei vecchi guardiani (ancorati, adulti e boss)",
                        "marcas dos guardiões antigos (ancorados, adultos e chefes)",
                        "marques dels guardians antics (ancorats, adults i caps)",
                        "marcas dos gardiáns antigos (ancorados, adultos e xefes)"),
    "arreglos.bebes": ("guardianes bebés que pasan a adultos", "baby guardians turned into adults", "gardiens bébés devenus adultes",
                       "Baby-Wächter werden erwachsen", "guardiani neonati resi adulti", "guardiões bebês viram adultos",
                       "guardians nadons que passen a adults", "gardiáns bebés que pasan a adultos"),
    "arreglos.nautilos": ("ahogados de plantilla bajados de su nautilo zombi", "template drowned taken off their zombie nautilus",
                          "noyés de structure descendus de leur nautile zombie", "Bauwerks-Ertrunkene vom Zombie-Nautilus geholt",
                          "annegati di struttura fatti scendere dal nautilo zombi", "afogados de estrutura tirados do náutilo zumbi",
                          "ofegats de plantilla baixats del seu nàutil zombi", "afogados de modelo baixados do seu nautilo zombi"),
    "arreglos.recoger": ("mobs de plantilla que ya no recogen objetos", "template mobs that no longer pick up items",
                         "mobs de structure qui ne ramassent plus d'objets", "Bauwerks-Mobs heben keine Gegenstände mehr auf",
                         "mob di struttura che non raccolgono più oggetti", "mobs de estrutura que não pegam mais itens",
                         "mobs de plantilla que ja no recullen objectes", "mobs de modelo que xa non recollen obxectos"),
    "arreglos.armas": ("guardianes que pudieron perder su arma (solo aviso)", "guardians that may have lost their weapon (warning only)",
                       "gardiens qui ont pu perdre leur arme (avertissement seulement)", "Wächter, die ihre Waffe verloren haben könnten (nur Hinweis)",
                       "guardiani che potrebbero aver perso l'arma (solo avviso)", "guardiões que podem ter perdido a arma (só aviso)",
                       "guardians que podrien haver perdut l'arma (només avís)", "gardiáns que puideron perder a súa arma (só aviso)"),
    # ---------------- bringing new content to an existing world (/heraldia update analyze, apply, undo)
    "actualizar.analizando": ("Analizando el mundo principal fuera del hilo del servidor (puede tardar unos minutos)...",
                              "Analysing the overworld off the server thread (this can take a few minutes)...",
                              "Analyse du monde principal hors du fil du serveur (cela peut prendre quelques minutes)...",
                              "Die Oberwelt wird außerhalb des Server-Threads analysiert (das kann einige Minuten dauern)...",
                              "Analisi del mondo principale fuori dal thread del server (può richiedere qualche minuto)...",
                              "Analisando o mundo principal fora da thread do servidor (pode levar alguns minutos)...",
                              "S'està analitzant el món principal fora del fil del servidor (pot trigar uns minuts)...",
                              "Analizando o mundo principal fóra do fío do servidor (pode tardar uns minutos)..."),
    "actualizar.ocupado": ("Ya hay un análisis en marcha.", "An analysis is already running.", "Une analyse est déjà en cours.",
                           "Es läuft bereits eine Analyse.", "C'è già un'analisi in corso.", "Já há uma análise em andamento.",
                           "Ja hi ha una anàlisi en marxa.", "Xa hai unha análise en marcha."),
    "actualizar.error": ("El análisis falló: %s", "The analysis failed: %s", "L'analyse a échoué : %s", "Die Analyse ist fehlgeschlagen: %s",
                         "L'analisi non è riuscita: %s", "A análise falhou: %s", "L'anàlisi ha fallat: %s", "A análise fallou: %s"),
    "actualizar.titulo": ("Análisis de actualización: %s chunks guardados, margen de %s bloques alrededor de cada construcción.",
                          "Update analysis: %s saved chunks, %s-block margin around every build.",
                          "Analyse de mise à jour : %s chunks enregistrés, marge de %s blocs autour de chaque construction.",
                          "Update-Analyse: %s gespeicherte Chunks, %s Blöcke Abstand um jedes Bauwerk.",
                          "Analisi di aggiornamento: %s chunk salvati, margine di %s blocchi attorno a ogni costruzione.",
                          "Análise de atualização: %s chunks salvos, margem de %s blocos em volta de cada construção.",
                          "Anàlisi d'actualització: %s chunks desats, marge de %s blocs al voltant de cada construcció.",
                          "Análise de actualización: %s chunks gardados, marxe de %s bloques arredor de cada construción."),
    "actualizar.protegidos": ("Protegido: %s indicios de construcción en %s chunks y %s chunks más dentro del margen. Ahí no se toca nada.",
                              "Protected: %s signs of building in %s chunks and %s more chunks inside the margin. Nothing is touched there.",
                              "Protégé : %s indices de construction dans %s chunks et %s chunks de plus dans la marge. Rien n'y est touché.",
                              "Geschützt: %s Bauspuren in %s Chunks und %s weitere Chunks im Abstand. Dort wird nichts verändert.",
                              "Protetto: %s indizi di costruzione in %s chunk e altri %s chunk nel margine. Lì non si tocca nulla.",
                              "Protegido: %s indícios de construção em %s chunks e mais %s chunks na margem. Nada é tocado ali.",
                              "Protegit: %s indicis de construcció en %s chunks i %s chunks més dins del marge. Allà no es toca res.",
                              "Protexido: %s indicios de construción en %s chunks e %s chunks máis dentro da marxe. Alí non se toca nada."),
    "actualizar.regenerar": ("Vía A: %s chunks vírgenes se regenerarían (de %s vírgenes; %s se dejan para no cortar estructuras).",
                             "Route A: %s virgin chunks would be regenerated (of %s virgin; %s kept so no structure is cut).",
                             "Voie A : %s chunks vierges seraient régénérés (sur %s vierges ; %s gardés pour ne couper aucune structure).",
                             "Weg A: %s unberührte Chunks würden neu generiert (von %s; %s bleiben, damit kein Bauwerk zerschnitten wird).",
                             "Via A: %s chunk vergini verrebbero rigenerati (su %s vergini; %s restano per non tagliare strutture).",
                             "Via A: %s chunks virgens seriam regenerados (de %s virgens; %s ficam para não cortar estruturas).",
                             "Via A: es regenerarien %s chunks verges (de %s verges; se'n deixen %s per no tallar estructures).",
                             "Vía A: rexeneraríanse %s chunks virxes (de %s virxes; déixanse %s para non cortar estruturas)."),
    "actualizar.colocar": ("Vía B: %s estructuras nuevas de Heraldia cabrían en sitios seguros (%s sin sitio seguro).",
                           "Route B: %s new Heraldia structures would fit in safe spots (%s without a safe spot).",
                           "Voie B : %s nouvelles structures de Heraldia tiendraient dans des endroits sûrs (%s sans endroit sûr).",
                           "Weg B: %s neue Heraldia-Bauwerke passen an sichere Stellen (%s ohne sichere Stelle).",
                           "Via B: %s nuove strutture di Heraldia entrerebbero in punti sicuri (%s senza punto sicuro).",
                           "Via B: %s estruturas novas do Heraldia caberiam em lugares seguros (%s sem lugar seguro).",
                           "Via B: hi cabrien %s estructures noves de Heraldia en llocs segurs (%s sense lloc segur).",
                           "Vía B: caberían %s estruturas novas de Heraldia en sitios seguros (%s sen sitio seguro)."),
    "actualizar.protecciones": ("Hay mods de protección (%s): no se pueden leer sus zonas reclamadas, así que apply no se ejecuta.",
                                "Protection mods are installed (%s): their claimed areas cannot be read, so apply will not run.",
                                "Des mods de protection sont installés (%s) : leurs zones revendiquées sont illisibles, apply ne s'exécute donc pas.",
                                "Schutz-Mods sind installiert (%s): ihre beanspruchten Gebiete sind nicht lesbar, daher läuft apply nicht.",
                                "Ci sono mod di protezione (%s): le loro zone rivendicate non si possono leggere, quindi apply non si esegue.",
                                "Há mods de proteção (%s): suas áreas reivindicadas não podem ser lidas, então apply não é executado.",
                                "Hi ha mods de protecció (%s): no es poden llegir les seves zones reclamades, així que apply no s'executa.",
                                "Hai mods de protección (%s): non se poden ler as súas zonas reclamadas, así que apply non se executa."),
    "actualizar.informe": ("Informe: %s (y el mapa %s, en la misma carpeta).", "Report: %s (and the map %s, in the same folder).",
                           "Rapport : %s (et la carte %s, dans le même dossier).", "Bericht: %s (und die Karte %s im selben Ordner).",
                           "Rapporto: %s (e la mappa %s, nella stessa cartella).", "Relatório: %s (e o mapa %s, na mesma pasta).",
                           "Informe: %s (i el mapa %s, a la mateixa carpeta).", "Informe: %s (e o mapa %s, no mesmo cartafol)."),
    "actualizar.nada_cambia": ("El análisis no ha cambiado nada del mundo.", "The analysis has not changed anything in the world.",
                               "L'analyse n'a rien modifié dans le monde.", "Die Analyse hat nichts an der Welt verändert.",
                               "L'analisi non ha cambiato nulla nel mondo.", "A análise não alterou nada no mundo.",
                               "L'anàlisi no ha canviat res del món.", "A análise non cambiou nada do mundo."),
    "actualizar.nada_que_hacer": ("No hay nada que actualizar en este mundo.", "There is nothing to update in this world.",
                                  "Il n'y a rien à mettre à jour dans ce monde.", "In dieser Welt gibt es nichts zu aktualisieren.",
                                  "Non c'è nulla da aggiornare in questo mondo.", "Não há nada para atualizar neste mundo.",
                                  "No hi ha res a actualitzar en aquest món.", "Non hai nada que actualizar neste mundo."),
    "actualizar.dialogo": ("Actualizar el mundo", "Update the world", "Mettre à jour le monde", "Welt aktualisieren",
                           "Aggiorna il mondo", "Atualizar o mundo", "Actualitza el món", "Actualizar o mundo"),
    "actualizar.aviso_parada": ("Al confirmar, se avisa a los jugadores y el servidor SE PARA. Tendrás que arrancarlo tú a mano: "
                                "al arrancar se hace el trabajo y queda el informe.",
                                "On confirming, players are warned and the server STOPS. You must start it again by hand: "
                                "the work is done on start-up and the report is left.",
                                "En confirmant, les joueurs sont prévenus et le serveur S'ARRÊTE. Tu devras le relancer à la main : "
                                "le travail se fait au démarrage et le rapport reste.",
                                "Beim Bestätigen werden die Spieler gewarnt und der Server STOPPT. Du musst ihn von Hand neu starten: "
                                "beim Start wird die Arbeit erledigt und der Bericht abgelegt.",
                                "Confermando, i giocatori vengono avvisati e il server SI FERMA. Dovrai riavviarlo a mano: "
                                "all'avvio si esegue il lavoro e resta il rapporto.",
                                "Ao confirmar, os jogadores são avisados e o servidor PARA. Você terá de iniciá-lo à mão: "
                                "ao iniciar, o trabalho é feito e o relatório fica.",
                                "En confirmar, s'avisa els jugadors i el servidor S'ATURA. L'hauràs d'engegar tu a mà: "
                                "en engegar es fa la feina i en queda l'informe.",
                                "Ao confirmar, avísase aos xogadores e o servidor DETENSE. Terás que arrincalo ti á man: "
                                "ao arrincar faise o traballo e queda o informe."),
    "actualizar.boton.copia": ("Copia y aplicar", "Back up and apply", "Sauvegarder et appliquer", "Sichern und anwenden",
                               "Copia e applica", "Copiar e aplicar", "Còpia i aplica", "Copia e aplicar"),
    "actualizar.boton.copia.ayuda": ("Copia antes las regiones afectadas; luego se puede deshacer con /heraldia update undo",
                                     "Backs up the affected regions first; it can then be undone with /heraldia update undo",
                                     "Sauvegarde d'abord les régions concernées ; annulable ensuite avec /heraldia update undo",
                                     "Sichert zuerst die betroffenen Regionen; danach mit /heraldia update undo rückgängig machbar",
                                     "Copia prima le regioni coinvolte; poi si può annullare con /heraldia update undo",
                                     "Copia antes as regiões afetadas; depois dá para desfazer com /heraldia update undo",
                                     "Copia abans les regions afectades; després es pot desfer amb /heraldia update undo",
                                     "Copia antes as rexións afectadas; logo pódese desfacer con /heraldia update undo"),
    "actualizar.boton.sin_copia": ("Aplicar sin copia", "Apply without backup", "Appliquer sans sauvegarde", "Ohne Sicherung anwenden",
                                   "Applica senza copia", "Aplicar sem cópia", "Aplica sense còpia", "Aplicar sen copia"),
    "actualizar.boton.sin_copia.ayuda": ("Sin copia no se puede deshacer", "Without a backup it cannot be undone",
                                         "Sans sauvegarde, impossible d'annuler", "Ohne Sicherung nicht rückgängig zu machen",
                                         "Senza copia non si può annullare", "Sem cópia não dá para desfazer",
                                         "Sense còpia no es pot desfer", "Sen copia non se pode desfacer"),
    "actualizar.boton.cancelar": ("Cancelar", "Cancel", "Annuler", "Abbrechen", "Annulla", "Cancelar", "Cancel·la", "Cancelar"),
    "actualizar.boton.riesgo": ("Entiendo el riesgo: aplicar", "I understand the risk: apply", "Je comprends le risque : appliquer",
                                "Ich verstehe das Risiko: anwenden", "Capisco il rischio: applica", "Entendo o risco: aplicar",
                                "Entenc el risc: aplica", "Entendo o risco: aplicar"),
    "actualizar.boton.riesgo.ayuda": ("Aplica sin copia de seguridad", "Applies without a backup", "Applique sans sauvegarde",
                                      "Wendet ohne Sicherung an", "Applica senza copia di sicurezza", "Aplica sem cópia de segurança",
                                      "Aplica sense còpia de seguretat", "Aplica sen copia de seguridade"),
    "actualizar.riesgo.titulo": ("Sin copia de seguridad", "No backup", "Sans sauvegarde", "Ohne Sicherung", "Senza copia",
                                 "Sem cópia de segurança", "Sense còpia de seguretat", "Sen copia de seguridade"),
    "actualizar.riesgo": ("Sin copia, los chunks borrados para regenerarse y las estructuras colocadas no se pueden deshacer. "
                          "Haz antes una copia del mundo entero si puedes.",
                          "Without a backup, deleted chunks and placed structures cannot be undone. "
                          "Back up the whole world first if you can.",
                          "Sans sauvegarde, les chunks supprimés et les structures placées ne peuvent pas être annulés. "
                          "Sauvegarde d'abord tout le monde si tu peux.",
                          "Ohne Sicherung lassen sich gelöschte Chunks und gesetzte Bauwerke nicht rückgängig machen. "
                          "Sichere vorher die ganze Welt, wenn du kannst.",
                          "Senza copia, i chunk cancellati e le strutture piazzate non si possono annullare. "
                          "Fai prima una copia dell'intero mondo, se puoi.",
                          "Sem cópia, os chunks apagados e as estruturas colocadas não podem ser desfeitos. "
                          "Faça antes uma cópia do mundo inteiro, se puder.",
                          "Sense còpia, els chunks esborrats i les estructures col·locades no es poden desfer. "
                          "Fes abans una còpia del món sencer si pots.",
                          "Sen copia, os chunks borrados e as estruturas colocadas non se poden desfacer. "
                          "Fai antes unha copia do mundo enteiro se podes."),
    "actualizar.confirmar_consola": ("Para aplicar con copia: /%s. Sin copia (no se puede deshacer): /%s.",
                                     "To apply with a backup: /%s. Without a backup (cannot be undone): /%s.",
                                     "Pour appliquer avec sauvegarde : /%s. Sans sauvegarde (irréversible) : /%s.",
                                     "Mit Sicherung anwenden: /%s. Ohne Sicherung (nicht umkehrbar): /%s.",
                                     "Per applicare con copia: /%s. Senza copia (non annullabile): /%s.",
                                     "Para aplicar com cópia: /%s. Sem cópia (não dá para desfazer): /%s.",
                                     "Per aplicar amb còpia: /%s. Sense còpia (no es pot desfer): /%s.",
                                     "Para aplicar con copia: /%s. Sen copia (non se pode desfacer): /%s."),
    "actualizar.riesgo_consola": ("Sin copia no se puede deshacer. Si lo tienes claro: /%s",
                                  "Without a backup it cannot be undone. If you are sure: /%s",
                                  "Sans sauvegarde, c'est irréversible. Si tu es sûr : /%s",
                                  "Ohne Sicherung nicht umkehrbar. Wenn du sicher bist: /%s",
                                  "Senza copia non si può annullare. Se sei sicuro: /%s",
                                  "Sem cópia não dá para desfazer. Se tiver certeza: /%s",
                                  "Sense còpia no es pot desfer. Si ho tens clar: /%s",
                                  "Sen copia non se pode desfacer. Se o tes claro: /%s"),
    "actualizar.caducado": ("Ese análisis ya no vale (es de otro o tiene más de 15 minutos): vuelve a usar /heraldia update apply.",
                            "That analysis is no longer valid (another one, or older than 15 minutes): run /heraldia update apply again.",
                            "Cette analyse n'est plus valable (une autre, ou plus de 15 minutes) : relance /heraldia update apply.",
                            "Diese Analyse gilt nicht mehr (eine andere oder älter als 15 Minuten): führe /heraldia update apply erneut aus.",
                            "Quell'analisi non vale più (è un'altra o ha più di 15 minuti): usa di nuovo /heraldia update apply.",
                            "Essa análise não vale mais (é outra ou tem mais de 15 minutos): use /heraldia update apply de novo.",
                            "Aquesta anàlisi ja no val (és una altra o té més de 15 minuts): torna a fer servir /heraldia update apply.",
                            "Esa análise xa non vale (é doutra ou ten máis de 15 minutos): volve usar /heraldia update apply."),
    "actualizar.confirmado": ("Confirmado. Se avisa a los jugadores y el servidor se para en %s s. Arráncalo luego a mano: "
                              "al arrancar se hace el trabajo.",
                              "Confirmed. Players are warned and the server stops in %s s. Start it again by hand afterwards: "
                              "the work is done on start-up.",
                              "Confirmé. Les joueurs sont prévenus et le serveur s'arrête dans %s s. Relance-le ensuite à la main : "
                              "le travail se fait au démarrage.",
                              "Bestätigt. Die Spieler werden gewarnt und der Server stoppt in %s s. Starte ihn danach von Hand: "
                              "die Arbeit wird beim Start erledigt.",
                              "Confermato. I giocatori vengono avvisati e il server si ferma tra %s s. Riavvialo poi a mano: "
                              "il lavoro si fa all'avvio.",
                              "Confirmado. Os jogadores são avisados e o servidor para em %s s. Depois inicie-o à mão: "
                              "o trabalho é feito ao iniciar.",
                              "Confirmat. S'avisa els jugadors i el servidor s'atura d'aquí a %s s. Després engega'l a mà: "
                              "la feina es fa en engegar.",
                              "Confirmado. Avísase aos xogadores e o servidor detense en %s s. Logo arríncao á man: "
                              "o traballo faise ao arrincar."),
    "actualizar.aviso_jugadores": ("El servidor se va a parar dentro de %s s para actualizar el mundo. Volverá cuando el administrador lo arranque.",
                                   "The server will stop in %s s to update the world. It will be back when the admin starts it again.",
                                   "Le serveur va s'arrêter dans %s s pour mettre à jour le monde. Il reviendra quand l'admin le relancera.",
                                   "Der Server stoppt in %s s, um die Welt zu aktualisieren. Er ist zurück, wenn der Admin ihn neu startet.",
                                   "Il server si fermerà tra %s s per aggiornare il mondo. Tornerà quando l'amministratore lo riavvierà.",
                                   "O servidor vai parar em %s s para atualizar o mundo. Voltará quando o administrador o iniciar.",
                                   "El servidor s'aturarà d'aquí a %s s per actualitzar el món. Tornarà quan l'administrador l'engegui.",
                                   "O servidor vaise deter dentro de %s s para actualizar o mundo. Volverá cando o administrador o arrinque."),
    "actualizar.terminado": ("Actualización hecha: %s chunks se regenerarán al visitarlos y %s estructuras nuevas colocadas. "
                             "Informe en heraldia/actualizar del mundo.",
                             "Update done: %s chunks will regenerate when visited and %s new structures placed. "
                             "Report in the world's heraldia/actualizar.",
                             "Mise à jour faite : %s chunks se régénéreront à la visite et %s nouvelles structures placées. "
                             "Rapport dans heraldia/actualizar du monde.",
                             "Update erledigt: %s Chunks werden beim Besuch neu generiert, %s neue Bauwerke gesetzt. "
                             "Bericht in heraldia/actualizar der Welt.",
                             "Aggiornamento fatto: %s chunk si rigenereranno alla visita e %s nuove strutture piazzate. "
                             "Rapporto in heraldia/actualizar del mondo.",
                             "Atualização feita: %s chunks serão regenerados ao visitá-los e %s estruturas novas colocadas. "
                             "Relatório em heraldia/actualizar do mundo.",
                             "Actualització feta: %s chunks es regeneraran en visitar-los i %s estructures noves col·locades. "
                             "Informe a heraldia/actualizar del món.",
                             "Actualización feita: %s chunks rexeneraranse ao visitalos e %s estruturas novas colocadas. "
                             "Informe en heraldia/actualizar do mundo."),
    "actualizar.sin_copia": ("No hay ninguna actualización con copia de seguridad que deshacer.", "There is no backed-up update to undo.",
                             "Aucune mise à jour sauvegardée à annuler.", "Es gibt kein gesichertes Update zum Rückgängigmachen.",
                             "Non c'è nessun aggiornamento con copia da annullare.", "Não há nenhuma atualização com cópia para desfazer.",
                             "No hi ha cap actualització amb còpia per desfer.", "Non hai ningunha actualización con copia que desfacer."),
    "actualizar.deshacer": ("Deshacer la actualización %s (%s): se restauran las regiones copiadas y se pierde lo cambiado en ellas "
                            "desde entonces; el servidor se para. Confirma con %s",
                            "Undo update %s (%s): the backed-up regions are restored and anything changed in them since is lost; "
                            "the server stops. Confirm with %s",
                            "Annuler la mise à jour %s (%s) : les régions sauvegardées sont restaurées et tout ce qui y a changé depuis "
                            "est perdu ; le serveur s'arrête. Confirme avec %s",
                            "Update %s (%s) rückgängig machen: die gesicherten Regionen werden wiederhergestellt, seitdem Geändertes geht "
                            "verloren; der Server stoppt. Bestätige mit %s",
                            "Annulla l'aggiornamento %s (%s): si ripristinano le regioni copiate e si perde ciò che vi è cambiato da allora; "
                            "il server si ferma. Conferma con %s",
                            "Desfazer a atualização %s (%s): as regiões copiadas são restauradas e o que mudou nelas desde então se perde; "
                            "o servidor para. Confirme com %s",
                            "Desfer l'actualització %s (%s): es restauren les regions copiades i es perd el que hi ha canviat des de llavors; "
                            "el servidor s'atura. Confirma amb %s",
                            "Desfacer a actualización %s (%s): restáuranse as rexións copiadas e pérdese o cambiado nelas desde entón; "
                            "o servidor detense. Confirma con %s"),
    "actualizar.boton.deshacer": ("[Deshacer]", "[Undo]", "[Annuler]", "[Rückgängig]", "[Annulla]", "[Desfazer]", "[Desfés]", "[Desfacer]"),
    # ---------------- repairs of what an earlier generator built wrong (/heraldia update mend, update/GenerationMend)
    "actualizar.reparar.buscando": ("Buscando fallos de generación que reparar (no se cambia nada)…",
                         "Looking for generation faults to repair (nothing is changed)…",
                         "Recherche des défauts de génération à réparer (rien n'est modifié)…",
                         "Suche nach Generierungsfehlern zum Reparieren (es wird nichts geändert)…",
                         "Ricerca dei difetti di generazione da riparare (non si cambia nulla)…",
                         "Procurando falhas de geração para reparar (nada é alterado)…",
                         "Cercant errors de generació per reparar (no es canvia res)…",
                         "Buscando fallos de xeración que reparar (non se cambia nada)…"),
    "actualizar.reparar.ocupado": ("Ya hay una búsqueda o una reparación en curso", "A search or a repair is already running",
                        "Une recherche ou une réparation est déjà en cours", "Eine Suche oder Reparatur läuft bereits",
                        "C'è già una ricerca o una riparazione in corso", "Já há uma busca ou um reparo em andamento",
                        "Ja hi ha una cerca o una reparació en curs", "Xa hai unha busca ou unha reparación en curso"),
    "actualizar.reparar.error": ("La búsqueda ha fallado: %s", "The search failed: %s", "La recherche a échoué : %s",
                      "Die Suche ist fehlgeschlagen: %s", "La ricerca non è riuscita: %s", "A busca falhou: %s",
                      "La cerca ha fallat: %s", "A busca fallou: %s"),
    "actualizar.reparar.caducado": ("Esa búsqueda ya no vale (pasaron más de 15 minutos o hubo otra): vuelve a pedir /heraldia update mend apply",
                         "That search is no longer valid (more than 15 minutes passed, or another one ran): ask for /heraldia update mend apply again",
                         "Cette recherche n'est plus valable (plus de 15 minutes, ou une autre a eu lieu) : relance /heraldia update mend apply",
                         "Diese Suche gilt nicht mehr (mehr als 15 Minuten vergangen oder eine andere lief): /heraldia update mend apply erneut ausführen",
                         "Quella ricerca non vale più (più di 15 minuti, o ce n'è stata un'altra): richiedi di nuovo /heraldia update mend apply",
                         "Essa busca não vale mais (passaram mais de 15 minutos ou houve outra): peça /heraldia update mend apply de novo",
                         "Aquesta cerca ja no val (han passat més de 15 minuts o n'hi ha hagut una altra): torna a demanar /heraldia update mend apply",
                         "Esa busca xa non vale (pasaron máis de 15 minutos ou houbo outra): volve pedir /heraldia update mend apply"),
    "actualizar.reparar.reparando": ("Reparando %s sitios, poco a poco y sin parar el servidor…", "Repairing %s places, a little at a time, with the server running…",
                          "Réparation de %s endroits, peu à peu et sans arrêter le serveur…",
                          "Repariere %s Stellen, nach und nach und ohne den Server anzuhalten…",
                          "Riparazione di %s punti, poco alla volta e senza fermare il server…",
                          "Reparando %s lugares, aos poucos e sem parar o servidor…",
                          "Reparant %s llocs, a poc a poc i sense aturar el servidor…",
                          "Reparando %s sitios, pouco a pouco e sen parar o servidor…"),
    "actualizar.reparar.nada": ("No hay nada que reparar", "There is nothing to repair", "Il n'y a rien à réparer", "Es gibt nichts zu reparieren",
                     "Non c'è nulla da riparare", "Não há nada para reparar", "No hi ha res per reparar", "Non hai nada que reparar"),
    "actualizar.reparar.confirmar_consola": ("Para reparar lo encontrado, escribe: /%s", "To repair what was found, type: /%s",
                                  "Pour réparer ce qui a été trouvé, tape : /%s", "Um das Gefundene zu reparieren, gib ein: /%s",
                                  "Per riparare ciò che è stato trovato, scrivi: /%s", "Para reparar o que foi encontrado, digite: /%s",
                                  "Per reparar el que s'ha trobat, escriu: /%s", "Para reparar o atopado, escribe: /%s"),
    "actualizar.reparar.aviso": ("Solo se toca lo que sigue exactamente como lo dejó el generador; lo que alguien haya cambiado se deja como está. Repetirlo no cambia nada más.",
                      "Only what is still exactly as the generator left it is touched; whatever someone changed is left as it is. Running it again changes nothing more.",
                      "Seul ce qui est encore exactement tel que le générateur l'a laissé est touché ; ce que quelqu'un a modifié reste tel quel. Le relancer ne change rien de plus.",
                      "Nur was noch genau so ist, wie der Generator es hinterlassen hat, wird angefasst; was jemand verändert hat, bleibt, wie es ist. Ein zweiter Lauf ändert nichts mehr.",
                      "Si tocca solo ciò che è ancora esattamente come l'ha lasciato il generatore; ciò che qualcuno ha cambiato resta com'è. Ripeterlo non cambia nient'altro.",
                      "Só é mexido o que continua exatamente como o gerador deixou; o que alguém mudou fica como está. Repetir não muda mais nada.",
                      "Només es toca el que continua exactament com ho va deixar el generador; el que algú hagi canviat es deixa com està. Repetir-ho no canvia res més.",
                      "Só se toca o que segue exactamente como o deixou o xerador; o que alguén cambiase déixase como está. Repetilo non cambia nada máis."),
    "actualizar.reparar.boton.reparar": ("Reparar", "Repair", "Réparer", "Reparieren", "Ripara", "Reparar", "Repara", "Reparar"),
    "actualizar.reparar.boton.reparar.ayuda": ("Repara lo encontrado, poco a poco y sin parar el servidor", "Repairs what was found, a little at a time, with the server running",
                                    "Répare ce qui a été trouvé, peu à peu et sans arrêter le serveur",
                                    "Repariert das Gefundene nach und nach, ohne den Server anzuhalten",
                                    "Ripara ciò che è stato trovato, poco alla volta e senza fermare il server",
                                    "Repara o que foi encontrado, aos poucos e sem parar o servidor",
                                    "Repara el que s'ha trobat, a poc a poc i sense aturar el servidor",
                                    "Repara o atopado, pouco a pouco e sen parar o servidor"),
    "actualizar.reparar.dialogo": ("Reparar fallos de generación", "Repair generation faults", "Réparer les défauts de génération",
                        "Generierungsfehler reparieren", "Riparare i difetti di generazione", "Reparar falhas de geração",
                        "Reparar errors de generació", "Reparar fallos de xeración"),
    "actualizar.reparar.linea": ("%s: %s por reparar, %s bien, %s que no se tocan, %s avisos", "%s: %s to repair, %s fine, %s left alone, %s notices",
                      "%s : %s à réparer, %s en bon état, %s laissés tels quels, %s avertissements",
                      "%s: %s zu reparieren, %s in Ordnung, %s unangetastet, %s Hinweise",
                      "%s: %s da riparare, %s a posto, %s lasciati così, %s avvisi",
                      "%s: %s para reparar, %s em ordem, %s deixados como estão, %s avisos",
                      "%s: %s per reparar, %s bé, %s que no es toquen, %s avisos",
                      "%s: %s por reparar, %s ben, %s que non se tocan, %s avisos"),
    "actualizar.reparar.linea.hecho": ("%s: %s reparados, %s bien, %s que no se tocan, %s avisos", "%s: %s repaired, %s fine, %s left alone, %s notices",
                            "%s : %s réparés, %s en bon état, %s laissés tels quels, %s avertissements",
                            "%s: %s repariert, %s in Ordnung, %s unangetastet, %s Hinweise",
                            "%s: %s riparati, %s a posto, %s lasciati così, %s avvisi",
                            "%s: %s reparados, %s em ordem, %s deixados como estão, %s avisos",
                            "%s: %s reparats, %s bé, %s que no es toquen, %s avisos",
                            "%s: %s reparados, %s ben, %s que non se tocan, %s avisos"),
    # how many blocks of the world a repair is about: the places are the command's unit, the blocks are the figure a
    # person can judge before confirming something that cannot be undone
    "actualizar.reparar.bloques": ("%s: %s bloques del mundo en total", "%s: %s blocks of the world in all",
                        "%s : %s blocs du monde en tout", "%s: %s Blöcke der Welt insgesamt",
                        "%s: %s blocchi del mondo in tutto", "%s: %s blocos do mundo no total",
                        "%s: %s blocs del món en total", "%s: %s bloques do mundo en total"),
    "actualizar.reparar.streams": ("arroyos sin fuente junto a la Casa del Heraldo", "streams with no source by the Herald's House",
                        "ruisseaux sans source près de la Maison du Héraut", "Bäche ohne Quelle beim Haus des Herolds",
                        "ruscelli senza sorgente presso la Casa dell'Araldo", "riachos sem nascente junto à Casa do Arauto",
                        "rierols sense font a tocar de la Casa de l'Herald", "regatos sen fonte xunto á Casa do Heraldo"),
    "actualizar.reparar.water": ("agua quieta colgada en el aire junto a la Casa del Heraldo", "still water standing in the air by the Herald's House",
                      "eau immobile suspendue dans le vide près de la Maison du Héraut", "stehendes Wasser in der Luft beim Haus des Herolds",
                      "acqua ferma sospesa nel vuoto presso la Casa dell'Araldo", "água parada suspensa no ar junto à Casa do Arauto",
                      "aigua quieta penjada a l'aire a tocar de la Casa de l'Herald", "auga queda colgada no aire xunto á Casa do Heraldo"),
    "actualizar.reparar.anillo": (
        "anillo de la Casa del Heraldo: %s escalones de un bloque en rampa (bancales). No se repara: rehacer el terreno donde vive la gente no distingue la tierra del generador de la de un jugador. Un pueblo nuevo ya sale con terrazas.",
        "Herald's House ring: %s one-block steps in ramps (rice terraces). Not repaired: rebuilding the ground where people live cannot tell the generator's earth from a player's. A town built today has terraces.",
        "anneau de la Maison du Héraut : %s marches d'un bloc en rampe (rizières). Non réparé : refaire le terrain là où vivent les gens ne distingue pas la terre du générateur de celle d'un joueur. Un village construit aujourd'hui a des terrasses.",
        "Ring des Hauses des Herolds: %s einstufige Stufen in Rampen (Reisterrassen). Nicht repariert: das Gelände neu zu formen, wo Leute leben, kann die Erde des Generators nicht von der eines Spielers unterscheiden. Ein heute gebautes Dorf hat Terrassen.",
        "anello della Casa dell'Araldo: %s gradini di un blocco a rampa (risaie). Non riparato: rifare il terreno dove vive la gente non distingue la terra del generatore da quella di un giocatore. Un villaggio costruito oggi ha le terrazze.",
        "anel da Casa do Arauto: %s degraus de um bloco em rampa (arrozais). Não é reparado: refazer o terreno onde vivem pessoas não distingue a terra do gerador da de um jogador. Uma vila construída hoje já tem terraços.",
        "anell de la Casa de l'Herald: %s graons d'un bloc en rampa (bancals). No es repara: refer el terreny on viu la gent no distingeix la terra del generador de la d'un jugador. Un poble nou ja surt amb terrasses.",
        "anel da Casa do Heraldo: %s chanzos dun bloque en rampla (socalcos). Non se repara: refacer o terreo onde vive xente non distingue a terra do xerador da dun xogador. Un pobo novo xa sae con terrazas."),
    "actualizar.reparar.wharf": ("puesto del guardia de los embarcaderos shulker", "the guard's post on the shulker wharfs",
                      "poste du garde des embarcadères shulkers", "Posten der Wache an den Shulker-Anlegern",
                      "postazione della guardia degli approdi shulker", "posto do guarda dos cais shulker",
                      "lloc del guàrdia dels embarcadors shulker", "posto do garda dos embarcadoiros shulker"),
    "actualizar.reparar.inn": ("puerta del cuarto de las posadas de camino", "the bedroom door of the roadside inns",
                    "porte de la chambre des auberges de route", "Zimmertür der Rasthäuser", "porta della stanza delle locande di strada",
                    "porta do quarto das estalagens de estrada", "porta de l'habitació de les posades de camí",
                    "porta do cuarto das pousadas de camiño"),
    "actualizar.reparar.donde.repair": ("  · en %s %s %s (%s)", "  · at %s %s %s (%s)", "  · en %s %s %s (%s)", "  · bei %s %s %s (%s)",
                             "  · a %s %s %s (%s)", "  · em %s %s %s (%s)", "  · a %s %s %s (%s)", "  · en %s %s %s (%s)"),
    "actualizar.reparar.donde.left": ("  · no se toca en %s %s %s: %s", "  · left alone at %s %s %s: %s", "  · laissé tel quel en %s %s %s : %s",
                           "  · unangetastet bei %s %s %s: %s", "  · lasciato così a %s %s %s: %s", "  · deixado como está em %s %s %s: %s",
                           "  · no es toca a %s %s %s: %s", "  · non se toca en %s %s %s: %s"),
    "actualizar.reparar.donde.notice": ("  · aviso en %s %s %s: %s", "  · notice at %s %s %s: %s", "  · avertissement en %s %s %s : %s",
                             "  · Hinweis bei %s %s %s: %s", "  · avviso a %s %s %s: %s", "  · aviso em %s %s %s: %s",
                             "  · avís a %s %s %s: %s", "  · aviso en %s %s %s: %s"),
    "actualizar.reparar.titulo": ("Búsqueda de fallos de generación: %s pasos, el más lento de %s ms", "Search for generation faults: %s steps, the slowest %s ms",
                       "Recherche des défauts de génération : %s étapes, la plus lente %s ms",
                       "Suche nach Generierungsfehlern: %s Schritte, der langsamste %s ms",
                       "Ricerca dei difetti di generazione: %s passi, il più lento %s ms",
                       "Busca de falhas de geração: %s passos, o mais lento %s ms",
                       "Cerca d'errors de generació: %s passos, el més lent de %s ms",
                       "Busca de fallos de xeración: %s pasos, o máis lento de %s ms"),
    "actualizar.reparar.titulo.hecho": ("Reparación terminada: %s pasos, el más lento de %s ms", "Repair finished: %s steps, the slowest %s ms",
                             "Réparation terminée : %s étapes, la plus lente %s ms", "Reparatur beendet: %s Schritte, der langsamste %s ms",
                             "Riparazione terminata: %s passi, il più lento %s ms", "Reparo concluído: %s passos, o mais lento %s ms",
                             "Reparació acabada: %s passos, el més lent de %s ms", "Reparación rematada: %s pasos, o máis lento de %s ms"),
    "actualizar.reparar.informe": ("Informe completo: %s", "Full report: %s", "Rapport complet : %s", "Vollständiger Bericht: %s",
                        "Rapporto completo: %s", "Relatório completo: %s", "Informe complet: %s", "Informe completo: %s"),
    "actualizar.reparar.nada_cambia": ("No se ha cambiado nada. Para reparar: /heraldia update mend apply <water|streams|wharf|inn|all>",
                            "Nothing was changed. To repair: /heraldia update mend apply <water|streams|wharf|inn|all>",
                            "Rien n'a été modifié. Pour réparer : /heraldia update mend apply <water|streams|wharf|inn|all>",
                            "Es wurde nichts geändert. Zum Reparieren: /heraldia update mend apply <water|streams|wharf|inn|all>",
                            "Non è stato cambiato nulla. Per riparare: /heraldia update mend apply <water|streams|wharf|inn|all>",
                            "Nada foi alterado. Para reparar: /heraldia update mend apply <water|streams|wharf|inn|all>",
                            "No s'ha canviat res. Per reparar: /heraldia update mend apply <water|streams|wharf|inn|all>",
                            "Non se cambiou nada. Para reparar: /heraldia update mend apply <water|streams|wharf|inn|all>"),
    # ---------------- the new option (options.py: heraldia.config.update.margen_bloques and its name)
}
# Translations of the new option in config/heraldia.json (es and en come from options.py).
OPTION = {
    "config.actualizar.margen_bloques": (
        "Marge de sécurité, en blocs, autour de toute construction de joueur détectée par /heraldia update analyze : rien n'y est régénéré ni placé",
        "Sicherheitsabstand in Blöcken um jedes von /heraldia update analyze erkannte Spielerbauwerk: dort wird nichts neu generiert oder gesetzt",
        "Margine di sicurezza, in blocchi, attorno a ogni costruzione di giocatore rilevata da /heraldia update analyze: lì non si rigenera né si piazza nulla",
        "Margem de segurança, em blocos, em volta de qualquer construção de jogador detectada por /heraldia update analyze: ali nada é regenerado nem colocado",
        "Marge de seguretat, en blocs, al voltant de qualsevol construcció de jugador que detecta /heraldia update analyze: allà no es regenera ni es col·loca res",
        "Marxe de seguridade, en bloques, arredor de calquera construción de xogador que detecta /heraldia update analyze: alí non se rexenera nin se coloca nada"),
    "config.actualizar.margen_bloques.nombre": (
        "Marge autour des constructions (blocs)", "Abstand um Bauwerke (Blöcke)", "Margine attorno alle costruzioni (blocchi)",
        "Margem em volta das construções (blocos)", "Marge al voltant de les construccions (blocs)",
        "Marxe arredor das construcións (bloques)"),
}


def _all():
    """{full key: (text per language, in the order of LANGUAGES)}."""
    out = {f"{NS}.{k}": v for k, v in _T.items()}
    for c in LANGUAGES:
        out[f"{NS}.idioma.nombre.{c}"] = tuple(LANGUAGE_NAMES[c] for _ in LANGUAGES)
    for k, v in out.items():
        assert len(v) == len(LANGUAGES), k
    return out


def lang():
    """{"es_es": {...}, "en_us": {...}} with the safe-update texts (those of the option are in options.py)."""
    out = {"es_es": {}, "en_us": {}}
    for k, v in _all().items():
        out["es_es"][k], out["en_us"][k] = v[0], v[1]
    return out


def translation(lang_code):
    """The texts of one language in idiomas/ (fr_fr, de_de...), including those of the new option."""
    i = LANGUAGES.index(lang_code)
    out = {k: v[i] for k, v in _all().items()}
    for k, v in OPTION.items():
        out[f"{NS}.{k}"] = v[i - 2]
    return out


def write():
    """Copies each translation's texts to idiomas/<code>.json (keeps the rest, ordered as it was)."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "languages")
    for c in LANGUAGES[2:]:
        p = os.path.join(folder, f"{c}.json")
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d.update(translation(c))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")


if __name__ == "__main__":
    write()
