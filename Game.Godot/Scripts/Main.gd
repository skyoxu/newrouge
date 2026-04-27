extends Control

var _label: Label
var _score: int = 0
const DEFAULT_RUN_HP := 80
const DEFAULT_RUN_GOLD := 180
var _hp: int = DEFAULT_RUN_HP
var _run_hp: int = DEFAULT_RUN_HP
var _run_gold: int = DEFAULT_RUN_GOLD
var _hud_node: CanvasItem
var _hud_visibility_initialized: bool = false
const DIFFICULTY_SELECT_SCENE := "res://Game.Godot/Scenes/UI/DifficultySelect.tscn"
const CHARACTER_SELECT_SCENE := "res://Game.Godot/Scenes/UI/CharacterSelect.tscn"
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const COMBAT_SCENE := "res://Game.Godot/Scenes/Combat.tscn"
const EVENT_SCENE := "res://Game.Godot/Scenes/Event.tscn"
const SHOP_SCENE := "res://Game.Godot/Scenes/Shop.tscn"
const REST_SCENE := "res://Game.Godot/Scenes/Rest.tscn"
const REWARD_SCENE := "res://Game.Godot/Scenes/Reward.tscn"
const REWARD_OFFER_PROVIDER_SCRIPT := preload("res://Game.Godot/Scripts/Reward/RewardOfferProvider.cs")
const LEGACY_START_SCENE := "res://Game.Godot/Scenes/Screens/StartScreen.tscn"
const DEMO_SCENE := "res://Game.Godot/Examples/Screens/DemoScreen.tscn"
const _ROUTABLE_NODE_SCENES := [COMBAT_SCENE, EVENT_SCENE, SHOP_SCENE, REST_SCENE]
const _REWARD_ENTRY_SCENES := [COMBAT_SCENE, EVENT_SCENE]

var _map_route_completed_nodes: int = 0
var _map_route_completed_node_ids: Array[String] = []
var _map_route_last_feedback: String = ""
var _map_route_last_selected_node_id: String = ""
var _map_route_start_invocation_count: int = 0
var _map_route_last_start_destination: String = ""
var _reward_route_pending: bool = false
var _reward_route_resolved: bool = false
var _shop_state_by_node: Dictionary = {}
var _active_shop_node_id: String = ""
var _reward_offer_provider: Node = null
var _reward_offer_by_context: Dictionary = {}
var _reward_offer_active_context_id: String = ""
var _reward_offer_seed_counter: int = 0
var _map_route_last_selected_node_type: String = ""
var _map_route_last_selected_node_floor: int = 1

func _should_show_template_demo_overlay() -> bool:
    var ff = get_node_or_null("/root/FeatureFlags")
    if ff != null and ff.has_method("IsEnabled") and ff.IsEnabled("demo_overlay"):
        return true

    if OS.has_environment("TEMPLATE_DEMO") and str(OS.get_environment("TEMPLATE_DEMO")).to_lower() == "1":
        return true

    return false

func _ready() -> void:
    print("[TEMPLATE_SMOKE_READY] Main scene initialized")
    _hud_node = get_node_or_null("HUD")
    var demo_root = get_node_or_null("VBox")
    if demo_root != null:
        demo_root.visible = _should_show_template_demo_overlay()

    var db = get_node_or_null("/root/SqlDb")
    if db != null:
        var ok = db.TryOpen("user://data/game.db")
        if not ok:
            print("[DB] open failed: ", str(db.LastError))
        else:
            print("[DB] opened at user://data/game.db")

    _label = get_node_or_null("VBox/Output")
    var publish_btn = get_node_or_null("VBox/PublishBtn")
    if publish_btn != null:
        publish_btn.pressed.connect(_on_publish)
    var save_load_btn = get_node_or_null("VBox/SaveLoadBtn")
    if save_load_btn != null:
        save_load_btn.pressed.connect(_on_save_load)
    var log_btn = get_node_or_null("VBox/LogBtn")
    if log_btn != null:
        log_btn.pressed.connect(_on_log)
    var add_score_btn = get_node_or_null("VBox/AddScoreBtn")
    if add_score_btn != null:
        add_score_btn.pressed.connect(_on_add_score)
    var lose_hp_btn = get_node_or_null("VBox/LoseHpBtn")
    if lose_hp_btn != null:
        lose_hp_btn.pressed.connect(_on_lose_hp)

    # Listen to UI menu events to start/quit game
    var bus = get_node_or_null("/root/EventBus")
    if bus != null:
        bus.connect("DomainEventEmitted", Callable(self, "_on_domain_event"))

    _sync_hud_run_resources()
    _update_hud_visibility_for_scene("")
    _ensure_reward_offer_provider()

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
        if _label != null:
            _label.text = "EventBus not found"
        return
    bus.PublishSimple("demo.event", "ui", "{\"msg\":\"hello\"}")
    if _label != null:
        _label.text = "Published demo.event"

func _on_save_load() -> void:
    var ds = get_node_or_null("/root/DataStore")
    if ds == null:
        if _label != null:
            _label.text = "DataStore not found"
        return
    var key = "demo_save"
    var json = "{\"ts\":" + str(Time.get_unix_time_from_system()) + "}"
    ds.SaveSync(key, json)
    var loaded = ds.LoadSync(key)
    if _label != null:
        _label.text = "Loaded: " + str(loaded)

func _on_log() -> void:
    var logger = get_node_or_null("/root/Logger")
    if logger == null:
        if _label != null:
            _label.text = "Logger not found"
        return
    logger.Info("Hello from Main.gd")
    if _label != null:
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
    if _label != null:
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
    if _label != null:
        _label.text = "HP = %d" % _hp

func _on_domain_event(type: String, source: String, data_json: String, id: String, spec: String, ct: String, ts: String) -> void:
    var nav = _resolve_navigator()
    if type == "ui.menu.start":
        _run_hp = DEFAULT_RUN_HP
        _run_gold = DEFAULT_RUN_GOLD
        _score = 0
        _clear_hud_run_summary()
        _sync_hud_run_resources()
        var demo = get_node_or_null("/root/Main/EngineDemo")
        if demo != null and demo.has_method("StartGame"):
            demo.StartGame()
        _switch_to(nav, DIFFICULTY_SELECT_SCENE)
    elif type == "core.run.difficulty.selected":
        _switch_to(nav, CHARACTER_SELECT_SCENE)
    elif type == "core.run.character.selected":
        _switch_to(nav, MAP_SCENE)
    elif type == "ui.menu.settings":
        var sp = get_node_or_null("SettingsLayer/SettingsPanel")
        if sp == null:
            sp = get_node_or_null("/root/Main/SettingsLayer/SettingsPanel")
        if sp == null:
            sp = get_node_or_null("/root/Main/SettingsPanel")
        if sp != null and sp.has_method("ShowPanel"):
            sp.ShowPanel()
    elif type == "ui.menu.quit":
        get_tree().quit()

func _switch_to(nav: Node, scene_path: String) -> void:
    if nav == null or not nav.has_method("SwitchTo"):
        return
    if ResourceLoader.exists(scene_path):
        var switched := bool(nav.SwitchTo(scene_path))
        if switched:
            _update_hud_visibility_for_scene(scene_path)

func _sync_hud_run_resources() -> void:
    if _hud_node == null:
        return
    if _hud_node.has_method("SetHealth"):
        _hud_node.call("SetHealth", _run_hp)
    if _hud_node.has_method("SetGold"):
        _hud_node.call("SetGold", _run_gold)
    if _hud_node.has_method("SetScore"):
        _hud_node.call("SetScore", _score)

func _clear_hud_run_summary() -> void:
    if _hud_node == null:
        return
    var panel := _hud_node.get_node_or_null("RunSummaryPanel")
    if panel != null:
        panel.visible = false

func _is_gameplay_scene(scene_path: String) -> bool:
    if scene_path == MAP_SCENE:
        return true
    return _ROUTABLE_NODE_SCENES.has(scene_path) or scene_path == REWARD_SCENE

func _update_hud_visibility_for_scene(scene_path: String) -> void:
    if _hud_node == null:
        return
    var normalized := scene_path.strip_edges()
    if normalized.is_empty():
        _hud_node.visible = false
        _hud_visibility_initialized = true
        return
    _hud_node.visible = _is_gameplay_scene(normalized)
    _hud_visibility_initialized = true

func _show_run_summary_and_return_to_main_menu(outcome: String, node_progress: int, reason: String) -> void:
    var nav = _resolve_navigator()
    var current_scene := ""
    if nav != null and nav.has_method("GetCurrentScenePathForTest"):
        current_scene = str(nav.call("GetCurrentScenePathForTest"))

    if nav != null and current_scene != MAP_SCENE:
        _switch_to(nav, MAP_SCENE)

    if _hud_node != null:
        _hud_node.visible = true
        if _hud_node.has_method("ShowRunSummaryForTest"):
            _hud_node.call("ShowRunSummaryForTest", outcome, node_progress, reason)

    var menu = get_node_or_null("MenuLayer/MainMenu")
    if menu != null:
        if menu.has_method("ShowMenu"):
            menu.call("ShowMenu")
        else:
            menu.visible = true

func IsMainMenuVisibleForTest() -> bool:
    var menu = get_node_or_null("MenuLayer/MainMenu")
    if menu == null:
        return false
    return bool(menu.visible)

func HandleCombatDefeatForTest(reason: String = "Player HP reached zero.") -> Dictionary:
    _run_hp = 0
    _reward_route_pending = false
    _reward_route_resolved = false
    _active_shop_node_id = ""
    _sync_hud_run_resources()
    _show_run_summary_and_return_to_main_menu("Defeat", _map_route_completed_nodes, reason)
    return {
        "ok": true,
        "reason": "",
        "scene_path": MAP_SCENE,
        "outcome": "defeat",
        "menu_visible": IsMainMenuVisibleForTest()
    }

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

func _resolve_node_floor(node_id: String) -> int:
    var normalized := node_id.strip_edges().to_lower()
    if normalized.begins_with("boss"):
        return 5
    var dash := normalized.find("-")
    if dash > 0:
        var digits := ""
        for ch in normalized.substr(dash + 1):
            if ch >= "0" and ch <= "9":
                digits += ch
            else:
                break
        if not digits.is_empty():
            return maxi(1, int(digits))
    return maxi(1, _map_route_completed_nodes + 1)

func _build_reward_context_id(node_id: String, node_type: String, floor: int) -> String:
    var normalized_id := node_id.strip_edges()
    var normalized_type := node_type.strip_edges().to_lower()
    if normalized_id.is_empty():
        normalized_id = "reward-node"
    if normalized_type.is_empty():
        normalized_type = "combat"
    return "act1:%s:floor%d:%s" % [normalized_type, floor, normalized_id]

func _build_reward_offer_seed(context_id: String) -> int:
    var hash := context_id.hash()
    return int(abs(hash) + _reward_offer_seed_counter)

func _ensure_reward_offer_provider() -> void:
    if _reward_offer_provider != null and is_instance_valid(_reward_offer_provider):
        return
    _reward_offer_provider = REWARD_OFFER_PROVIDER_SCRIPT.new()
    _reward_offer_provider.name = "RewardOfferProvider"
    add_child(_reward_offer_provider)

func _build_first_entry_reward_offer(context_id: String, encounter_type: String, floor: int) -> Array:
    _ensure_reward_offer_provider()
    if _reward_offer_provider == null or not _reward_offer_provider.has_method("BuildFirstEntryOfferForContext"):
        return []
    var stream_position: int = int(max(0, _map_route_completed_nodes))
    var seed := _build_reward_offer_seed(context_id)
    _reward_offer_seed_counter += 1
    var result = _reward_offer_provider.call(
        "BuildFirstEntryOfferForContext",
        1,
        encounter_type,
        seed,
        stream_position,
        3
    )
    if typeof(result) != TYPE_ARRAY:
        return []
    var offers: Array = []
    for item in result:
        if typeof(item) == TYPE_DICTIONARY:
            offers.append((item as Dictionary).duplicate(true))
    return offers

func _ensure_reward_offer_for_active_context() -> Dictionary:
    var context_id := _reward_offer_active_context_id.strip_edges()
    if context_id.is_empty():
        context_id = _build_reward_context_id(
            _map_route_last_selected_node_id,
            _map_route_last_selected_node_type,
            _map_route_last_selected_node_floor
        )
    _reward_offer_active_context_id = context_id
    if _reward_offer_by_context.has(context_id):
        var existing = _reward_offer_by_context[context_id]
        if typeof(existing) == TYPE_DICTIONARY:
            return (existing as Dictionary).duplicate(true)

    var encounter_type := _map_route_last_selected_node_type.strip_edges().to_lower()
    if encounter_type.is_empty():
        encounter_type = "combat"
    if encounter_type == "event":
        encounter_type = "normal"
    elif encounter_type != "combat" and encounter_type != "normal" and encounter_type != "elite" and encounter_type != "boss":
        encounter_type = "normal"
    if encounter_type == "combat":
        encounter_type = "normal"

    var offers := _build_first_entry_reward_offer(context_id, encounter_type, _map_route_last_selected_node_floor)
    var payload := {
        "context_id": context_id,
        "act_id": 1,
        "encounter_type": encounter_type,
        "floor": _map_route_last_selected_node_floor,
        "offers": offers,
        "source": "shared-card-pool"
    }
    _reward_offer_by_context[context_id] = payload.duplicate(true)
    return payload

func GetRewardOfferSnapshotForScene() -> Dictionary:
    return _ensure_reward_offer_for_active_context()

func _build_default_shop_state(node_id: String) -> Dictionary:
    var normalized := node_id.strip_edges()
    if normalized.is_empty():
        normalized = "shop-default"
    var offer_a := "%s_offer_a" % normalized
    var offer_b := "%s_offer_b" % normalized
    var offer_c := "%s_offer_c" % normalized
    return {
        "shop_id": normalized,
        "gold": 180,
        "offers": [
            {"id": offer_a, "price": 60, "taken": false},
            {"id": offer_b, "price": 90, "taken": false},
            {"id": offer_c, "price": 240, "taken": false}
        ],
        "owned_offer_ids": [],
        "removable_cards": ["curse_doubt"],
        "reforge_targets": [offer_b],
        "removed_outcome": ""
    }

func _activate_shop_route_state(node_id: String) -> void:
    var key := node_id.strip_edges()
    if key.is_empty():
        key = "shop-default"
    _active_shop_node_id = key
    if not _shop_state_by_node.has(key):
        _shop_state_by_node[key] = _build_default_shop_state(key)

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
    _map_route_last_selected_node_type = node_type.strip_edges().to_lower()
    _map_route_last_selected_node_floor = _resolve_node_floor(node_id)
    _map_route_start_invocation_count += 1
    _map_route_last_start_destination = destination
    if destination == SHOP_SCENE:
        _activate_shop_route_state(node_id)
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
        _reward_offer_active_context_id = _build_reward_context_id(
            _map_route_last_selected_node_id,
            _map_route_last_selected_node_type,
            _map_route_last_selected_node_floor
        )
        _ensure_reward_offer_for_active_context()
        _switch_to(nav, REWARD_SCENE)
        _map_route_last_feedback = ""
        return {"ok": true, "reason": "", "scene_path": REWARD_SCENE, "completed_node_count": _map_route_completed_nodes}

    if not _ROUTABLE_NODE_SCENES.has(current_scene):
        _map_route_last_feedback = "No node flow in progress."
        return {"ok": false, "reason": "no-node-flow-in-progress", "scene_path": current_scene, "completed_node_count": _map_route_completed_nodes}

    _map_route_completed_nodes += 1
    if not _map_route_last_selected_node_id.strip_edges().is_empty():
        _map_route_completed_node_ids.append(_map_route_last_selected_node_id)
    if current_scene == SHOP_SCENE:
        _active_shop_node_id = ""
    _switch_to(nav, MAP_SCENE)
    _map_route_last_feedback = ""
    return {"ok": true, "reason": "", "scene_path": MAP_SCENE, "completed_node_count": _map_route_completed_nodes}

func GetMapRouteCompletedNodeCountForTest() -> int:
    return _map_route_completed_nodes

func GetMapRouteCompletedNodeIdsForTest() -> Array:
    return _map_route_completed_node_ids.duplicate()

func GetMapRouteLastSelectedNodeIdForTest() -> String:
    return _map_route_last_selected_node_id

func GetMapRouteLastFeedbackForTest() -> String:
    return _map_route_last_feedback

func ResetMapRouteProgressForTest() -> void:
    _map_route_completed_nodes = 0
    _map_route_completed_node_ids.clear()
    _map_route_last_feedback = ""
    _map_route_last_selected_node_id = ""
    _reward_route_pending = false
    _reward_route_resolved = false
    _active_shop_node_id = ""
    _shop_state_by_node.clear()
    _map_route_start_invocation_count = 0
    _map_route_last_start_destination = ""
    _map_route_last_selected_node_type = ""
    _map_route_last_selected_node_floor = 1
    _reward_offer_by_context.clear()
    _reward_offer_active_context_id = ""
    _reward_offer_seed_counter = 0

func GetMapRouteStartInvocationCountForTest() -> int:
    return _map_route_start_invocation_count

func GetMapRouteLastStartDestinationForTest() -> String:
    return _map_route_last_start_destination

func GetActiveShopStateForScene() -> Dictionary:
    if _active_shop_node_id.is_empty():
        return {}
    if not _shop_state_by_node.has(_active_shop_node_id):
        return {}
    var state = _shop_state_by_node.get(_active_shop_node_id, {})
    if typeof(state) != TYPE_DICTIONARY:
        return {}
    return (state as Dictionary).duplicate(true)

func ApplyShopStateForScene(state: Dictionary) -> bool:
    if _active_shop_node_id.is_empty():
        return false
    _shop_state_by_node[_active_shop_node_id] = state.duplicate(true)
    return true

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
    var is_boss_completion := _map_route_last_selected_node_id.strip_edges().to_lower().begins_with("boss")
    if is_boss_completion:
        _show_run_summary_and_return_to_main_menu("Victory", _map_route_completed_nodes, "Boss defeated.")
        return {
            "ok": true,
            "reason": "",
            "scene_path": MAP_SCENE,
            "outcome": "victory",
            "menu_visible": IsMainMenuVisibleForTest()
        }

    _switch_to(nav, MAP_SCENE)
    return {"ok": true, "reason": "", "scene_path": MAP_SCENE}

func GetExpectedM1RunEntryRouteForTest() -> Array:
    return [DIFFICULTY_SELECT_SCENE, CHARACTER_SELECT_SCENE, MAP_SCENE]

func GetLegacyRunEntryTargetsForTest() -> Array:
    return [LEGACY_START_SCENE, DEMO_SCENE]
