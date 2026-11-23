#!/usr/bin/env python3
"""Facts about a Wii U executable (RPX/RPL): sections, code size, function symbols, imports.

Own tool, reads the file only. usage: rpxinfo.py FILE [--imports OUT.txt]
An RPX is a big-endian 32-bit ELF whose sections may be deflated (flag 0x08000000, 4-byte size first).
Imports are symbols that lie in a section of type 0x80000002 named .fimport_<lib> / .dimport_<lib>.
"""
import struct
import sys
import zlib

SHF_EXEC, SHF_ZLIB = 0x4, 0x08000000
SHT_SYMTAB, SHT_NOBITS, SHT_IMPORTS, SHT_RELA = 2, 8, 0x80000002, 4


def load(path):
    d = open(path, "rb").read()
    assert d[:4] == b"\x7fELF" and d[4] == 1 and d[5] == 2, "not a big-endian ELF32"
    shoff, = struct.unpack_from(">I", d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from(">HHH", d, 0x2E)
    secs = []
    for i in range(shnum):
        name, typ, flags, addr, off, size, link, info, align, entsize = struct.unpack_from(">10I", d, shoff + i * shentsize)
        secs.append(dict(i=i, name=name, type=typ, flags=flags, addr=addr, off=off, size=size, link=link, info=info, entsize=entsize))

    def data(s):
        if s["type"] == SHT_NOBITS or s["off"] == 0:
            return b""
        raw = d[s["off"]:s["off"] + s["size"]]
        if s["flags"] & SHF_ZLIB:
            n, = struct.unpack_from(">I", raw, 0)
            raw = zlib.decompress(raw[4:])
            assert len(raw) == n
        return raw

    strtab = data(secs[shstrndx])
    for s in secs:
        e = strtab.index(b"\0", s["name"])
        s["sname"] = strtab[s["name"]:e].decode("ascii", "replace")
    return d, secs, data


def main():
    path = sys.argv[1]
    d, secs, data = load(path)
    out = sys.argv[sys.argv.index("--imports") + 1] if "--imports" in sys.argv else None
    text = [s for s in secs if s["flags"] & SHF_EXEC and s["type"] == 1]
    text_bytes = sum(len(data(s)) for s in text)
    imports_secs = {s["i"]: s for s in secs if s["type"] == SHT_IMPORTS}
    nfunc = nsized = 0
    imports = {}
    for s in secs:
        if s["type"] != SHT_SYMTAB:
            continue
        sym = data(s)
        strs = data(secs[s["link"]])
        for o in range(0, len(sym), 16):
            name, value, size, info, other, shndx = struct.unpack_from(">IIIBBH", sym, o)
            if shndx in imports_secs:
                e = strs.index(b"\0", name)
                n = strs[name:e].decode("ascii", "replace")
                if n:
                    lib = imports_secs[shndx]["sname"]
                    imports.setdefault(lib, set()).add(n)
            elif info & 0xF == 2:
                nfunc += 1
                nsized += size > 0
    nrela = sum(s["size"] for s in secs if s["type"] == SHT_RELA)
    print("file            %s (%d bytes)" % (path, len(d)))
    print("code            %d bytes = %d instructions in %s" % (text_bytes, text_bytes // 4, ", ".join("%s@%08X" % (s["sname"], s["addr"]) for s in text)))
    print("function syms   %d (%d with a size)" % (nfunc, nsized))
    fi = {k: v for k, v in imports.items() if k.startswith(".fimport_")}
    di = {k: v for k, v in imports.items() if k.startswith(".dimport_")}
    print("imports         %d functions from %d libraries, %d data" % (sum(map(len, fi.values())), len(fi), sum(map(len, di.values()))))
    for lib in sorted(fi):
        print("   %-22s %4d" % (lib[9:], len(fi[lib])))
    if out:
        with open(out, "w") as f:
            for lib in sorted(imports):
                kind = "f" if lib.startswith(".fimport_") else "d"
                for n in sorted(imports[lib]):
                    f.write("%s %s %s\n" % (kind, lib[9:], n))


if __name__ == "__main__":
    main()
