
import xml.etree.ElementTree as ET
p=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine/o1-d06-refine.vsp3"
root=ET.parse(p).getroot()
for el in root.iter("WingGeom"):
    print("WingGeom children:")
    for c in el:
        print("  ",c.tag, c.attrib.get("Value"))
