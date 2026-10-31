"""Tests for the external OpenVSP worker geometry mapping (no OpenVSP required).

The real worker runs in the OpenVSP-bundled Python 3.9 interpreter. These tests
use a fake ``openvsp`` module to pin the section-parameter mapping, including the
W10 tip-twist fix: every wing section carries a ``twist_deg`` value that the
worker applies through the XSec ``Twist`` parameter about the leading edge.
"""
import unittest

from research.concorde_metaopt.aircraft import openvsp_geometry


class FakeParm(str):
    """Hashable parameter handle carrying its (section, name) identity."""


class FakeVSP:
    XS_FOUR_SERIES = "four-series"

    def __init__(self, section_count):
        self.section_count = section_count
        self.params = {}
        self.xform = {}

    def AddGeom(self, kind):
        return "geom"

    def SetGeomName(self, geom, name):
        self.geom_name = name

    def InsertXSec(self, geom, index, kind):
        self.inserted = getattr(self, "inserted", 0) + 1

    def GetXSecSurf(self, geom, index):
        return "surf"

    def GetNumXSec(self, surf):
        return self.section_count

    def GetXSec(self, surf, index):
        return "xsec%d" % index

    def GetXSecParm(self, xsec, name):
        return FakeParm(xsec + ":" + name)

    def SetParmVal(self, *args):
        if len(args) == 2:
            self.params[str(args[0])] = float(args[1])
        else:
            self.xform[(args[1], args[2])] = float(args[3])

    def Update(self):
        pass


def wing_spec(twists, symmetric=True):
    fractions = [0.0, 0.480469, 0.945313, 1.0]
    chords = [29.901819, 12.2, 3.9, 0.973136]
    leading_edges = [0.0, 8.0, 14.0, 16.0]
    sections = [
        {
            "percent_span_location": fraction,
            "chord_m": chord,
            "leading_edge_x_m": leading_edge,
            "twist_deg": twist,
        }
        for fraction, chord, leading_edge, twist in zip(fractions, chords, leading_edges, twists)
    ]
    return {
        "kind": "wing",
        "name": "main_wing",
        "symmetric": symmetric,
        "span_m": 25.604638,
        "location": [14.0, 0.0, -0.8],
        "rotation": [0.0, 0.0, 0.0],
        "sections": sections,
    }


class AddWingTwistTests(unittest.TestCase):
    def test_every_section_sets_twist_and_leading_edge_twist_location(self):
        vsp = FakeVSP(4)
        openvsp_geometry._add_wing(vsp, wing_spec([0.0, 0.0, 0.0, 2.0]))
        self.assertEqual(vsp.params["xsec0:Twist"], 0.0)
        self.assertEqual(vsp.params["xsec3:Twist"], 2.0)
        for index in range(4):
            key = "xsec%d:Twist_Location" % index
            self.assertIn(key, vsp.params)
            self.assertEqual(vsp.params[key], 0.0)
        self.assertEqual(vsp.params["xsec3:Tip_Chord"], 0.973136)
        self.assertAlmostEqual(vsp.params["xsec1:Root_Chord"], 29.901819)

    def test_missing_twist_defaults_to_zero(self):
        spec = wing_spec([0.0, 0.0, 0.0, 0.0])
        for section in spec["sections"]:
            del section["twist_deg"]
        vsp = FakeVSP(4)
        openvsp_geometry._add_wing(vsp, spec)
        for index in range(4):
            self.assertEqual(vsp.params["xsec%d:Twist" % index], 0.0)

    def test_symmetric_wing_uses_half_span(self):
        vsp = FakeVSP(4)
        openvsp_geometry._add_wing(vsp, wing_spec([0.0, 0.0, 0.0, 0.0]))
        span = vsp.params["xsec1:Span"]
        expected = (0.480469 - 0.0) * (25.604638 / 2.0)
        self.assertAlmostEqual(span, expected)


if __name__ == "__main__":
    unittest.main()