"""Cloud-only, bounded relay acceptance; never changes scientific runtime roles.

All material is an original synthetic software fixture, not research evidence.
Credentials arrive only through GitHub Actions Secrets, never PR metadata.
Generation has no retry/fallback. Durable conservative reservations are never
released automatically, even after a complete receipt. Unknown billing stops
the trial; restarting does not create another CNY30 allowance.
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
    if sum(e['reserved_ceiling_cny'] for e in entries) > LIMIT + 1e-8:
        raise TrialError('over_budget_ledger')
    return ledger


def reserve(ledger, call_id, ceiling, persist):
    if any(e['call_id']==call_id for e in ledger['entries']):
        return False
    if not math.isfinite(ceiling) or ceiling <= 0:
        raise TrialError('invalid_reservation')
    used = sum(e['reserved_ceiling_cny'] for e in ledger['entries'])
    if used + ceiling > LIMIT:
        return False
    ledger['entries'].append({'call_id':call_id, 'reserved_ceiling_cny':ceiling,
                              'status':'reserved_before_transport'})
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
                'source_trace':data.get('source_ids')==['S1','S2','S3'],
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
        'deepseek-flash':(2,.04,0,8),
    }
    rates = prices[route['model']]
    fields = ('input_per_million','cache_read_per_million','cache_write_per_million','output_per_million')
    base = {k:v*route['multiplier'] for k,v in zip(fields,rates)}
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
    # Finish the common evidence comparison before spending on the second fixture.
    for case in ('evidence','engineering'):
        for group in plan['groups']:
            if inventory[group['id']]['status'] != 'received':
                continue
            for model in group['models']:
                call_id = group['id']+'|'+model+'|'+case
                if any(e['call_id']==call_id for e in ledger['entries']):
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
                input_ceiling = max(8192,len(json.dumps(payload,ensure_ascii=False).encode())+4096)
                output_ceiling = 16384 if family=='openai' else 8192
                # Sevenfold currency/billing safety margin; do not report it as actual spend.
                # Reservations are cumulative and never reclaimed during this authorization.
                ceiling = round(max(.10,7*billing_quotes.reserve_cost(quote,input_ceiling,output_ceiling)),8)
                persist = lambda value: state.write('ledger.json',value)
                if not reserve(ledger,call_id,ceiling,persist):
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
                    'source_url':SOURCES[family],'reserved_ceiling_cny':ceiling}
                started = time.monotonic()
                try:
                    response, response_headers = http_json(route['root']+path,headers,payload)
                    text, raw_usage, reported, complete = decode(route,response)
                    usage = receipt_numbers(raw_usage)
                    input_tokens = usage.get('input_tokens',usage.get('prompt_tokens'))
                    output_tokens = usage.get('output_tokens',usage.get('completion_tokens'))
                    modeled,unknown,parts = billing_quotes.bill(quote,usage,input_tokens,output_tokens,
                        anthropic=family=='anthropic')
                    # Date-pinned model versions are recorded but require manual identity review.
                    identity_ok = reported==model
                    if modeled>ceiling or parts['full_request_input_tokens']>input_ceiling or output_tokens>output_ceiling or unknown:
                        raise TrialError('billing_ceiling_or_receipt_violation')
                    entry.update(status='response_received_reservation_retained', modeled_cost_cny=modeled)
                    record.update(status='complete' if complete and identity_ok else 'incomplete_or_identity_unverified',
                        reported_model=safe_text(reported,secret_values),identity_exact=identity_ok,
                        complete=complete,text=safe_text(text,secret_values),usage=usage,
                        modeled_cost_cny=modeled,billing_parts=parts,grade=grade(text,case) if complete and identity_ok else None)
                    records.append(record)
                    record['elapsed_seconds']=round(time.monotonic()-started,3)
                    persist(ledger)
                    print(call_id+': '+record['status'],flush=True)
                    if not identity_ok:
                        ledger['stop_reason']='model_identity_requires_review'
                        persist(ledger)
                        return
                except (TrialError,billing_quotes.BillingQuoteError,ValueError,TypeError,KeyError) as error:
                    # Keep this reservation and STOP, even for a seemingly harmless 400/401.
                    entry['status']='ambiguous_failure_reservation_retained'
                    record.update(status='ambiguous_failure_no_retry',
                        diagnostic=str(error) if type(error) is TrialError else type(error).__name__,
                        elapsed_seconds=round(time.monotonic()-started,3))
                    records.append(record)
                    ledger['stop_reason']='generation_or_billing_requires_review'
                    persist(ledger)
                    print(call_id+': stopped; reservation held; no retry',flush=True)
                    return
    ledger['stop_reason']='planned_available_comparisons_finished_or_budget_limited'
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
                  'budget_safety_multiplier':7,'reservations_never_automatically_released':True}
        state.write('ledger.json',ledger)
    validate_ledger(ledger,plan_hash)
    if ledger.get('stop_reason') or any(e['status']=='reserved_before_transport' for e in ledger['entries']):
        raise TrialError('existing_trial_stopped_do_not_replay_authorization')
    keys = receive_credentials(plan)
    try:
        run_trial(state,plan,keys,ledger)
    finally:
        keys.clear()
    print(json.dumps({'trial_id':TRIAL,'reserved_upper_cny':sum(e['reserved_ceiling_cny'] for e in ledger['entries']),
        'modeled_cny':round(sum(e.get('modeled_cost_cny',0) for e in ledger['entries']),8),
        'stop_reason':ledger.get('stop_reason'),'actual_invoice_reconciled':False}),flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        # Exception messages may contain credentials; emit only controlled types/codes.
        print('Trial stopped: '+(str(error) if type(error) is TrialError else type(error).__name__),file=sys.stderr)
        sys.exit(1)
