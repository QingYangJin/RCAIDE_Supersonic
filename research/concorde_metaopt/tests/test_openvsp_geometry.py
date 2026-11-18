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
    XS_ELLIPSE = "ellipse"
    ABS = 0
    SYM_XZ = 2

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

    def GetParm(self, geom, name, group):
        return FakeParm(group + ":" + name)

    def GetParmVal(self, handle):
        return self.params.get(str(handle), 0.0)

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
        "thickness_to_chord": 0.03,
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


class AbsoluteTransformTests(unittest.TestCase):
    def test_vertical_tail_has_absolute_nonzero_rotation_and_no_symmetry(self):
        spec = wing_spec([0.0] * 4, symmetric=False)
        spec.update(name="vertical_tail", rotation=[90.0, 0.0, 0.0], location=[42.0, 0.0, 1.5])
        vsp = FakeVSP(4)
        openvsp_geometry._add_wing(vsp, spec)
        self.assertEqual(vsp.params["XForm:Abs_Or_Relitive_flag"], vsp.ABS)
        self.assertEqual(vsp.params["XForm:X_Rotation"], 90.0)
        self.assertEqual(vsp.params["XForm:X_Location"], 42.0)
        self.assertEqual(vsp.params["XForm:Z_Location"], 1.5)
        self.assertEqual(vsp.params["Sym:Sym_Planar_Flag"], 0.0)

    def test_main_wing_explicitly_sets_symmetry(self):
        vsp = FakeVSP(4)
        openvsp_geometry._add_wing(vsp, wing_spec([0.0] * 4))
        self.assertEqual(vsp.params["Sym:Sym_Planar_Flag"], vsp.SYM_XZ)

    def test_missing_transform_parameter_fails(self):
        vsp = FakeVSP(4)
        original = vsp.GetParm
        vsp.GetParm = lambda geom, name, group: "" if name == "X_Rotation" else original(geom, name, group)
        with self.assertRaisesRegex(RuntimeError, "missing XForm parameter X_Rotation"):
            openvsp_geometry._add_wing(vsp, wing_spec([0.0] * 4))

    def test_rejected_transform_fails_instead_of_echoing_request(self):
        for key in ("XForm:X_Rotation", "XForm:Abs_Or_Relitive_flag"):
            with self.subTest(key=key):
                vsp = FakeVSP(4)
                original = vsp.GetParmVal
                vsp.GetParmVal = lambda handle: 123.0 if str(handle) == key else original(handle)
                with self.assertRaisesRegex(RuntimeError, "XForm .* rejected"):
                    openvsp_geometry._add_wing(vsp, wing_spec([0.0] * 4))

    def test_nonfinite_readback_fails(self):
        vsp = FakeVSP(4)
        original = vsp.GetParmVal
        vsp.GetParmVal = lambda handle: float("nan") if str(handle) == "XForm:Y_Location" else original(handle)
        with self.assertRaisesRegex(RuntimeError, "XForm Y_Location rejected"):
            openvsp_geometry._add_wing(vsp, wing_spec([0.0] * 4))

    def test_invalid_vectors_rejected_before_transform_writes(self):
        for key, value in (("location", [1, 2]), ("rotation", [0, 0, float("nan")]),
                           ("location", [0, float("inf"), 0])):
            with self.subTest(key=key, value=value):
                vsp = FakeVSP(4)
                spec = dict(name="test", **{key: value})
                with self.assertRaises(ValueError):
                    openvsp_geometry._apply_absolute_transform(vsp, "geom", spec)
                self.assertFalse(vsp.params)

    def test_fuselage_also_applies_absolute_placement(self):
        vsp = FakeVSP(5)
        spec = dict(name="fuselage", length_m=10.0, location=[3.0, 2.0, 1.0],
                    rotation=[0.0, 5.0, 0.0], stations=[
                        dict(x_m=x, width_m=1.0, height_m=1.0) for x in (0, 2, 5, 8, 10)])
        openvsp_geometry._add_fuselage(vsp, spec)
        self.assertEqual(vsp.params["XForm:X_Location"], 3.0)
        self.assertEqual(vsp.params["XForm:Y_Rotation"], 5.0)

    def test_default_placement_is_explicit_identity(self):
        vsp = FakeVSP(4)
        openvsp_geometry._apply_absolute_transform(vsp, "geom", dict(name="default"))
        self.assertEqual(len(vsp.params), 7)
        self.assertTrue(all(value == 0.0 for value in vsp.params.values()))

    def test_missing_symmetry_parameter_fails(self):
        vsp = FakeVSP(4)
        original = vsp.GetParm
        vsp.GetParm = lambda geom, name, group: "" if group == "Sym" else original(geom, name, group)
        with self.assertRaisesRegex(RuntimeError, "missing planar symmetry parameter"):
            openvsp_geometry._add_wing(vsp, wing_spec([0.0] * 4))

    def test_rejected_symmetry_fails(self):
        vsp = FakeVSP(4)
        original = vsp.GetParmVal
        vsp.GetParmVal = lambda handle: 99.0 if str(handle).startswith("Sym:") else original(handle)
        with self.assertRaisesRegex(RuntimeError, "planar symmetry rejected"):
            openvsp_geometry._add_wing(vsp, wing_spec([0.0] * 4))


class AirfoilThicknessTests(unittest.TestCase):
    def test_all_sections_receive_explicit_thickness(self):
        for value in (0.03, 0.04):
            vsp = FakeVSP(4)
            spec = wing_spec([0.] * 4)
            spec["thickness_to_chord"] = value
            openvsp_geometry._add_wing(vsp, spec)
            for index in range(4):
                self.assertEqual(vsp.params["xsec%d:ThickChord" % index], value)

    def test_invalid_or_absent_thickness_rejected(self):
        for value in (None, True, 0., -0.1, 1., float("nan"), float("inf"), "0.03"):
            vsp = FakeVSP(4)
            spec = wing_spec([0.] * 4)
            spec["thickness_to_chord"] = value
            with self.assertRaisesRegex(ValueError, "thickness_to_chord"):
                openvsp_geometry._add_wing(vsp, spec)
            self.assertFalse(vsp.params)

    def test_missing_handle_rejected(self):
        vsp = FakeVSP(4)
        original = vsp.GetXSecParm
        vsp.GetXSecParm = lambda xsec, name: "" if name == "ThickChord" else original(xsec, name)
        with self.assertRaisesRegex(RuntimeError, "missing ThickChord"):
            openvsp_geometry._add_wing(vsp, wing_spec([0.] * 4))

    def test_rejected_or_nonfinite_thickness_rejected(self):
        for value in (.1, float("nan")):
            vsp = FakeVSP(4)
            original = vsp.GetParmVal
            vsp.GetParmVal = lambda handle: value if str(handle).endswith(":ThickChord") else original(handle)
            with self.assertRaisesRegex(RuntimeError, "ThickChord .* rejected"):
                openvsp_geometry._add_wing(vsp, wing_spec([0.] * 4))

    def test_request_passes_both_component_thicknesses(self):
        from pathlib import Path
        from research.concorde_metaopt.aircraft.geometry_model import build_geometry
        from research.concorde_metaopt.aircraft.openvsp_check import build_openvsp_request
        import yaml
        config = yaml.safe_load((Path(__file__).parents[1] / "configs/design_space_12d_lifting_surfaces.yaml").read_text())
        variables = config["variables"] + config["fixed_variables"]
        model = build_geometry([v["name"] for v in variables], [v["baseline"] for v in variables])
        components = build_openvsp_request(model, Path("unused"))["components"]
        self.assertEqual([c["thickness_to_chord"] for c in components[:2]], [.03, .04])


if __name__ == "__main__":
    unittest.main()