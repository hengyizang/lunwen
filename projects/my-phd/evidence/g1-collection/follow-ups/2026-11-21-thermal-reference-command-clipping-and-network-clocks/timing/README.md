# R5 clock evidence for mobile communication and a wired hardware reference

## Porto vehicle-to-infrastructure 60 GHz radio

The two campaigns use a fixed access point, one moving vehicle with a client and colocated monitoring radio, and NTP over a separate control network. The archive supports checking GPS time against recorder time and revisiting communication observations during motion. Packet captures contain one observer's timestamps. Identifying radio propagation or an independently calibrated per-packet one-way delay would require corresponding endpoint observations. [Data record](https://zenodo.org/records/7026551) · [Data paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9957741/)

- In 2020 all 4,941 GPRMC rows have identical recorded `timestamp` and `gpstime`. In 2021 all 10,012 GPRMC rows have `timestamp − gpstime` between 3,601 and 3,616 s; 9,568 equal 3,601 s. These are raw field differences for the same sentence. Their cause and a clock correction cannot be inferred by subtracting one hour. GNGSA lacks its own UTC time field and the export includes one row labeled `c`; the per-sentence table preserves both labels.
- The application exports contain 12,827 rows in 36 traces. Exactly one of 747 positive packet-count bins in the 2021 export has a negative mean local timestamp difference (−128.535993 µs). Rows matching an available GPRMC integer second are simple membership tests over that campaign. Multiple rows can match a second, and no identity match is implied between a radio packet and a motion record.
- The archive contains 38 radiotap pcaps with 28,507,500 complete frames. In 2021 traces 300 and 407 each have 14 trailing bytes, insufficient for a further 16-byte packet header. For the first 1,000 CSV-exported observations per year, `trace_nr` and frame number identify matching raw headers. All 2,000 wire lengths matched; 686 exported timestamps differed at the nanosecond level, by at most 300 ns, within half a raw timestamp tick. Distinct pcap and throughput trace counts arise because the archive offers different sets of members for these products.

## SLATE-PTP switched-network reference

This wired testbed has a GNSS grandmaster, an external 1 PPS reference for the follower's hardware clock, hardware timestamps, and a PTP-unaware switched fabric under controlled traffic. The authors report an independently referenced bound of ±20 ns. The deposit supplies packet exchanges with recorded clock differences; it supplies no independent per-packet external 1 PPS offset series or motion data. [Data record](https://zenodo.org/records/21770838) · [Data paper, Table 2 and §§3–4](https://pmc.ncbi.nlm.nih.gov/articles/PMC13562064/)

- Across 45 files, 356,353 `sync` rows contain `t1,t2` and 356,328 `delay_req` rows contain `t3,t4`. No row contains all four fields. Within each file the record sequence increments by one and `capture_ts` never moves backward. Forward and reverse columns use integer-nanosecond differences across clocks. The half difference of their two file-level medians describes directional asymmetry plus residual offset. It does not pair simultaneous events.
- The deposit notebook's `_safe_int` converts integer-looking Unix epoch nanosecond strings through binary64. This conversion alters 1,372,636 of 1,425,362 nonempty timing values, by up to 128 ns each. Every one of the 712,681 individual directional subtractions changes. Replaying the notebook's baseline sequential update equations on both representations changes 350,483 of 356,293 eligible offset estimates; 291,763 change by more than 20 ns and the maximum change is 495 ns. For M1-L0 the RMS estimated offset is 27.933082 ns with integer parsing and 103.225577 ns with notebook parsing. These numbers quantify differences in the replay calculation. They do not measure a physical change in the clocks, and they do not establish what parser was used for results in other publications.
- The update computes mean path delay on a reverse message using the last forward observation, then estimates offset at a later forward observation using that delay. `last_delay_update_to_sync` measures this age from the logging clock. The reported 95th percentiles use nearest rank.

## Attribution and replay

`sources.json` gives the individual authors, version DOIs, publisher MD5s, download links and CC BY 4.0 licenses. The five measurement tables are independent derived summaries. They reproduce no radio payload or complete upstream data file. Inspected publication versions, evidence grades, locators and citation relations are in `literature.csv` and `citation-edges.csv`.

Run from this directory with Python 3.11 or later and the ZIP files obtained from the two versioned releases.

```sh
python check_porto.py v2i-80211ad-dataset.zip output
python check_slate.py SLATE-PTP.zip output
```
