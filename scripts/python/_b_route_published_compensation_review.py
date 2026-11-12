"""Published-history compensation profile; original routes keep their meanings."""
import _b_route_qualified_compensation_review_v2 as common
from _b_route_compensation_review_profiles import PUBLISHED as PROFILE

SUBJECT = PROFILE.name('subject')
PROOF = PROFILE.name('proof')
VERDICT = PROFILE.name('verdict')
DELIVERY = PROFILE.name('delivery')
CLAIM = PROFILE.claim
MODE = PROFILE.mode
selected = common.selected
read_subject = common.read_subject
model_packet = common.model_packet
bindings = common.bindings
verdict_schema = common.verdict_schema
check_verdict = common.check_verdict
prompt = common.prompt
artifacts = common.artifacts
support_names = common.support_names
produce_proof = common.produce_proof
verify_saved = common.verify_saved
seal = common.seal
verify_semantic = common.verify_semantic
bind_action = common.bind_action


def history(root, original):
    return common.history(root, original, profile=PROFILE)


def original_review(snapshot, original):
    return common.original_review(snapshot, original, profile=PROFILE)


def family_for_snapshot(snapshot):
    return common.family_for_snapshot(snapshot, profile=PROFILE)


def capture_files(snapshot, *, original):
    return common.capture_files(snapshot, original=original, profile=PROFILE)


def consider_legacy_authorities(snapshot, subject):
    return common.consider_legacy_authorities(snapshot, subject, profile=PROFILE)
