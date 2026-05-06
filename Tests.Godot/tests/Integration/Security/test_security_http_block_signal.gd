extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

func _canonical_signal_name() -> StringName:
    return &"RequestBlocked"


func _client() -> Node:
    var sc = load("res://Game.Godot/Scripts/Security/SecurityHttpClient.cs")
    assert_bool(sc != null).is_true()
    assert_bool(sc.has_method("new")).is_true()
    var c = sc.new()
    assert_bool(c != null).is_true()
    add_child(auto_free(c))
    return c


func _read_signal_args(c: Node, signal_name: StringName) -> Array:
    for signal_info in c.get_signal_list():
        if StringName(signal_info.get("name", "")) == signal_name:
            return signal_info.get("args", [])
    return []


func _matches_expected_contract(actual_args: Array, expected_args: Array) -> bool:
    if actual_args.size() != expected_args.size():
        return false
    for index in range(expected_args.size()):
        var actual = actual_args[index]
        var expected = expected_args[index]
        if str(actual.get("name", "")) != str(expected.get("name", "")):
            return false
        if int(actual.get("type", -1)) != int(expected.get("type", -1)):
            return false
    return true


func _evaluate_signal_contract(actual_args: Array, expected_args: Array) -> Dictionary:
    if actual_args.size() != expected_args.size():
        return {
            "status": "fail",
            "code": "signal_arity_mismatch",
            "category": "contract-drift",
        }

    for index in range(expected_args.size()):
        var actual = actual_args[index]
        var expected = expected_args[index]
        if str(actual.get("name", "")) != str(expected.get("name", "")):
            return {
                "status": "fail",
                "code": "signal_parameter_name_mismatch",
                "category": "contract-drift",
            }
        if int(actual.get("type", -1)) != int(expected.get("type", -1)):
            return {
                "status": "fail",
                "code": "signal_parameter_type_mismatch",
                "category": "contract-drift",
            }

    return {
        "status": "ok",
        "code": "none",
        "category": "none",
    }


## ACC:T94.4
func test_emits_request_blocked_signal_on_denied() -> void:
    var c = _client()

    var signal_name: StringName = _canonical_signal_name()
    assert_bool(c.has_signal(signal_name)).is_true()

    var blocked := {
        "reason": "",
        "url": "",
        "count": 0,
    }
    var on_blocked := func(reason: String, url: String) -> void:
        blocked["reason"] = reason
        blocked["url"] = url
        blocked["count"] = int(blocked.get("count", 0)) + 1
    c.connect(signal_name, on_blocked)

    var ok = c.Validate("GET", "http://example.com", "", 0)
    assert_bool(ok).is_false()

    await get_tree().process_frame

    assert_int(int(blocked.get("count", 0))).is_equal(1)
    assert_str(str(blocked.get("reason", ""))).is_equal("not https")
    assert_str(str(blocked.get("url", ""))).is_equal("http://example.com")


## ACC:T94.7
func test_reports_drifted_signal_contract_as_deterministic_failure() -> void:
    var c = _client()
    var signal_name: StringName = _canonical_signal_name()
    assert_bool(c.has_signal(signal_name)).is_true()

    var actual_args := _read_signal_args(c, signal_name)
    assert_int(actual_args.size()).is_equal(2)

    var expected_pass := [
        {"name": "reason", "type": TYPE_STRING},
        {"name": "url", "type": TYPE_STRING},
    ]
    var expected_drift := [
        {"name": "reason", "type": TYPE_STRING},
        {"name": "url", "type": TYPE_INT},
    ]

    assert_bool(_matches_expected_contract(actual_args, expected_pass)).is_true()

    var drift_result_first := _evaluate_signal_contract(actual_args, expected_drift)
    var drift_result_second := _evaluate_signal_contract(actual_args, expected_drift)

    assert_str(str(drift_result_first.get("status", ""))).is_equal("fail")
    assert_str(str(drift_result_first.get("code", ""))).is_equal("signal_parameter_type_mismatch")
    assert_str(str(drift_result_first.get("category", ""))).is_equal("contract-drift")

    assert_str(str(drift_result_second.get("status", ""))).is_equal(str(drift_result_first.get("status", "")))
    assert_str(str(drift_result_second.get("code", ""))).is_equal(str(drift_result_first.get("code", "")))
    assert_str(str(drift_result_second.get("category", ""))).is_equal(str(drift_result_first.get("category", "")))

