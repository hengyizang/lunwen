// Node 18+. Run: node derive-grasp.mjs OUT [LOCAL_MAGNUS_HAND_REPO]
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const base = 'https://raw.githubusercontent.com/tomasBGC/magnus-hand/ebc230abaeb7add5af39e6a18e0e0819ee12d6ea/';
const inputs = [
  {
    "path": "data/load_cell_dataset.csv",
    "sha": "0de939a80af87a2cfa0425d046eae33234f80d6f"
  },
  {
    "path": "data/closed_loop/slip_detection_live_verification.json",
    "sha": "86d8acd71dda6c81e0aba1f741a7f3111e80e45d"
  },
  {
    "path": "data/closed_loop/eflesh_test_20260908T121329Z grasp test.csv",
    "sha": "5e7b0f04462f73877ddbe1618a0e6bbedccc8e20"
  },
  {
    "path": "data/closed_loop/eflesh_test_20260908T121329Z grasp test_meta.json",
    "sha": "71485f2868cc071105b28afe19fc90a6f0a63617"
  }
];

function summarizeGrasp(loadTable, julyText, septemberText, metadataText) {
  function csv(text) {
    const lines = text.trim().split(/\r?\n/);
    const keys = lines.shift().split(',');
    return lines.map((line) => {
      const cells = line.split(',');
      if (cells.length !== keys.length) throw new Error('Unexpected CSV layout');
      return Object.fromEntries(keys.map((key, i) => [key, cells[i]]));
    });
  }
  const levels = ['control', 'light', 'medium', 'firm'];
  const fingers = ['Index', 'Middle', 'Ring', 'Thumb'];
  const quantitative = csv(loadTable);
  const groups = [['finger', 'level', 'ticks', 'rep_files', 'scenarios', 'contact_1', 'force_ge_1N', 'label_mismatches_at_0_3N', 'min_force_N', 'median_force_N', 'max_force_N']];
  for (const finger of ['ALL', ...fingers]) {
    for (const level of levels) {
      const sub = quantitative.filter((x) => (finger === 'ALL' || x.finger === finger) && x.level === level);
      if (!sub.length) continue;
      const forces = sub.map((x) => Number(x.Force)).sort((a,b) => a-b);
      if (!forces.every(Number.isFinite)) throw new Error('Invalid force');
      const mid = Math.floor(forces.length / 2);
      const median = forces.length % 2 ? forces[mid] : (forces[mid-1] + forces[mid]) / 2;
      groups.push([finger, level, sub.length, new Set(sub.map((x) => x.source_file)).size,
                   new Set(sub.map((x) => x.scenario)).size, sub.filter((x) => x.Contact === '1').length,
                   forces.filter((f) => f >= 1).length, sub.filter((x) => Number(x.Contact) !== Number(Number(x.Force) >= 0.3)).length,
                   forces[0].toFixed(6), median.toFixed(6), forces.at(-1).toFixed(6)]);
    }
  }
  const july = JSON.parse(julyText);
  const september = csv(septemberText);
  const metadata = JSON.parse(metadataText);
  if (metadata.n_ticks !== september.length) throw new Error('Metadata length mismatch');
  const live = [['session', 'phase', 'finger', 'ticks', 'contact_true', 'slip_event_true', 'no_contact_zero_gated_force_raw_above_0_3N',
                 'no_contact_nonzero_gated', 'max_raw_model_N', 'max_gated_model_N', 'max_reported_position_pct']];
  const summarizeFinger = (session, phase, finger, values) => {
    live.push([session, phase, finger, values.length, values.filter((v) => v.contact).length,
               values.filter((v) => v.slip_event).length,
               values.filter((v) => !v.contact && v.force === 0 && v.raw_force > 0.3).length,
               values.filter((v) => !v.contact && v.force !== 0).length,
               Math.max(...values.map((v) => v.raw_force)).toFixed(6),
               Math.max(...values.map((v) => v.force)).toFixed(6),
               values[0].position === undefined ? '' : Math.max(...values.map((v) => v.position))]);
  };
  for (const finger of fingers) {
    for (const phase of ['all', 'grip', 'hold']) {
      const values = july.events.filter((x) => phase === 'all' || x.phase === phase).map((x) => x.results[finger]);
      summarizeFinger('2026-07-21', phase, finger, values);
    }
    const vals = september.map((x) => ({
      force: Number(x[finger+'_force']), raw_force: Number(x[finger+'_raw_force']),
      contact: x[finger+'_contact'] === 'True', slip_event: x[finger+'_slip_event'] === 'True',
      position: Number(x[finger+'_position_pct'])
    }));
    summarizeFinger('2026-09-08', 'all', finger, vals);
  }
  const septCounts = live.slice(1).filter((r) => r[0] === '2026-09-08').reduce((s,r) => s+r[5],0);
  const julyCounts = live.slice(1).filter((r) => r[0] === '2026-07-21' && r[1] === 'all').reduce((s,r) => s+r[5],0);
  if (septCounts !== metadata.n_slip_events || julyCounts !== july.n_slip_events) throw new Error('Event count mismatch');
  const encode = (rows) => rows.map((r) => r.join(',')).join('\n') + '\n';
  return {'grasp-loadcell-support.csv':encode(groups), 'grasp-live-feedback.csv':encode(live)};
}

const [out, local] = process.argv.slice(2);
if (!out) throw new Error('Usage: node derive-grasp.mjs OUT [LOCAL_MAGNUS_HAND_REPO]');
const source = [];
for (const file of inputs) {
  let data;
  if (local) {
    data = await readFile(join(local,file.path));
  } else {
    const response = await fetch(base + file.path.split('/').map(encodeURIComponent).join('/'));
    if (!response.ok) throw new Error('Source fetch failed: ' + file.path +' '+ response.status);
    data = Buffer.from(await response.arrayBuffer());
  }
  const id = createHash('sha1').update('blob ' + data.length + '\0').update(data).digest('hex');
  if (id !== file.sha) throw new Error('Unexpected Git blob: ' + file.path);
  source.push(data.toString('utf8'));
}
await mkdir(out, {recursive:true});
for (const [name, data] of Object.entries(summarizeGrasp(...source))) {
  await writeFile(join(out,name), data);
}
