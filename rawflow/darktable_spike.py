"""Experimental legacy-XMP probe, deliberately excluded from production editing.
Layouts verified against darktable release-5.6.2 source. Little-endian arm64 only.
Uses deprecated basicadj for a narrow feasibility test, not scene-referred quality.
"""
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
from .core import doctor


def generate_profiles(out):
    tool = doctor()['tools']['darktable-cli']
    if not tool.get('version', '').startswith('darktable 5.6.2'):
        raise ValueError('XMP binary probe is pinned to darktable 5.6.2')
    rootdir = Path(out)
    rootdir.mkdir(parents=True, exist_ok=False)
    rdf = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
    dt = 'http://darktable.sf.net/'
    ET.register_namespace('x', 'adobe:ns:meta/'); ET.register_namespace('rdf', rdf); ET.register_namespace('darktable', dt)
    for name in ('baseline','exposure','white_balance','color','contrast'):
        basic = struct.pack('<5fi5f', 0, 1 if name=='exposure' else 0, 0, 0,
                            .25 if name=='contrast' else 0, 0, 18.42, 0,
                            .25 if name=='color' else 0, 0, 0)
        temp = struct.pack('<4fi', 2.5 if name=='white_balance' else 2., 1., 1.5, 1., 0)
        root=ET.Element('{adobe:ns:meta/}xmpmeta')
        rr=ET.SubElement(root, '{'+rdf+'}RDF')
        desc=ET.SubElement(rr, '{'+rdf+'}Description', {
            '{'+rdf+'}about':'', '{'+dt+'}xmp_version':'1', '{'+dt+'}history_end':'2',
            '{'+dt+'}auto_presets_applied':'1'})
        entries={'history_modversion':['4','2'],'history_enabled':['1','1'],
                 'history_operation':['temperature','basicadj'], 'history_params':[temp.hex(),basic.hex()],
                 'multi_priority':['0','0'],'multi_name':['','']}
        for field, values in entries.items():
            seq=ET.SubElement(ET.SubElement(desc,'{'+dt+'}'+field),'{'+rdf+'}Seq')
            for val in values: ET.SubElement(seq,'{'+rdf+'}li').text=val
        ET.ElementTree(root).write(rootdir/f'{name}.xmp',encoding='utf-8',xml_declaration=True)
    return rootdir
