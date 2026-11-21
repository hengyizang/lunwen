"""Compare independent Vicon joint-marker displacement with encoder motion.

Run beside derive_bilateral.py. Inputs are the same 8 FF/DL participant MAT
files. Do not infer one-way transmission delay from motion correlations.
"""
import argparse
from pathlib import Path
import re

import numpy as np
from scipy.io import loadmat
from derive_bilateral import shifted_match, write_table


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    files=sorted(p for p in args.source.glob("*.mat") if
                 re.fullmatch(r"OneDofHashtrudi-subject[1-4]-group[A-D]-(DL|FF)\.mat",p.name))
    if len(files)!=8:
        raise ValueError("Expected four subjects in two conditions each")
    output=[]
    for path in files:
        data=loadmat(path,squeeze_me=True,variable_names=["time","unit1_posout","unit2_posout",
                                                          "endstop_translation","endstop_visibility"])
        marker=data["endstop_translation"].T
        if not np.allclose(np.diff(data["time"]),.001,rtol=0,atol=1e-8):
            raise ValueError("Unexpected nominal sampling interval")
        count=len(marker)//5000
        for width in [2,10,20]:
            for unit in [1,2]:
                positions=data[f"unit{unit}_posout"]
                accepted=[]
                visible=0
                energetic=0
                discontinuous=0
                for start in range(0,count*5000,5000):
                    stop=start+5000
                    if not (data["endstop_visibility"][start:stop]==1).all():
                        continue
                    visible+=1
                    # Both speeds use the same centered difference interval:
                    # mm/s for the marker, rad/s for the encoder.
                    xyz=marker[start:stop]
                    q=positions[start:stop]
                    optical=np.linalg.norm(xyz[width:]-xyz[:-width],axis=1)*1000/width
                    discontinuous+=int(np.any(np.abs(np.diff(q))>np.pi))
                    encoder=np.abs(q[width:]-q[:-width])*1000/width
                    # Scale only for the eligibility filter: std >~0.1 rad/s,
                    # std >~5 mm/s at every candidate lag. Pearson r is invariant.
                    match=shifted_match(encoder,optical/50.0)
                    if match is None:
                        continue
                    energetic+=1
                    if match[1]>=.8:
                        accepted.append(match)
                output.append(dict(member=path.name,encoder_device=unit,difference_span_ms=width,
                                   complete_5s_windows=count,fully_marker_visible_windows=visible,
                                   visible_windows_with_encoder_step_over_pi=discontinuous,
                                   whole_record_encoder_steps_over_pi=int(np.sum(np.abs(np.diff(positions))>np.pi)),
                                   eligible_motion_windows=energetic,r_ge_0p8_windows=len(accepted),
                                   edge_lag_windows=sum(abs(x[0])==100 for x in accepted),
                                   median_marker_minus_encoder_lag_ms="" if not accepted else float(np.median([x[0] for x in accepted])),
                                   median_peak_r="" if not accepted else round(np.median([x[1] for x in accepted]),7)))
    args.output.mkdir(exist_ok=True,parents=True)
    write_table(args.output/"bilateral-optical-reference.csv",output)


if __name__=="__main__":
    main()
