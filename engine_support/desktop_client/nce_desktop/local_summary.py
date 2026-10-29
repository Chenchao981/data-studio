"""Read explicit identities from generated standard tables, never from filenames."""

import csv
import io
import tempfile
from zipfile import ZipFile


def clean_summary(package, stage):
    identities = set()
    count = 0
    found = False
    truncated = False

    def add(lot, wafer=""):
        nonlocal truncated
        if lot is None or str(lot).strip() == "":
            return
        pair = (str(lot), str(wafer) if wafer is not None else "")
        if len(identities) < 10000:
            identities.add(pair)
        elif pair not in identities:
            truncated = True

    with ZipFile(package) as archive:
        for name in archive.namelist():
            if stage == "CP" and "_cleaned_" in name and name.endswith(".csv"):
                with archive.open(name) as stream:
                    rows = csv.DictReader(
                        io.TextIOWrapper(stream, encoding="utf-8-sig")
                    )
                    if not {"Lot_ID", "Wafer_ID"}.issubset(rows.fieldnames or []):
                        continue
                    found = True
                    for row in rows:
                        count += 1
                        add(row["Lot_ID"], row["Wafer_ID"])
            elif stage == "FT" and name.endswith(".xlsx"):
                from openpyxl import load_workbook

                # Spill large reports to disk instead of retaining all XLSX bytes in memory.
                with tempfile.TemporaryFile() as temporary, archive.open(
                    name
                ) as stream:
                    import shutil

                    shutil.copyfileobj(stream, temporary)
                    temporary.seek(0)
                    book = load_workbook(temporary, read_only=True, data_only=True)
                    try:
                        for sheet in book:
                            if not (
                                sheet.title.startswith(
                                    ("DC_Data", "DVDS_Data", "RG_Data", "RAW")
                                )
                            ):
                                continue
                            rows = sheet.iter_rows(values_only=True)
                            header = next(rows, ())
                            index = next(
                                (
                                    i
                                    for i, x in enumerate(header)
                                    if x in ("lot_ID", "Lot_ID", "批次")
                                ),
                                None,
                            )
                            if index is None:
                                continue
                            found = True
                            for row in rows:
                                if not any(x is not None for x in row):
                                    continue
                                count += 1
                                add(row[index])
                    finally:
                        book.close()
    return {
        "product": None,
        "lot_wafers": [
            {"lot": lot, "wafer": wafer} for lot, wafer in sorted(identities)
        ],
        "truncated": truncated,
        "basis": "生成结果中的原始批次字段",
        "output_table_rows": count if found else None,
    }
