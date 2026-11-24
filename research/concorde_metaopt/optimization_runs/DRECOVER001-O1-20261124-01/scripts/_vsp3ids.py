
import xml.etree.ElementTree as ET, collections, re
p=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine/o1-d06-refine.vsp3"
root=ET.parse(p).getroot()
ids=collections.Counter()
for el in root.iter():
    for k,v in el.attrib.items():
        if k in ("ID","AttachID") and v and set(v)<=set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            ids[len(v)]+=1
    if el.tag=="ID" and el.text and set(el.text.strip())<=set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        ids[len(el.text.strip())]+=1
print("length histogram for uppercase ID-shaped values:", dict(sorted(ids.items())))
# sample non-ID-looking values for ID attrs
odd=[ (el.tag,k,v) for el in root.iter() for k,v in el.attrib.items() if k in ("ID","AttachID") and not (v and set(v)<=set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))]
print("non-uppercase ID attrs:", len(odd), odd[:5])
