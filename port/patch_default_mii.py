"""nn_act gives the account's Mii as a valid FFLStoreData (a default Mii), not 96 zero bytes.

Rio 2016 builds the player's character in the hub town from the account Mii (nn::act::GetMiiEx). The runtime
returned 96 zero bytes (no valid Mii: wrong CRC), the title made no MiiData, and CreateModelResourceName read through
the null RefPtr<MiiData> (guest address 0x4, at 0x0215B4FC) right after "Now loading...".

Now, offline, the Mii comes from (1) CAFE_ACCOUNT_DAT, a Cemu account.dat ("MiiData=<192 hex digits>", e.g.
<mlc01>/usr/save/system/act/80000001/account.dat): the player's own Mii, read at run time, never copied anywhere;
(2) else a default Mii made the way Cemu makes one for a new account (all 16-bit fields 1, a few fixed fields, the
name "Player", the CRC-16/CCITT over the 96 bytes brought to 0 through the id word at +4). No Nintendo data.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/os/nn_services.cpp")
text = open(path, encoding="utf-8").read()
if "patch_default_mii" in text:
    print("already: nn_services.cpp")
    sys.exit(0)

old = """Result act_mii(uint8_t* data) {
    trace_net(__func__);
    if (data && act_online()) std::memcpy(data, online::account().mii.data(), 0x60);
    else if (data) std::memset(data, 0, 0x60);
    return kSuccess;
}
"""
new = """// port/patch_default_mii.py: the offline account Mii. CAFE_ACCOUNT_DAT (a Cemu account.dat, its MiiData= line)
// or a default Mii built as Cemu builds one for a new account. CRC-16/CCITT (poly 0x1021, init 0) over all 96 bytes
// is 0 for a valid FFLStoreData.
uint16_t ffl_crc16(const uint8_t* data, size_t size) {
    uint16_t crc = 0;
    for (size_t i = 0; i < size; ++i) {
        for (int bit = 0; bit < 8; ++bit) crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021) : static_cast<uint16_t>(crc << 1);
        crc ^= data[i];
    }
    return crc;
}
std::array<uint8_t, 0x60> make_default_mii() {
    std::array<uint8_t, 0x60> m{};
    const auto put16 = [&](size_t at, uint16_t v) { m[at] = static_cast<uint8_t>(v >> 8); m[at + 1] = static_cast<uint8_t>(v); };
    for (size_t i = 0; i < 0x60; i += 2) put16(i, 1);
    put16(0x3A, 1 | (3 << 9));
    put16(0x02, 1 | (1 << 12));
    m[0x08] = 0x00; m[0x09] = 0x03; m[0x0A] = 0x33; m[0x0B] = 0x34; // id low 0x33334
    for (size_t i = 0; i < 0x60; i += 2) std::swap(m[i], m[i + 1]); // the fields are stored little-endian
    static constexpr char kName[] = "Player";
    for (size_t i = 0; i < 10; ++i) {
        const uint16_t c = i < sizeof kName - 1 ? static_cast<uint8_t>(kName[i]) : 0;
        m[0x1A + 2 * i] = static_cast<uint8_t>(c);
        m[0x1A + 2 * i + 1] = static_cast<uint8_t>(c >> 8);
    }
    for (uint32_t counter = 0; ffl_crc16(m.data(), m.size()) != 0 && counter < 0x1000000; ++counter) {
        m[4] = static_cast<uint8_t>(counter >> 24); m[5] = static_cast<uint8_t>(counter >> 16);
        m[6] = static_cast<uint8_t>(counter >> 8); m[7] = static_cast<uint8_t>(counter);
    }
    return m;
}
const std::array<uint8_t, 0x60>& offline_mii() {
    static const std::array<uint8_t, 0x60> mii = [] {
        if (const char* path = std::getenv("CAFE_ACCOUNT_DAT"); path && *path) {
            if (FILE* f = std::fopen(path, "rb")) {
                char line[512];
                while (std::fgets(line, sizeof line, f)) {
                    if (std::strncmp(line, "MiiData=", 8) != 0) continue;
                    std::array<uint8_t, 0x60> m{};
                    bool ok = true;
                    for (size_t i = 0; i < m.size() && ok; ++i) {
                        unsigned v = 0;
                        ok = std::sscanf(line + 8 + 2 * i, "%2x", &v) == 1;
                        m[i] = static_cast<uint8_t>(v);
                    }
                    if (ok && ffl_crc16(m.data(), m.size()) == 0) {
                        std::fclose(f);
                        std::fprintf(stderr, "cafe: account Mii from %s\\n", path);
                        return m;
                    }
                }
                std::fclose(f);
            }
            std::fprintf(stderr, "cafe: no valid MiiData in CAFE_ACCOUNT_DAT=%s, using the default Mii\\n", path);
        }
        return make_default_mii();
    }();
    return mii;
}
Result act_mii(uint8_t* data) {
    trace_net(__func__);
    if (data && act_online()) std::memcpy(data, online::account().mii.data(), 0x60);
    else if (data) std::memcpy(data, offline_mii().data(), 0x60);
    return kSuccess;
}
"""
assert text.count(old) == 1
text = text.replace(old, new)
for inc in ("#include <array>\n", "#include <cstdio>\n", "#include <cstdlib>\n", "#include <cstring>\n", "#include <utility>\n"):
    if inc not in text:
        first = text.index("#include <")
        text = text[:first] + inc + text[first:]
open(path, "w", encoding="utf-8", newline="\n").write(text)
print("patched: nn_services.cpp (offline account Mii)")
