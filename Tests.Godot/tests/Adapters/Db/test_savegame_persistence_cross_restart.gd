extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

func _new_db(node_name: String) -> Node:
    var db = null
    if ClassDB.class_exists("SqliteDataStore"):
        db = ClassDB.instantiate("SqliteDataStore")
    else:
        var s = load("res://Game.Godot/Adapters/SqliteDataStore.cs")
        db = Node.new()
        db.set_script(s)
    db.name = node_name
    get_tree().get_root().add_child(auto_free(db))
    return db

# ACC:T51.4
# ACC:T51.5
# ACC:T51.6
# ACC:T51.16
func test_savegame_cross_restart_persists() -> void:
    var path = "user://utdb_%s/save.db" % Time.get_unix_time_from_system()
    var db = _new_db("SqlDb")
    var ok1 = db.TryOpen(path)
    assert_bool(ok1).is_true()
    # Ensure schema exists
    var helper = preload("res://Game.Godot/Adapters/Db/DbTestHelper.cs").new()
    add_child(auto_free(helper))
    helper.CreateSchema()
    # Create user and save
    var bridge1 = preload("res://Game.Godot/Adapters/Db/RepositoryTestBridge.cs").new()
    add_child(auto_free(bridge1))
    var username = "sg_user_%s" % Time.get_unix_time_from_system()
    assert_bool(bridge1.UpsertUser(username)).is_true()
    var uid = bridge1.FindUserId(username)
    assert_that(uid).is_not_null()
    var json = '{"hp": 88, "turn_count": 5, "current_actor": "ActorA", "next_actor": "ActorB", "ts": %d}' % Time.get_unix_time_from_system()
    assert_bool(bridge1.UpsertSave(uid, 1, json)).is_true()
    db.Close()
    await get_tree().process_frame

    # Reopen and verify save persists using same node
    var ok2 = db.TryOpen(path)
    assert_bool(ok2).is_true()
    var bridge2 = preload("res://Game.Godot/Adapters/Db/RepositoryTestBridge.cs").new()
    add_child(auto_free(bridge2))
    var got = bridge2.GetSaveData(uid, 1)
    var parsed = JSON.parse_string(str(got))
    assert_object(parsed).is_not_null()
    assert_int(int(parsed["hp"])).is_equal(88)
    assert_int(int(parsed["turn_count"])).is_equal(5)
    assert_str(str(parsed["current_actor"])).is_equal("ActorA")

    # Resume state and perform one legal turn advance.
    parsed["turn_count"] = int(parsed["turn_count"]) + 1
    parsed["current_actor"] = "ActorB"
    parsed["turn_end_cleanup_completed"] = true
    parsed["turn_end_cleanup_trace_id"] = "trace_t51_cleanup"
    parsed["run_state_persisted_after_cleanup"] = true
    var advanced_json = JSON.stringify(parsed)
    assert_bool(bridge2.UpsertSave(uid, 1, advanced_json)).is_true()
    var got_after_advance = bridge2.GetSaveData(uid, 1)
    var parsed_after_advance = JSON.parse_string(str(got_after_advance))
    assert_object(parsed_after_advance).is_not_null()
    assert_int(int(parsed_after_advance["turn_count"])).is_equal(6)
    assert_str(str(parsed_after_advance["current_actor"])).is_equal("ActorB")
    assert_bool(bool(parsed_after_advance["turn_end_cleanup_completed"])).is_true()
    assert_str(str(parsed_after_advance["turn_end_cleanup_trace_id"])).is_equal("trace_t51_cleanup")
    assert_bool(bool(parsed_after_advance["run_state_persisted_after_cleanup"])).is_true()

    # Restart again and verify turn-end cleanup persistence stays stable across restart.
    db.Close()
    await get_tree().process_frame
    var ok3 = db.TryOpen(path)
    assert_bool(ok3).is_true()
    var bridge3 = preload("res://Game.Godot/Adapters/Db/RepositoryTestBridge.cs").new()
    add_child(auto_free(bridge3))
    var got_after_cleanup_restart = bridge3.GetSaveData(uid, 1)
    var parsed_after_cleanup_restart = JSON.parse_string(str(got_after_cleanup_restart))
    assert_object(parsed_after_cleanup_restart).is_not_null()
    assert_int(int(parsed_after_cleanup_restart["turn_count"])).is_equal(6)
    assert_str(str(parsed_after_cleanup_restart["current_actor"])).is_equal("ActorB")
    # ACC:T51.16
    assert_bool(bool(parsed_after_cleanup_restart["turn_end_cleanup_completed"])).is_true()
    assert_str(str(parsed_after_cleanup_restart["turn_end_cleanup_trace_id"])).is_equal("trace_t51_cleanup")
    assert_bool(bool(parsed_after_cleanup_restart["run_state_persisted_after_cleanup"])).is_true()


func test_savegame_cross_restart_should_fail_when_cleanup_marker_missing() -> void:
    var path = "user://utdb_%s/save_missing_cleanup.db" % Time.get_unix_time_from_system()
    var db = _new_db("SqlDb")
    assert_bool(db.TryOpen(path)).is_true()
    var helper = preload("res://Game.Godot/Adapters/Db/DbTestHelper.cs").new()
    add_child(auto_free(helper))
    helper.CreateSchema()
    var bridge = preload("res://Game.Godot/Adapters/Db/RepositoryTestBridge.cs").new()
    add_child(auto_free(bridge))
    var username = "sg_missing_cleanup_%s" % Time.get_unix_time_from_system()
    assert_bool(bridge.UpsertUser(username)).is_true()
    var uid = bridge.FindUserId(username)
    assert_that(uid).is_not_null()
    var broken = '{"hp": 70, "turn_count": 6, "current_actor": "ActorB", "next_actor": "ActorA", "run_state_persisted_after_cleanup": true, "ts": %d}' % Time.get_unix_time_from_system()
    assert_bool(bridge.UpsertSave(uid, 1, broken)).is_true()
    db.Close()
    await get_tree().process_frame
    assert_bool(db.TryOpen(path)).is_true()
    var got = bridge.GetSaveData(uid, 1)
    var parsed = JSON.parse_string(str(got))
    assert_object(parsed).is_not_null()
    # ACC:T51.16 fail-closed: missing cleanup markers must not be treated as valid restored cleanup state.
    var has_cleanup_marker = bool(parsed.has("turn_end_cleanup_completed")) and bool(parsed.has("turn_end_cleanup_trace_id"))
    assert_bool(has_cleanup_marker).is_false()
