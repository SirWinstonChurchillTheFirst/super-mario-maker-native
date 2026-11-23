"""Uniform blocks copied when a draw is recorded, at 60 frames a second too (Mario Tennis's turned match picture).

The GPU reads a draw's uniform blocks straight from guest memory (imported), when the command buffer EXECUTES. With
frame interpolation on (frames_per_frame > 1, e.g. a 144 Hz PC monitor) the runtime copies them into its frame record
when the draw is recorded; at 60 frames a second (the console's TV, TTT2_FPS=60) it did not. Mario Tennis rewrites
the uniform blocks of its full-screen passes (tone map, anti-aliasing) for later passes of the same frame before the
GPU has run the earlier ones, so those passes ran with another pass's constants: the match picture came out turned
(console) or as a flat colour (PC with TTT2_FPS=60). On the console's GPU the draw runs right away and sees its
own values. Now the uniform blocks are always copied at record time; the two frame records alternate per frame.
TTT2_SNAPSHOT_CONSTANTS=0 restores the old behaviour at 60 (A/B).
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
SRC = os.path.join(ROOT, "runtime/src/gpu/vulkan")


def patch(rel, pairs):
    path = os.path.join(SRC, rel)
    text = open(path, encoding="utf-8").read()
    if "patch_snapshot_constants" in text:
        print("already:", rel)
        return
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit(f"{rel}: anchor not found once: {old[:70]!r}")
        text = text.replace(old, new)
    open(path, "w", encoding="utf-8", newline="").write(text)
    print("patched:", rel)


patch("renderer.h", [(
    "    uint32_t frames_per_frame_ = 1; // frames shown per frame the title renders\n",
    "    uint32_t frames_per_frame_ = 1; // frames shown per frame the title renders\n"
    "    // port/patch_snapshot_constants.py: uniform blocks copied at record time with one frame per frame too.\n"
    "    bool snapshot_constants_ = false;\n"
    "    uint64_t snapshot_frame_ = ~0ull;\n"
    "    void rotate_snapshot_record();\n")])

patch("interpolate.cpp", [
    ("    frames_per_frame_ = std::clamp((fps + 30) / 60, 1u, 4u);\n"
     "    if (frames_per_frame_ > 1) {\n",
     "    frames_per_frame_ = std::clamp((fps + 30) / 60, 1u, 4u);\n"
     "    {\n"
     "        const char* v = std::getenv(\"TTT2_SNAPSHOT_CONSTANTS\");\n"
     "        snapshot_constants_ = frames_per_frame_ == 1 && (v == nullptr || *v != '0'); // port/patch_snapshot_constants.py\n"
     "    }\n"
     "    if (frames_per_frame_ > 1 || snapshot_constants_) {\n"),
    ("void Renderer::record_constants(uint32_t draw_index, const ConstantSources& sources, abi::DrawConstants& dc) {\n",
     "// port/patch_snapshot_constants.py: at one frame per frame the two records alternate per frame; the one about\n"
     "// to be reused is waited for (the GPU work of the frame before last).\n"
     "void Renderer::rotate_snapshot_record() {\n"
     "    if (snapshot_frame_ == frame_number_) return;\n"
     "    snapshot_frame_ = frame_number_;\n"
     "    record_value_[current_record_] = submitted_ + 1;\n"
     "    current_record_ ^= 1;\n"
     "    if (record_value_[current_record_] > submitted_) submit(false);\n"
     "    wait_value(record_value_[current_record_]);\n"
     "    frame_records_[current_record_].clear();\n"
     "}\n"
     "\n"
     "void Renderer::record_constants(uint32_t draw_index, const ConstantSources& sources, abi::DrawConstants& dc) {\n"),
])

patch("draw.cpp", [
    ("    const uint32_t draw_index = frames_per_frame_ > 1 ? begin_draw_record(regs, d) : 0;\n",
     "    if (snapshot_constants_ && !replaying_) rotate_snapshot_record(); // port/patch_snapshot_constants.py\n"
     "    const uint32_t draw_index = frames_per_frame_ > 1 || snapshot_constants_ ? begin_draw_record(regs, d) : 0;\n"),
    ("    const bool record = frames_per_frame_ > 1 && !replaying_;\n",
     "    const bool record = (frames_per_frame_ > 1 || snapshot_constants_) && !replaying_;\n"),
])
