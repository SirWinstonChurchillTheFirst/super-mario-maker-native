"""An empty Mii database (FFL_ODB.dat) where a console always has one.

Every Wii U has Mii Maker's database in its shared save (made at system setup). Without one, FFL makes it on the
first FFLInitResEx and returns 10 ("database was created") instead of 0; Rio 2016 takes anything but 0 as a failed
FFL start, skips its Mii set-up and later reads through a null MiiData. From the second start on it worked.

Now, when a title opens <save root>/mlc01/usr/.../user/common/db/FFL_ODB.dat for reading and it is not there, the
runtime first writes the database exactly as FFL itself writes an empty one (seen in the file FFL made): "FFOC",
zeros to 276544 bytes, the last two bytes the CRC-16/CCITT that makes the file's CRC 0 (FFL's check).
No Nintendo data: the layout is what the game's own library writes. FFL makes FFL_HDB.dat itself and is happy.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/vfs.cpp")
text = open(path, encoding="utf-8").read()
if "patch_ffl_odb" in text:
    print("already: vfs.cpp")
    sys.exit(0)

anchor = "Status open_file_impl(std::string_view path, std::string_view mode, int32_t& handle) {\n"
helper = r'''// port/patch_ffl_odb.py: an empty Mii database as FFL writes one ("FFOC", zeros, CRC-16/CCITT at the end).
void make_empty_ffl_odb(const fs::path& file) {
    constexpr size_t kSize = 276544;
    std::vector<uint8_t> data(kSize, 0);
    data[0] = 'F'; data[1] = 'F'; data[2] = 'O'; data[3] = 'C';
    uint16_t crc = 0;
    for (uint8_t b : data) { // the CRC field counts as zero while it is computed
        for (int bit = 0; bit < 8; ++bit) crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021) : static_cast<uint16_t>(crc << 1);
        crc ^= b;
    }
    data[kSize - 2] = static_cast<uint8_t>(crc >> 8);
    data[kSize - 1] = static_cast<uint8_t>(crc);
    std::error_code ec;
    fs::create_directories(file.parent_path(), ec);
    if (FILE* f = std::fopen(file.string().c_str(), "wb")) {
        std::fwrite(data.data(), 1, data.size(), f);
        std::fclose(f);
        std::fprintf(stderr, "cafe: made an empty Mii database %s\n", file.string().c_str());
    }
}

'''
text = text.replace(anchor, helper + anchor, 1)
old = "    if (r.area == Area::kSave && r.mlc && mode.find_first_of(\"wa\") != std::string_view::npos) {\n"
new = ("    if (r.area == Area::kSave && r.mlc && !r.save_parts.empty() && iequals(r.save_parts.back(), \"FFL_ODB.dat\") &&\n"
       "        mode.find_first_of(\"wa\") == std::string_view::npos) {\n"
       "        const fs::path file = host_resolve(g_save_root, r.save_parts);\n"
       "        std::error_code ec;\n"
       "        if (!fs::exists(file, ec)) make_empty_ffl_odb(file);\n"
       "    }\n" + old)
assert text.count(old) == 1
text = text.replace(old, new)
if "#include <vector>" not in text:
    text = text.replace("#include <unordered_map>\n", "#include <unordered_map>\n#include <vector>\n", 1)
open(path, "w", encoding="utf-8", newline="\n").write(text)
print("patched: vfs.cpp (empty FFL_ODB.dat)")
