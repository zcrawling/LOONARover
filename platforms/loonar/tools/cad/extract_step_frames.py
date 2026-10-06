#!/usr/bin/env python3
"""Extract AP214 assembly occurrence frames; these are CAD frames, not sensor axes.

Requires numpy/scipy. Repeated products are expanded as distinct occurrences.
The output is a frozen assembly snapshot, not robot joint kinematics.
"""
import argparse
import hashlib
import json
import re
import warnings
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation


def refs(text):
    return [int(i) for i in re.findall(r'#(\d+)', re.sub(r"'(?:[^']|'')*'", '', text))]


def label(text):
    strings = re.findall(r"'((?:[^']|'')*)'", text)
    value = strings[1] if len(strings) > 1 else strings[0]
    value = re.sub(r'\\X2\\(.*?)\\X0\\', lambda m: bytes.fromhex(m[1]).decode('utf-16-be'), value)
    return ' '.join(value.replace("''", "'").split())


def extract(path):
    source = path.read_text()
    entities = {int(i): v for i, v in re.findall(r'#(\d+)\s*=\s*(.*?);', source, re.S)}
    products = {i: label(entities[refs(entities[refs(v)[0]])[-1]])
                for i, v in entities.items() if v.startswith('PRODUCT_DEFINITION(')}

    def unit(rep):
        context = entities[refs(entities[rep])[-1]]
        units = re.search(r'GLOBAL_UNIT_ASSIGNED_CONTEXT\(\((.*?)\)\)', context)[1]
        for u in refs(units):
            text = entities[u]
            if 'LENGTH_UNIT' in text:
                if 'SI_UNIT(.MILLI.,.METRE.)' in text: return .001
                if 'SI_UNIT($,.METRE.)' in text: return 1.
                raise ValueError(f'Unsupported length unit #{u}: {text}')
        raise ValueError('Missing length unit')

    def vector(i):
        return np.array([float(x) for x in re.search(r'\(([^()]*)\)\)$', entities[i])[1].split(',')])

    def placement(i, scale):
        r = refs(entities[i])
        # This export specifies both direction vectors. Fail on omitted axes.
        if len(r) != 3: raise ValueError(f'Incomplete placement #{i}')
        z, x = vector(r[1]), vector(r[2])
        z /= np.linalg.norm(z)
        x -= z * np.dot(z, x)
        x /= np.linalg.norm(x)
        m = np.eye(4)
        m[:3, :3] = np.array([x, np.cross(z, x), z]).T
        m[:3, 3] = vector(r[0]) * scale
        return m

    transforms = {}
    for v in entities.values():
        if not v.startswith('CONTEXT_DEPENDENT_SHAPE_REPRESENTATION'): continue
        rel, pds = refs(v)
        occ = refs(entities[pds])[-1]
        relationship = re.search(r'REPRESENTATION_RELATIONSHIP\((.*?)\)', entities[rel])[1]
        child_rep, parent_rep = refs(relationship)
        tid = int(re.search(r'REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION\(#(\d+)\)', entities[rel])[1])
        a, b = refs(entities[tid])
        transforms[occ] = placement(b, unit(parent_rep)) @ np.linalg.inv(placement(a, unit(child_rep)))

    children = {}
    used = set()
    for i, v in entities.items():
        if not v.startswith('NEXT_ASSEMBLY_USAGE_OCCURRENCE'): continue
        parent, child = refs(v)[:2]
        children.setdefault(parent, []).append((i, child))
        used.add(child)
    roots = set(products) - used
    if len(roots) != 1: raise ValueError(f'Expected one root, got {roots}')
    root = roots.pop()
    rows = []

    def visit(product, parent_frame, world, stack):
        if product in stack: raise ValueError('Assembly cycle')
        for occurrence, child in children.get(product, []):
            matrix = transforms[occurrence]
            frame = f'{parent_frame}_o{occurrence}'
            global_matrix = world @ matrix
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                rpy = Rotation.from_matrix(matrix[:3, :3]).as_euler('xyz')
            rows.append(dict(frame=frame, parent=parent_frame, name=products[child],
                             occurrence=occurrence, product_definition=child,
                             xyz_m=matrix[:3, 3].tolist(), rpy_rad=rpy.tolist(),
                             matrix=matrix.tolist(), root_matrix=global_matrix.tolist()))
            visit(child, frame, global_matrix, stack | {product})
    visit(root, 'cad_root', np.eye(4), set())
    return dict(source=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                root_product=products[root], units='metres/radians',
                purpose='CAD assembly snapshot only; movable components frozen at exported pose', frames=rows)


def snapshot(data):
    robot = ET.Element('robot', name='loonar_cad_snapshot')
    ET.SubElement(robot, 'link', name='cad_root')
    for row in data['frames']:
        ET.SubElement(robot, 'link', name=row['frame'])
        joint = ET.SubElement(robot, 'joint', name=row['frame']+'_snapshot', type='fixed')
        ET.SubElement(joint, 'parent', link=row['parent'])
        ET.SubElement(joint, 'child', link=row['frame'])
        ET.SubElement(joint, 'origin', xyz=' '.join(f'{x:.12g}' for x in row['xyz_m']),
                      rpy=' '.join(f'{x:.12g}' for x in row['rpy_rad']))
    ET.indent(robot)
    return ET.tostring(robot, encoding='unicode')+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = extract(args.step)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'cad_frames.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    (args.output/'cad_snapshot.urdf').write_text(snapshot(data))
    print(f"Extracted {len(data['frames'])} occurrence frames")


if __name__ == '__main__': main()
