"""Read the NIST V2 archive and annotate the optical features, without discarding rows."""
import argparse
import csv
import hashlib
import io
import math
import statistics
import zipfile
from pathlib import Path


def run(zip_path, output):
    if hashlib.sha256(zip_path.read_bytes()).hexdigest() != '88fde686d77ad8af9b67838a74c8c3ea1b7dda57c81deb16a521b81716d84def':
        raise ValueError('Unexpected NIST archive')
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive, (output/'nist-26-runs.csv').open('w',newline='') as table:
        if archive.testzip() is not None:
            raise ValueError('Archive CRC failure')
        labels = csv.DictReader(io.StringIO(archive.read('Dataset/meta_data.csv').decode()), delimiter='\t')
        files = set(n for n in archive.namelist() if '/outintf_' in n)
        seen = set()
        wr = csv.writer(table,lineterminator='\n')
        wr.writerow(['csv_member','metadata_file_as_written','metadata_mapping','collection_date','wireless_mode',
                     'node','sir_condition','run_index','rows','cycle_index_resets_or_repeats','nonpositive_total_s',
                     'zero_touchdown_mm','negative_touchdown_n','median_negative_touchdown_mm','valid_positive_total_n',
                     'median_positive_total_s','max_bottom_dwell_s','max_high_wait_s','member_sha256'])
        for row in labels:
            group = row['Folder'][-3:]
            source = row['File Name']
            actual, how = source,'exact'
            if group == '001' and source == 'outintf_Inf_1.csv' and row['Run Index']=='2':
                actual,how = 'outintf_Inf_2.csv','reconciled redundant metadata name by run index and actual member'
            if group == '003' and source == 'outintf_Inf_1.csv':
                actual,how = 'outintf_inf_01.csv','reconciled case and zero-padding'
            member = 'Dataset/'+group+'/'+actual
            assert member in files and member not in seen
            seen.add(member)
            blob = archive.read(member)
            records = list(csv.reader(io.StringIO(blob.decode())))
            assert records[0]==['Cycle number','Delta t(high)','Delta t(plunge)','Touch down position (mm)','Delta t(Bottom)','Total cycle time']
            numeric=[list(map(float,r)) for r in records[1:]]
            assert all(len(r)==6 and all(map(math.isfinite,r)) for r in numeric)
            cycles,high,_,touch,bottom,total=zip(*numeric)
            depths=[v for v in touch if v<0]
            positive=[v for v in total if v>0]
            assert depths and positive
            wr.writerow([member,source,how,row['Date Collected'],row['Data Modulation Mode'],row['Impacted Node'],
                         row['SIR Value (dB)'],row['Run Index'],len(numeric),
                         sum(a>=b for a,b in zip(cycles,cycles[1:])),sum(t<=0 for t in total),sum(t==0 for t in touch),
                         len(depths),round(statistics.median(depths),5),len(positive),round(statistics.median(positive),6),
                         max(bottom),max(high),hashlib.sha256(blob).hexdigest()])
        assert seen==files and len(files)==26


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('output',type=Path)
    opts=p.parse_args()
    run(opts.archive,opts.output)
