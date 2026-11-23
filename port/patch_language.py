"""The console language the title reads (UCReadSysConfig cafe.language / cafe.cntry_reg) from a setting, not fixed English.

The runtime answered English (United Kingdom) for every title; Cemu on the player's console shows the same games in
German. Now: CAFE_LANGUAGE (ja, en, fr, de, it, es, zh, ko, nl, pt, ru, tw, a locale like de_DE, or the Wii U number
0-11) wins; else the host's locale (LC_ALL / LC_MESSAGES / LANG on Linux, the user locale on Windows); else English.
The country follows the language (de -> Germany, fr -> France, ...; English stays United Kingdom, the EU default).
The console's launch.sh sets CAFE_LANGUAGE from Batocera's system.language. One log line names the choice.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/os/system_config.cpp")
text = open(path, encoding="utf-8").read()
if "patch_language" in text:
    print("already: system_config.cpp")
    sys.exit(0)

pairs = [
    ("#include <cstdio>\n#include <cstring>\n#include <string_view>\n",
     "#include <cctype>\n#include <cstdio>\n#include <cstdlib>\n#include <cstring>\n#include <string>\n#include <string_view>\n"
     "#ifdef _WIN32\n#include <windows.h>\n#endif\n"),
    ("// MCP ---------------------------------------------------------------------\n",
     "// port/patch_language.py: the language (Wii U numbering) and its country, from CAFE_LANGUAGE or the host locale.\n"
     "struct LanguageChoice { uint32_t language, country; };\n"
     "LanguageChoice choose_language() {\n"
     "    struct Entry { const char* code; uint32_t language, country; };\n"
     "    // Wii U: 0 ja, 1 en, 2 fr, 3 de, 4 it, 5 es, 6 zh, 7 ko, 8 nl, 9 pt, 10 ru, 11 tw; countries as the Wii's codes.\n"
     "    static constexpr Entry kTable[] = {{\"ja\", 0, 1},  {\"en\", 1, kCountryUnitedKingdom}, {\"fr\", 2, 77}, {\"de\", 3, 78},\n"
     "                                       {\"it\", 4, 83}, {\"es\", 5, 105}, {\"zh\", 6, 160}, {\"ko\", 7, 136},\n"
     "                                       {\"nl\", 8, 94}, {\"pt\", 9, 99}, {\"ru\", 10, 100}, {\"tw\", 11, 128}};\n"
     "    std::string wanted;\n"
     "    const char* source = \"default\";\n"
     "    if (const char* v = std::getenv(\"CAFE_LANGUAGE\"); v && *v) {\n"
     "        wanted = v;\n"
     "        source = \"CAFE_LANGUAGE\";\n"
     "    } else {\n"
     "#ifdef _WIN32\n"
     "        wchar_t name[LOCALE_NAME_MAX_LENGTH] = {};\n"
     "        if (GetUserDefaultLocaleName(name, LOCALE_NAME_MAX_LENGTH) > 0) {\n"
     "            for (const wchar_t* c = name; *c && *c != L'-'; ++c) wanted += static_cast<char>(*c);\n"
     "            source = \"the user locale\";\n"
     "        }\n"
     "#else\n"
     "        for (const char* var : {\"LC_ALL\", \"LC_MESSAGES\", \"LANG\"}) {\n"
     "            const char* v = std::getenv(var);\n"
     "            if (v && *v && std::strcmp(v, \"C\") != 0 && std::strcmp(v, \"POSIX\") != 0) {\n"
     "                wanted = v;\n"
     "                source = var;\n"
     "                break;\n"
     "            }\n"
     "        }\n"
     "#endif\n"
     "    }\n"
     "    for (char& c : wanted) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));\n"
     "    LanguageChoice choice{kLanguageEnglish, kCountryUnitedKingdom};\n"
     "    if (!wanted.empty() && std::isdigit(static_cast<unsigned char>(wanted[0]))) {\n"
     "        const uint32_t n = static_cast<uint32_t>(std::atoi(wanted.c_str()));\n"
     "        for (const Entry& e : kTable) if (e.language == n) choice = {e.language, e.country};\n"
     "    } else if (wanted.rfind(\"german\", 0) == 0) {\n"
     "        choice = {3, 78};\n"
     "    } else if (wanted.size() >= 2) {\n"
     "        const std::string code = wanted == \"zh_tw\" || wanted.rfind(\"zh_tw\", 0) == 0 ? \"tw\" : wanted.substr(0, 2);\n"
     "        for (const Entry& e : kTable) if (code == e.code) choice = {e.language, e.country};\n"
     "    }\n"
     "    std::fprintf(stderr, \"ttt2: system language %u, country %u (from %s%s%s)\\n\", choice.language, choice.country, source,\n"
     "                 wanted.empty() ? \"\" : \" = \", wanted.c_str());\n"
     "    return choice;\n"
     "}\n"
     "const LanguageChoice& language_choice() {\n"
     "    static const LanguageChoice choice = choose_language();\n"
     "    return choice;\n"
     "}\n"
     "\n"
     "// MCP ---------------------------------------------------------------------\n"),
    ("bool lookup(std::string_view name, uint32_t& value) {\n",
     "bool lookup(std::string_view name, uint32_t& value) {\n"
     "    if (name == \"cafe.language\") {\n"
     "        value = language_choice().language;\n"
     "        return true;\n"
     "    }\n"
     "    if (name == \"cafe.cntry_reg\") {\n"
     "        value = language_choice().country;\n"
     "        return true;\n"
     "    }\n"),
]
for old, new in pairs:
    if text.count(old) != 1:
        sys.exit(f"system_config.cpp: anchor not found once: {old[:50]!r}")
    text = text.replace(old, new)
open(path, "w", encoding="utf-8", newline="").write(text)
print("patched: system_config.cpp")
