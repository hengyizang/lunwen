"""Recompute stationary PMSM current features and condition-level torque fits.

Inputs are the two ZIP-compressed CSV files and Torque_Table.csv from Kaggle
version 3. Requires Python >=3.11, pandas and numpy. Each torque target is
counted once per speed and operating point, regardless of the scope row count.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pandas as pd


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class HashReader(io.RawIOBase):
    def __init__(self, original):
        self.original = original
        self.sha = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, target):
        data = self.original.read(len(target))
        target[:len(data)] = data
        self.sha.update(data)
        return len(data)


def process(source, speed):
    name = f'Time_series_{speed}rpm.csv'
    path = source / (name + '.zip')
    aggregates = {}
    previous = {}
    columns = ['OP', 'time in s', 'i_a in A', 'i_b in A', 'i_c in A',
               'epsilon_el in rad', 's_n']
    with ZipFile(path) as archive, archive.open(name) as original:
        entry = archive.getinfo(name)
        hashed = HashReader(original)
        for chunk in pd.read_csv(io.BufferedReader(hashed, buffer_size=2**20),
                                 usecols=columns, chunksize=250_000):
            for op, block in chunk.groupby('OP', sort=False):
                op = int(op)
                a,b,c = (block[k].to_numpy() for k in columns[2:5])
                t = block['time in s'].to_numpy()
                angle = block['epsilon_el in rad'].to_numpy()
                complete=np.isfinite(a)&np.isfinite(b)&np.isfinite(c)&np.isfinite(angle)
                current_missing=int((~(np.isfinite(a)&np.isfinite(b)&np.isfinite(c))).sum())
                angle_missing=int((~np.isfinite(angle)).sum())
                a,b,c,angle=(v[complete] for v in (a,b,c,angle))
                # Amplitude-invariant Clarke and Park, positive q = -sin(theta)*alpha + cos(theta)*beta.
                alpha = (2*a-b-c)/3
                beta = (b-c)/np.sqrt(3)
                co,si = np.cos(angle),np.sin(angle)
                d,q = co*alpha+si*beta,co*beta-si*alpha
                state = block.s_n.dropna().to_numpy()
                if not np.isin(state, np.arange(1,9)).all():
                    raise ValueError('Unexpected inverter state')
                elapsed = np.diff(t, prepend=previous.get(op, t[0]-1e-6))
                previous[op] = t[-1]
                row = aggregates.setdefault(op, dict(n=0, valid_switch=0, nonincreasing_t=0,
                    irregular_dt_over_1ns=0, first_s=t[0], last_s=t[-1],
                    feature_rows=0, missing_phase_rows=0, missing_angle=0, missing_time=0,
                    dsum=0., qsum=0., dqsum=0., i2sum=0.))
                row['n'] += len(t)
                row['feature_rows'] += len(d)
                row['missing_phase_rows'] += current_missing
                row['missing_angle'] += angle_missing
                row['missing_time'] += int((~np.isfinite(t)).sum())
                row['valid_switch'] += len(state)
                row['nonincreasing_t'] += int((elapsed<=0).sum())
                row['irregular_dt_over_1ns'] += int((np.abs(elapsed-1e-6)>1e-9).sum())
                row['last_s'] = t[-1]
                row['dsum'] += float(d.sum())
                row['qsum'] += float(q.sum())
                row['dqsum'] += float(d@q)
                row['i2sum'] += float(a@a+b@b+c@c)
        record = dict(member=name, archive_bytes=path.stat().st_size,
                      archive_sha256=digest(path), member_bytes=entry.file_size,
                      member_crc32=f'{entry.CRC:08x}', member_sha256=hashed.sha.hexdigest())
    result = []
    for op,v in sorted(aggregates.items()):
        n=v['feature_rows']
        if not n:
            raise ValueError('No complete current-angle rows for an operating point')
        result.append(dict(speed_rpm=speed, op=op, scope_rows=v['n'],current_angle_complete_rows=n,
            missing_phase_current_rows=v['missing_phase_rows'],missing_angle_rows=v['missing_angle'],
            missing_time_rows=v['missing_time'],
            first_time_s=v['first_s'], last_time_s=v['last_s'],
            nonincreasing_time=v['nonincreasing_t'], increments_off_1us_by_over_1ns=v['irregular_dt_over_1ns'],
            rows_with_switch_state=v['valid_switch'], mean_id_a=v['dsum']/n,
            mean_iq_a=v['qsum']/n, mean_id_iq_a2=v['dqsum']/n,
            phase_pooled_rms_a=np.sqrt(v['i2sum']/(3*n))))
    return pd.DataFrame(result), record


def write_table(out, name, records):
    records.to_csv(out/name,index=False,float_format='%.9f',lineterminator='\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('out',type=Path)
    a=p.parse_args()
    a.out.mkdir(exist_ok=True,parents=True)
    with ThreadPoolExecutor(2) as executor:
        pair=list(executor.map(lambda s:process(a.source,s),(120,2000)))
    references=pd.read_csv(a.source/'Torque_Table.csv').rename(
        columns={'OP':'op','Speed in 1/min':'speed_rpm','T in Nm':'mean_shaft_torque_nm'})
    currents=pd.concat([x[0] for x in pair],ignore_index=True)
    data=currents.merge(references,on=['speed_rpm','op'],how='outer',validate='one_to_one',
                        indicator=True)
    if not data['_merge'].eq('both').all():
        raise ValueError('Missing current measurement or torque target')
    data=data.drop(columns='_merge')
    write_table(a.out,'torque-grid-operating-points.csv',data.drop(columns='mean_shaft_torque_nm'))
    low=data.loc[data.speed_rpm==120].set_index('op')
    high=data.loc[data.speed_rpm==2000].set_index('op')
    differences=(high[['mean_id_a','mean_iq_a','mean_shaft_torque_nm']]-
                 low[['mean_id_a','mean_iq_a','mean_shaft_torque_nm']]).add_prefix('delta_2000_minus_120_')
    write_table(a.out,'torque-grid-speed-differences.csv',differences.reset_index())
    write_table(a.out,'torque-grid-source-files.csv',pd.DataFrame([x[1] for x in pair]))
    fits=[]
    for speed,train in data.groupby('speed_rpm'):
        for label,cols in [('q_only',['mean_iq_a']),('q_and_dq',['mean_iq_a','mean_id_iq_a2'])]:
            def design(frame):
                return np.column_stack([np.ones(len(frame)),frame[cols].to_numpy()])
            b,_,rank,_=np.linalg.lstsq(design(train),train.mean_shaft_torque_nm,rcond=None)
            for test_speed,test in data.groupby('speed_rpm'):
                residual=design(test)@b-test.mean_shaft_torque_nm.to_numpy()
                fits.append(dict(model=label,train_rpm=speed,test_rpm=test_speed,
                    train_ops=len(train),test_ops=len(test),design_rank=rank,
                    intercept_nm=b[0],q_nm_per_a=b[1],dq_nm_per_a2=b[2] if len(b)>2 else np.nan,
                    rmse_nm=np.sqrt(np.mean(residual**2)),mae_nm=np.mean(np.abs(residual)),
                    max_abs_residual_nm=np.max(np.abs(residual))))
    write_table(a.out,'torque-grid-cross-speed-models.csv',pd.DataFrame(fits))


if __name__=='__main__':
    main()
