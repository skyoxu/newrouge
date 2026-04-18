extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const ADR_0032 := "ADR-0032"
const ADR_0010 := "ADR-0010"

func _validate_adr_linkage_gate(evidence: Array[String]) -> bool:
	if evidence.is_empty():
		return false

	for item in evidence:
		var has_0032 := item.find(ADR_0032) != -1
		var has_0010 := item.find(ADR_0010) != -1
		if not (has_0032 and has_0010):
			return false
	return true

# acceptance: ACC:T19.8
# adr-trace: ADR-0032 ADR-0010
func test_task0019_adr_linkage_gate_accepts_consistent_evidence() -> void:
	var evidence: Array[String] = [
		"refs: Tests.Godot/tests/Tasks/test_task0019_acceptance.gd ADR-0032 ADR-0010",
		"checklist: reward-offer-locking ADR-0032 ADR-0010"
	]
	var result := _validate_adr_linkage_gate(evidence)
	assert_bool(result).is_true()

# acceptance: ACC:T19.9
# adr-trace: ADR-0032 ADR-0010
func test_task0019_adr_linkage_gate_rejects_split_or_mismatched_evidence() -> void:
	var evidence: Array[String] = [
		"refs: Tests.Godot/tests/Tasks/test_task0019_acceptance.gd ADR-0032",
		"checklist: reward-offer-locking ADR-0010"
	]
	var result := _validate_adr_linkage_gate(evidence)
	assert_bool(result).is_false()

func test_task0019_adr_linkage_gate_rejects_missing_required_adr() -> void:
	var evidence: Array[String] = [
		"refs: Tests.Godot/tests/Tasks/test_task0019_acceptance.gd ADR-0032"
	]
	var result := _validate_adr_linkage_gate(evidence)
	assert_bool(result).is_false()
