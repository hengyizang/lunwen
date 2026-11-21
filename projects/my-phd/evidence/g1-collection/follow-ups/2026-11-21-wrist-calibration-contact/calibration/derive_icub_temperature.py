"""Recompute condition endpoints and reference-temperature contrasts from the article's JATS tables."""
import argparse
import csv
import hashlib
from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET


def cells(row):
    return ["".join(cell.itertext()).strip().replace("−", "-") for cell in row.findall("td")]


def write(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml", type=Path, help="PMC6960532 full-text XML from Europe PMC")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = args.xml.read_bytes()
    if hashlib.sha256(data).hexdigest() != "a6d07083c0c3753b8c91e2489df161d4b545624730bd6af012e63bea19f9c665":
        raise ValueError("XML differs from the version inspected")
    root = ET.fromstring(data)
    tables = {x.findtext("label"): x.findall("./table/tbody/tr") for x in root.findall(".//table-wrap")}
    sessions = []
    for row in tables["Table 2"]:
        cols = cells(row)
        if len(cols) == 1:
            role = {"Calibration Data Sets": "calibration", "Validation Data Sets": "validation"}[cols[0]]
        else:
            condition, day, start, end = cols
            sessions.append(dict(role=role, condition=condition, study_day=int(day), start_C=start,
                                 end_C=end, delta_C=Decimal(end) - Decimal(start)))
    values = {}
    for name in ["Table 3", "Table 5"]:
        values[name] = {}
        for row in tables[name]:
            method, *record = cells(row)
            values[name][method] = list(map(Decimal, record))
    contrast = []
    for prefix in ["S", "C", "O"]:
        default, removed = prefix+"wTdTO", prefix+"wTrTO"
        offset = [y-x for x,y in zip(values["Table 5"][default], values["Table 5"][removed])]
        mse = [y-x for x,y in zip(values["Table 3"][default], values["Table 3"][removed])]
        fields = {"family": {"S":"sphere","C":"centralized","O":"one_shot"}[prefix],
                  "from": default, "to": removed}
        fields.update(zip(("delta_Fx_N","delta_Fy_N","delta_Fz_N","delta_Tx_Nm","delta_Ty_Nm","delta_Tz_Nm"),offset))
        fields.update(zip(("delta_MSE_Fx_N2","delta_MSE_Fy_N2","delta_MSE_Fz_N2",
                           "delta_MSE_Tx_Nm2","delta_MSE_Ty_Nm2","delta_MSE_Tz_Nm2"),mse))
        contrast.append(fields)
    if len(sessions) != 13 or len(contrast) != 3:
        raise ValueError("Unexpected table coverage")
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output / "icub-temperature-sessions.csv", sessions)
    write(args.output / "icub-temperature-reference-contrasts.csv", contrast)


if __name__ == "__main__":
    main()
