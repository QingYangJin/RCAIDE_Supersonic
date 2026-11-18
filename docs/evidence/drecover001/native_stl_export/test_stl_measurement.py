"""Synthetic parser regressions; never real mesh evidence."""
from pathlib import Path
import tempfile
import struct
import unittest
import numpy as np
from run_stl_diagnostic import measure


class STLMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "fixture.stl"

    def ascii(self, triangles):
        rows = ["solid fixture"]
        for tri in triangles:
            rows += ["facet normal 0 0 0", "outer loop"]
            rows += ["vertex " + " ".join(str(x) for x in vertex) for vertex in tri]
            rows += ["endloop", "endfacet"]
        rows += ["endsolid fixture"]
        self.path.write_text("\n".join(rows))
        return measure(self.path)

    def test_single_triangle_bounds_area_boundary(self):
        m = self.ascii([[(0, 0, 0), (1, 0, 0), (0, 1, 0)]])
        self.assertEqual(m["bounds_m"], [[0., 0., 0.], [1., 1., 0.]])
        self.assertEqual(m["surface_area_m2"], .5)
        self.assertEqual(m["boundary_edges_after_quantization"], 3)
        self.assertEqual(m["near_zero_area_triangles"], 0)

    def test_binary_and_ascii_agree(self):
        triangle = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        a = self.ascii([triangle])
        raw = b"fixture".ljust(80, b" ") + struct.pack("<I12fH", 1, *([0., 0., 1.] + [x for v in triangle for x in v]), 0)
        self.path.write_bytes(raw)
        b = measure(self.path)
        for key in ("triangles", "bounds_m", "surface_area_m2", "boundary_edges_after_quantization"):
            self.assertEqual(a[key], b[key])
        self.assertEqual(b["format"], "binary")

    def test_tetra_closed_edge_counts(self):
        p = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
        m = self.ascii([[p[i] for i in indices] for indices in ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))])
        self.assertEqual(m["boundary_edges_after_quantization"], 0)
        self.assertEqual(m["nonmanifold_edges_after_quantization"], 0)
        self.assertEqual(m["duplicate_triangle_excess"], 0)

    def test_duplicate_and_nonmanifold_detected(self):
        tri = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        m = self.ascii([tri] * 3)
        self.assertEqual(m["duplicate_triangle_excess"], 2)
        self.assertEqual(m["nonmanifold_edges_after_quantization"], 3)

    def test_collapsed_and_collinear_faces_detected(self):
        m = self.ascii([[(0, 0, 0), (0, 0, 0), (1, 0, 0)], [(0, 0, 0), (1, 0, 0), (2, 0, 0)]])
        self.assertEqual(m["near_zero_area_triangles"], 2)
        self.assertEqual(m["collapsed_faces_after_quantization"], 1)

    def test_nonfinite_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            self.ascii([[(float("nan"), 0, 0), (1, 0, 0), (0, 1, 0)]])

    def test_missing_and_incomplete_rejected(self):
        for content in ("solid empty\nendsolid empty", "vertex 0 0 0", "vertex 1 2"):
            self.path.write_text(content)
            with self.assertRaises(ValueError):
                measure(self.path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
