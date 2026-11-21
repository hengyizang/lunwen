"""Collapse repeated link rows and cross-check decoded FlockLab strobe masks against serial logs.

Usage: python derive_flocklab.py RAW OUT
RAW contains the 9 *_preprocessed_all.zip and two 2020-03_raw_*.zip listed in the receipt.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
from pathlib import Path
import re
from zipfile import ZipFile


def write(path, items):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=items[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(items)


def load_csv(z, name):
    with z.open(name) as binary, io.TextIOWrapper(binary, encoding='utf-8') as f:
        rows = csv.reader(f)
        names = next(rows)
        assert names[-4:] == ['snd_id','rcv_id','rcv_total','rcv_stream']
        for cells in rows:
            # Writer strips failed-source fields with a regex. Its line can have only 10 fields.
            size=len(cells)
            if len(cells) == 10 and cells[-1] == '':
                cells.append('')
            yield cells,size


def decoded(value):
    count, stream = value[:2]
    if not stream or not count:
        return None
    if len(stream) != 100 or set(stream) - {'0','1'} or int(count) != stream.count('1'):
        return None
    return stream


def collect(raw, output):
    stats, march_and_nov = [], {}
    for file in sorted(raw.glob('????-??_preprocessed_all.zip')):
        month = file.name[:7]
        with ZipFile(file) as archive:
            for name in sorted(n for n in archive.namelist() if n.endswith('.csv')):
                board = Path(name).stem.split('FlockLab_')[-1]
                totals = Counter()
                tests = defaultdict(dict)
                metadata = {}
                dates = {}
                truncated=defaultdict(set)
                truncated_count=Counter()
                for row,nfields in load_csv(archive, name):
                    test=row[1]
                    dates[test]=row[0]
                    if test not in tests:tests[test]={}
                    totals[test]+=1
                    if len(row)!=11 or not row[7] or not row[8]:
                        truncated[test].add(tuple(row))
                        truncated_count[test]+=1
                        continue
                    date, test, channel, power, payload, host, seed, tx, rx, count, stream = row
                    config = (date,channel,power,payload,host,seed)
                    if metadata.setdefault(test, config) != config:
                        raise ValueError('Multiple configurations for one test')
                    # Source/receiver are kept as published; IDs validated numerically.
                    pair = int(tx), int(rx)
                    values = tests[test].setdefault(pair, set())
                    values.add((count,stream,nfields))

                for test, links in sorted(tests.items(), key=lambda x:int(x[0])):
                    valid = {}
                    mixed = bad = only_missing = ambiguous = mismatch = 0
                    for pair, vals in links.items():
                        groups = {v for v in map(decoded, vals) if v is not None}
                        if len(groups)>1:
                            ambiguous += 1
                        elif groups:
                            valid[pair] = next(iter(groups))
                            mixed += any(v[:2] == ('','') for v in vals)
                        elif all(v[:2] == ('','') for v in vals):
                            only_missing += 1
                        else:
                            bad += 1
                        mismatch += sum(bool(c and s) and len(s)==100 and int(c)!=s.count('1') for c,s,_ in vals)
                    unique_rows = sum(map(len, links.values())) + len(truncated[test])
                    recv = sum(v.count('1') for v in valid.values())
                    zeros = sum(v == '0'*100 for v in valid.values())
                    ones = sum(v == '1'*100 for v in valid.values())
                    both = [(valid[(a,b)],valid[(b,a)]) for a,b in valid if a<b and (b,a) in valid]
                    rank = absdiff = 0
                    for ab,ba in both:
                        delta = abs(ab.count('1')-ba.count('1'))
                        rank += (delta>=50)
                        absdiff = max(absdiff,delta)
                    stats.append(dict(month_archive=month,platform=board,test=int(test),utc_test_date=dates[test],
                       source_rows=totals[test],unique_full_rows=unique_rows,duplicate_full_rows=totals[test]-unique_rows,
                       truncated_unidentifiable_rows=truncated_count[test],distinct_truncated_unidentifiable_rows=len(truncated[test]),
                       distinct_directed_slots=len(links),unique_valid_masks=len(valid),valid_plus_blank=mixed,
                       blank_only_slots=only_missing,ambiguous_valid_masks=ambiguous,other_unusable_slots=bad,
                       count_mask_mismatching_distinct_versions=mismatch,reported_receptions=recv,
                       waveform_positions=len(valid)*100,all_missed_slots=zeros,all_received_slots=ones,
                       bidirectional_pairs=len(both),pairs_abs_count_gap_ge_50=rank,max_abs_directional_gap=absdiff if both else ''))
                    if (month,board) in {('2020-03','dpp-cc430'),('2019-11','sky')}:
                        march_and_nov[board,int(test)] = valid
    write(output/'flocklab-link-coverage.csv',stats)
    return march_and_nov


def nested_source(z, registry):
    rows = []
    while len(z.namelist()) == 1:
        filename, = z.namelist()
        data = z.read(filename)
        digest = 'md5:'+hashlib.md5(data).hexdigest()
        assert digest == registry[filename]['checksum']
        rows.append((filename,len(data),digest))
        z = ZipFile(io.BytesIO(data))
    return z,rows


def raw_checks(raw, output, clean):
    import json
    files = {x['key']:x for x in json.loads((raw/'3731498.json').read_bytes())['files']}
    results, containers = [], []
    for board in ('dpp-cc430','sky'):
        source = f'2020-03_raw_{board}.zip'
        with ZipFile(raw/source) as outer:
            z, levels = nested_source(outer,files)
            actual = sorted(n for n in z.namelist() if n.endswith('/serial.csv'))
            containers.append(dict(file=source,nested_sequence='|'.join(x[0] for x in levels),
                nested_sizes='|'.join(str(x[1]) for x in levels),nested_registry_md5='|'.join(x[2] for x in levels),
                actual_dates='|'.join(sorted({n.split('/')[1] for n in actual})),serial_files=len(actual)))
            for member in actual:
                prefix = member.rsplit('/',1)[0]
                test = int(prefix.rsplit('/',1)[1])
                serial = z.read(member)
                send = set()
                stamp = defaultdict(set)
                labels = defaultdict(set)
                for line in serial.decode('utf-8','replace').splitlines():
                    parts = line.split(',',4)
                    if len(parts)!=5: continue
                    when, _, dest, _, txt = parts
                    if not txt.startswith('Log:'): continue
                    match = re.fullmatch(r'Log:(\d+):Strobing',txt)
                    if match:
                        if int(match[1]) == int(dest):
                            send.add(int(dest))
                        continue
                    match = re.fullmatch(r'Log:(\d+):(\d+):([0-9.]+)',txt)
                    if match:
                        bitmask=''.join(format(int(k),'08b') for k in match[3].rstrip('.').split('.'))[:100]
                        key = int(match[1]),int(dest)
                        mask = decoded((match[2],bitmask))
                        if mask is not None:
                            labels[key].add(mask)
                            stamp[dest,when].add(key)
                valid = clean.get((board,test),{})
                agree = sum(any(v==m for m in labels[p]) for p,v in valid.items() if p in labels)
                confirmed = sum(any(v==m for m in labels[p]) and p[0] in send for p,v in valid.items() if p in labels)
                both = set(valid)&set(labels)
                results.append(dict(platform=board,test=test,serial_member=member,
                    serial_sha256=hashlib.sha256(serial).hexdigest(),preprocessed_test_in_month=int((board,test) in clean),
                    sender_nodes_logging_strobing=len(send),raw_reported_slots=len(labels),
                    processed_unique_valid=len(valid),slots_paired=len(both),mask_agreement=agree,
                    mask_agreement_sender_self_report=confirmed,
                    processed_mask_only=len(set(valid)-set(labels)),raw_report_only=len(set(labels)-set(valid)),
                    distinct_receiver_serial_timestamps=len(stamp),max_distinct_slot_reports_same_receiver_timestamp=max(map(len,stamp.values()),default=0)))
            if z is not outer:z.close()
    write(output/'flocklab-serial-pairing.csv',results)
    write(output/'flocklab-raw-containers.csv',containers)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    clean=collect(args.raw,args.output)
    raw_checks(args.raw,args.output,clean)


if __name__=='__main__':
    main()
