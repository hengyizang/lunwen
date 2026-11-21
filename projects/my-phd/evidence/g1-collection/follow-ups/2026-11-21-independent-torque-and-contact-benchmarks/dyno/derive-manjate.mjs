// Recompute the four CSV summaries with Node 18+.
// Usage: node derive-manjate.mjs OUT [LOCAL_DASHBOARD_DIRECTORY]
// Without LOCAL_DASHBOARD_DIRECTORY, fetch both fixed-version reports.
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const base = 'https://raw.githubusercontent.com/ItsMeAech/pmsm-foc-fec-dynamometer/361663949df83a58f5a65bb132a995604912df3b/dashboards/';
const inputs = [
  ['foc_vs_fec_merged_dashboard.html','1c2a862b1c41ec7a77e0b400d01d365e3f273022'],
  ['fec_test_dashboard.html','ac427f61862493a1e6d03598bd05e89b4e732535']
];

function summarize(mergedText, singleText) {
  function embedded(html, name) {
    const line = html.split('\n').find((row) => row.startsWith('const ' + name + ' = {'));
    if (!line || !line.endsWith(';')) throw new Error('Missing dashboard object ' + name);
    return JSON.parse(line.slice(('const ' + name + ' = ').length, -1));
  }
  const fec = embedded(mergedText, 'D');
  const foc = embedded(mergedText, 'F');
  if (JSON.stringify(fec) !== JSON.stringify(embedded(singleText, 'D'))) {
    throw new Error('FEC object differs across reports');
  }
  const steady = [['slots', 'complete_numeric_rows', 'all_fields_null', 'partial_rows', 'first_time_s', 'last_time_s', 'min_thrust_g', 'max_thrust_g']];
  const series = fec.steady;
  const channels = ['t', 'pwm', 'rpm', 'thr', 'cur'];
  if (!channels.every((key) => series[key].length === series.t.length)) throw new Error('Unequal steady lengths');
  const complete = series.t.map((_, i) => channels.map((key) => series[key][i])).filter((r) => r.every(Number.isFinite));
  const nulls = series.t.filter((_, i) => channels.every((key) => series[key][i] === null)).length;
  const thrust = complete.map((r) => r[3]);
  steady.push([series.t.length, complete.length, nulls, series.t.length - complete.length - nulls, complete[0][0], complete.at(-1)[0], Math.min(...thrust), Math.max(...thrust)]);
  const trials = [['drive', 'step_from_pct', 'step_to_pct', 'repetition', 'electrical_samples', 'displayed_force_samples', 'min_bus_V', 'max_bus_A', 'below_12V_count', 'min_displayed_force_g', 'max_displayed_force_g']];
  const groups = [['drive', 'step_from_pct', 'step_to_pct', 'repetitions', 'electrical_samples', 'displayed_force_samples', 'min_bus_V', 'max_bus_A', 'below_12V_count']];
  const sweeps = [['drive', 'author_sweep', 'plateaus', 'finite_efficiency_plateaus', 'lowest_command_pct', 'highest_command_pct', 'highest_command_thrust_g']];
  for (const [drive, data] of [['FEC', fec], ['FOC', foc]]) {
    for (const s of data.eff) {
      if (![s.thr, s.gpw, s.rpm].every((a) => a.length === s.pwm.length)) throw new Error('Unequal sweep arrays');
      const hi = Math.max(...s.pwm);
      sweeps.push([drive, s.name, s.pwm.length, s.gpw.filter(Number.isFinite).length, Math.min(...s.pwm), hi, s.thr[s.pwm.indexOf(hi)]]);
    }
    for (const [step, reps] of Object.entries(data.trans)) {
      let nb = 0, nf = 0, low = 0, vmin = Infinity, imax = -Infinity;
      for (const s of reps) {
        if (![s.rpm, s.volt, s.cur].every((a) => a.length === s.bms.length && a.every(Number.isFinite)) ||
            s.thr.length !== s.thr_t.length || !s.thr.every(Number.isFinite)) throw new Error('Malformed trial');
        const mv = Math.min(...s.volt), mc = Math.max(...s.cur);
        const below = s.volt.filter((v) => v < 12).length;
        trials.push([drive, 20, step, s.rep, s.bms.length, s.thr_t.length, mv, mc, below, Math.min(...s.thr), Math.max(...s.thr)]);
        nb += s.bms.length;
        nf += s.thr_t.length;
        low += below;
        vmin = Math.min(mv, vmin);
        imax = Math.max(mc, imax);
      }
      groups.push([drive, 20, step, reps.length, nb, nf, vmin, imax, low]);
    }
  }
  const encode = (rows) => rows.map((r) => r.join(',')).join('\n') + '\n';
  return {'manjate-steady.csv': encode(steady), 'manjate-sweeps.csv': encode(sweeps),
          'manjate-trials.csv': encode(trials), 'manjate-step-groups.csv': encode(groups)};
}

const [outputDir, localDir] = process.argv.slice(2);
if (!outputDir) throw new Error('Usage: node derive-manjate.mjs OUT [LOCAL_DASHBOARD_DIRECTORY]');
const reports = [];
for (const [file, expected] of inputs) {
  let bytes;
  if (localDir) {
    bytes = await readFile(join(localDir, file));
  } else {
    const response = await fetch(base + file);
    if (!response.ok) throw new Error('Failed to fetch ' + file + ': HTTP ' + response.status);
    bytes = Buffer.from(await response.arrayBuffer());
  }
  const hash = createHash('sha1').update('blob ' + bytes.length + '\0').update(bytes).digest('hex');
  if (hash !== expected) throw new Error('Source Git object mismatch in ' + file);
  reports.push(bytes.toString('utf8'));
}
await mkdir(outputDir, {recursive:true});
for (const [file, body] of Object.entries(summarize(...reports))) {
  await writeFile(join(outputDir,file), body);
}
