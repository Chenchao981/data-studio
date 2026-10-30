"""Stream only explicit FT identity cells, without constructing measurement cells.

Numeric/date identity cells fall back to the original openpyxl reader. This fast
path is for the text Lot columns emitted by the fixed FT writers.
"""
import posixpath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


class UnsupportedIdentity(ValueError):
    pass


def read_identities(file):
    lots, count, found = set(), 0, False
    with ZipFile(file) as archive:
        shared = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            with archive.open('xl/sharedStrings.xml') as stream:
                for _, item in ET.iterparse(stream, events=('end',)):
                    if item.tag == NS+'si':
                        shared.append(''.join(t.text or '' for t in item.iter(NS+'t')))
                        item.clear()

        def value(cell):
            kind = cell.get('t')
            raw = cell.find(NS+'v')
            if kind == 'inlineStr':
                inline = cell.find(NS+'is')
                return None if inline is None else ''.join(t.text or '' for t in inline.iter(NS+'t'))
            if raw is None or raw.text is None:
                return None
            if kind == 's':
                return shared[int(raw.text)]
            if kind in {'str', 'e'}:
                return raw.text
            raise UnsupportedIdentity('Non-text Lot column needs the original reader')

        relationships = {r.get('Id'): r for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        for sheet in workbook.findall(NS+'sheets/'+NS+'sheet'):
            if not sheet.get('name', '').startswith(('DC_Data', 'DVDS_Data', 'RG_Data', 'RAW')):
                continue
            rel = relationships[sheet.get(REL)]
            target = rel.get('Target', '')
            name = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            if rel.get('TargetMode') == 'External' or not name.startswith('xl/'):
                raise ValueError('Invalid worksheet relationship')
            column = None
            with archive.open(name) as stream:
                context = ET.iterparse(stream, events=('start', 'end'))
                _, root = next(context)
                for event, row in context:
                    if event != 'end' or row.tag != NS+'row':
                        continue
                    cells = row.findall(NS+'c')
                    if row.get('r') == '1':
                        for cell in cells:
                            if value(cell) in ('lot_ID', 'Lot_ID', '批次'):
                                column = ''.join(c for c in cell.get('r', '') if c.isalpha())
                                found = True
                                break
                    elif column:
                        # Count populated rows even when their identity cell is blank.
                        if any(c.find(NS+'v') is not None and c.find(NS+'v').text is not None
                               or c.find(NS+'is') is not None for c in cells):
                            count += 1
                        cell = next((c for c in cells if ''.join(x for x in c.get('r', '') if x.isalpha()) == column), None)
                        lot = value(cell) if cell is not None else None
                        if lot is not None and str(lot).strip():
                            lots.add(str(lot))
                    row.clear()
                    # Remove completed row objects, preserving bounded memory.
                    data = root.find(NS+'sheetData')
                    if data is not None:
                        data.clear()
    return lots, count, found
