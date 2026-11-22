"""Compute differences from explicitly identified published stage values and model parameters."""
import csv
from decimal import Decimal
from pathlib import Path
import sys

def save(path,fields,rows):
    with path.open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(fields);w.writerows(rows)
def calc(output):
    # Chao Zhang et al., 10.1177/16878132261422288, Results text adjacent to Fig. 11, CC BY-NC 4.0.
    vals=[('15.11','9.23','.29'),('20.89','17.15','.168'),('30.62','26.21','.10')]
    stage=[];prev=None
    for i,(p,s,r) in enumerate(vals,1):
        peak,stable,ecr=map(Decimal,(p,s,r))
        stage.append((i,peak-stable,'' if prev is None else ecr-prev,'' if prev is None else round(100*(ecr-prev)/prev,2)))
        prev=ecr
    save(output/'canted-coil-contrasts.csv',['engaged_springs','peak_minus_stable_force_N','stable_ECR_change_from_prior_milliohm','stable_ECR_change_from_prior_percent'],stage)
    # Qian et al., 10.1177/16878132241248348, Table 2, CC BY 4.0.
    means='0.00225 0.00286 0.00339 0.00371 0.00403 0.00419 0.00437 0.00443 0.00448 0.00449'.split()
    variances='0.0314 0.0285 0.0304 0.0278 0.0267 0.0268 0.0268 0.0242 0.0228 0.0214'.split()
    result=[]
    for i,(m,v) in enumerate(zip(means,variances),1):
        result.append((100*i,Decimal(m)-Decimal(means[0]),Decimal(v)-Decimal(variances[0])))
    save(output/'contact-degradation-contrasts.csv',['cycles','fitted_mu_omega_minus_100cycle_baseline','fitted_variance_omega_minus_100cycle_baseline'],result)
if __name__=='__main__':calc(Path(sys.argv[1]))
