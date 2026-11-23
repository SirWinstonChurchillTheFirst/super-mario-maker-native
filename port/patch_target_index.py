#!/usr/bin/env python3
"""patch_target_index.py SMASH4_DIR : render targets found by address through a hash index instead of a scan.

Targets are never removed, and Mario Kart 8 makes ~4200 of them (per-driver lighting cubes, slices). Every texture
bind (find_target per mip level and slice) and every draw's colour/depth lookup scanned them all: on the console
the draw thread spent half its time in texture binds (5 s per 10 s) and a race ran at 9-14 frames/s. Targets keep
their address for life, so an address -> targets index is exact."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_target_index: text not found in %s: %r' % (path, old[:70]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


edit('runtime/src/gpu/vulkan/renderer.h', [
    ('''    std::vector<std::unique_ptr<Target>> targets_;''',
     '''    std::vector<std::unique_ptr<Target>> targets_;
    std::unordered_map<uint32_t, std::vector<Target*>> targets_by_address_; // port/patch_target_index.py'''),
])

edit('runtime/src/gpu/vulkan/targets.cpp', [
    ('''Target* Renderer::find_target(uint32_t address, uint32_t format, bool depth) {
    Target* best = nullptr;
    for (auto& t : targets_) {
        if (t->address != address || t->depth != depth) continue;
        if (format != 0 && (t->format & 0x3F) != (format & 0x3F)) continue;
        if (best == nullptr || t->written > best->written) best = t.get();
    }
    return best;
}''', '''Target* Renderer::find_target(uint32_t address, uint32_t format, bool depth) {
    Target* best = nullptr;
    const auto it = targets_by_address_.find(address); // port/patch_target_index.py
    if (it == targets_by_address_.end()) return nullptr;
    for (Target* t : it->second) {
        if (t->address != address || t->depth != depth) continue;
        if (format != 0 && (t->format & 0x3F) != (format & 0x3F)) continue;
        if (best == nullptr || t->written > best->written) best = t;
    }
    return best;
}'''),
    ('''    for (auto& t : targets_) {
        if (!t->depth && t->address == address && t->format == format && t->pitch == pitch && t->height == height) {
            t->base_reg = base_reg;
            return t.get();
        }
    }''', '''    if (const auto it = targets_by_address_.find(address); it != targets_by_address_.end()) {
        for (Target* t : it->second) {
            if (!t->depth && t->address == address && t->format == format && t->pitch == pitch && t->height == height) {
                t->base_reg = base_reg;
                return t;
            }
        }
    }'''),
    ('''    for (auto& t : targets_) {
        if (t->depth && t->address == address && t->format == format && t->pitch == pitch && t->height == height) {
            return t.get();
        }
    }''', '''    if (const auto it = targets_by_address_.find(address); it != targets_by_address_.end()) {
        for (Target* t : it->second) {
            if (t->depth && t->address == address && t->format == format && t->pitch == pitch && t->height == height) {
                return t;
            }
        }
    }'''),
])

# both creation sites: register the new target in the index
p = root + '/runtime/src/gpu/vulkan/targets.cpp'
s = open(p, encoding='utf-8').read()
OLD = '''    targets_.push_back(std::move(t));
    return targets_.back().get();'''
NEW = '''    targets_by_address_[t->address].push_back(t.get()); // port/patch_target_index.py
    targets_.push_back(std::move(t));
    return targets_.back().get();'''
if 'targets_by_address_[t->address]' not in s:
    if s.count(OLD) != 2:
        sys.exit('patch_target_index: expected 2 creation sites, found %d' % s.count(OLD))
    s = s.replace(OLD, NEW)
    open(p, 'w', encoding='utf-8').write(s)

# The CPU-write check (cpu_wrote: which targets did the CPU overwrite?) walks address-ordered targets near the range
# instead of all of them.
edit('runtime/src/gpu/vulkan/renderer.h', [
    ('''    std::unordered_map<uint32_t, std::vector<Target*>> targets_by_address_; // port/patch_target_index.py''',
     '''    std::unordered_map<uint32_t, std::vector<Target*>> targets_by_address_; // port/patch_target_index.py
    std::map<uint32_t, std::vector<Target*>> targets_sorted_; // port/patch_target_index.py: by address
    uint32_t max_target_span_ = 0;'''),
])
p = root + '/runtime/src/gpu/vulkan/targets.cpp'
s = open(p, encoding='utf-8').read()
OLD = '''    targets_by_address_[t->address].push_back(t.get()); // port/patch_target_index.py
'''
NEW = '''    targets_by_address_[t->address].push_back(t.get()); // port/patch_target_index.py
    targets_sorted_[t->address].push_back(t.get());
    max_target_span_ = std::max(max_target_span_, t->end - t->address);
'''
if NEW not in s:
    s = s.replace(OLD, NEW)
    open(p, 'w', encoding='utf-8').write(s)
edit('runtime/src/gpu/vulkan/textures.cpp', [
    ('''        uint64_t now = 0;
        for (auto& t : targets_) {
            if (t->address < end && t->end > address) t->overwritten = now ? now : (now = stamp());
        }''', '''        uint64_t now = 0;
        const uint32_t from = address > max_target_span_ ? address - max_target_span_ : 0; // port/patch_target_index.py
        for (auto it = targets_sorted_.lower_bound(from); it != targets_sorted_.end() && it->first < end; ++it) {
            for (Target* t : it->second) {
                if (t->address < end && t->end > address) t->overwritten = now ? now : (now = stamp());
            }
        }'''),
])
