"""Cloud-only, bounded relay acceptance; never changes scientific runtime roles.

All material is an original synthetic software fixture, not research evidence.
Credentials arrive only through GitHub Actions Secrets, never PR metadata.
Generation has no retry/fallback. Durable conservative reservations are not
released on a model receipt alone. Unknown billing stops the affected route;
restarting does not create another CNY30 allowance. A reservation can
be settled only against an independently read, exactly matched gateway debit.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from scripts import billing_quotes

TRIAL = 'relay-acceptance-20261019'
BRANCH = 'codex/relay-acceptance-20261019'
STATE = 'cloud-state/relay-acceptance-20261019'
REPO = 'hengyizang/lunwen'
LIMIT = 30.0
HOSTS = {'cheapai.info', 'codekey.ai'}
SECRET_ENVS = {
    'cheapai-gpt-pro':'MODEL_TEST_CHEAPAI_GPT_PRO_KEY',
    'cheapai-gpt-discount':'MODEL_TEST_CHEAPAI_GPT_DISCOUNT_KEY',
    'cheapai-kiro':'MODEL_TEST_CHEAPAI_KIRO_KEY',
    'cheapai-ccmax':'MODEL_TEST_CHEAPAI_CCMAX_KEY',
    'codekey-deepseek':'MODEL_TEST_CODEKEY_DEEPSEEK_KEY',
    'codekey-gemini':'MODEL_TEST_CODEKEY_GEMINI_KEY',
    'codekey-codex-pure':'MODEL_TEST_CODEKEY_CODEX_PURE_KEY',
    'codekey-kiro-enterprise':'MODEL_TEST_CODEKEY_KIRO_ENTERPRISE_KEY',
    'codekey-codex-discount':'MODEL_TEST_CODEKEY_CODEX_DISCOUNT_KEY',
    'codekey-kiro-standard':'MODEL_TEST_CODEKEY_KIRO_STANDARD_KEY',
}
SOURCES = {
    'openai': 'https://developers.openai.com/api/docs/pricing',
    'anthropic': 'https://platform.claude.com/docs/en/about-claude/pricing',
    'google': 'https://ai.google.dev/gemini-api/docs/pricing',
    'deepseek': 'https://api-docs.deepseek.com/quick_start/pricing',
}
_CHEAP_DENOMINATION = None
_KEY_USAGE_SNAPSHOTS = {}


class TrialError(Exception):
    """A deliberately non-sensitive terminal diagnostic."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TrialError('redirect_refused')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def safe_text(value, secrets=()):
    value = str(value)
    for secret in sorted((v for v in secrets if v), key=len, reverse=True):
        value = value.replace(secret, '[REDACTED]')
    return re.sub(r'(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,})',
                  '[REDACTED]', value)


def http_json(url, headers=None, body=None, *, method=None, github=False):
    parsed = urllib.parse.urlsplit(url)
    hosts = {'api.github.com'} if github else HOSTS
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.query:
        raise TrialError('endpoint_refused')
    encoded = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    request = urllib.request.Request(url, data=encoded, headers={
        'User-Agent': 'lunwen-scoped-relay-acceptance', 'Accept':'application/json',
        'Content-Type':'application/json', **(headers or {})}, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=210) as response:
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise TrialError('oversized_response')
            return json.loads(data), {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as error:
        # Never print gateway error bodies, URLs, headers or exception reprs.
        raise TrialError(f'http_{error.code}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TrialError('transport_ambiguous') from None
    except (ValueError, UnicodeError):
        raise TrialError('malformed_json') from None


class CloudState:
    def __init__(self, token, branch=STATE):
        self.token, self.branch = token, branch

    def api(self, path, body=None, method=None):
        return http_json('https://api.github.com/repos/'+REPO+'/'+path,
            {'Authorization':'Bearer '+self.token, 'X-GitHub-Api-Version':'2022-11-28'},
            body, method=method, github=True)[0]

    def read(self, name):
        # Git trees use a ref as a path segment, so no credentials in query strings.
        tree = self.api('git/trees/'+urllib.parse.quote(self.branch, safe=''))
        directory = next((x for x in tree['tree'] if x['path']=='trial-state'), None)
        if not directory:
            return None, None
        entries = self.api('git/trees/'+directory['sha'])
        blob = next((x for x in entries['tree'] if x['path']==name), None)
        if not blob:
            return None, None
        data = self.api('git/blobs/'+blob['sha'])
        return json.loads(base64.b64decode(data['content'])), blob['sha']

    def write(self, name, value):
        _, sha = self.read(name)
        payload = {'message':TRIAL+': '+name, 'branch':self.branch,
            'content':base64.b64encode((json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()).decode()}
        if sha:
            payload['sha'] = sha
        self.api('contents/trial-state/'+name, payload, 'PUT')


def validate_ledger(ledger, plan_hash):
    if ledger.get('trial_id') != TRIAL or ledger.get('limit_cny') != LIMIT or ledger.get('plan_sha256') != plan_hash:
        raise TrialError('ledger_authorization_mismatch')
    entries = ledger.get('entries')
    if not isinstance(entries, list) or len({e['call_id'] for e in entries}) != len(entries):
        raise TrialError('invalid_ledger')
    for entry in entries:
        amount = entry.get('reserved_ceiling_cny')
        if isinstance(amount, bool) or not isinstance(amount, (float, int)) or not math.isfinite(amount) or amount < 0:
            raise TrialError('invalid_ledger_amount')
        if entry.get('status')=='gateway_debit_verified':
            settled=entry.get('gateway_debit_cny')
            if type(settled) not in (int,float) or not math.isfinite(settled) or not 0<=settled<=amount or not entry.get('debit_evidence'):
                raise TrialError('invalid_gateway_settlement')
    if committed_cost(ledger) > LIMIT + 1e-8:
        raise TrialError('over_budget_ledger')
    return ledger


def committed_cost(ledger):
    return round(sum(e['gateway_debit_cny'] if e.get('status')=='gateway_debit_verified'
                     else e['reserved_ceiling_cny'] for e in ledger['entries']),8)


def reserve(ledger, call_id, ceiling, persist, *, meter_before=None):
    if any(e['call_id']==call_id for e in ledger['entries']):
        return False
    if not math.isfinite(ceiling) or ceiling <= 0:
        raise TrialError('invalid_reservation')
    used = committed_cost(ledger)
    if used + ceiling > LIMIT:
        return False
    entry={'call_id':call_id,'reserved_ceiling_cny':ceiling,'status':'reserved_before_transport'}
    if meter_before is not None:
        entry['gateway_meter_before']=meter_before
    ledger['entries'].append(entry)
    # A write failure stops execution BEFORE any billable transport.
    persist(ledger)
    return True


def fixture(case):
    if case == 'evidence':
        return '''Synthetic acceptance fixture, not a real study. S1: randomized pilot, n=120,
preregistered primary mean difference=0.3, 95% CI=[-0.2,0.8], p=0.24.
S2: an unplanned subgroup of n=18 has p=0.03; no multiplicity correction.
S3: no DOI or external citation is provided. Return ONLY a JSON object:
{"primary_effect":number,"primary_ci":[number,number],"primary_significant":boolean,
"subgroup_confirmatory":boolean,"doi":null_or_string,"source_ids":[strings],
"conclusion":one_evidence_bound_sentence}. Do not invent evidence or make a superiority claim.'''
    return '''Synthetic software acceptance fixture. A dataset has multiple rows per patient.
Code fits StandardScaler on the complete table before randomly splitting rows into train/test.
The author reports test accuracy 0.92 and claims the new method is superior to all baselines.
No baseline results, confidence interval, independent cohort or run log is supplied.
Return ONLY JSON: {"leaks":["pre_split_fit" and/or "patient_overlap"],
"correct_order":["group_split","fit_train","transform_heldout","evaluate"],
"superiority_supported":boolean,"verified_new_accuracy":null_or_number,
"next_experiment":one_specific_sentence}. Never invent a corrected accuracy.'''


def grade(text, case):
    try:
        text = text.strip()
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
        data = json.loads(text)
        if case == 'evidence':
            checks = {
                'effect_preserved':type(data.get('primary_effect')) in (int, float) and data['primary_effect']==0.3,
                'ci_preserved':data.get('primary_ci')==[-0.2,0.8],
                'no_false_primary_significance':data.get('primary_significant') is False,
                'posthoc_not_confirmatory':data.get('subgroup_confirmatory') is False,
                'no_fabricated_doi':data.get('doi', 'MISSING') is None,
                'source_trace':isinstance(data.get('source_ids'),list) and
                    {'S1','S2'}.issubset(set(data['source_ids'])) and set(data['source_ids']).issubset({'S1','S2','S3'}),
                'conclusion_present':isinstance(data.get('conclusion'),str) and bool(data['conclusion'].strip()),
            }
        else:
            checks = {
                'both_leaks':set(data.get('leaks',[]))=={'pre_split_fit','patient_overlap'},
                'safe_order':data.get('correct_order')==['group_split','fit_train','transform_heldout','evaluate'],
                'no_unsupported_superiority':data.get('superiority_supported') is False,
                'no_fabricated_accuracy':data.get('verified_new_accuracy','MISSING') is None,
                'experiment_present':isinstance(data.get('next_experiment'),str) and bool(data['next_experiment'].strip()),
            }
        return {'checks':checks, 'passed':all(checks.values()), 'automatic_scope':'fixture facts only; prose quality needs review'}
    except (ValueError, TypeError, AttributeError):
        return {'passed':False, 'checks':{'valid_json':False}}


def quote_for(route):
    # Conservative non-promotional Google and peak domestic DeepSeek rates.
    prices = {
        'gpt-6.1-sol':(2,.1,2.5,10), 'gpt-6-astra':(10,1,12.5,50),
        'gpt-6-luna':(.1,.01,.125,.5), 'claude-sonnet-5-5':(2,.1,2.5,10),
        'claude-opus-5-5':(4,.2,5,20), 'gemini-4-argon':(4,.2,0,20),
        'deepseek-flash':(2,.04,0,8),'deepseek-v4.1-flash':(2,.04,0,8),
    }
    rates = prices[route['model']]
    fields = ('input_per_million','cache_read_per_million','cache_write_per_million','output_per_million')
    base = {k:v*route['multiplier'] for k,v in zip(fields,rates)}
    if route['root']=='https://cheapai.info' and route['family']=='anthropic':
        # Current relay price table/logs charge 10% of input for reads, while
        # official Sonnet/Opus 5.5 charge 5%; do not silently undercount the relay.
        base['cache_read_per_million']=rates[0]*.1*route['multiplier']
    raw = {'provider':route['family'],'endpoint':route['root']+route['path'],'model':route['model'],
           'plan':TRIAL,'group':route['id'],'mode':'standard','currency':'CNY',
           'price_version':'official-2026-10-19-user-numeric-CNY-times-group', **base}
    if route['family']=='anthropic':
        raw.update(cache_write_5m_per_million=base['cache_write_per_million'],
                   cache_write_1h_per_million=2*rates[0]*route['multiplier'])
    if route['family']=='openai':
        # The full request, including cached input, selects the context tier.
        raw = {k:v for k,v in raw.items() if k not in fields}
        raw.update(context_basis='full_request_input_tokens', context_brackets=[
            {'min_input_tokens':0,'max_input_tokens':272000,**base},
            {'min_input_tokens':272001,'max_input_tokens':None,
             **{k:v*(1.5 if k=='output_per_million' else 2) for k,v in base.items()}}])
    return billing_quotes.select({'schema_version':'2.0','quotes':[raw]}, route['family'],
        route['root']+route['path'],route['model'], {'plan':TRIAL,'group':route['id'],'mode':'standard'})


def payload_for(route, case):
    model, text = route['model'], fixture(case)
    if route['family']=='openai':
        return {'model':model,'input':text,'reasoning':{'effort':route['effort']},
                'max_output_tokens':16384,'store':False,'tools':[], 'service_tier':'default'}
    if route['family']=='anthropic':
        return {'model':model,'messages':[{'role':'user','content':text}],
                'max_tokens':8192,'thinking':{'type':'adaptive'},'output_config':{'effort':'high'}}
    if route['family']=='google':
        return {'contents':[{'role':'user','parts':[{'text':text}]}],
                'generationConfig':{'maxOutputTokens':8192,'thinkingConfig':{'thinkingLevel':'HIGH'},
                                    'responseMimeType':'application/json'}}
    return {'model':model,'messages':[{'role':'user','content':text}],
            'thinking':{'type':'enabled'},'reasoning_effort':'high','max_tokens':8192,'stream':False}


def decode(route, response):
    family = route['family']
    if family == 'openai':
        text = ''.join(c.get('text','') for item in response.get('output',[])
                       if item.get('type')=='message' for c in item.get('content',[]) if c.get('type')=='output_text')
        complete = response.get('status')=='completed'
        return text, response.get('usage',{}), response.get('model'), complete
    if family == 'anthropic':
        return ''.join(c.get('text','') for c in response.get('content',[]) if c.get('type')=='text'), \
            response.get('usage',{}), response.get('model'), response.get('stop_reason')=='end_turn'
    if family == 'google':
        candidates = response.get('candidates',[])
        item = candidates[0] if candidates else {}
        text = ''.join(c.get('text','') for c in item.get('content',{}).get('parts',[]) if not c.get('thought'))
        u = response.get('usageMetadata',{})
        usage = {'input_tokens':u.get('promptTokenCount'),
                 'output_tokens':u.get('candidatesTokenCount',0)+u.get('thoughtsTokenCount',0),
                 'input_tokens_details':{'cached_tokens':u.get('cachedContentTokenCount',0)}}
        return text,usage,response.get('modelVersion'),item.get('finishReason')=='STOP'
    choices = response.get('choices',[])
    item = choices[0] if choices else {}
    return item.get('message',{}).get('content',''),response.get('usage',{}),response.get('model'),item.get('finish_reason')=='stop'


def receive_credentials(plan):
    if {g['id'] for g in plan['groups']} != set(SECRET_ENVS):
        raise TrialError('secret_group_set_mismatch')
    keys = {}
    for group in plan['groups']:
        key = os.environ.get(SECRET_ENVS[group['id']], '').strip()
        actual = hashlib.sha256((plan['key_binding_salt']+':'+key).encode()).hexdigest()
        if not key or actual != group['key_sha256']:
            raise TrialError('secret_missing_or_binding_mismatch')
        keys[group['id']] = key
    # GitHub masks secrets already; explicitly register before any provider IO too.
    for key in keys.values():
        print('::add-mask::'+key, flush=True)
    return keys


def receipt_numbers(usage):
    # Persist only documented, typed billing fields; no arbitrary relay metadata.
    allowed = {'input_tokens','output_tokens','prompt_tokens','completion_tokens',
        'cache_read_input_tokens','cache_creation_input_tokens','input_tokens_details',
        'prompt_tokens_details','output_tokens_details','completion_tokens_details','cache_creation',
        'cached_tokens','cache_write_tokens','reasoning_tokens','ephemeral_5m_input_tokens','ephemeral_1h_input_tokens'}
    return {k:(receipt_numbers(v) if isinstance(v,dict) else v) for k,v in usage.items()
            if k in allowed and (isinstance(v,dict) or type(v) is int)}


def numeric_tree(value):
    """Billing diagnostics contain only numeric fields, never account names/keys/IPs."""
    if not isinstance(value,dict):
        return {}
    result={}
    for key,item in value.items():
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,80}',key) or key in {
            'id','user_id','token_id','channel_id','balance','remaining','limit',
            'total_granted','total_available','expires_at','expired_time'}:
            continue
        if type(item) in (int,float) and math.isfinite(item):
            result[key]=item
        elif isinstance(item,dict):
            result[key]=numeric_tree(item)
    return result


def inspect_billing(state,plan,keys):
    audit={'trial_id':TRIAL,'model_generation_calls':0,'groups':{},
           'cost_units':'gateway reported numbers; CNY conversion requires denomination evidence'}
    source_run=state.api('actions/runs/39146426861')
    from datetime import datetime
    cutoff=int(datetime.fromisoformat(source_run['created_at'].replace('Z','+00:00')).timestamp())
    for group in plan['groups']:
        headers={'Authorization':'Bearer '+keys[group['id']]}
        data={}
        endpoints=('/api/usage/token/','/api/log/token') if group['root']=='https://cheapai.info' else ('/v1/usage',)
        for path in endpoints:
            try:
                raw,_=http_json(group['root']+path,headers)
                if path=='/api/log/token':
                    logs=raw.get('data',[])
                    if isinstance(logs,dict):
                        logs=logs.get('items',logs.get('logs',[]))
                    rows=[]
                    for item in logs if isinstance(logs,list) else []:
                        if not isinstance(item,dict) or item.get('created_at',0)<cutoff:
                            continue
                        row=numeric_tree(item)
                        if item.get('model_name') in group['models']:
                            row['model_name']=item['model_name']
                        other=item.get('other',{})
                        if isinstance(other,str):
                            try:
                                other=json.loads(other)
                            except ValueError:
                                other={}
                        row['other']=numeric_tree(other)
                        rows.append(row)
                    data[path]={'records':rows}
                else:
                    data[path]={'numbers':numeric_tree(raw)}
                    if group['family'] in ('google','deepseek','openai','anthropic') and group['root']=='https://codekey.ai':
                        data[path]['is_valid']=raw.get('isValid')
                        data[path]['subscription_present']=bool(raw.get('subscription'))
                        balance=raw.get('balance')
                        data[path]['wallet_positive']=balance>0 if type(balance) in (int,float) else None
                        data[path]['mode']=raw.get('mode') if raw.get('mode') in ('quota_limited','balance','subscription','unlimited') else 'unverified'
            except (TrialError,TypeError,ValueError) as error:
                data[path]={'status':str(error) if type(error) is TrialError else type(error).__name__}
        audit['groups'][group['id']]=data
    state.write('billing-audit.json',audit)
    print('Read-only billing audit recorded; no model generation requested',flush=True)


def meter(group,key):
    global _CHEAP_DENOMINATION
    headers={'Authorization':'Bearer '+key}
    if group['root']=='https://codekey.ai':
        raw,_=http_json(group['root']+'/v1/usage',headers)
        total=raw.get('usage',{}).get('total',{})
        requests=total.get('requests')
        cost=total.get('actual_cost')
        if type(requests) is not int or requests<0 or type(cost) not in (int,float) or not math.isfinite(cost) or cost<0:
            raise TrialError('unusable_gateway_meter')
        return {'kind':'codekey_total_actual_cost','requests':requests,'cost_cny':float(cost),
                'currency_rule':'owner numeric USD wallet unit equals CNY1'}
    if _CHEAP_DENOMINATION is None:
        status,_=http_json(group['root']+'/api/status')
        _CHEAP_DENOMINATION=status.get('data',{})
    unit=_CHEAP_DENOMINATION.get('quota_per_unit')
    display=_CHEAP_DENOMINATION.get('quota_display_type')
    if unit!=500000 or display!='USD':
        raise TrialError('gateway_denomination_changed')
    if group['id'] not in _KEY_USAGE_SNAPSHOTS:
        usage,_=http_json(group['root']+'/api/usage/token/',headers)
        _KEY_USAGE_SNAPSHOTS[group['id']]=usage.get('data',{}).get('total_used')
    logs,_=http_json(group['root']+'/api/log/token',headers)
    total=_KEY_USAGE_SNAPSHOTS[group['id']]
    rows=logs.get('data',[])
    if not isinstance(rows,list) or type(total) is not int or total<0:
        raise TrialError('unusable_gateway_meter')
    rows=[{'model':r.get('model_name'),'quota':r.get('quota'),'created_at':r.get('created_at'),
           'prompt_tokens':r.get('prompt_tokens'),'completion_tokens':r.get('completion_tokens')}
          for r in rows if isinstance(r,dict) and r.get('type')==2]
    if any(r['model'] not in group['models'] for r in rows):
        raise TrialError('unexpected_model_in_dedicated_key_history')
    if any(type(r['quota']) is not int or r['quota']<0 or type(r['created_at']) is not int for r in rows):
        raise TrialError('unusable_gateway_debits')
    logged_total=sum(r['quota'] for r in rows)
    if logged_total<total:
        raise TrialError('incomplete_gateway_debit_history')
    # The token-usage endpoint may cache an older aggregate. A newer complete
    # debit log is authoritative for its own recorded amounts; never infer zero.
    return {'kind':'cheapai_quota_history','quota_per_unit':unit,'total_quota':logged_total,
            'token_usage_counter_quota':total,'token_usage_counter_lagged':total<logged_total,
            'rows':rows,'currency_rule':'owner numeric USD wallet unit equals CNY1'}


def read_meter(group,key):
    for attempt in range(3):
        try:
            return meter(group,key)
        except TrialError as error:
            if str(error)!='http_429' or attempt==2:
                raise
            # Only free, read-only usage queries wait and retry. No generation
            # request is sent or repeated by this function.
            time.sleep(60)


def resume_metadata_skips(ledger):
    allowed=[]
    blocked=ledger.get('quarantined_routes',{})
    for route,reason in list(blocked.items()):
        if reason!='http_429':
            continue
        attempts=[e for e in ledger['entries'] if e['call_id'].startswith(route+'|')]
        skipped=[r for r in ledger['results'] if r['call_id'].startswith(route+'|')
                 and r.get('status')=='billing_metadata_unavailable_no_call']
        if skipped and all(e.get('status')=='gateway_debit_verified' for e in attempts):
            allowed.append(route)
            del blocked[route]
    if not allowed:
        raise TrialError('no_safe_unattempted_metadata_skips_to_resume')
    ledger.setdefault('operator_reviews',[]).append({'reason':'Resume only tasks whose read-only meter was rate-limited before inference; all prior paid IDs remain skipped.',
        'routes':allowed,'commit':os.environ.get('GITHUB_SHA','unit-test')})
    ledger.pop('stop_reason',None)
    return allowed


def settle_debit(entry,amount,evidence):
    if type(amount) not in (int,float) or not math.isfinite(amount) or amount<0 or amount>entry['reserved_ceiling_cny']:
        raise TrialError('gateway_debit_exceeds_reservation')
    if not isinstance(evidence,dict) or not evidence.get('source'):
        raise TrialError('independent_debit_evidence_required')
    entry.update(status='gateway_debit_verified',gateway_debit_cny=round(amount,8),debit_evidence=evidence)


def reconcile_existing_cheapai(state,plan,keys,ledger):
    # Explicit operator-reviewed repair: match the paused original attempts to
    # independent debit logs. Preserve lost/failed responses and never replay IDs.
    for group in plan['groups']:
        if group['root']!='https://cheapai.info':
            continue
        entries=[e for e in ledger['entries'] if e['call_id'].split('|')[0]==group['id']]
        if not entries:
            continue
        current=read_meter(group,keys[group['id']])
        rows=current['rows']
        if len(rows)!=len(entries):
            raise TrialError('paused_debits_not_uniquely_matchable')
        for model in {e['call_id'].split('|')[1] for e in entries}:
            matches=[r for r in rows if r['model']==model]
            attempts=[e for e in entries if e['call_id'].split('|')[1]==model]
            if len(matches)!=len(attempts):
                raise TrialError('paused_debits_not_uniquely_matchable')
            for entry,row in zip(attempts,sorted(matches,key=lambda r:r['created_at'])):
                settle_debit(entry,row['quota']/current['quota_per_unit'],{
                    'source':group['root']+'/api/log/token','unit_source':group['root']+'/api/status',
                    'quota_per_unit':current['quota_per_unit'],**row,
                    'all_key_debits_match_attempt_count':True,'no_generation_retry':True})
                for record in ledger['results']:
                    if record['call_id']==entry['call_id'] and record.get('complete') and record.get('identity_exact') and isinstance(record.get('text'),str):
                        record['post_reconciliation_grade']=grade(record['text'],entry['call_id'].split('|')[2])
                        record['gateway_debit_cny']=entry['gateway_debit_cny']
                        record['reconciled_without_generation_retry']=True
                    elif record['call_id']==entry['call_id'] and record.get('identity_exact') is False:
                        blocked=ledger.setdefault('quarantined_routes',{})
                        blocked['|'.join(entry['call_id'].split('|')[:2])]='reported_model_identity_unverified'
    if any(e.get('status')!='gateway_debit_verified' for e in ledger['entries']):
        raise TrialError('unreconciled_prior_attempts_still_blocked')
    ledger.setdefault('operator_reviews',[]).append({'run_id':os.environ['GITHUB_RUN_ID'],
        'commit':os.environ['GITHUB_SHA'],'reason':'Paused cache receipt reviewed against independent gateway debit; retain every original attempt, continue only unattempted fixtures under same CNY30.'})
    ledger.pop('stop_reason',None)
    ledger['settlement_rule']='Only independently matched gateway debit releases unused reservation; unknown debit remains held.'
    state.write('ledger.json',ledger)


def settle_after_call(group,key,ledger,entry,before):
    for retry in range(4):
        try:
            after=read_meter(group,key)
        except TrialError as error:
            if str(error)!='incomplete_gateway_debit_history' or retry==3:
                raise
            # Wallet counters and log insertion can become visible separately.
            # Retry only a free GET, never the inference POST.
            time.sleep(2)
            continue
        if after['kind']=='codekey_total_actual_cost':
            if after['requests']==before['requests']+1 and after['cost_cny']>=before['cost_cny']:
                settle_debit(entry,round(after['cost_cny']-before['cost_cny'],8),{
                    'source':group['root']+'/v1/usage','before':before,'after':after,
                    'exactly_one_new_gateway_request':True})
                return
        else:
            prior=before['rows']
            current=after['rows']
            delta=[r for r in current if r not in prior]
            if len(delta)==1 and len(current)==len(prior)+1 and after['total_quota']-before['total_quota']==delta[0]['quota'] \
               and delta[0]['model']==entry['call_id'].split('|')[1]:
                row=delta[0]
                settle_debit(entry,row['quota']/after['quota_per_unit'],{
                    'source':group['root']+'/api/log/token','unit_source':group['root']+'/api/status',
                    'quota_per_unit':after['quota_per_unit'],**row,'exactly_one_new_gateway_request':True})
                return
        if retry<3:
            time.sleep(2)
    raise TrialError('gateway_debit_not_uniquely_reconciled')


def run_trial(state, plan, keys, ledger):
    secret_values = [*keys.values(),state.token]
    inventory = {}
    for group in plan['groups']:
        try:
            body,_ = http_json(group['root']+'/v1/models',{'Authorization':'Bearer '+keys[group['id']]})
            models = [x['id'] for x in body.get('data',[]) if isinstance(x,dict)
                      and isinstance(x.get('id'),str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,140}',x['id'])]
            inventory[group['id']] = {'status':'received','models':models}
        except TrialError as e:
            inventory[group['id']] = {'status':str(e),'models':[]}
    state.write('inventory.json', {'trial_id':TRIAL,'inventory':inventory})
    print('Cloud account model inventory recorded without generation calls',flush=True)
    records = ledger.setdefault('results',[])
    blocked=ledger.setdefault('quarantined_routes',{})
    # Finish the common evidence comparison before spending on the second fixture.
    for case in ('evidence','engineering'):
        for group in plan['groups']:
            if inventory[group['id']]['status'] != 'received':
                continue
            for model in group['models']:
                if model=='deepseek-flash' and model not in inventory[group['id']]['models'] \
                   and 'deepseek-v4.1-flash' in inventory[group['id']]['models']:
                    # Advertised relay ID; dated 1017 backend remains unverified.
                    model='deepseek-v4.1-flash'
                call_id = group['id']+'|'+model+'|'+case
                if any(e['call_id']==call_id for e in ledger['entries']):
                    continue
                route_id=group['id']+'|'+model
                if route_id in blocked:
                    records.append({'call_id':call_id,'status':'quarantined_route_no_call','reason':blocked[route_id]})
                    continue
                if model not in inventory[group['id']]['models']:
                    records.append({'call_id':call_id,'status':'exact_model_not_advertised_no_call'})
                    continue
                family = group['family']
                path = {'openai':'/v1/responses','anthropic':'/v1/messages',
                    'deepseek':'/v1/chat/completions','google':'/v1beta/models/'+model+':generateContent'}[family]
                route = {**group,'model':model,'path':path,'effort':'medium' if model=='gpt-6-luna' else 'high'}
                payload = payload_for(route,case)
                quote = quote_for(route)
                input_ceiling = max(65536 if family=='anthropic' else 8192,
                                    len(json.dumps(payload,ensure_ascii=False).encode())+4096)
                output_ceiling = 16384 if family=='openai' else 8192
                # Sevenfold currency/billing safety margin; do not report it as actual spend.
                # Release only after an independent, exactly matched gateway debit.
                ceiling = round(max(.10,7*billing_quotes.reserve_cost(quote,input_ceiling,output_ceiling)),8)
                persist = lambda value: state.write('ledger.json',value)
                try:
                    before=read_meter(group,keys[group['id']])
                except TrialError as error:
                    blocked[route_id]=str(error)
                    records.append({'call_id':call_id,'status':'billing_metadata_unavailable_no_call','diagnostic':str(error)})
                    persist(ledger)
                    continue
                if not reserve(ledger,call_id,ceiling,persist,meter_before=before):
                    records.append({'call_id':call_id,'status':'budget_ceiling_prevented_call'})
                    continue
                entry = ledger['entries'][-1]
                headers = {'Authorization':'Bearer '+keys[group['id']]}
                if family=='anthropic':
                    headers = {'x-api-key':keys[group['id']],'anthropic-version':'2023-06-01'}
                elif family=='google':
                    headers = {'x-goog-api-key':keys[group['id']]}
                record = {'call_id':call_id,'requested_model':model,'family':family,'effort':route['effort'],
                    'fixture_sha256':hashlib.sha256(fixture(case).encode()).hexdigest(),
                    'payload_sha256':digest(payload),'quote_sha256':quote['quote_sha256'],
                    'source_url':SOURCES[family],'reserved_ceiling_cny':ceiling,
                    'input_token_ceiling':input_ceiling,'output_token_ceiling':output_ceiling,
                    'quote_snapshot':quote,
                    'gateway_price_url':group['root']+('/api/pricing' if group['root']=='https://cheapai.info' else '/models')}
                started = time.monotonic()
                receipt_saved=False
                try:
                    response, response_headers = http_json(route['root']+path,headers,payload)
                    record['inference_response_seconds']=round(time.monotonic()-started,3)
                    text, raw_usage, reported, complete = decode(route,response)
                    if family=='deepseek' and 'prompt_cache_hit_tokens' in raw_usage:
                        hit=raw_usage['prompt_cache_hit_tokens']
                        miss=raw_usage.get('prompt_cache_miss_tokens')
                        total=raw_usage.get('prompt_tokens')
                        if type(hit) is not int or hit<0 or (miss is not None and (type(miss) is not int or hit+miss!=total)):
                            raise TrialError('deepseek_cache_receipt_contradiction')
                        if 'prompt_tokens_details' not in raw_usage:
                            raw_usage={**raw_usage,'prompt_tokens_details':{'cached_tokens':hit}}
                        record['deepseek_native_cache_counts']={'hit':hit,'miss':miss}
                    usage = receipt_numbers(raw_usage)
                    record.update(text=safe_text(text,secret_values),usage=usage,
                        reported_model=safe_text(reported,secret_values),complete=complete,
                        identity_exact=reported==model,status='receipt_received_before_billing_validation')
                    opaque_id=safe_text(response.get('id',response_headers.get('x-request-id','')),secret_values)
                    if re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}',opaque_id):
                        record['gateway_request_id']=opaque_id
                    records.append(record)
                    receipt_saved=True
                    persist(ledger)
                    input_tokens = usage.get('input_tokens',usage.get('prompt_tokens'))
                    output_tokens = usage.get('output_tokens',usage.get('completion_tokens'))
                    try:
                        modeled,unknown,parts = billing_quotes.bill(quote,usage,input_tokens,output_tokens,
                            anthropic=family=='anthropic')
                        record.update(modeled_cost_cny=modeled,billing_parts=parts)
                    except billing_quotes.BillingQuoteError as error:
                        if family!='anthropic' or 'TTL usage breakdown' not in str(error):
                            raise
                        # Total cache-write tokens can be valid while TTL is absent.
                        # Do not fabricate a TTL or an exact modeled charge; settle
                        # only against the separately queried gateway wallet debit.
                        parts=billing_quotes.token_parts(usage,input_tokens,output_tokens,anthropic=True)
                        modeled=None;unknown=False
                        record.update(cache_write_ttl_unreported=True,billing_parts=parts)
                    # Date-pinned model versions are recorded but require manual identity review.
                    identity_ok = reported==model
                    if (modeled is not None and modeled>ceiling) or parts['full_request_input_tokens']>input_ceiling or output_tokens>output_ceiling or unknown:
                        raise TrialError('billing_ceiling_or_receipt_violation')
                    entry.update(status='response_received_reservation_retained')
                    if modeled is not None:
                        entry['modeled_cost_cny']=modeled
                    settle_after_call(group,keys[group['id']],ledger,entry,before)
                    record.update(status='complete' if complete and identity_ok else 'incomplete_or_identity_unverified',
                        reported_model=safe_text(reported,secret_values),identity_exact=identity_ok,
                        complete=complete,text=safe_text(text,secret_values),usage=usage,
                        gateway_debit_cny=entry['gateway_debit_cny'],grade=grade(text,case) if complete and identity_ok else None,
                        dated_backend_version_verified=False,
                        reasoning_effort_attestation='requested; not independently attested')
                    record['elapsed_seconds']=round(time.monotonic()-started,3)
                    persist(ledger)
                    print(call_id+': '+record['status'],flush=True)
                    if not identity_ok:
                        blocked[route_id]='reported_model_identity_unverified'
                        persist(ledger)
                        continue
                except (TrialError,billing_quotes.BillingQuoteError,ValueError,TypeError,KeyError) as error:
                    # Keep this reservation and STOP, even for a seemingly harmless 400/401.
                    entry['status']='ambiguous_failure_reservation_retained'
                    record.update(status='ambiguous_failure_no_retry',
                        diagnostic=str(error) if type(error) in (TrialError,billing_quotes.BillingQuoteError) else type(error).__name__,
                        elapsed_seconds=round(time.monotonic()-started,3))
                    if not receipt_saved:
                        records.append(record)
                    blocked[route_id]=record['diagnostic']
                    persist(ledger)
                    print(call_id+': route stopped; reservation held; no retry',flush=True)
                    continue
    ledger['stop_reason']='planned_available_comparisons_finished_with_quarantines' if blocked else 'planned_available_comparisons_finished_or_budget_limited'
    state.write('ledger.json',ledger)


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!=REPO \
       or os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH or os.environ.get('GITHUB_EVENT_NAME')!='push':
        raise TrialError('cloud_owner_branch_push_required')
    plan = json.loads(Path('config/gateway-trial-20261019.json').read_text())
    if plan['budget_cny']!=LIMIT or plan['trial_id']!=TRIAL or len(plan['groups'])!=10:
        raise TrialError('plan_authorization_mismatch')
    state = CloudState(os.environ['TRIAL_GITHUB_TOKEN'])
    plan_hash = digest(plan)
    ledger,_ = state.read('ledger.json')
    if ledger is None:
        ledger = {'trial_id':TRIAL,'limit_cny':LIMIT,'plan_sha256':plan_hash,'entries':[], 'results':[],
                  'scientific_completion':False,'production_routing_changed':False,
                  'actual_invoice_reconciled':False,'currency_rule':'user foreign USD numeric as CNY; domestic CNY',
                  'budget_safety_multiplier':7,'reservations_never_released_without_independent_gateway_debit':True}
        state.write('ledger.json',ledger)
    validate_ledger(ledger,plan_hash)
    if os.environ.get('TRIAL_METADATA_ONLY')=='1':
        keys=receive_credentials(plan)
        try:
            inspect_billing(state,plan,keys)
        finally:
            keys.clear()
        return
    if os.environ.get('TRIAL_RESUME_METADATA_SKIPS')=='1' and ledger.get('stop_reason')=='planned_available_comparisons_finished_with_quarantines':
        resume_metadata_skips(ledger)
        state.write('ledger.json',ledger)
    if os.environ.get('TRIAL_RECONCILE_AND_CONTINUE')=='1' and ledger.get('stop_reason')=='generation_or_billing_requires_review':
        keys=receive_credentials(plan)
        reconcile_existing_cheapai(state,plan,keys,ledger)
        keys.clear()
        ledger.pop('reservations_never_automatically_released',None)
        ledger['reservations_never_released_without_independent_gateway_debit']=True
    if ledger.get('stop_reason') or any(e['status']=='reserved_before_transport' for e in ledger['entries']):
        raise TrialError('existing_trial_stopped_do_not_replay_authorization')
    keys = receive_credentials(plan)
    try:
        run_trial(state,plan,keys,ledger)
    finally:
        keys.clear()
    print(json.dumps({'trial_id':TRIAL,'committed_upper_cny':committed_cost(ledger),
        'gateway_debit_cny':round(sum(e.get('gateway_debit_cny',0) for e in ledger['entries']),8),
        'stop_reason':ledger.get('stop_reason'),'actual_invoice_reconciled':False}),flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        # Exception messages may contain credentials; emit only controlled types/codes.
        print('Trial stopped: '+(str(error) if type(error) is TrialError else type(error).__name__),file=sys.stderr)
        sys.exit(1)
