"""TTT2_GPU_TIMEOUT_S=<seconds> (test switch): how long the runtime waits for a GPU submission before it gives up
(default 10 s). For runs on a software Vulkan (lavapipe), whose frames can take longer.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
SRC = os.path.join(ROOT, "runtime/src/gpu/vulkan")
helper = ("namespace {\n"
          "// port/patch_gpu_timeout.py\n"
          "uint64_t gpu_timeout_ns() {\n"
          "    static const uint64_t ns = [] {\n"
          "        const char* v = std::getenv(\"TTT2_GPU_TIMEOUT_S\");\n"
          "        const double s = v ? std::atof(v) : 10.0;\n"
          "        return static_cast<uint64_t>((s > 0 ? s : 10.0) * 1e9);\n"
          "    }();\n"
          "    return ns;\n"
          "}\n"
          "} // namespace\n")
for rel in ("renderer.cpp", "present.cpp"):
    path = os.path.join(SRC, rel)
    text = open(path, encoding="utf-8").read()
    if "patch_gpu_timeout" in text:
        print("already:", rel)
        continue
    if "10'000'000'000ull" not in text:
        sys.exit(rel + ": timeout not found")
    text = text.replace("10'000'000'000ull", "gpu_timeout_ns()")
    anchor = "namespace cafe::gpu::vk {\n" if rel == "present.cpp" else "namespace vk {\n"
    if anchor not in text:
        sys.exit(rel + ": namespace anchor not found")
    text = text.replace(anchor, anchor + helper, 1)
    for inc in ("#include <cstdlib>\n",):
        if inc not in text:
            first = text.index("#include <")
            text = text[:first] + inc + text[first:]
    open(path, "w", encoding="utf-8", newline="").write(text)
    print("patched:", rel)
