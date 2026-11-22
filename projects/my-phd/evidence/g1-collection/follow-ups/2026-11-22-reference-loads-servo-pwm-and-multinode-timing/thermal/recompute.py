"""Reproduce factual checks with Python 3 and openpyxl. Source files stay in --cache."""
import argparse
import csv
import hashlib
import math
import re
import statistics
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from openpyxl import load_workbook

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cache", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.cache.mkdir(parents=True, exist_ok=True)
args.output.mkdir(parents=True, exist_ok=True)
with Path(__file__).with_name("inputs.csv").open(encoding="utf-8") as f:
    inputs = list(csv.DictReader(f))
for source in inputs:
    path = args.cache / source["local_name"]
    if not path.exists():
        req = urllib.request.Request(source["url"], headers={"User-Agent": "G1-research/1.0"})
        with urllib.request.urlopen(req, timeout=90) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            raise ValueError("Upstream file changed: " + source["url"])
        path.write_bytes(data)
    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("Unexpected source version: " + str(path))

def book(stem):
    return load_workbook(args.cache / (stem + ".xlsx"), read_only=True, data_only=True)

def write(name, header, data):
    with (args.output / name).open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(header.split(","))
        for row in data:
            writer.writerow([format(v, ".9g") if isinstance(v, float) else v for v in row])

pzt = book("PMC13500680")
s34 = list(pzt["Fig. S34"].values)
loads = []
for col, axis in enumerate(s34[0][3:21], 3):
    load = int(re.search(r"\d+", s34[1][col]).group())
    begin, end = s34[2][col], s34[8][col]
    loads.append((axis, load, "N" if axis.startswith("F") else "mN m", 4,
                  100 * (end - begin) / begin, 100 * (end - begin) / load))
write("pzt-loaded-drift.csv", "axis,nominal_load,unit,temperature_levels,change_25_to_55_pct_of_25C_mean,change_25_to_55_pct_of_nominal_load", loads)

s35 = list(pzt["Fig. S35"].values)
assert [r[0] for r in s35[1:]] == [25,30,35,40,45,50]
write("pzt-unloaded-drift.csv", "electrode,temperature_levels,change_25_to_50_mV,change_25_to_50_pct_of_25C_mean",
      [(f"U{i}", len(s35)-1, s35[-1][2*i-1]-s35[1][2*i-1],
        100*(s35[-1][2*i-1]/s35[1][2*i-1]-1)) for i in range(1,7)])

paired = defaultdict(list)
for r in pzt["Fig. S24"].iter_rows(min_row=2,values_only=True):
    hz, axis, trial, applied, measured = r
    if hz is not None:
        paired[(hz, axis)].append((trial, measured-applied))
paired_stats = []
for (hz, axis), obs in sorted(paired.items()):
    trial_ids = {trial for trial,_ in obs}
    errors = [e for _,e in obs]
    paired_stats.append((hz,axis,len(obs),len(trial_ids),"N" if axis.startswith("F") else "mN m",
                         statistics.mean(errors), math.sqrt(statistics.mean(e*e for e in errors)),
                         max(map(abs,errors))))
write("pzt-paired-loads.csv","frequency_Hz,axis,paired_rows,distinct_counts_within_group,load_unit,mean_measured_minus_applied,rmse,max_abs_difference",paired_stats)

s39 = defaultdict(list)
for unit,temp,*values in pzt["Fig. S39b"].iter_rows(min_row=2, values_only=True):
    for axis,value in zip(("Fx","Fy","Fz","Mx","My","Mz"),values):
        s39[(unit,axis)].append((temp,value))
batch=[]
for (unit,axis), seq in sorted(s39.items()):
    seq.sort()
    vals=[v for _,v in seq]
    assert [t for t,_ in seq] == [25,35,45,55]
    batch.append((unit,axis,100*(vals[-1]/vals[0]-1),sum(b>a for a,b in zip(vals,vals[1:])),
                  sum(b==a for a,b in zip(vals,vals[1:]))))
write("pzt-eight-units.csv","unit,axis,change_25_to_55_pct_of_25C_output,upward_steps_of_three,flat_steps_of_three",batch)

book2 = book("026-71572-z")
crossed=[]
for sheet,start_col,ncols,control,interference,unit in [
        ("Fig 2.",17,6,"temperature","pressure","K"),("Fig 3.",24,5,"pressure","temperature","kPa")]:
    rows=list(book2[sheet].values)
    for row in rows[3:]:
        x=row[start_col]
        values=row[start_col+1:start_col+1+ncols]
        if isinstance(x,(int,float)) and all(isinstance(v,(int,float)) for v in values):
            crossed.append((sheet.strip(),control,x,unit,interference,len(values),max(values)-min(values)))
write("skin-crossed-conditions.csv","sheet,primary_control,setpoint,unit,secondary_control,levels,span_of_deltaR_over_R0_across_secondary_levels",crossed)

yu = book("024-46836-1")
yu_temp=[(r[1],r[2]) for r in list(yu['Fig 3b'].values)[2:] if isinstance(r[1],(int,float)) and isinstance(r[2],(int,float))]
yu_pressure=[(r[1],r[2]) for r in list(yu['Fig 3d'].values)[2:] if isinstance(r[1],(int,float)) and isinstance(r[2],(int,float))]
house = book("024-51261-5")
house_force = [(r[0],r[1]) for r in list(house['Figure 2c'].values)[1:] if isinstance(r[0],(int,float))]
house_temp = [(r[0],r[1]) for r in list(house['Figure 2e'].values)[1:] if isinstance(r[0],(int,float))]
write("separate-sweeps.csv","paper,sheet,independent_variable,unit,rows,min_value,max_value",
      [(s,sh,lab,u,len(vals),min(x for x,_ in vals),max(x for x,_ in vals)) for s,sh,lab,u,vals in [
          ("Yu et al.","Fig 3b","temperature difference","K",yu_temp),
          ("Yu et al.","Fig 3d","pressure","kPa",yu_pressure),
          ("robot housekeeping","Figure 2c","normal load (sheet label Pressure(N))","N",house_force),
          ("robot housekeeping","Figure 2e","temperature","degC",house_temp)]])

li=ET.parse(args.cache / "PMC10457871.xml")
table=li.findall(".//table-wrap")[1]
rows=[["".join(c.itertext()).strip() for c in tr] for tr in table.findall(".//tr")]
assert rows[0][1:4] == ["ELM","GWO-ELM","IGWO-ELM"]
metrics=[]
for row in rows[1:]:
    values=[float(s.replace("×10−","e-")) for s in row[1:]]
    metrics.append((row[0],100*(values[0]-values[2])/values[0],1+sum(v<values[2] for v in values)))
write("balance-heldout.csv","axis,pct_reduction_table2_igwo_elm_vs_elm,rank_among_five_lower_is_better",metrics)

hydro = book("026-69450-9")
exposures = []
for r in hydro["FigureS35"].iter_rows(min_row=3, max_row=6,values_only=True):
    pressures = r[9]
    currents_at_thermal_levels = r[10:17:2]
    assert len(currents_at_thermal_levels)==4 and pressures in [2,4,6,8]
    exposures.append((pressures,4,max(currents_at_thermal_levels)-min(currents_at_thermal_levels)))
write("hydrogel-thermal-conditions.csv","pressure_kPa,temperature_gradient_series,span_of_reported_current_increments_uA",exposures)

optical = book("024-52331-4")
hysteresis = []
for r in optical["Figure 2d, e"].iter_rows(min_row=4,values_only=True):
    if len(r) >= 7 and all(isinstance(v,(float,int)) for v in r[4:7]):
        load,up,down = r[4:7]
        hysteresis.append((load, abs(up-down)))
write("optical-hysteresis.csv","nominal_normal_force_N,abs_loading_unloading_integrated_intensity_difference_source_units",hysteresis)

s36 = list(pzt["Fig. S36"].values)
matrices = {}
for start in (1,13,25,37):
    temp = int(re.search(r"\d+",s36[start][0]).group())
    block = s36[start+2:start+8]
    assert [r[0] for r in block] == ["U1","U2","U3","U4","U5","U6"]
    matrices[temp] = [math.sqrt(sum(r[column]**2 for r in block)) for column in range(1,13)]
assert sorted(matrices) == [40,45,50,55]
changes=[]
for i,axis in enumerate(("Fx","Fy","Fz","Mx","My","Mz")):
    for sign,j in [("+",2*i),("-",2*i+1)]:
        values=[matrices[t][j] for t in sorted(matrices)]
        changes.append((axis,sign,len(values),100*(values[-1]/values[0]-1)))
write("pzt-coefficient-change.csv","axis,direction,temperature_specific_matrices,change_40_to_55_pct_in_electrode_column_L2_norm",changes)
