#!/usr/bin/env python3
"""One-off edit of smash4/recomp/src/rpx.cpp: R_PPC_EMB_SDA21 picks its base by fit. Kept for the record;
the result is in port/upstream-local.patch."""
import sys

p = sys.argv[1]
s = open(p).read()
i = s.index("        const bool second = home ==")
j = s.index("        const uint32_t word = read_be32(data);", i)
new = """        // The base the offset fits decides; where both fit, the section of the symbol does.
        const int64_t from_sda = int64_t{value} - int64_t{image.file_info.sda_base};
        const int64_t from_sda2 = int64_t{value} - int64_t{image.file_info.sda2_base};
        const bool fits = from_sda >= -0x8000 && from_sda < 0x8000;
        const bool fits2 = from_sda2 >= -0x8000 && from_sda2 < 0x8000;
        if (!fits && !fits2) {
            fail("SDA21 relocation out of range (symbol in " + home + ", value " + std::to_string(value) + ")");
        }
        const bool second = fits2 && (!fits || home == ".sdata2" || home == ".sbss2");
        const int64_t delta = second ? from_sda2 : from_sda;
"""
open(p, "w").write(s[:i] + new + s[j:])
