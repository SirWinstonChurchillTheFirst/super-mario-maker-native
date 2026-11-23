#!/usr/bin/env python3
"""Relative FS paths are resolved against the working directory (FSChangeDir).

usage: patch_fs_cwd.py RUNTIME_DIR   (os_extra.cpp's FSChangeDir calls vfs::set_cwd)

Before: FSChangeDir was only remembered for FSGetCwd. Paper Mario Color Splash changes to /vol/content and opens
"sound/gojika_sound.bfsar" -> not found (-6), then a null access. After: a GUEST path that does not start with '/'
is taken below the current directory (default "/", so "vol/content/..." works as before). Only the guest-path entry
points (resolve, area_root) do this: components() also splits title-relative host paths ("content/...").
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])


def sub(path, old, new, count=1):
    p = root / path
    text = p.read_text()
    if new in text:
        print(f"{path}: already patched")
        return
    if text.count(old) != count:
        sys.exit(f"{path}: expected {count}x {old[:60]!r}, found {text.count(old)}")
    p.write_text(text.replace(old, new))
    print(f"{path}: ok")


sub("src/vfs.cpp", """// "/vol/content/./a//b/../c" -> {"vol", "content", "a", "c"}
std::vector<std::string> components(std::string_view path) {""", """// port/patch_fs_cwd.py: the title's working directory (FSChangeDir), for relative guest paths
std::mutex g_cwd_mutex;
std::string g_cwd = "/";

// port/patch_fs_cwd.py: a guest path without a leading '/' is below the working directory
std::string absolute(std::string_view path) {
    if (path.empty() || path[0] == '/') return std::string(path);
    std::lock_guard lock(g_cwd_mutex);
    return g_cwd + "/" + std::string(path);
}

// "/vol/content/./a//b/../c" -> {"vol", "content", "a", "c"}
std::vector<std::string> components(std::string_view path) {""")

sub("src/vfs.cpp", """fs::path area_root(const Resolved& r, std::string_view path) {
    if (r.area != Area::kAoc) return g_save_root;
    if (r.sys) return sys_root();
    std::string name = components(path)[1];""", """fs::path area_root(const Resolved& r, std::string_view path) {
    const std::string full = absolute(path); // port/patch_fs_cwd.py
    if (r.area != Area::kAoc) return g_save_root;
    if (r.sys) return sys_root();
    std::string name = components(full)[1];""")

sub("src/vfs.cpp", """Resolved resolve(std::string_view path) {
    const auto parts = components(path);""", """} // namespace

void set_cwd(std::string_view path) { // port/patch_fs_cwd.py
    std::lock_guard lock(g_cwd_mutex);
    g_cwd = path.empty() ? std::string("/") : std::string(path);
}

namespace {

Resolved resolve(std::string_view guest_path) {
    const std::string full = absolute(guest_path); // port/patch_fs_cwd.py
    const std::string_view path = full;
    const auto parts = components(path);""")

sub("include/cafe/vfs.h", """Status open_file(std::string_view path, std::string_view mode, int32_t& handle);""",
    """Status open_file(std::string_view path, std::string_view mode, int32_t& handle);
// port/patch_fs_cwd.py: FSChangeDir's directory; guest paths without a leading '/' are below it.
void set_cwd(std::string_view path);""")
