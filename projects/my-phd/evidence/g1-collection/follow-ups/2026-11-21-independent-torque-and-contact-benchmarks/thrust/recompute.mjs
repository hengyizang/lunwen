/** Recompute original bench summaries. Usage: node recompute.mjs OUTPUT [CACHE] */
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const home = fileURLToPath(new URL('.', import.meta.url));
const outputDir = resolve(process.argv[2] || 'recomputed');
const cacheDir = resolve(process.argv[3] || 'bench-cache');
await mkdir(outputDir, {recursive:true});
await mkdir(cacheDir, {recursive:true});

function checkBlob(bytes, entry) {
  const hash=createHash('sha1').update('blob '+bytes.length+'\0').update(bytes).digest('hex');
  if(hash!==entry.git_blob || bytes.length!==entry.bytes) throw Error('Source digest mismatch: '+entry.path);
}
async function loadInput(source, entry) {
  const dest=join(cacheDir,entry.git_blob);
  let bytes;
  try {bytes=await readFile(dest);} catch(e) {if(e.code!=='ENOENT')throw e;}
  if(!bytes){
    const encoded=entry.path.split('/').map(encodeURIComponent).join('/');
    const url='https://raw.githubusercontent.com/'+source.repository+'/'+source.commit+'/'+encoded;
    const response=await fetch(url);
    if(!response.ok)throw Error(response.status+' '+url);
    bytes=Buffer.from(await response.arrayBuffer());
    checkBlob(bytes,entry);
    await writeFile(dest,bytes);
  }
  checkBlob(bytes,entry);
  try{return new TextDecoder('utf-8',{fatal:true}).decode(bytes);}
  catch{return new TextDecoder('windows-1252').decode(bytes);}
}

function calculate(sources, files) {
  const output = {};
  function emit(table, row) {
    if (!output[table]) output[table] = [];
    output[table].push(row);
  }
  function numericCsv(content) {
    const lines = content.trim().replace(/^\uFEFF/, '').split(/\r\n|\r|\n/).filter(x => x.trim());
    const sep = lines[0].includes(';') ? ';' : ',';
    const names = lines[0].split(sep).map(s => s.trim());
    const rows = lines.slice(1).map(line => line.split(sep).map(s => s.trim()==='' ? NaN : Number(s)));
    return { names, rows, sep };
  }
  function close(a,b) {
    return Math.abs(a-b) < 1e-5*Math.max(1,Math.abs(a),Math.abs(b));
  }
  function fixed(x) {
    return Number.isFinite(x) ? x.toFixed(9) : '';
  }
  const ca=sources.find(s=>s.id==='cao-strawson');
  for (const raw of ca.files.filter(x=>x.path.startsWith('rawdata/'))) {
    const name=raw.path.split('/').pop();
    const edit=ca.files.find(x=>x.path==='modifieddata/'+name);
    const a=numericCsv(files.get(raw.git_blob)).rows;
    const b=numericCsv(files.get(edit.git_blob)).rows;
    if (a.length!==11||b.length!==11||!a.every((r,i)=>r[1]===b[i][1] && (i===0||r[1]>a[i-1][1]))) throw Error(name);
    const peak=a.findIndex(row=>row[5]===Math.max(...a.map(r=>r[5])));
    let changed=0, copied=0, rawEqual=0, modEqual=0, rawDecreases=0;
    for (let i=0;i<a.length;i++) {
      if (!close(a[i][5],b[i][5])) {
        changed++;
        if (i>peak && [5,6,7,8,9,10,11].every(k=>close(b[i][k],a[peak][k]))) copied++;
      }
      if (i) {
        rawEqual+=Number(a[i][5]===a[i-1][5]);
        modEqual+=Number(b[i][5]===b[i-1][5]);
        rawDecreases+=Number(a[i][5]<a[i-1][5]);
      }
    }
    emit('cao-strawson-edits.csv',{
      file:name,raw_blob:raw.git_blob,edited_blob:edit.git_blob,rows:a.length,supply_group_V:name.endsWith('_7.csv')?'7.4':'11.1',
      min_ESC_us:a[0][1],max_ESC_us:a.at(-1)[1],optical_nonzero_rows:a.filter(r=>r[9]!==0).length,
      changed_thrust_rows:changed,full_peak_vector_copies:copied,raw_equal_adjacent_thrust:rawEqual,edited_equal_adjacent_thrust:modEqual,
      raw_decreasing_adjacent_thrust:rawDecreases,raw_peak_gf:fixed(a[peak][5]),raw_final_gf:fixed(a.at(-1)[5]),edited_minus_raw_final_gf:fixed(b.at(-1)[5]-a.at(-1)[5])
    });
  }
  for (const s of sources.filter(s=>['stanford','quanser','aerostack','gestelt'].includes(s.id))) {
    const tables=new Map();
    for (const f of s.files.filter(o=>o.path.endsWith('.csv'))) {
      if(s.id==='stanford'&&!f.path.includes('/thrust_stand/')) continue;
      const t=numericCsv(files.get(f.git_blob));
      function position(prefix){return t.names.findIndex(x=>x.startsWith(prefix));}
      const idx=['ESC signal (','Torque (','Thrust (','Voltage (','Current (','Motor Electrical Speed (','Motor Optical Speed (','Time ('].map(position);
      const name=f.path.split('/').pop();
      const v=t.rows.map(row=>idx.map(i=>i<0?NaN:row[i]));
      const common=v.filter(row=>row.slice(0,5).every(Number.isFinite));
      if(common.length!==v.length) throw Error('Incomplete first five numeric columns '+f.path);
      const col=j=>v.map(r=>r[j]).filter(Number.isFinite);
      const range=j=>{const vals=col(j);return vals.length?[fixed(Math.min(...vals)),fixed(Math.max(...vals))]:['',''];};
      const [pwmMin,pwmMax]=range(0),[torqueMin,torqueMax]=range(1),[thrustMin,thrustMax]=range(2);
      let nonincreasingTime=0;
      for(let i=1;i<v.length;i++) if(Number.isFinite(v[i][7])&&v[i][7]<=v[i-1][7])nonincreasingTime++;
      const role=s.id==='aerostack'&&name.includes('-TM-')?'six-column map input':s.id==='gestelt'?'source-labelled processed table':'logged capture';
      emit('bench-traces.csv',{
        source:s.id,file:name,git_blob:f.git_blob,role,delimiter:t.sep===';'?'semicolon':'comma',rows:v.length,common_rows:common.length,
        min_ESC_us:pwmMin,max_ESC_us:pwmMax,min_signed_torque_Nm:torqueMin,max_signed_torque_Nm:torqueMax,
        thrust_unit:t.names[idx[2]]==='Thrust (kgf)'?'kgf':'N',min_signed_thrust:thrustMin,max_signed_thrust:thrustMax,
        timed_rows:col(7).length,nonincreasing_adjacent_times:nonincreasingTime,electrical_speed_present:col(5).length,
        nonzero_electrical_speed:col(5).filter(x=>x!==0).length,optical_speed_present:col(6).length,
        positive_optical_speed:col(6).filter(x=>x>0).length,negative_optical_speed:col(6).filter(x=>x<0).length,
        source_default_filter_rows:s.id==='aerostack'?v.filter(r=>r[3]>20.4&&r[3]<25.2&&r[0]>1300&&r[0]<1500&&-r[2]>0&&-r[2]<11).length:''
      });
      tables.set(name,v);
    }
    if(s.id==='aerostack') {
      // Match six reported channels. Multiset intersection preserves repeated rows.
      function signature(row) {return row.slice(0,6).map(n=>Math.round(n*1e5)).join('/');}
      for(const mode of ['MR','SR']){
        const combined=tables.get('xNova-TM-'+mode+'.csv');
        const remaining=new Map();
        for(const row of combined){const key=signature(row);remaining.set(key,(remaining.get(key)||0)+1);}
        for(const [file,rows] of tables){
          if(!file.startsWith('xNova-'+mode+'-'))continue;
          let count=0;
          for(const row of rows){
            const key=signature(row);
            if(remaining.get(key)>0){count++;remaining.set(key,remaining.get(key)-1);}
          }
          emit('map-input-overlap.csv',{fixture:mode,timed_file:file,timed_rows:rows.length,combined_rows:combined.length,
            multiset_intersection_rows:count,does_source_default_comma_reader_parse_combined:mode==='MR'});
        }
      }
    }
    if(s.id==='quanser'){
      const vv=[...tables.values()][0];
      if(vv.length!==42)throw Error('Unexpected Cobra record length');
      for(let i=0;i<21;i++){
        const a=vv[i],b=vv[i+21];
        if(a[0]!==b[0])throw Error('Mismatched repeated sweep command');
        emit('repeated-pulse.csv',{ESC_us:a[0],first_t_s:fixed(a[7]),second_t_s:fixed(b[7]),second_minus_first_signed_thrust_N:fixed(b[2]-a[2]),
          second_minus_first_torque_Nm:fixed(b[1]-a[1]),second_minus_first_voltage_V:fixed(b[3]-a[3]),second_minus_first_current_A:fixed(b[4]-a[4])});
      }
    }
    if(s.id==='gestelt'){
      for(const [before,after] of [
        ['18_9_23_flywoo_nin1404_bench_test_cleaned.csv','18_9_23_flywoo_nin1404_bench_test_cleaned_wo_top_vals.csv'],
        ['nuswarm_9_12_consolidated.csv','nuswarm_9_12_consolidated_clean.csv']
      ]){
        const a=tables.get(before),b=tables.get(after);
        const exact=a.slice(0,b.length).filter((row,i)=>row.slice(0,7).every((v,k)=>Object.is(v,b[i][k]))).length;
        emit('trimmed-rows.csv',{parent:before,trimmed:after,parent_rows:a.length,trimmed_rows:b.length,
          exact_prefix_rows_command_torque_thrust_voltage_current_and_both_speed_fields:exact,
          parent_last_ESC_us:a.at(-1)[0],trimmed_last_ESC_us:b.at(-1)[0],parent_last_optical_rpm:a.at(-1)[6]});
      }
    }
  }
  const bit=sources.find(s=>s.id==='bitcraze');
  const doc=bit.files.find(f=>f.path.endsWith('pwm-to-thrust.md'));
  const numeric=files.get(doc.git_blob).split(/\r?\n/).filter(l=>/^\|\s*\d/.test(l)).map(l=>l.split('|').slice(1,-1).map(Number));
  if(numeric.length!==16)throw Error('Unexpected Bitcraze table format');
  const irreg=numeric.filter((x,i)=>Math.abs(x[3]-6.25*i)>1e-6);
  emit('legacy-sweep.csv',{source:'bitcraze',numeric_rows:numeric.length,manual_reading_step_seconds:4,
    first_thrust_g:numeric[0][1],last_thrust_g:numeric.at(-1)[1],supply_drop_V:fixed(numeric[0][2]-numeric.at(-1)[2]),
    first_current_A:numeric[0][0],last_current_A:numeric.at(-1)[0],last_logged_pwm_pct:numeric.at(-1)[3],
    rows_off_nominal_6p25_pct_grid:irreg.length,logged_off_grid_pwm_pct:irreg.map(v=>v[3]).join('|')});
  return output;
}

function csvText(rows) {
  const fields=Object.keys(rows[0]);
  function cell(value) {
    const str=String(value);
    return /[",\r\n]/.test(str) ? '"'+str.replaceAll('"','""')+'"' : str;
  }
  const lines=[fields.join(',')];
  for(const row of rows) lines.push(fields.map(k=>cell(row[k])).join(','));
  return lines.join('\n')+'\n';
}

const manifest=JSON.parse(await readFile(join(home,'search.json'),'utf8'));
const sources=await Promise.all(manifest.sources.map(async id=>JSON.parse(await readFile(join(home,id+'-source.json'),'utf8'))));
const texts=new Map();
for(const source of sources){
  const required=source.files.filter(f=>f.path.endsWith('.csv') || (source.id==='bitcraze'&&f.path.endsWith('pwm-to-thrust.md')));
  for(const file of required){
    if(!texts.has(file.git_blob))texts.set(file.git_blob,await loadInput(source,file));
  }
}
for(const [name,rows] of Object.entries(calculate(sources,texts))){
  await writeFile(join(outputDir,name),csvText(rows),'utf8');
}
