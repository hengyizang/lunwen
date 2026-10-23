"""Explicit fake shared guard for unrelated transport/routing unit fixtures.

Dedicated test_relay_guard tests exercise the real guard and CAS against an
in-memory store. These stubs never touch GitHub, meters, keys or paid services.
"""
from copy import deepcopy
from unittest.mock import patch
from scripts import relay_guard


class MemoryStore:
    def __init__(self):
        self.files={};self.writes=[];self.fail_write=False;self.before_write=None
        for branch,name in relay_guard.SOURCES:self.put(branch,"trial-state",name,{"entries":[]})

    def put(self,branch,directory,name,value):
        import hashlib,json
        blob=hashlib.sha1(json.dumps(value,sort_keys=True).encode()).hexdigest()
        self.files[(branch,directory,name)]=(deepcopy(value),blob)
        return blob

    def read(self,branch,directory,name):
        return deepcopy(self.files.get((branch,directory,name),(None,None)))

    def write(self,name,value,expected):
        if self.before_write:
            hook=self.before_write;self.before_write=None;hook()
        _,current=self.read(relay_guard.BRANCH,"relay-guard",name)
        if self.fail_write or expected!=current:raise relay_guard.RelayGuardError("Synthetic CAS conflict; no generation authorized")
        blob=self.put(relay_guard.BRANCH,"relay-guard",name,value)
        self.writes.append((name,deepcopy(value),expected))
        return blob


def install_fake_guard(stack):
    """Only use in suites already mocking model/meter transport."""
    counter=[0]
    def begin(provider,*,scope,max_cost_cny,**kwargs):
        counter[0]+=1
        return {"id":"synthetic-shared-"+str(counter[0]),"provider":provider,"scope":scope,"max_cost_cny":max_cost_cny}
    return {"begin":stack.enter_context(patch.object(relay_guard,"begin",side_effect=begin)),
            "bind_meter":stack.enter_context(patch.object(relay_guard,"bind_meter",return_value=None)),
            "finish":stack.enter_context(patch.object(relay_guard,"finish",return_value=None)),
            "authorize_transport":stack.enter_context(patch.object(relay_guard,"authorize_transport",return_value=None))}
