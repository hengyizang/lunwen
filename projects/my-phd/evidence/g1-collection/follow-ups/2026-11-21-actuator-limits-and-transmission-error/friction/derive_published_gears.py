"""Recover per-gear aggregates from printed torque tables 2.2–2.4 in Ponce Quiroga (2022)."""
import argparse
import csv
import hashlib
from pathlib import Path
import statistics
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    digest = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    text = subprocess.check_output(["pdftotext", "-layout", str(args.pdf), "-"], text=True)
    table_headers = text.split("Indirect Torque Measures")[1:]
    if len(table_headers) != 3:
        raise ValueError("Unexpected number of torque subtables")
    results = []
    for i, (gear, repetitions, table) in enumerate(zip(("HFUC", "HFUS", "HDUR"), (3, 4, 1), table_headers), 2):
        cells = []
        for line in table.splitlines():
            fields = line.replace("N.m", "").split()
            if len(fields) != 1 + 2 * repetitions:
                continue
            try:
                values = [None if v == "-" else float(v) for v in fields]
            except ValueError:
                continue
            cells.append(values)
            if len(cells) == 11:
                break
        if len(cells) != 11 or cells[0][0] != 0 or cells[1][1:1+repetitions] != [0] * repetitions:
            raise ValueError(f"Unexpected numbered table {i}")
        widths = []
        for values in cells[2:]:
            indirect = values[1:1+repetitions]
            direct = values[1+repetitions:]
            widths.append(statistics.median(d-i for d,i in zip(direct, indirect)))
        results.append(dict(gear=gear, printed_table=f"2.{i}", repetitions_per_matched_output=repetitions,
                            matched_output_loads=len(widths), lowest_matched_output_Nm=f"{cells[2][0]:.3f}",
                            highest_matched_output_Nm=f"{cells[-1][0]:.3f}",
                            median_direct_threshold_input_Nm_with_unloaded_output=f"{statistics.median(cells[0][1+repetitions:]):.4f}",
                            backdrive_output_threshold_Nm_with_unloaded_input=f"{cells[1][0]:.3f}",
                            median_paired_input_width_Nm_at_lowest_matched_output=f"{widths[0]:.4f}",
                            median_paired_input_width_Nm_at_highest_matched_output=f"{widths[-1]:.4f}",
                            increasing_adjacent_median_widths=sum(b > a for a,b in zip(widths, widths[1:])),
                            adjacent_load_pairs=len(widths)-1, pdf_sha256=digest))
    args.output.mkdir(exist_ok=True, parents=True)
    with (args.output/"published-gear-thresholds.csv").open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=results[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    main()
