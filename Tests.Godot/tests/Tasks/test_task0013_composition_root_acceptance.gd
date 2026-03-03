extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const REQUIRED_AUTOLOAD_PATHS := {
    "EventBus": "res://Game.Godot/Adapters/EventBusAdapter.cs",
    "DataStore": "res://Game.Godot/Adapters/DataStoreAdapter.cs",
    "Logger": "res://Game.Godot/Adapters/LoggerAdapter.cs",
    "SecurityAudit": "res://Game.Godot/Scripts/Security/SecurityAudit.cs",
    "PerformanceTracker": "res://Game.Godot/Scripts/Perf/PerformanceTracker.cs",
    "SentryClient": "res://Game.Godot/Scripts/Obs/SentryClient.cs",
    "FeatureFlags": "res://Game.Godot/Scripts/Config/FeatureFlags.cs",
    "CompositionRoot": "res://Game.Godot/Autoloads/CompositionRoot.cs"
}

const BRIDGE_FORBIDDEN_MARKERS := [
    "namespace Game.Core.Domain",
    "Game.Core.Domain",
    "Game.Core.Services",
    "CombatService",
    "DeckService",
    "MapService",
    "StatusService",
    "DifficultyRuleService",
    "StateMachine",
    "ResolveEffect"
]

const BRIDGE_FORBIDDEN_USINGS := [
    "using Game.Core.Domain",
    "using Game.Core.Services"
]

const COMPOSITION_ROOT_ALLOWED_PUBLIC_METHODS := {
    "_EnterTree": true,
    "_Ready": true,
    "PortsStatus": true,
    "HasInitializationErrors": true,
    "InitializationErrors": true,
    "HasInjectionErrors": true,
    "InjectionErrors": true,
    "ClearInjectionErrors": true,
    "InjectNode": true
}

const AUTOLOAD_ALLOWED_PUBLIC_METHODS := {
    "res://Game.Godot/Adapters/EventBusAdapter.cs": {
        "Subscribe": true,
        "PublishSimple": true,
        "Dispose": true
    },
    "res://Game.Godot/Adapters/DataStoreAdapter.cs": {
        "SaveSync": true,
        "SaveAsync": true,
        "LoadSync": true,
        "LoadAsync": true,
        "DeleteSync": true,
        "DeleteAsync": true
    },
    "res://Game.Godot/Adapters/LoggerAdapter.cs": {
        "Info": true,
        "Warn": true,
        "Error": true
    },
    "res://Game.Godot/Scripts/Security/SecurityAudit.cs": {
        "_Ready": true
    },
    "res://Game.Godot/Scripts/Perf/PerformanceTracker.cs": {
        "_Ready": true,
        "_Process": true
    },
    "res://Game.Godot/Scripts/Obs/SentryClient.cs": {
        "_Ready": true,
        "CaptureMessage": true,
        "CaptureException": true
    },
    "res://Game.Godot/Scripts/Config/FeatureFlags.cs": {
        "_Ready": true,
        "IsEnabled": true,
        "Enable": true,
        "Disable": true,
        "Set": true,
        "Save": true
    },
    "res://Game.Godot/Autoloads/CompositionRoot.cs": COMPOSITION_ROOT_ALLOWED_PUBLIC_METHODS
}

const RUNTIME_NODE_ALIASES := {
    "EventBus": ["EventBus", "EventBusAdapter"],
    "DataStore": ["DataStore", "DataStoreAdapter"],
    "Logger": ["Logger", "LoggerAdapter"],
    "CompositionRoot": ["CompositionRoot"]
}

func _read_text_file(path: String) -> String:
    var file := FileAccess.open(path, FileAccess.READ)
    if file == null:
        return ""
    var content := file.get_as_text()
    file.close()
    return content

func _strip_wrapping_quotes(value: String) -> String:
    if value.length() >= 2 and value.begins_with("\"") and value.ends_with("\""):
        return value.substr(1, value.length() - 2)
    return value

func _normalize_autoload_value(value: String) -> String:
    var normalized := value.strip_edges()
    if normalized.begins_with("*"):
        normalized = normalized.substr(1)
    return normalized

func _parse_autoload_entries(project_text: String) -> Dictionary:
    var entries: Dictionary = {}
    var in_autoload_section := false
    for raw_line in project_text.split("\n", false):
        var line := raw_line.strip_edges()
        if line == "" or line.begins_with(";"):
            continue
        if line.begins_with("[") and line.ends_with("]"):
            in_autoload_section = (line == "[autoload]")
            continue
        if not in_autoload_section:
            continue
        var split_index := line.find("=")
        if split_index <= 0:
            continue
        var key := line.substr(0, split_index).strip_edges()
        var value := line.substr(split_index + 1).strip_edges()
        entries[key] = _strip_wrapping_quotes(value)
    return entries

func _resolve_project_file_with_autoloads() -> String:
    var candidates := [
        ProjectSettings.globalize_path("res://../project.godot").simplify_path(),
        ProjectSettings.globalize_path("res://project.godot").simplify_path()
    ]
    for candidate in candidates:
        if not FileAccess.file_exists(candidate):
            continue
        var text := _read_text_file(candidate)
        if text.find("[autoload]") != -1 and text.find("CompositionRoot") != -1:
            return candidate
    for candidate in candidates:
        if FileAccess.file_exists(candidate):
            return candidate
    return ""

func _get_autoload_node(autoload_name: String):
    return get_tree().root.get_node_or_null(autoload_name)

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

func _ensure_composition_root_node():
    var existing = _get_autoload_node("CompositionRoot")
    if existing != null:
        return existing

    var composition_root_script = preload("res://Game.Godot/Autoloads/CompositionRoot.cs")
    var created = composition_root_script.new()
    if created == null:
        return null
    created.name = "CompositionRoot"
    get_tree().root.add_child(created)
    return created

func _extract_using_directives(content: String) -> Array:
    var usings: Array = []
    for raw_line in content.split("\n", false):
        var line := raw_line.strip_edges()
        if line.begins_with("using "):
            usings.append(line)
    return usings

func _extract_public_method_names(content: String) -> Array:
    var methods: Array = []
    for raw_line in content.split("\n", false):
        var line := raw_line.strip_edges()
        if not line.begins_with("public "):
            continue
        if line.find("(") == -1:
            continue
        if line.find(" get;") != -1 or line.find(" set;") != -1:
            continue
        var header := line.substr(0, line.find("(")).strip_edges()
        var parts := header.split(" ", false)
        if parts.is_empty():
            continue
        methods.append(str(parts[parts.size() - 1]).strip_edges())
    return methods

func _find_method_arg_count(target: Object, method_name: String) -> int:
    for method_info in target.get_method_list():
        if not method_info.has("name"):
            continue
        if str(method_info["name"]) != method_name:
            continue
        if method_info.has("args"):
            return method_info["args"].size()
        return 0
    return -1

# ACC:T13.1
func test_task13_required_autoload_registry_contains_composition_root_dependencies() -> void:
    var project_file := _resolve_project_file_with_autoloads()
    assert_bool(project_file != "").is_true()

    var project_text := _read_text_file(project_file)
    assert_bool(project_text.find("[autoload]") != -1).is_true()

    var autoloads := _parse_autoload_entries(project_text)
    for name in REQUIRED_AUTOLOAD_PATHS.keys():
        assert_bool(autoloads.has(name)).is_true()
        var actual := _normalize_autoload_value(str(autoloads[name]))
        var expected := str(REQUIRED_AUTOLOAD_PATHS[name])
        assert_str(actual).is_equal(expected)

# ACC:T13.1
func test_task13_autoload_scripts_remain_bridge_only_without_domain_markers() -> void:
    for script_path in REQUIRED_AUTOLOAD_PATHS.values():
        var absolute_path := ProjectSettings.globalize_path(str(script_path)).simplify_path()
        assert_bool(FileAccess.file_exists(absolute_path)).is_true()

        var content := _read_text_file(absolute_path)
        assert_bool(content.length() > 0).is_true()

        for marker in BRIDGE_FORBIDDEN_MARKERS:
            assert_bool(content.find(marker) == -1).is_true()

        var using_directives := _extract_using_directives(content)
        for forbidden_using in BRIDGE_FORBIDDEN_USINGS:
            for using_line in using_directives:
                assert_bool(str(using_line).find(forbidden_using) == -1).is_true()

        for using_line in using_directives:
            var line := str(using_line)
            if not line.begins_with("using Game.Core."):
                continue
            var is_allowed := (
                line.find("using Game.Core.Ports") != -1
                or line.find("using Game.Core.Contracts") != -1
            )
            assert_bool(is_allowed).is_true()

        for raw_line in content.split("\n", false):
            var line := str(raw_line).strip_edges()
            if line.find("Game.Core.") == -1:
                continue
            var is_allowed_ref := (
                line.find("Game.Core.Ports") != -1
                or line.find("Game.Core.Contracts") != -1
            )
            assert_bool(is_allowed_ref).is_true()

        var script_key := str(script_path)
        assert_bool(AUTOLOAD_ALLOWED_PUBLIC_METHODS.has(script_key)).is_true()
        var allowed_methods: Dictionary = AUTOLOAD_ALLOWED_PUBLIC_METHODS[script_key]
        var public_methods := _extract_public_method_names(content)
        for method_name in public_methods:
            assert_bool(allowed_methods.has(str(method_name))).is_true()

# ACC:T13.1
func test_task13_required_autoload_paths_point_to_csharp_bridge_layers() -> void:
    var project_file := _resolve_project_file_with_autoloads()
    assert_bool(project_file != "").is_true()

    var autoloads := _parse_autoload_entries(_read_text_file(project_file))
    for name in REQUIRED_AUTOLOAD_PATHS.keys():
        var actual := _normalize_autoload_value(str(autoloads.get(name, "")))
        assert_bool(actual.begins_with("res://Game.Godot/")).is_true()
        assert_bool(actual.ends_with(".cs")).is_true()

        var in_allowed_layer := (
            actual.find("/Adapters/") != -1
            or actual.find("/Scripts/") != -1
            or actual.find("/Autoloads/") != -1
        )
        assert_bool(in_allowed_layer).is_true()
        assert_bool(actual.find("/Game.Core/") == -1).is_true()

# ACC:T13.3
func test_task13_composition_root_injects_ports_to_multiple_probe_nodes() -> void:
    var composition_root = _ensure_composition_root_node()
    assert_bool(composition_root != null).is_true()
    if composition_root == null:
        return
    assert_bool(composition_root.has_method("InjectNode")).is_true()
    assert_bool(composition_root.has_method("HasInitializationErrors")).is_true()
    assert_bool(bool(composition_root.call("HasInitializationErrors"))).is_false()
    if composition_root.has_method("ClearInjectionErrors"):
        composition_root.call("ClearInjectionErrors")
    if composition_root.has_method("HasInjectionErrors"):
        assert_bool(bool(composition_root.call("HasInjectionErrors"))).is_false()

    var probe_script = preload("res://tests/Tasks/support/composition_root_probe.gd")
    var probe_a = probe_script.new()
    var probe_b = probe_script.new()
    assert_int(_find_method_arg_count(probe_a, "InjectCompositionPorts")).is_equal(6)
    assert_int(_find_method_arg_count(probe_b, "InjectCompositionPorts")).is_equal(6)
    add_child(auto_free(probe_a))
    add_child(auto_free(probe_b))

    var injected_a := bool(composition_root.call("InjectNode", probe_a))
    var injected_b := bool(composition_root.call("InjectNode", probe_b))
    assert_bool(injected_a).is_true()
    assert_bool(injected_b).is_true()
    assert_bool(probe_a.injected).is_true()
    assert_bool(probe_b.injected).is_true()

    for port_name in ["time", "input", "resourceLoader", "dataStore", "logger", "eventBus"]:
        assert_bool(probe_a.has_non_null_port(port_name)).is_true()
        assert_bool(probe_b.has_non_null_port(port_name)).is_true()

    if composition_root.has_method("HasInjectionErrors"):
        assert_bool(bool(composition_root.call("HasInjectionErrors"))).is_false()

# ACC:T13.2
func test_task13_runtime_ports_and_core_nodes_are_resolvable() -> void:
    var composition_root = _ensure_composition_root_node()
    assert_bool(composition_root != null).is_true()
    if composition_root == null:
        return

    assert_bool(composition_root.has_method("PortsStatus")).is_true()
    assert_bool(composition_root.has_method("HasInitializationErrors")).is_true()
    assert_bool(composition_root.has_method("InitializationErrors")).is_true()

    assert_bool(bool(composition_root.call("HasInitializationErrors"))).is_false()
    var init_errors = composition_root.call("InitializationErrors")
    assert_int(init_errors.size()).is_equal(0)

    var ports_status: Dictionary = composition_root.call("PortsStatus")
    for port_name in ["time", "input", "resourceLoader", "dataStore", "logger", "eventBus"]:
        assert_bool(ports_status.has(port_name)).is_true()
        assert_bool(bool(ports_status[port_name])).is_true()

    var root_node = _resolve_runtime_node("CompositionRoot", composition_root)
    assert_bool(root_node != null).is_true()

# ACC:T13.3
func test_task13_composition_root_rejects_nodes_without_injection_hook() -> void:
    var composition_root = _ensure_composition_root_node()
    assert_bool(composition_root != null).is_true()
    if composition_root == null:
        return
    assert_bool(composition_root.has_method("InjectNode")).is_true()
    assert_bool(composition_root.has_method("HasInjectionErrors")).is_true()
    assert_bool(composition_root.has_method("InjectionErrors")).is_true()
    if composition_root.has_method("ClearInjectionErrors"):
        composition_root.call("ClearInjectionErrors")

    var plain_node := Node.new()
    plain_node.name = "NoHookProbe"
    add_child(auto_free(plain_node))
    assert_int(_find_method_arg_count(plain_node, "InjectCompositionPorts")).is_equal(-1)
    var injected := bool(composition_root.call("InjectNode", plain_node))
    assert_bool(injected).is_false()
    assert_bool(bool(composition_root.call("HasInjectionErrors"))).is_true()
    var injection_errors = composition_root.call("InjectionErrors")
    assert_int(injection_errors.size()).is_greater(0)
    assert_str(str(injection_errors[0])).contains("invalid hook signature")
    assert_str(str(injection_errors[0])).contains("NoHookProbe")

# ACC:T13.3
func test_task13_composition_root_reports_failure_for_faulty_injection_hook() -> void:
    var composition_root = _ensure_composition_root_node()
    assert_bool(composition_root != null).is_true()
    if composition_root == null:
        return
    assert_bool(composition_root.has_method("InjectNode")).is_true()
    assert_bool(composition_root.has_method("HasInjectionErrors")).is_true()
    assert_bool(composition_root.has_method("InjectionErrors")).is_true()
    if composition_root.has_method("ClearInjectionErrors"):
        composition_root.call("ClearInjectionErrors")

    var faulty_probe_script = preload("res://tests/Tasks/support/composition_root_faulty_probe.gd")
    var faulty_probe = faulty_probe_script.new()
    faulty_probe.name = "FaultyHookProbe"
    assert_int(_find_method_arg_count(faulty_probe, "InjectCompositionPorts")).is_equal(6)
    add_child(auto_free(faulty_probe))

    var injected := bool(composition_root.call("InjectNode", faulty_probe))
    assert_bool(injected).is_false()
    assert_bool(faulty_probe.invoked).is_true()
    assert_bool(bool(composition_root.call("HasInjectionErrors"))).is_true()

    var injection_errors = composition_root.call("InjectionErrors")
    assert_int(injection_errors.size()).is_greater(0)
    assert_str(str(injection_errors[0])).contains("returned false")
    assert_str(str(injection_errors[0])).contains("FaultyHookProbe")
    if composition_root.has_method("ClearInjectionErrors"):
        composition_root.call("ClearInjectionErrors")

# ACC:T13.3
func test_task13_composition_root_reports_failure_for_throwing_injection_hook() -> void:
    var composition_root = _ensure_composition_root_node()
    assert_bool(composition_root != null).is_true()
    if composition_root == null:
        return
    assert_bool(composition_root.has_method("InjectNode")).is_true()
    assert_bool(composition_root.has_method("HasInjectionErrors")).is_true()
    assert_bool(composition_root.has_method("InjectionErrors")).is_true()
    if composition_root.has_method("ClearInjectionErrors"):
        composition_root.call("ClearInjectionErrors")

    var throwing_probe_script = preload("res://tests/Tasks/support/CompositionRootThrowingProbe.cs")
    var throwing_probe = throwing_probe_script.new()
    throwing_probe.name = "ThrowingHookProbe"
    add_child(auto_free(throwing_probe))

    var injected := bool(composition_root.call("InjectNode", throwing_probe))
    assert_bool(injected).is_false()
    assert_bool(bool(throwing_probe.call("WasInvoked"))).is_true()
    assert_bool(bool(composition_root.call("HasInjectionErrors"))).is_true()

    var injection_errors = composition_root.call("InjectionErrors")
    assert_int(injection_errors.size()).is_greater(0)
    assert_str(str(injection_errors[0])).contains("InjectNode failed for")
    assert_str(str(injection_errors[0])).contains("ThrowingHookProbe")
    if composition_root.has_method("ClearInjectionErrors"):
        composition_root.call("ClearInjectionErrors")

# ACC:T13.3
func test_task13_composition_root_rejects_bad_signature_injection_hook() -> void:
    var composition_root = _ensure_composition_root_node()
    assert_bool(composition_root != null).is_true()
    if composition_root == null:
        return
    assert_bool(composition_root.has_method("InjectNode")).is_true()
    assert_bool(composition_root.has_method("HasInjectionErrors")).is_true()
    assert_bool(composition_root.has_method("InjectionErrors")).is_true()
    if composition_root.has_method("ClearInjectionErrors"):
        composition_root.call("ClearInjectionErrors")

    var bad_signature_script = preload("res://tests/Tasks/support/composition_root_bad_signature_probe.gd")
    var bad_signature_probe = bad_signature_script.new()
    bad_signature_probe.name = "BadSignatureProbe"
    assert_int(_find_method_arg_count(bad_signature_probe, "InjectCompositionPorts")).is_equal(0)
    add_child(auto_free(bad_signature_probe))

    var injected := bool(composition_root.call("InjectNode", bad_signature_probe))
    assert_bool(injected).is_false()
    assert_bool(bool(composition_root.call("HasInjectionErrors"))).is_true()

    var injection_errors = composition_root.call("InjectionErrors")
    assert_int(injection_errors.size()).is_greater(0)
    assert_str(str(injection_errors[0])).contains("invalid hook signature")
    assert_str(str(injection_errors[0])).contains("BadSignatureProbe")
    if composition_root.has_method("ClearInjectionErrors"):
        composition_root.call("ClearInjectionErrors")
