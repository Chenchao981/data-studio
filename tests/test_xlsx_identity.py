import importlib.util
from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('xlsx_identity', ROOT/'engine_support/desktop_client/nce_desktop/xlsx_identity.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def original(path):
    lots, count, found = set(), 0, False
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in book:
            if not sheet.title.startswith(('DC_Data', 'DVDS_Data', 'RG_Data', 'RAW')):
                continue
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, ())
            index = next((i for i, x in enumerate(header) if x in ('lot_ID','Lot_ID','批次')), None)
            if index is None:
                continue
            found = True
            for row in rows:
                if not any(x is not None for x in row):
                    continue
                count += 1
                if row[index] is not None and str(row[index]).strip():
                    lots.add(str(row[index]))
    finally:
        book.close()
    return lots, count, found


@pytest.mark.parametrize('shared', [True, False])
def test_identity_matches_original_with_sparse_rows_and_multiple_sheets(tmp_path, shared):
    path = tmp_path/'report.xlsx'
    tables = {'DC_Data': [['NUM','lot_ID','value'],[1,'001',2.3],[2,'批次A',None],[],[4,None,0],[5,'001',-1]],
              'RG_Data': [['Lot_ID','RG'],['批次B',0],['  ',1]],
              'Other': [['lot_ID'],['not a measurement']],
              'RAW_no_lot': [['parameter'],[20]]}
    if shared:
        import xlsxwriter
        book = xlsxwriter.Workbook(path)
        for name, rows in tables.items():
            sheet = book.add_worksheet(name)
            for i, row in enumerate(rows):
                sheet.write_row(i, 0, row)
        book.close()
    else:
        book = Workbook();book.remove(book.active)
        for name, rows in tables.items():
            sheet = book.create_sheet(name)
            for row in rows:sheet.append(row)
        book.save(path)
    assert module.read_identities(path) == original(path)


def test_numeric_lot_uses_original_reader(tmp_path):
    path = tmp_path/'numeric.xlsx'
    book = Workbook();sheet = book.active;sheet.title = 'DC_Data'
    sheet.append(['Lot_ID','value']);sheet.append([123,2]);book.save(path)
    with pytest.raises(module.UnsupportedIdentity):module.read_identities(path)
