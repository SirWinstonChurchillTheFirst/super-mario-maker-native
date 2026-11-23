#!/usr/bin/env python3
"""One-off edit of smash4/runtime/src/gx2/surface.cpp: GX2CopySurfaceEx for the whole-surface case.
Kept for the record; the result is in port/upstream-local.patch."""
import sys

p = sys.argv[1]
s = open(p).read()
a = "void GX2ResolveAAColorBuffer(ColorBuffer* src, Surface* dst, uint32_t dst_level, uint32_t dst_slice) {"
assert a in s and "GX2CopySurfaceEx" not in s
b = """// GX2CopySurfaceEx: `count` rectangles {left, top, right, bottom} of the source level, each to a point {x, y} of
// the destination level. One rectangle covering the whole level, to (0, 0), is GX2CopySurface; a partial copy is
// not written yet and stops with its numbers rather than copying the wrong area.
void GX2CopySurfaceEx(Surface* src, uint32_t src_level, uint32_t src_slice, Surface* dst, uint32_t dst_level,
                      uint32_t dst_slice, uint32_t count, const be<int32_t>* rects, const be<int32_t>* points) {
    const int32_t width = static_cast<int32_t>(std::max(uint32_t{src->width} >> src_level, 1u));
    const int32_t height = static_cast<int32_t>(std::max(uint32_t{src->height} >> src_level, 1u));
    for (uint32_t i = 0; i < count; ++i) {
        const int32_t left = rects[i * 4], top = rects[i * 4 + 1], right = rects[i * 4 + 2], bottom = rects[i * 4 + 3];
        const int32_t x = points[i * 2], y = points[i * 2 + 1];
        if (left != 0 || top != 0 || right != width || bottom != height || x != 0 || y != 0) {
            fatal("GX2CopySurfaceEx: partial copy (%d,%d)-(%d,%d) of %dx%d to (%d,%d) is not implemented yet", left, top,
                  right, bottom, width, height, x, y);
        }
        GX2CopySurface(src, src_level, src_slice, dst, dst_level, dst_slice);
    }
}

"""
s = s.replace(a, b + a)
a = "CAFE_EXPORT(gx2, GX2CopySurface, GX2CopySurface);"
assert a in s
s = s.replace(a, a + "\nCAFE_EXPORT(gx2, GX2CopySurfaceEx, GX2CopySurfaceEx);")
open(p, "w").write(s)
