#!/usr/bin/env python3
"""Bistatic scattering of a voxelized target in Meep (untested sketch: meep not installed here).

Run voxelize_msh.py first. Meep length unit a = 1 m  ->  frequency f = c/lambda = 1/lambda
(c = 1 in Meep units), so 100 MHz (lambda = 3 m) is frequency 1/3.

Usage:  python3 meep_rcs_voxel.py target.npz
Note: do NOT use `symmetries=` - the target is asymmetric.
"""
import sys
import numpy as np
import meep as mp

d = np.load(sys.argv[1])
mask, origin, vres = d["mask"], d["origin"], float(d["res"])

fcen = 1 / 3.0           # 100 MHz when 1 Meep length = 1 m
res = 1 / vres           # Meep pixels per length: same grid as the voxels (or an integer multiple)
dpml = 1.5               # ~ half a wavelength
size = np.array(mask.shape) * vres
pad = 1.5
cell = mp.Vector3(*(size + 2 * (pad + dpml)))

# Target: epsilon per voxel. Metal ~ large eps; use mp.perfect_electric_conductor-like via eps=-1e3 if needed.
eps_metal = 1e4
grid = np.where(mask, eps_metal, 1.0)
center = origin + size / 2
medium = mp.MaterialGrid(mp.Vector3(*mask.shape), mp.air, mp.Medium(epsilon=eps_metal),
                         weights=mask.astype(float), do_averaging=False)
geom = [mp.Block(mp.Vector3(*size), center=mp.Vector3(*center), material=medium)]


def make_sim(with_target):
    # Plane wave travelling +x, Ez polarised, injected on a plane left of the target.
    src_x = -cell.x / 2 + dpml + 0.3
    sources = [mp.Source(mp.ContinuousSource(fcen, fwidth=0.1 * fcen),
                         component=mp.Ez, center=mp.Vector3(src_x, 0, 0),
                         size=mp.Vector3(0, cell.y, cell.z))]
    return mp.Simulation(cell_size=cell, resolution=res,
                         boundary_layers=[mp.PML(dpml)],
                         sources=sources,
                         geometry=geom if with_target else [],
                         k_point=False)


def run(with_target, minus=None):
    sim = make_sim(with_target)
    # Near-to-far box around the target
    m = 0.5
    b = size / 2 + m
    c = mp.Vector3(*center)
    n2f = sim.add_near2far(
        fcen, 0, 1,
        mp.Near2FarRegion(c + mp.Vector3(-b[0], 0, 0), size=mp.Vector3(0, 2 * b[1], 2 * b[2]), weight=-1),
        mp.Near2FarRegion(c + mp.Vector3(+b[0], 0, 0), size=mp.Vector3(0, 2 * b[1], 2 * b[2]), weight=+1),
        mp.Near2FarRegion(c + mp.Vector3(0, -b[1], 0), size=mp.Vector3(2 * b[0], 0, 2 * b[2]), weight=-1),
        mp.Near2FarRegion(c + mp.Vector3(0, +b[1], 0), size=mp.Vector3(2 * b[0], 0, 2 * b[2]), weight=+1),
        mp.Near2FarRegion(c + mp.Vector3(0, 0, -b[2]), size=mp.Vector3(2 * b[0], 2 * b[1], 0), weight=-1),
        mp.Near2FarRegion(c + mp.Vector3(0, 0, +b[2]), size=mp.Vector3(2 * b[0], 2 * b[1], 0), weight=+1),
    )
    if minus is not None:
        sim.load_minus_near2far_data(n2f, minus)  # subtract empty-cell (incident) field
    sim.run(until=40 / fcen)
    return sim, n2f


sim0, n2f0 = run(False)
empty = sim0.get_near2far_data(n2f0)
sim1, n2f1 = run(True, minus=empty)  # n2f1 now holds the scattered field only

# Bistatic cut in the x-y plane at R = 100 wavelengths; theta measured from +x.
R = 100 / fcen
for deg in range(0, 360, 10):
    th = np.deg2rad(deg)
    ff = sim1.get_farfield(n2f1, mp.Vector3(R * np.cos(th), R * np.sin(th), 0))
    E = np.array(ff[:3])
    print(deg, float(np.sum(np.abs(E) ** 2)))
