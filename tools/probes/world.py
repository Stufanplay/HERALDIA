"""Read block states from a saved 26.3 world (region files) into {(x, y, z): "minecraft:block[props]"}."""
import io, math, os, struct, zlib
import nbtlib


def _chunk(region_path, cx, cz):
    with open(region_path, "rb") as f:
        data = f.read()
    i = 4 * ((cx & 31) + (cz & 31) * 32)
    off = int.from_bytes(data[i:i + 3], "big")
    if not off:
        return None
    start = off * 4096
    length = struct.unpack(">I", data[start:start + 4])[0]
    comp = data[start + 4]
    raw = data[start + 5:start + 4 + length]
    raw = zlib.decompress(raw) if comp == 2 else raw
    return nbtlib.File.parse(io.BytesIO(raw))


def _state(entry):
    if isinstance(entry, str):
        return str(entry)
    if "" in entry:
        return str(entry[""])
    name = str(entry["Name"] if "Name" in entry else entry["id"])
    props = entry.get("Properties") or entry.get("properties")
    if props:
        name += "[" + ",".join(f"{k}={v}" for k, v in sorted(props.items())) + "]"
    return name


def blocks(world_dir, x0, x1, y0, y1, z0, z1, dim="overworld"):
    reg = os.path.join(world_dir, "dimensions", "minecraft", dim, "region")
    out = {}
    for cx in range(x0 >> 4, (x1 >> 4) + 1):
        for cz in range(z0 >> 4, (z1 >> 4) + 1):
            ch = _chunk(os.path.join(reg, f"r.{cx >> 5}.{cz >> 5}.mca"), cx, cz)
            if ch is None:
                continue
            for sec in ch["sections"]:
                sy = int(sec["Y"])
                if sy * 16 > y1 or sy * 16 + 15 < y0 or "block_states" not in sec:
                    continue
                bs = sec["block_states"]
                pal = [_state(p) for p in bs["palette"]]
                data = bs.get("data")
                bits = max(4, math.ceil(math.log2(len(pal)))) if len(pal) > 1 else 0
                per = 64 // bits if bits else 0
                for i in range(4096):
                    if bits:
                        word = int(data[i // per]) & 0xFFFFFFFFFFFFFFFF
                        idx = (word >> ((i % per) * bits)) & ((1 << bits) - 1)
                    else:
                        idx = 0
                    lx, lz, ly = i & 15, (i >> 4) & 15, i >> 8
                    x, y, z = cx * 16 + lx, sy * 16 + ly, cz * 16 + lz
                    if x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1:
                        st = pal[idx]
                        if st not in ("minecraft:air", "minecraft:cave_air"):
                            out[(x, y, z)] = st
    return out
