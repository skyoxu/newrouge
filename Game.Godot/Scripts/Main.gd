extends Control

@onready var _label: Label = $VBox/Output
var _score: int = 0
var _hp: int = 100
const DIFFICULTY_SELECT_SCENE := "res://Game.Godot/Scenes/UI/DifficultySelect.tscn"
const CHARACTER_SELECT_SCENE := "res://Game.Godot/Scenes/UI/CharacterSelect.tscn"
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE := "res://Game.Godot/Scenes/Combat.tscn"
const EVENT_SCENE := "res://Game.Godot/Scenes/Event.tscn"
const SHOP_SCENE := "res://Game.Godot/Scenes/Shop.tscn"
const REST_SCENE := "res://Game.Godot/Scenes/Rest.tscn"
const REWARD_SCENE := "res://Game.Godot/Scenes/Reward.tscn"
const LEGACY_START_SCENE := "res://Game.Godot/Scenes/Screens/StartScreen.tscn"
const DEMO_SCENE := "res://Game.Godot/Examples/Screens/DemoScreen.tscn"
const _ROUTABLE_NODE_SCENES := [COMBAT_SCENE, EVENT_SCENE, SHOP_SCENE, REST_SCENE]
const _REWARD_ENTRY_SCENES := [COMBAT_SCENE, EVENT_SCENE]

var _map_route_completed_nodes: int = 0
var _map_route_last_feedback: String = ""
var _map_route_last_selected_node_id: String = ""
var _reward_route_pending: bool = false
var _reward_route_resolved: bool = false

func _ready() -> void:
    print("[TEMPLATE_SMOKE_READY] Main scene initialized")
    var db = get_node_or_null("/root/SqlDb")
    if db != null:
        var ok = db.TryOpen("user://data/game.db")
        if not ok:
            print("[DB] open failed: ", str(db.LastError))
        else:
            print("[DB] opened at user://data/game.db")
    $VBox/PublishBtn.pressed.connect(_on_publish)
    $VBox/SaveLoadBtn.pressed.connect(_on_save_load)
    $VBox/LogBtn.pressed.connect(_on_log)
    if has_node("VBox/AddScoreBtn"):
        $VBox/AddScoreBtn.pressed.connect(_on_add_score)
    if has_node("VBox/LoseHpBtn"):
        $VBox/LoseHpBtn.pressed.connect(_on_lose_hp)
    # Listen to UI menu events to start/quit game
    var bus = get_node_or_null("/root/EventBus")
    if bus != null:
        bus.connect("DomainEventEmitted", Callable(self, "_on_domain_event"))

func _exit_tree() -> void:
    var bus = get_node_or_null("/root/EventBus")
    if bus == null:
        return
    var callable := Callable(self, "_on_domain_event")
    if bus.is_connected("DomainEventEmitted", callable):
        bus.disconnect("DomainEventEmitted", callable)

func _on_publish() -> void:
    var bus = get_node_or_null("/root/EventBus")
    if bus == null:
        _label.text = "EventBus not found"
        return
    bus.PublishSimple("demo.event", "ui", "{\"msg\":\"hello\"}")
    _label.text = "Published demo.event"

func _on_save_load() -> void:
    var ds = get_node_or_null("/root/DataStore")
    if ds == null:
        _label.text = "DataStore not found"
        return
    var key = "demo_save"
    var json = "{\"ts\":" + str(Time.get_unix_time_from_system()) + "}"
    ds.SaveSync(key, json)
    var loaded = ds.LoadSync(key)
    _label.text = "Loaded: " + str(loaded)

func _on_log() -> void:
    var logger = get_node_or_null("/root/Logger")
    if logger == null:
        _label.text = "Logger not found"
        return
    logger.Info("Hello from Main.gd")
    _label.text = "Logged to console"

func _bus():
    return get_node_or_null("/root/EventBus")

func _on_add_score() -> void:
    _score += 10
    var demo = get_node_or_null("/root/Main/EngineDemo")
    if demo != null and demo.has_method("AddScore"):
        demo.AddScore(10)
    else:
        var bus = _bus()
        if bus != null:
            bus.PublishSimple("core.score.updated", "ui", "{\"value\":%d}" % _score)
    _label.text = "Score = %d" % _score

func _on_lose_hp() -> void:
    _hp = max(0, _hp - 5)
    var demo = get_node_or_null("/root/Main/EngineDemo")
    if demo != null and demo.has_method("ApplyDamage"):
        demo.ApplyDamage(5)
    else:
        var bus = _bus()
        if bus != null:
            bus.PublishSimple("core.health.updated", "ui", "{\"value\":%d}" % _hp)
    _label.text = "HP = %d" % _hp

func _on_domain_event(type: String, source: String, data_json: String, id: String, spec: String, ct: String, ts: String) -> void:
    var nav = _resolve_navigator()
    if type == "ui.menu.start":
        var demo = get_node_or_null("/root/Main/EngineDemo")
        if demo != null and demo.has_method("StartGame"):
            demo.StartGame()
        _switch_to(nav, DIFFICULTY_SELECT_SCENE)
    elif type == "core.run.difficulty.selected":
        _switch_to(nav, CHARACTER_SELECT_SCENE)
    elif type == "core.run.character.selected":
        _switch_to(nav, MAP_SCENE)
    elif type == "ui.menu.settings":
        var sp = get_node_or_null("/root/Main/SettingsPanel")
        if sp != null and sp.has_method("ShowPanel"):
            sp.ShowPanel()
    elif type == "ui.menu.quit":
        get_tree().quit()

func _switch_to(nav: Node, scene_path: String) -> void:
    if nav == null or not nav.has_method("SwitchTo"):
        return
    if ResourceLoader.exists(scene_path):
        nav.SwitchTo(scene_path)

func _resolve_navigator() -> Node:
    var nav = get_node_or_null("ScreenNavigator")
    if nav != null:
        return nav
    return get_node_or_null("/root/Main/ScreenNavigator")

func _resolve_map_node_scene(node_type: String) -> String:
    var normalized := node_type.strip_edges().to_lower()
    if normalized == "combat":
        return COMBAT_SCENE
    if normalized == "event":
        return EVENT_SCENE
    if normalized == "shop":
        return SHOP_SCENE
    if normalized == "rest":
        return REST_SCENE
    return ""

func StartMapNodeRouteForTest(node_id: String, node_type: String, reachable: bool, block_reason: String = "") -> Dictionary:
    var nav = _resolve_navigator()
    if nav == null:
        _map_route_last_feedback = "Navigator unavailable."
        return {"ok": false, "reason": "navigator-missing", "scene_path": "", "flow": ""}

    var current_scene := ""
    if nav.has_method("GetCurrentScenePathForTest"):
        current_scene = str(nav.call("GetCurrentScenePathForTest"))
    if current_scene != MAP_SCENE:
        _map_route_last_feedback = "Route entry requires the current scene to be Map."
        return {"ok": false, "reason": "not-on-map", "scene_path": current_scene, "flow": ""}

    if not reachable:
        _map_route_last_feedback = block_reason if not block_reason.strip_edges().is_empty() else "Node is unreachable."
        return {"ok": false, "reason": _map_route_last_feedback, "scene_path": current_scene, "flow": ""}

    var destination := _resolve_map_node_scene(node_type)
    if destination.is_empty():
        _map_route_last_feedback = "No owned flow for node type."
        return {"ok": false, "reason": "unsupported-node-type", "scene_path": current_scene, "flow": ""}

    _map_route_last_feedback = ""
    _map_route_last_selected_node_id = node_id
    _switch_to(nav, destination)
    return {"ok": true, "reason": "", "scene_path": destination, "flow": node_type.strip_edges().to_lower()}

func CompleteMapNodeFlowForTest() -> Dictionary:
    var nav = _resolve_navigator()
    if nav == null:
        return {"ok": false, "reason": "navigator-missing", "scene_path": "", "completed_node_count": _map_route_completed_nodes}

    var current_scene := ""
    if nav.has_method("GetCurrentScenePathForTest"):
        current_scene = str(nav.call("GetCurrentScenePathForTest"))
    if _REWARD_ENTRY_SCENES.has(current_scene):
        _reward_route_pending = true
        _reward_route_resolved = false
        _switch_to(nav, REWARD_SCENE)
        _map_route_last_feedback = ""
        return {"ok": true, "reason": "", "scene_path": REWARD_SCENE, "completed_node_count": _map_route_completed_nodes}

    if not _ROUTABLE_NODE_SCENES.has(current_scene):
        _map_route_last_feedback = "No node flow in progress."
        return {"ok": false, "reason": "no-node-flow-in-progress", "scene_path": current_scene, "completed_node_count": _map_route_completed_nodes}

    _map_route_completed_nodes += 1
    _switch_to(nav, MAP_SCENE)
    _map_route_last_feedback = ""
    return {"ok": true, "reason": "", "scene_path": MAP_SCENE, "completed_node_count": _map_route_completed_nodes}

func GetMapRouteCompletedNodeCountForTest() -> int:
    return _map_route_completed_nodes

func GetMapRouteLastFeedbackForTest() -> String:
    return _map_route_last_feedback

func ResetMapRouteProgressForTest() -> void:
    _map_route_completed_nodes = 0
    _map_route_last_feedback = ""
    _map_route_last_selected_node_id = ""
    _reward_route_pending = false
    _reward_route_resolved = false

func ResolveRewardForTest(action: String) -> Dictionary:
    var nav = _resolve_navigator()
    if nav == null:
        return {"ok": false, "reason": "navigator-missing", "scene_path": ""}

    var current_scene := ""
    if nav.has_method("GetCurrentScenePathForTest"):
        current_scene = str(nav.call("GetCurrentScenePathForTest"))
    if current_scene != REWARD_SCENE:
        return {"ok": false, "reason": "not-on-reward", "scene_path": current_scene}

    if not _reward_route_pending:
        return {"ok": false, "reason": "reward-route-not-pending", "scene_path": current_scene}
    if _reward_route_resolved:
        return {"ok": false, "reason": "reward-route-already-resolved", "scene_path": current_scene}

    var normalized := action.strip_edges().to_lower()
    if normalized != "confirm" and normalized != "skip":
        return {"ok": false, "reason": "unsupported-action", "scene_path": current_scene}

    _reward_route_resolved = true
    _reward_route_pending = false
    _map_route_completed_nodes += 1
    _switch_to(nav, MAP_SCENE)
    return {"ok": true, "reason": "", "scene_path": MAP_SCENE}

func GetExpectedM1RunEntryRouteForTest() -> Array:
    return [DIFFICULTY_SELECT_SCENE, CHARACTER_SELECT_SCENE, MAP_SCENE]

func GetLegacyRunEntryTargetsForTest() -> Array:
    return [LEGACY_START_SCENE, DEMO_SCENE]
