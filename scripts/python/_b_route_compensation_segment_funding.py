"""Fixed genuine-owner boundary, not a compensation accounting pool.

The optional issuer must live beside this module and own the real original
budget/unknown ledger. No CLI allowance, dictionary, saved receipt or caller
counter can install it. Its absence blocks dispatch/replay, not development.
"""
import importlib
from pathlib import Path
import weakref

import _b_route_adoption_review as review
from _b_route_codec import ReasonCode

OWNER_MODULE = '_b_route_compensation_budget_owner'
_KEY = object()
_ISSUED = weakref.WeakSet()


class BudgetSession:
    def __init__(self,key,owner,root,plan,read_only):
        review.require(key is _KEY,'genuine compensation funding factory','unissued session')
        self.owner,self.root,self.plan,self.read_only=owner,root,plan,read_only
        _ISSUED.add(self)

    def recheck(self):
        require_session(self)
        self.owner.recheck(self.root,self.plan)

    def reserve(self,key,identity,remaining):
        self.recheck()
        review.require(not self.read_only,'writable genuine budget session','read-only session')
        # Original owner must atomically recognize this exact stable intent,
        # check the entire remaining finite plan and retain existing unknowns.
        ref=self.owner.reserve(key,identity,remaining)
        self.owner.verify(ref,key,identity,None)
        return ref

    def inspect(self,key,identity):
        self.recheck()
        return self.owner.inspect(key,identity)

    def verify(self,ref,key,identity,outcome):
        self.recheck()
        self.owner.verify(ref,key,identity,outcome)

    def complete(self,ref,key,identity,outcome):
        self.recheck()
        review.require(not self.read_only,'writable genuine budget session','read-only session')
        self.owner.complete(ref,key,identity,outcome)
        self.owner.verify(ref,key,identity,outcome)

    def unknown(self,ref,key,identity,reason):
        self.recheck()
        review.require(not self.read_only,'writable genuine budget session','read-only session')
        self.owner.unknown(ref,key,identity,reason)


def require_session(value):
    review.require(type(value) is BudgetSession and value in _ISSUED,
                   'factory-issued original compensation budget session','caller funding is not authority')


def capture(root,plan, *, read_only=False):
    path=Path(__file__).with_name(OWNER_MODULE+'.py')
    review.require(path.is_file(),'installed genuine compensation budget issuer; original unknowns retained',
        'compensation_budget_owner_unavailable',ReasonCode.DEPENDENCY_UNAVAILABLE)
    owner_module=importlib.import_module(OWNER_MODULE)
    review.require(Path(owner_module.__file__).resolve()==path.resolve(),
                   'fixed installed funding owner path','foreign funding issuer')
    # The installed issuer's source is included in review.policy_observations.
    owner=owner_module.capture(Path(root).absolute(),plan,read_only=read_only)
    review.require(not isinstance(owner,(dict,bool)) and all(callable(getattr(owner,n,None)) for n in
        ('recheck','reserve','inspect','verify','complete','unknown')),
        'original ledger owner capability','invalid budget owner')
    session=BudgetSession(_KEY,owner,Path(root).absolute(),plan,read_only)
    session.recheck()
    return session
