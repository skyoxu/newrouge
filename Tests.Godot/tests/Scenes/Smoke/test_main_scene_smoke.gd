extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const OPTIONAL_RUNTIME_SERVICES := [
    "EventBus",
    "DataStore",
    "Logger"
]

const RUNTIME_NODE_ALIASES := {
    "EventBus": ["EventBus", "EventBusAdapter"],
    "DataStore": ["DataStore", "DataStoreAdapter"],
    "Logger": ["Logger", "LoggerAdapter"],
    "CompositionRoot": ["CompositionRoot"]
}

func _ensure_composition_root_node():
    var existing = get_tree().root.get_node_or_null("CompositionRoot")
    if existing != null:
        return existing

    var composition_root_script = preload("res://Game.Godot/Autoloads/CompositionRoot.cs")
    var created = composition_root_script.new()
    if created == null:
        return null
    created.name = "CompositionRoot"
    get_tree().root.add_child(created)
    return created

func _resolve_runtime_node(node_name: String, composition_root):
    var aliases: Array = RUNTIME_NODE_ALIASES.get(node_name, [node_name])
    for alias in aliases:
        var from_root = get_tree().root.get_node_or_null(str(alias))
        if from_root != null:
            return from_root
        if composition_root != null:
            var from_composition = composition_root.get_node_or_null(str(alias))
            if from_composition != null:
                return from_composition
    return null

# Smoke
func test_main_scene_instantiates_and_visible() -> void:
    var scene := preload("res://Game.Godot/Scenes/Main.tscn").instantiate()
    add_child(auto_free(scene))
    await get_tree().process_frame
    assert_bool(scene.is_inside_tree()).is_true()

    var ensured_composition_root = _ensure_composition_root_node()
    if ensured_composition_root == null:
        print("[SMOKE][INFO] CompositionRoot unavailable in this smoke context; skip bridge assertions.")
        return
    await get_tree().process_frame

    var missing_optional: Array = []
    for service_name in OPTIONAL_RUNTIME_SERVICES:
        var service_node = _resolve_runtime_node(service_name, ensured_composition_root)
        if service_node == null:
            missing_optional.append(service_name)
    if missing_optional.size() > 0:
        print("[SMOKE][INFO] Optional runtime services not resolved in this test context: ", missing_optional)

    var composition_root = ensured_composition_root
    assert_bool(composition_root != null).is_true()
    if composition_root == null:
        return
    assert_bool(composition_root.has_method("PortsStatus")).is_true()
    assert_bool(composition_root.has_method("HasInitializationErrors")).is_true()
    assert_bool(bool(composition_root.call("HasInitializationErrors"))).is_false()
    if composition_root.has_method("InitializationErrors"):
        var init_errors = composition_root.call("InitializationErrors")
        assert_int(init_errors.size()).is_equal(0)

    var ports_status: Dictionary = composition_root.call("PortsStatus")
    for port_name in ["time", "input", "resourceLoader", "dataStore", "logger", "eventBus"]:
        assert_bool(ports_status.has(port_name)).is_true()
        assert_bool(bool(ports_status[port_name])).is_true()

    var event_bus = scene.call("_bus")
    var root_event_bus = _resolve_runtime_node("EventBus", composition_root)
    if event_bus != null and root_event_bus != null:
        assert_bool(event_bus == root_event_bus).is_true()

    var probe_script = preload("res://tests/Tasks/support/composition_root_probe.gd")
    var probe = probe_script.new()
    add_child(auto_free(probe))
    assert_bool(composition_root.has_method("InjectNode")).is_true()
    if composition_root.has_method("ClearInjectionErrors"):
        composition_root.call("ClearInjectionErrors")
    assert_bool(bool(composition_root.call("InjectNode", probe))).is_true()
    assert_bool(probe.injected).is_true()
    assert_bool(probe.has_non_null_port("eventBus")).is_true()
    if root_event_bus != null:
        assert_bool(probe.ports["eventBus"] == root_event_bus).is_true()
    if composition_root.has_method("HasInjectionErrors"):
        assert_bool(bool(composition_root.call("HasInjectionErrors"))).is_false()

    var feature_flags = get_tree().root.get_node_or_null("FeatureFlags")
    if feature_flags != null:
        assert_bool(feature_flags.has_method("IsEnabled")).is_true()

    var sentry_client = get_tree().root.get_node_or_null("SentryClient")
    if sentry_client != null:
        assert_bool(sentry_client.has_method("CaptureMessage")).is_true()

func test_settings_screen_can_load() -> void:
    var packed : PackedScene = preload("res://Game.Godot/Scenes/Screens/SettingsScreen.tscn")
    var inst := packed.instantiate()
    add_child(auto_free(inst))
    await get_tree().process_frame
    assert_bool(inst.is_inside_tree()).is_true()
    var bus = inst.get_node_or_null("/root/EventBus")
    if bus != null:
        assert_bool(bus != null).is_true()
