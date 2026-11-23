"""Write-backs read from cached memory where the device has it.

The retirement thread tiles every written-back render target from its staging buffer into guest memory on the CPU,
and a title that waits for a GPU timestamp waits for that too. The staging buffers asked for host-visible, coherent
memory only; on the console's Radeon (Mesa RADV, an APU) that is write-combined memory, which the CPU reads without
its cache: 140 KB of Super Mario 3D World's targets took 8.4 ms a frame (about 16 MB/s), the title waited 18 ms a
frame on its timestamp and held 30 frames a second (TTT2_WAIT_LOG, 22 November). The stream encoder's buffers
(stream.cpp) already prefer cached memory for the same reason; the write-back staging buffers now do the same.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/gpu/vulkan/targets.cpp")
text = open(path, encoding="utf-8").read()
old = ("            write_back_staging_.push_back(ctx_.create_buffer(\n"
       "                kWriteBackBytes, VK_BUFFER_USAGE_TRANSFER_DST_BIT,\n"
       "                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT));\n")
new = ("            // Cached memory where there is some: the CPU reads every byte when it tiles the copy into guest\n"
       "            // memory, and uncached (write-combined) memory made that 16 MB/s on an APU (port/patch_writeback_cached.py).\n"
       "            VkMemoryPropertyFlags flags = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;\n"
       "            for (uint32_t i = 0; i < ctx_.memory.memoryTypeCount; ++i) {\n"
       "                const auto cached = flags | VK_MEMORY_PROPERTY_HOST_CACHED_BIT;\n"
       "                if ((ctx_.memory.memoryTypes[i].propertyFlags & cached) == cached) {\n"
       "                    flags = cached;\n"
       "                    break;\n"
       "                }\n"
       "            }\n"
       "            static const bool said = (std::fprintf(stderr, \"ttt2: GPU: write-backs read from %s memory\\n\",\n"
       "                                                   (flags & VK_MEMORY_PROPERTY_HOST_CACHED_BIT) ? \"cached\" : \"uncached\"), true);\n"
       "            (void)said;\n"
       "            write_back_staging_.push_back(ctx_.create_buffer(kWriteBackBytes, VK_BUFFER_USAGE_TRANSFER_DST_BIT, flags));\n")
if "patch_writeback_cached" in text:
    print("already: targets.cpp")
elif text.count(old) != 1:
    sys.exit("targets.cpp: the staging buffer allocation was not found once")
else:
    open(path, "w", encoding="utf-8", newline="").write(text.replace(old, new))
    print("patched: targets.cpp")
