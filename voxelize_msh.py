#!/usr/bin/env python3
"""Voxelize a closed triangle surface mesh (Gmsh .msh v2.2 ASCII) into a boolean grid.

Usage:
    python3 voxelize_msh.py target.msh out.npz --res 0.05 [--scale 1.0] [--center]

--res    voxel size in output units (after --scale)
--scale  multiply mesh coordinates (e.g. 10 if one mesh unit is 10 m)
--center move the bounding-box centre to the origin

Output npz: mask (nx,ny,nz) bool, origin (3,), res (float). Voxel (i,j,k) has its
centre at origin + (i+0.5, j+0.5, k+0.5) * res.

Method: cast a ray along +x through every (y,z) voxel column, collect the x of each
triangle crossing, sort, and fill between pairs (even-odd rule). Pure numpy.
"""
import argparse
import numpy as np


def read_msh_triangles(path):
    """Return (V, F): vertices (n,3) float and triangles (m,3) int (0-based)."""
    with open(path) as f:
        lines = f.read().split("\n")
    i = lines.index("$Nodes")
    n = int(lines[i + 1])
    ids, xyz = [], []
    for l in lines[i + 2:i + 2 + n]:
        t = l.split()
        ids.append(int(t[0]))
        xyz.append([float(t[1]), float(t[2]), float(t[3])])
    remap = {nid: k for k, nid in enumerate(ids)}
    i = lines.index("$Elements")
    m = int(lines[i + 1])
    tris = []
    for l in lines[i + 2:i + 2 + m]:
        t = l.split()
        if t[1] == "2":  # 3-node triangle
            tris.append([remap[int(x)] for x in t[-3:]])
    return np.array(xyz), np.array(tris, dtype=int)


def voxelize(V, F, res):
    lo = V.min(axis=0) - 2 * res
    hi = V.max(axis=0) + 2 * res
    shape = np.ceil((hi - lo) / res).astype(int)
    origin = lo
    # Tiny irrational offset on ray position avoids rays hitting edges/vertices exactly.
    cy = origin[1] + (np.arange(shape[1]) + 0.5) * res + 1.2345e-7 * res
    cz = origin[2] + (np.arange(shape[2]) + 0.5) * res + 2.7182e-7 * res

    crossings = {}  # (j,k) -> list of x
    for a, b, c in F:
        p, q, r = V[a], V[b], V[c]
        # 2D triangle in (y,z)
        d = (q[1] - p[1]) * (r[2] - p[2]) - (r[1] - p[1]) * (q[2] - p[2])
        if abs(d) < 1e-15:
            continue  # triangle parallel to the ray
        j0 = max(int(np.floor((min(p[1], q[1], r[1]) - origin[1]) / res - 0.5)), 0)
        j1 = min(int(np.ceil((max(p[1], q[1], r[1]) - origin[1]) / res + 0.5)), shape[1])
        k0 = max(int(np.floor((min(p[2], q[2], r[2]) - origin[2]) / res - 0.5)), 0)
        k1 = min(int(np.ceil((max(p[2], q[2], r[2]) - origin[2]) / res + 0.5)), shape[2])
        if j0 >= j1 or k0 >= k1:
            continue
        Y, Z = np.meshgrid(cy[j0:j1], cz[k0:k1], indexing="ij")
        # barycentric coordinates
        w1 = ((Y - p[1]) * (r[2] - p[2]) - (r[1] - p[1]) * (Z - p[2])) / d
        w2 = ((q[1] - p[1]) * (Z - p[2]) - (Y - p[1]) * (q[2] - p[2])) / d
        w0 = 1.0 - w1 - w2
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        X = w0 * p[0] + w1 * q[0] + w2 * r[0]
        for jj, kk in zip(*np.nonzero(inside)):
            crossings.setdefault((j0 + jj, k0 + kk), []).append(X[jj, kk])

    mask = np.zeros(shape, dtype=bool)
    cx = origin[0] + (np.arange(shape[0]) + 0.5) * res
    odd = 0
    for (j, k), xs in crossings.items():
        xs = np.sort(xs)
        if len(xs) % 2:
            odd += 1
            continue  # leaked ray (mesh not watertight here); leave column empty
        for x_in, x_out in zip(xs[0::2], xs[1::2]):
            mask[(cx >= x_in) & (cx < x_out), j, k] = True
    return mask, origin, odd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("msh")
    ap.add_argument("out")
    ap.add_argument("--res", type=float, required=True)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--center", action="store_true")
    a = ap.parse_args()

    V, F = read_msh_triangles(a.msh)
    V = V * a.scale
    if a.center:
        V = V - (V.min(axis=0) + V.max(axis=0)) / 2
    mask, origin, odd = voxelize(V, F, a.res)
    np.savez_compressed(a.out, mask=mask, origin=origin, res=a.res)

    vox_vol = mask.sum() * a.res ** 3
    print(f"triangles {len(F)}, grid {mask.shape}, filled {mask.sum()} voxels")
    print(f"voxel volume {vox_vol:.4g}, bbox {V.min(0)} .. {V.max(0)}")
    if odd:
        print(f"WARNING: {odd} columns had an odd number of crossings (skipped)")


if __name__ == "__main__":
    main()
