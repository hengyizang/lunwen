"""Extract the angle-wise table-5 summaries from the NCBI BioC XML, PMC5424729.
Usage: python derive_contact_delays.py PATH_TO_ARCHIVED_BIOC_XML OUTPUT_DIRECTORY
"""
import argparse
import csv
import hashlib
import re
from pathlib import Path
from xml.etree import ElementTree as ET


def table_rows(source):
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != "c28f4ecae8e6b5a97c052e995c156721ed47a34113d2c6a08707c7bc5d3da299":
        raise ValueError("Different BioC XML version")
    for passage in ET.fromstring(raw).findall(".//passage"):
        attrs = {field.get("key"):field.text for field in passage.findall("infon")}
        if attrs.get("id") == "sensors-17-00852-t005" and attrs.get("type") == "table":
            rows = [[("".join(cell.itertext())).strip() for cell in tr]
                    for tr in ET.fromstring(attrs["xml"]).findall(".//tr")]
            break
    else:
        raise ValueError("Table 5 unavailable")
    header, filtered, derivative = rows
    if len(header) != 9 or len(filtered) != 9 or len(derivative) != 9:
        raise ValueError("Unexpected table layout")
    values = []
    for idx in range(1,9,2):
        degrees = int(re.search(r"\d+", header[idx])[0])
        if str(degrees) not in header[idx+1]:
            raise ValueError("Mean/SD angle pairing failed")
        entries = []
        for cell in (filtered[idx], filtered[idx+1], derivative[idx], derivative[idx+1]):
            m = re.fullmatch(r"([\d.]+)\s*ms", cell)
            if not m:
                raise ValueError(cell)
            entries.append(float(m[1]))
        values.append([degrees, 10, *entries, round(entries[0]-entries[2], 1)])
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml", type=Path)
    parser.add_argument("outdir", type=Path)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    with (args.outdir/"antenna-contact-delays.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["object_orientation_deg","reported_trials_at_orientation",
                         "filtered_residual_mean_ms","filtered_residual_sd_ms",
                         "residual_derivative_mean_ms","residual_derivative_sd_ms",
                         "difference_of_published_means_ms"])
        writer.writerows(table_rows(args.xml))


if __name__ == "__main__":
    main()
