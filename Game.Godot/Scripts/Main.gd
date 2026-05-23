extends Control

var _label: Label
var _score: int = 0
const DEFAULT_RUN_HP := 80
const DEFAULT_RUN_GOLD := 180
var _hp: int = DEFAULT_RUN_HP
var _run_hp: int = DEFAULT_RUN_HP
var _run_gold: int = DEFAULT_RUN_GOLD
var _run_deck_card_ids: Array[String] = []
var _run_relic_ids: Array[String] = []
var _run_consumable_ids: Array[String] = []
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
const SETTLEMENT_SCENE := "res://Game.Godot/Scenes/Settlement.tscn"
const START_SCENE_OVERRIDE_ENV := "NEWROUGE_START_SCENE"
const LEGACY_START_SCENE := "res://Game.Godot/Scenes/Screens/StartScreen.tscn"
const DEMO_SCENE := "res://Game.Godot/Examples/Screens/DemoScreen.tscn"
const _ROUTABLE_NODE_SCENES := [COMBAT_SCENE, EVENT_SCENE, SHOP_SCENE, REST_SCENE]
const _REWARD_ENTRY_SCENES := [COMBAT_SCENE, EVENT_SCENE]
const ACT_CONFIG_CANDIDATE_PATHS := [
    "res://Game.Core/Data/act1-config.json",
    "res://../Game.Core/Data/act1-config.json"
]
const CARD_DEFINITION_CANDIDATE_PATHS := [
    "res://Game.Core/Data/m1-card-definitions.json",
    "res://../Game.Core/Data/m1-card-definitions.json"
]
const STARTING_DECK_CANDIDATE_PATHS := [
    "res://Game.Core/Data/m1-warrior-starting-deck.json",
    "res://../Game.Core/Data/m1-warrior-starting-deck.json"
]
const REWARD_POOL_CANDIDATE_PATHS := [
    "res://Game.Core/Data/m1-reward-pools.json",
    "res://../Game.Core/Data/m1-reward-pools.json"
]
const RELIC_DEFINITION_CANDIDATE_PATHS := [
    "res://Game.Core/Data/m1-relic-definitions.json",
    "res://../Game.Core/Data/m1-relic-definitions.json"
]
const EN_TRANSLATIONS_FILE := "res://Game.Godot/Translations/en.csv"
const ZH_TRANSLATIONS_FILE := "res://Game.Godot/Translations/zh-CN.csv"
const REWARD_CARD_ART_CANDIDATE_PATHS := [
    "res://Game.Godot/Assets/Textures/Cards/card_spore_slash.png",
    "res://../Game.Godot/Assets/Textures/Cards/card_spore_slash.png"
]
const REWARD_MODIFIER_PIPELINE_BRIDGE_SCRIPT := "res://Game.Godot/Scripts/Reward/RewardEntryModifierPipelineBridge.cs"

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
var _reward_offer_by_context: Dictionary = {}
var _reward_offer_active_context_id: String = ""
var _reward_offer_seed_counter: int = 0
var _reward_selection_state_by_context: Dictionary = {}
var _reward_runtime_modifiers_by_context: Dictionary = {}
var _reward_modifier_pipeline = null
var _latest_reward_modifier_failure: Dictionary = {}
var _map_route_last_selected_node_type: String = ""
var _map_route_last_selected_node_floor: int = 1
var _startup_scene_override_for_test: String = ""
var _pending_settlement_payload: Dictionary = {}
var _card_text_catalog: Dictionary = {}
var _relic_text_catalog: Dictionary = {}
var _translation_text_catalog: Dictionary = {}

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
    _reset_run_deck_for_test()
    call_deferred("_apply_startup_scene_override_if_needed")

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

func _on_domain_event(type: String, _source: String, _data_json: String, _id: String, _spec: String, _ct: String, _ts: String) -> void:
    var nav = _resolve_navigator()
    if type == "ui.menu.start":
        _run_hp = DEFAULT_RUN_HP
        _run_gold = DEFAULT_RUN_GOLD
        _score = 0
        _reset_run_deck_for_test()
        _run_relic_ids.clear()
        _run_consumable_ids.clear()
        _clear_reward_runtime_modifier_state()
        _clear_hud_run_summary()
        _sync_hud_run_resources()
        var demo = get_node_or_null("/root/Main/EngineDemo")
        if demo != null and demo.has_method("StartGame"):
            demo.StartGame()
        _switch_to(nav, DIFFICULTY_SELECT_SCENE)
    elif type == "core.run.resumed":
        _handle_continue_resume(nav)
    elif type == "core.run.difficulty.selected":
        _switch_to(nav, CHARACTER_SELECT_SCENE)
    elif type == "core.run.character.selected":
        _seed_run_deck_from_starting_deck_if_empty()
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

func _handle_continue_resume(nav: Node) -> void:
    if nav == null:
        return
    var target := _resolve_continue_resume_scene()
    if target.is_empty():
        return
    _switch_to(nav, target)

func SetStartupSceneOverrideForTest(scene_key: String) -> void:
    _startup_scene_override_for_test = scene_key.strip_edges()

func ApplyStartupSceneOverrideForTest(scene_key: String) -> bool:
    _startup_scene_override_for_test = scene_key.strip_edges()
    return _apply_startup_scene_override_if_needed()

func GetStartupSceneOverrideForTest() -> String:
    return _resolve_startup_scene_override_key()

func _apply_startup_scene_override_if_needed() -> bool:
    var override_key := _resolve_startup_scene_override_key()
    if override_key.is_empty():
        return false

    var destination := _resolve_debug_start_scene(override_key)
    if destination.is_empty():
        return false

    var nav = _resolve_navigator()
    if nav == null:
        return false

    _set_main_menu_visible(false)
    _clear_hud_run_summary()
    _sync_hud_run_resources()
    _switch_to(nav, destination)
    return true

func _resolve_startup_scene_override_key() -> String:
    if not _startup_scene_override_for_test.is_empty():
        return _startup_scene_override_for_test.to_lower()

    if OS.has_environment(START_SCENE_OVERRIDE_ENV):
        return str(OS.get_environment(START_SCENE_OVERRIDE_ENV)).strip_edges().to_lower()

    return ""

func _resolve_debug_start_scene(scene_key: String) -> String:
    var normalized := scene_key.strip_edges().to_lower()
    if normalized == "combat":
        return COMBAT_SCENE
    if normalized == "map":
        return MAP_SCENE
    if normalized == "event":
        return EVENT_SCENE
    if normalized == "shop":
        return SHOP_SCENE
    if normalized == "rest":
        return REST_SCENE
    if normalized == "reward":
        return REWARD_SCENE
    return ""

func _set_main_menu_visible(show_menu: bool) -> void:
    var menu = get_node_or_null("MenuLayer/MainMenu")
    if menu == null:
        return
    if show_menu:
        if menu.has_method("ShowMenu"):
            menu.call("ShowMenu")
        else:
            menu.visible = true
        return
    if menu.has_method("HideMenu"):
        menu.call("HideMenu")
    else:
        menu.visible = false

func _resolve_continue_resume_scene() -> String:
    var autosave_path := "user://autosave_slot.json"
    if not FileAccess.file_exists(autosave_path):
        return ""
    var file := FileAccess.open(autosave_path, FileAccess.READ)
    if file == null:
        return ""
    var payload := str(file.get_as_text()).strip_edges()
    if payload.is_empty():
        return ""
    var parsed: Variant = JSON.parse_string(payload)
    if not (parsed is Dictionary):
        return ""
    var envelope := parsed as Dictionary
    var save_point_id := str(envelope.get("save_point_id", "")).to_lower()
    if save_point_id.begins_with("combat"):
        return COMBAT_SCENE
    if save_point_id.begins_with("map") or save_point_id.begins_with("node_pre_enter") or save_point_id == "menu":
        return MAP_SCENE
    return ""

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

func _build_settlement_payload(outcome: String, node_progress: int, reason: String) -> Dictionary:
    return {
        "outcome": outcome.strip_edges(),
        "node_progress": node_progress,
        "reason": reason.strip_edges(),
        "title": "Run Settlement",
        "action_label": "Return to Main Menu"
    }

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

func _show_settlement_scene(outcome: String, node_progress: int, reason: String) -> void:
    var nav = _resolve_navigator()
    if nav == null:
        return
    _pending_settlement_payload = _build_settlement_payload(outcome, node_progress, reason)
    _clear_hud_run_summary()
    _set_main_menu_visible(false)
    _switch_to(nav, SETTLEMENT_SCENE)

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
    _show_settlement_scene("Defeat", _map_route_completed_nodes, reason)
    return {
        "ok": true,
        "reason": "",
        "scene_path": SETTLEMENT_SCENE,
        "outcome": "defeat",
        "menu_visible": IsMainMenuVisibleForTest()
    }

func GetSettlementPayloadForScene() -> Dictionary:
    return _pending_settlement_payload.duplicate(true)

func ReturnToMainMenuFromSettlementForTest() -> Dictionary:
    var nav = _resolve_navigator()
    if nav == null:
        return {"ok": false, "reason": "navigator-missing", "scene_path": ""}
    if nav.has_method("ClearCurrentSceneForTest"):
        nav.call("ClearCurrentSceneForTest")
    _pending_settlement_payload.clear()
    _clear_hud_run_summary()
    _update_hud_visibility_for_scene("")
    _set_main_menu_visible(true)
    return {"ok": true, "reason": "", "scene_path": "", "menu_visible": IsMainMenuVisibleForTest()}

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

func _build_reward_context_id(node_id: String, node_type: String, floor_index: int) -> String:
    var normalized_id := node_id.strip_edges()
    var normalized_type := node_type.strip_edges().to_lower()
    if normalized_id.is_empty():
        normalized_id = "reward-node"
    if normalized_type.is_empty():
        normalized_type = "combat"
    return "act1:%s:floor%d:%s" % [normalized_type, floor_index, normalized_id]

func _build_reward_offer_seed(context_id: String) -> int:
    var context_hash = context_id.hash()
    return int(abs(context_hash) + _reward_offer_seed_counter)

func _build_first_entry_reward_offer(_context_id: String, _encounter_type: String, _floor_index: int) -> Array:
    var reward_pool_id = _resolve_reward_pool_id_for_active_context()
    var offers: Array = []
    var card_ids = _resolve_first_entry_reward_card_ids(reward_pool_id)
    var index := 0
    for card_id in card_ids:
        index += 1
        offers.append(_build_reward_offer_entry(card_id, index))
    return offers

func _build_reward_entries_for_pool(reward_pool_id: String) -> Array:
    var entries: Array = []
    var reward_pool = _load_reward_pool_definition(reward_pool_id)
    if reward_pool.is_empty():
        return entries
    var entry_config = reward_pool.get("entries", {})
    if typeof(entry_config) != TYPE_DICTIONARY:
        return entries
    var typed_config = entry_config as Dictionary
    _append_reward_entry(entries, "gold", typed_config.get("gold", 0))
    _append_reward_entry(entries, "consumable", typed_config.get("consumable", 0))
    _append_reward_entry(entries, "relic", typed_config.get("relic", 0))
    _append_reward_entry(entries, "common_card_choice", typed_config.get("common_card_choice", 0))
    _append_reward_entry(entries, "rare_card_choice", typed_config.get("rare_card_choice", 0))
    _append_reward_entry(entries, "epic_card_choice", typed_config.get("epic_card_choice", 0))
    return entries

func _append_reward_entry(entries: Array, reward_type: String, config_variant) -> void:
    if typeof(config_variant) == TYPE_INT and int(config_variant) == 0:
        return
    if typeof(config_variant) != TYPE_DICTIONARY:
        return
    var config = (config_variant as Dictionary).duplicate(true)
    entries.append(_build_reward_entry_data(reward_type, config))

func _build_reward_entry_data(reward_type: String, config: Dictionary) -> Dictionary:
    var entry = {
        "entry_id": reward_type,
        "reward_type": reward_type,
        "title": _resolve_reward_entry_title(reward_type, config),
        "tooltip": _resolve_reward_entry_tooltip(reward_type, config),
        "icon_path": _resolve_reward_entry_icon_path(reward_type, config),
        "config": config.duplicate(true)
    }
    if reward_type.ends_with("_card_choice"):
        entry["cards"] = _build_reward_card_choices(str(config.get("pool_id", "")).strip_edges(), int(config.get("pick", 3)))
    return entry

func _build_reward_card_choices(pool_id: String, pick_count: int) -> Array:
    var cards: Array = []
    var all_cards = _load_reward_card_choice_pool(pool_id)
    if all_cards.is_empty():
        return cards
    var index := 0
    for card_id in all_cards:
        if index >= pick_count:
            break
        index += 1
        cards.append(_build_reward_offer_entry(card_id, index))
    return cards

func _resolve_reward_entry_title(reward_type: String, config: Dictionary) -> String:
    match reward_type:
        "gold":
            return "Gold x%s" % str(config.get("amount", 0))
        "consumable":
            return str(config.get("name", "Consumable")).strip_edges()
        "relic":
            return _resolve_relic_display_name(str(config.get("relic_id", "")).strip_edges())
        "common_card_choice":
            return "Common Cards 3-Choice"
        "rare_card_choice":
            return "Rare Cards 3-Choice"
        "epic_card_choice":
            return "Epic Cards 3-Choice"
        _:
            return reward_type

func _resolve_reward_entry_tooltip(reward_type: String, config: Dictionary) -> String:
    match reward_type:
        "gold":
            return "Gain %s gold." % str(config.get("amount", 0))
        "consumable":
            return str(config.get("description", "")).strip_edges()
        "relic":
            return _resolve_relic_display_description(str(config.get("relic_id", "")).strip_edges())
        "common_card_choice":
            return "Open a common card reward pack and pick one card."
        "rare_card_choice":
            return "Open a rare card reward pack and pick one card."
        "epic_card_choice":
            return "Open an epic card reward pack and pick one card."
        _:
            return ""

func _resolve_reward_entry_icon_path(reward_type: String, _config: Dictionary) -> String:
    match reward_type:
        "gold":
            return "res://Game.Godot/Assets/Textures/Cards/card_reward_heavy_strike.png"
        "consumable":
            return "res://Game.Godot/Assets/Textures/Cards/card_reward_iron_wave.png"
        "relic":
            return "res://Game.Godot/Assets/Textures/Cards/card_reward_rage_surge.png"
        "common_card_choice":
            return "res://Game.Godot/Assets/Textures/Cards/card_reward_heavy_strike.png"
        "rare_card_choice":
            return "res://Game.Godot/Assets/Textures/Cards/card_reward_shield_wall.png"
        "epic_card_choice":
            return "res://Game.Godot/Assets/Textures/Cards/card_reward_rage_surge.png"
        _:
            return "res://Game.Godot/Assets/Textures/Cards/card_reward_defend.png"

func _load_reward_pool_definition(reward_pool_id: String) -> Dictionary:
    if reward_pool_id.is_empty():
        return {}
    for candidate_path in REWARD_POOL_CANDIDATE_PATHS:
        if not FileAccess.file_exists(candidate_path):
            continue
        var file := FileAccess.open(candidate_path, FileAccess.READ)
        if file == null:
            continue
        var payload := str(file.get_as_text()).strip_edges()
        file.close()
        if payload.is_empty():
            continue
        var parsed = JSON.parse_string(payload)
        if typeof(parsed) != TYPE_DICTIONARY:
            continue
        var root = parsed as Dictionary
        var pools_variant = root.get("reward_pools", [])
        if typeof(pools_variant) != TYPE_ARRAY:
            continue
        for pool_variant in pools_variant:
            if typeof(pool_variant) != TYPE_DICTIONARY:
                continue
            var pool = pool_variant as Dictionary
            if str(pool.get("id", "")).strip_edges() == reward_pool_id:
                return pool.duplicate(true)
    return {}

func _load_relic_text_catalog() -> Dictionary:
    for candidate_path in RELIC_DEFINITION_CANDIDATE_PATHS:
        if not FileAccess.file_exists(candidate_path):
            continue
        var file := FileAccess.open(candidate_path, FileAccess.READ)
        if file == null:
            continue
        var payload := str(file.get_as_text()).strip_edges()
        file.close()
        if payload.is_empty():
            continue
        var parsed = JSON.parse_string(payload)
        if typeof(parsed) != TYPE_DICTIONARY:
            continue
        var root = parsed as Dictionary
        var relics_variant = root.get("relics", [])
        if typeof(relics_variant) != TYPE_ARRAY:
            continue
        var catalog: Dictionary = {}
        for relic_variant in relics_variant:
            if typeof(relic_variant) != TYPE_DICTIONARY:
                continue
            var relic = relic_variant as Dictionary
            var id = str(relic.get("id", "")).strip_edges()
            if id.is_empty():
                continue
            catalog[id] = {
                "name_key": str(relic.get("name_key", id + ".name")).strip_edges(),
                "description_key": str(relic.get("description_key", id + ".description")).strip_edges()
            }
        return catalog
    return {}

func _resolve_relic_display_name(relic_id: String) -> String:
    var normalized = relic_id.strip_edges()
    if normalized.is_empty():
        return "Relic"
    if _relic_text_catalog.is_empty():
        _relic_text_catalog = _load_relic_text_catalog()
    if _relic_text_catalog.has(normalized):
        var metadata = _relic_text_catalog[normalized]
        if typeof(metadata) == TYPE_DICTIONARY:
            return _resolve_card_display_text(str((metadata as Dictionary).get("name_key", normalized)).strip_edges())
    return normalized

func _resolve_relic_display_description(relic_id: String) -> String:
    var normalized = relic_id.strip_edges()
    if normalized.is_empty():
        return ""
    if _relic_text_catalog.is_empty():
        _relic_text_catalog = _load_relic_text_catalog()
    if _relic_text_catalog.has(normalized):
        var metadata = _relic_text_catalog[normalized]
        if typeof(metadata) == TYPE_DICTIONARY:
            return _resolve_card_display_text(str((metadata as Dictionary).get("description_key", normalized)).strip_edges())
    return "Gain relic %s." % normalized

func _load_reward_card_choice_pool(pool_id: String) -> Array[String]:
    if pool_id.is_empty():
        return []
    for candidate_path in REWARD_POOL_CANDIDATE_PATHS:
        if not FileAccess.file_exists(candidate_path):
            continue
        var file := FileAccess.open(candidate_path, FileAccess.READ)
        if file == null:
            continue
        var payload := str(file.get_as_text()).strip_edges()
        file.close()
        if payload.is_empty():
            continue
        var parsed = JSON.parse_string(payload)
        if typeof(parsed) != TYPE_DICTIONARY:
            continue
        var root = parsed as Dictionary
        var pools_variant = root.get("card_choice_pools", [])
        if typeof(pools_variant) != TYPE_ARRAY:
            continue
        for pool_variant in pools_variant:
            if typeof(pool_variant) != TYPE_DICTIONARY:
                continue
            var pool = pool_variant as Dictionary
            if str(pool.get("id", "")).strip_edges() != pool_id:
                continue
            var cards_variant = pool.get("cards", [])
            if typeof(cards_variant) != TYPE_ARRAY:
                return []
            var result: Array[String] = []
            for card_variant in (cards_variant as Array):
                result.append(str(card_variant).strip_edges())
            return result
    return []

func _resolve_first_entry_reward_card_ids(reward_pool_id: String) -> Array[String]:
    if reward_pool_id == "reward.act1.normal_1":
        return [
            "card.warrior.heavy_strike",
            "card.warrior.cleave",
            "card.warrior.defend"
        ]
    return []

func _build_reward_offer_entry(card_id: String, offer_index: int) -> Dictionary:
    var metadata = _resolve_card_text_metadata(card_id)
    var name_key = str(metadata.get("name_key", card_id + ".name")).strip_edges()
    var description_key = str(metadata.get("description_key", card_id + ".description")).strip_edges()
    var display_name = _resolve_card_display_text(name_key)
    var display_description = _resolve_card_display_text(description_key)
    return {
        "id": card_id,
        "name_key": name_key,
        "description_key": description_key,
        "name": display_name,
        "description": display_description,
        "display_name": display_name,
        "display_description": display_description,
        "art_path": _resolve_card_art_path(card_id),
        "form": metadata.get("form", "Base"),
        "selectable": true,
        "source": "shared-card-pool",
        "offer_index": offer_index
    }

func _resolve_card_text_metadata(card_id: String) -> Dictionary:
    if _card_text_catalog.is_empty():
        _card_text_catalog = _load_card_text_catalog()
    if _card_text_catalog.has(card_id):
        var metadata = _card_text_catalog[card_id]
        if typeof(metadata) == TYPE_DICTIONARY:
            return (metadata as Dictionary).duplicate(true)
    return {
        "name_key": card_id + ".name",
        "description_key": card_id + ".description",
        "form": "Base"
    }

func _load_card_text_catalog() -> Dictionary:
    for candidate_path in CARD_DEFINITION_CANDIDATE_PATHS:
        if not FileAccess.file_exists(candidate_path):
            continue
        var file := FileAccess.open(candidate_path, FileAccess.READ)
        if file == null:
            continue
        var payload := str(file.get_as_text()).strip_edges()
        file.close()
        if payload.is_empty():
            continue
        var parsed = JSON.parse_string(payload)
        if typeof(parsed) != TYPE_DICTIONARY:
            continue
        var root := parsed as Dictionary
        var cards_variant = root.get("cards", [])
        if typeof(cards_variant) != TYPE_ARRAY:
            continue
        var catalog: Dictionary = {}
        for card_variant in cards_variant:
            if typeof(card_variant) != TYPE_DICTIONARY:
                continue
            var card = card_variant as Dictionary
            var id = str(card.get("id", "")).strip_edges()
            if id.is_empty():
                continue
            catalog[id] = {
                "name_key": str(card.get("name_key", id + ".name")).strip_edges(),
                "description_key": str(card.get("description_key", id + ".description")).strip_edges(),
                "form": str(card.get("default_form", "Base")).strip_edges()
            }
        return catalog
    return {}

func _resolve_card_display_text(key: String) -> String:
    if key.strip_edges().is_empty():
        return ""
    var localized = TranslationServer.translate(key)
    if localized != key and not str(localized).strip_edges().is_empty():
        return str(localized).strip_edges()
    var locale = _normalize_locale(TranslationServer.get_locale())
    var primary = _load_translation_values(_translation_file_for_locale(locale))
    if primary.has(key):
        return str(primary[key]).strip_edges()
    if locale != "en":
        var fallback = _load_translation_values(EN_TRANSLATIONS_FILE)
        if fallback.has(key):
            return str(fallback[key]).strip_edges()
    return key

func _resolve_card_art_path(card_id: String) -> String:
    if card_id == "card.warrior.defend":
        return "res://Game.Godot/Assets/Textures/Cards/card_reward_defend.png"
    if card_id == "card.warrior.heavy_strike":
        return "res://Game.Godot/Assets/Textures/Cards/card_reward_heavy_strike.png"
    if card_id == "card.warrior.cleave":
        return "res://Game.Godot/Assets/Textures/Cards/card_reward_cleave.png"
    if card_id == "card.warrior.shield_wall":
        return "res://Game.Godot/Assets/Textures/Cards/card_reward_shield_wall.png"
    if card_id == "card.warrior.iron_wave":
        return "res://Game.Godot/Assets/Textures/Cards/card_reward_iron_wave.png"
    if card_id == "card.warrior.rage_surge":
        return "res://Game.Godot/Assets/Textures/Cards/card_reward_rage_surge.png"
    for candidate_path in REWARD_CARD_ART_CANDIDATE_PATHS:
        if FileAccess.file_exists(candidate_path):
            return candidate_path
    return ""

func _translation_file_for_locale(locale: String) -> String:
    if locale.begins_with("zh"):
        return ZH_TRANSLATIONS_FILE
    return EN_TRANSLATIONS_FILE

func _normalize_locale(locale: String) -> String:
    if locale.strip_edges().is_empty():
        return "en"
    return locale.strip_edges().replace("_", "-").to_lower()

func _load_translation_values(csv_path: String) -> Dictionary:
    if _translation_text_catalog.has(csv_path):
        return _translation_text_catalog[csv_path]
    var values := {}
    var absolute_path := ProjectSettings.globalize_path(csv_path)
    if not FileAccess.file_exists(absolute_path):
        _translation_text_catalog[csv_path] = values
        return values
    var file := FileAccess.open(absolute_path, FileAccess.READ)
    if file == null:
        _translation_text_catalog[csv_path] = values
        return values
    var raw := file.get_as_text()
    file.close()
    for line in raw.split("\n", false):
        var trimmed := line.strip_edges()
        if trimmed == "" or trimmed.begins_with("key,value"):
            continue
        var comma := trimmed.find(",")
        if comma <= 0:
            continue
        var entry_key := trimmed.substr(0, comma).strip_edges()
        var entry_value := trimmed.substr(comma + 1).strip_edges()
        if entry_key != "" and entry_value != "":
            values[entry_key] = entry_value
    _translation_text_catalog[csv_path] = values
    return values

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

    var reward_pool_id := _resolve_reward_pool_id_for_active_context()
    var offers := _build_first_entry_reward_offer(context_id, encounter_type, _map_route_last_selected_node_floor)
    var entries := _build_reward_entries_for_pool(reward_pool_id)
    entries = _apply_reward_entry_modifiers(context_id, reward_pool_id, entries)
    var payload := {
        "context_id": context_id,
        "act_id": 1,
        "encounter_type": encounter_type,
        "floor": _map_route_last_selected_node_floor,
        "reward_pool_id": reward_pool_id,
        "entries": entries,
        "offers": offers,
        "source": "shared-card-pool"
    }
    _reward_offer_by_context[context_id] = payload.duplicate(true)
    if not _reward_selection_state_by_context.has(context_id):
        _reward_selection_state_by_context[context_id] = {
            "claimed_reward_types": [],
            "skipped_reward_types": []
        }
    return payload

func _build_reward_offer_preview_for_active_context() -> Dictionary:
    var context_id := _reward_offer_active_context_id.strip_edges()
    if context_id.is_empty():
        context_id = _build_reward_context_id(
            _map_route_last_selected_node_id,
            _map_route_last_selected_node_type,
            _map_route_last_selected_node_floor
        )

    var encounter_type := _map_route_last_selected_node_type.strip_edges().to_lower()
    if encounter_type.is_empty():
        encounter_type = "combat"
    if encounter_type == "event":
        encounter_type = "normal"
    elif encounter_type != "combat" and encounter_type != "normal" and encounter_type != "elite" and encounter_type != "boss":
        encounter_type = "normal"
    if encounter_type == "combat":
        encounter_type = "normal"

    var reward_pool_id := _resolve_reward_pool_id_for_active_context()
    var offers := _build_first_entry_reward_offer(context_id, encounter_type, _map_route_last_selected_node_floor)
    var entries := _build_reward_entries_for_pool(reward_pool_id)
    return {
        "context_id": context_id,
        "act_id": 1,
        "encounter_type": encounter_type,
        "floor": _map_route_last_selected_node_floor,
        "reward_pool_id": reward_pool_id,
        "entries": entries,
        "offers": offers,
        "source": "shared-card-pool"
    }

func _resolve_reward_modifier_context_key(context_id: String) -> String:
    var normalized_context := context_id.strip_edges()
    if not normalized_context.is_empty():
        return normalized_context
    if not _reward_offer_active_context_id.strip_edges().is_empty():
        return _reward_offer_active_context_id.strip_edges()
    if _map_route_last_selected_node_id.strip_edges().is_empty():
        return ""
    return _build_reward_context_id(
        _map_route_last_selected_node_id,
        _map_route_last_selected_node_type,
        _map_route_last_selected_node_floor
    )

func RegisterRewardEntryModifierForTest(context_id: String, modifier: Dictionary) -> bool:
    var normalized_context := _resolve_reward_modifier_context_key(context_id)
    if normalized_context.is_empty() or typeof(modifier) != TYPE_DICTIONARY:
        return false
    var action := str(modifier.get("action", "")).strip_edges().to_lower()
    if action != "add" and action != "remove" and action != "mutate":
        return false
    if action == "add":
        var reward_type := str(modifier.get("reward_type", "")).strip_edges()
        var config_variant = modifier.get("config", {})
        if reward_type.is_empty() or typeof(config_variant) != TYPE_DICTIONARY:
            return false
        var config := config_variant as Dictionary
        if not _is_supported_reward_entry_type(reward_type):
            return false
        if not _is_valid_reward_entry_config(reward_type, config):
            return false
    else:
        var target_entry_id := str(modifier.get("target_entry_id", "")).strip_edges()
        if target_entry_id.is_empty():
            return false
        if action == "mutate" and typeof(modifier.get("config", {})) != TYPE_DICTIONARY:
            return false
    if not _reward_runtime_modifiers_by_context.has(normalized_context):
        _reward_runtime_modifiers_by_context[normalized_context] = []
    var modifiers: Array = _reward_runtime_modifiers_by_context[normalized_context]
    modifiers.append(modifier.duplicate(true))
    _reward_runtime_modifiers_by_context[normalized_context] = modifiers
    return true

func ClearRewardEntryModifiersForTest() -> void:
    _reward_runtime_modifiers_by_context.clear()

func GetPendingRewardEntryModifierCountForTest(context_id: String) -> int:
    var normalized_context := _resolve_reward_modifier_context_key(context_id)
    if normalized_context.is_empty() or not _reward_runtime_modifiers_by_context.has(normalized_context):
        return 0
    var modifiers = _reward_runtime_modifiers_by_context[normalized_context]
    return (modifiers as Array).size() if typeof(modifiers) == TYPE_ARRAY else 0

func GetPendingRewardContextIdForTest() -> String:
    return _resolve_reward_modifier_context_key("")

func GetLatestRewardModifierFailureForTest() -> Dictionary:
    return _latest_reward_modifier_failure.duplicate(true)

func _clear_reward_runtime_modifier_state() -> void:
    _reward_runtime_modifiers_by_context.clear()
    _latest_reward_modifier_failure.clear()

func _ensure_reward_modifier_pipeline():
    if _reward_modifier_pipeline != null:
        return _reward_modifier_pipeline
    var bridge_script = load(REWARD_MODIFIER_PIPELINE_BRIDGE_SCRIPT)
    if bridge_script == null:
        push_error("Reward modifier pipeline bridge script could not be loaded.")
        return null
    _reward_modifier_pipeline = bridge_script.new()
    if _reward_modifier_pipeline == null or not _reward_modifier_pipeline.has_method("Apply"):
        push_error("Reward modifier pipeline bridge instance is unavailable.")
        _reward_modifier_pipeline = null
        return null
    return _reward_modifier_pipeline

func _apply_reward_entry_modifiers(context_id: String, _reward_pool_id: String, entries: Array) -> Array:
    var normalized_context := context_id.strip_edges()
    _latest_reward_modifier_failure.clear()
    if normalized_context.is_empty() or not _reward_runtime_modifiers_by_context.has(normalized_context):
        return entries
    var modifiers_variant = _reward_runtime_modifiers_by_context.get(normalized_context, [])
    if typeof(modifiers_variant) != TYPE_ARRAY:
        return entries
    var typed_entries: Array[Dictionary] = []
    for entry_variant in entries:
        if typeof(entry_variant) != TYPE_DICTIONARY:
            continue
        typed_entries.append((entry_variant as Dictionary).duplicate(true))
    var typed_modifiers: Array[Dictionary] = []
    for modifier_variant in (modifiers_variant as Array):
        if typeof(modifier_variant) != TYPE_DICTIONARY:
            continue
        typed_modifiers.append((modifier_variant as Dictionary).duplicate(true))

    var pipeline = _ensure_reward_modifier_pipeline()
    if pipeline == null:
        _latest_reward_modifier_failure = {
            "context_id": normalized_context,
            "rejection_reason": "bridge_unavailable",
            "modifier_count": typed_modifiers.size()
        }
        return entries
    var result = pipeline.call("Apply", typed_entries, typed_modifiers)
    if typeof(result) != TYPE_DICTIONARY:
        _latest_reward_modifier_failure = {
            "context_id": normalized_context,
            "rejection_reason": "bridge_invalid_result",
            "modifier_count": typed_modifiers.size()
        }
        return entries
    if bool(result.get("rejected", false)):
        _latest_reward_modifier_failure = {
            "context_id": normalized_context,
            "rejection_reason": str(result.get("rejection_reason", "")).strip_edges(),
            "modifier_count": typed_modifiers.size()
        }
        push_error("Invalid reward modifier payload for %s" % normalized_context)
        return entries

    var rebuilt: Array = []
    var result_entries = result.get("entries", [])
    if typeof(result_entries) != TYPE_ARRAY:
        return entries
    for entry_variant in (result_entries as Array):
        if typeof(entry_variant) != TYPE_DICTIONARY:
            continue
        var entry = entry_variant as Dictionary
        var reward_type := str(entry.get("reward_type", "")).strip_edges()
        var config := entry.get("config", {}) as Dictionary
        rebuilt.append(_build_reward_entry_data(reward_type, config))
    _reward_runtime_modifiers_by_context.erase(normalized_context)
    return rebuilt

func _is_supported_reward_entry_type(reward_type: String) -> bool:
    return reward_type in ["gold", "consumable", "relic", "common_card_choice", "rare_card_choice", "epic_card_choice"]

func _is_valid_reward_entry_config(reward_type: String, config: Dictionary) -> bool:
    if reward_type == "gold":
        return int(config.get("amount", -1)) >= 0
    if reward_type == "consumable":
        return not str(config.get("item_id", "")).strip_edges().is_empty()
    if reward_type == "relic":
        return not str(config.get("relic_id", "")).strip_edges().is_empty()
    if reward_type.ends_with("_card_choice"):
        return not str(config.get("pool_id", "")).strip_edges().is_empty() and int(config.get("pick", 0)) > 0
    return false

func GetRewardOfferSnapshotForScene() -> Dictionary:
    if not _reward_route_pending:
        var nav = _resolve_navigator()
        var current_scene := ""
        if nav != null and nav.has_method("GetCurrentScenePathForTest"):
            current_scene = str(nav.call("GetCurrentScenePathForTest"))
        if current_scene != REWARD_SCENE:
            return _build_reward_offer_preview_for_active_context()
    return _ensure_reward_offer_for_active_context()

func _resolve_reward_pool_id_for_active_context() -> String:
    var node_id := _map_route_last_selected_node_id.strip_edges()
    var node_type := _map_route_last_selected_node_type.strip_edges().to_lower()
    if node_id.is_empty():
        return _default_reward_pool_id_for_node_type(node_type)
    var node := _resolve_act_node_config(node_id)
    if node.is_empty():
        return _default_reward_pool_id_for_node_type(node_type)
    var reward_pool_id := str(node.get("reward_pool_id", "")).strip_edges()
    if reward_pool_id.is_empty():
        return _default_reward_pool_id_for_node_type(node_type)
    return reward_pool_id

func _default_reward_pool_id_for_node_type(node_type: String) -> String:
    var normalized := node_type.strip_edges().to_lower()
    if normalized == "event":
        return "reward.act1.event_1"
    if normalized == "boss":
        return "reward.act1.boss_1"
    return "reward.act1.normal_1"
    
func _resolve_act_node_config(node_id: String) -> Dictionary:
    var normalized_id := node_id.strip_edges()
    if normalized_id.is_empty():
        return {}
    for candidate_path in ACT_CONFIG_CANDIDATE_PATHS:
        if not FileAccess.file_exists(candidate_path):
            continue
        var file := FileAccess.open(candidate_path, FileAccess.READ)
        if file == null:
            continue
        var payload := str(file.get_as_text()).strip_edges()
        file.close()
        if payload.is_empty():
            continue
        var parsed = JSON.parse_string(payload)
        if typeof(parsed) != TYPE_DICTIONARY:
            continue
        var root := parsed as Dictionary
        var node_graph = root.get("node_graph", {})
        if typeof(node_graph) != TYPE_DICTIONARY:
            continue
        var nodes = (node_graph as Dictionary).get("nodes", [])
        if typeof(nodes) != TYPE_ARRAY:
            continue
        for node_variant in nodes:
            if typeof(node_variant) != TYPE_DICTIONARY:
                continue
            var node = node_variant as Dictionary
            if str(node.get("id", "")).strip_edges() == normalized_id:
                return node.duplicate(true)
    return {}

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
    var nav = _resolve_navigator()
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
    _reward_selection_state_by_context.clear()
    _reward_offer_active_context_id = ""
    _reward_offer_seed_counter = 0
    _clear_reward_runtime_modifier_state()
    _reset_run_deck_for_test()
    if nav != null:
        _switch_to(nav, MAP_SCENE)

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

func ResolveRewardForTest(action_payload) -> Dictionary:
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

    var parsed = _parse_reward_action_payload(action_payload)
    var normalized = str(parsed.get("action", "")).strip_edges().to_lower()
    var selected_card_id = str(parsed.get("selected_card_id", "")).strip_edges()
    var selected_index = int(parsed.get("selected_index", -1))
    var selected_reward_type = str(parsed.get("selected_reward_type", "")).strip_edges()
    var skip_reward_type = str(parsed.get("skip_reward_type", "")).strip_edges()
    if normalized != "confirm" and normalized != "skip":
        return {"ok": false, "reason": "unsupported-action", "scene_path": current_scene}

    var deck_before = _run_deck_card_ids.size()
    if normalized == "confirm":
        _apply_reward_claim(selected_reward_type, selected_card_id, selected_index)
    elif normalized == "skip":
        _mark_reward_type_skipped(skip_reward_type)

    if not _all_reward_entries_resolved():
        return {
            "ok": true,
            "reason": "",
            "scene_path": REWARD_SCENE,
            "deck_before_count": deck_before,
            "deck_after_count": _run_deck_card_ids.size(),
            "selected_card_id": selected_card_id,
            "selected_reward_type": selected_reward_type
        }

    _reward_route_resolved = true
    _reward_route_pending = false
    _map_route_completed_nodes += 1
    var deck_after = _run_deck_card_ids.size()
    var is_boss_completion = _map_route_last_selected_node_id.strip_edges().to_lower().begins_with("boss")
    if is_boss_completion:
        _reward_offer_active_context_id = ""
        _show_settlement_scene("Victory", _map_route_completed_nodes, "Boss defeated.")
        return {
            "ok": true,
            "reason": "",
            "scene_path": SETTLEMENT_SCENE,
            "outcome": "victory",
            "menu_visible": IsMainMenuVisibleForTest(),
            "deck_before_count": deck_before,
            "deck_after_count": deck_after,
            "selected_card_id": selected_card_id
        }

    _reward_offer_active_context_id = ""
    _switch_to(nav, MAP_SCENE)
    return {
        "ok": true,
        "reason": "",
        "scene_path": MAP_SCENE,
        "deck_before_count": deck_before,
        "deck_after_count": deck_after,
        "selected_card_id": selected_card_id,
        "selected_reward_type": selected_reward_type
    }

func SkipRemainingRewardsForTest() -> Dictionary:
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

    var context_id := _reward_offer_active_context_id.strip_edges()
    if context_id.is_empty():
        return {"ok": false, "reason": "reward-context-missing", "scene_path": current_scene}

    var payload = _reward_offer_by_context.get(context_id, {})
    if typeof(payload) == TYPE_DICTIONARY:
        var entries_variant = (payload as Dictionary).get("entries", [])
        if typeof(entries_variant) == TYPE_ARRAY:
            for entry_variant in (entries_variant as Array):
                if typeof(entry_variant) != TYPE_DICTIONARY:
                    continue
                var reward_type := str((entry_variant as Dictionary).get("reward_type", "")).strip_edges()
                if reward_type.is_empty():
                    continue
                _mark_reward_type_skipped(reward_type)

    _reward_route_resolved = true
    _reward_route_pending = false
    _map_route_completed_nodes += 1
    if not _map_route_last_selected_node_id.strip_edges().is_empty():
        _map_route_completed_node_ids.append(_map_route_last_selected_node_id)
    _reward_offer_active_context_id = ""
    _switch_to(nav, MAP_SCENE)
    return {
        "ok": true,
        "reason": "",
        "scene_path": MAP_SCENE,
        "completed_node_count": _map_route_completed_nodes
    }

func _all_reward_entries_resolved() -> bool:
    var context_id = _reward_offer_active_context_id.strip_edges()
    if context_id.is_empty():
        return true
    var payload = _reward_offer_by_context.get(context_id, {})
    if typeof(payload) != TYPE_DICTIONARY:
        return true
    var entries_variant = (payload as Dictionary).get("entries", [])
    if typeof(entries_variant) != TYPE_ARRAY:
        return true
    var total_resolvable: int = 0
    for entry_variant in (entries_variant as Array):
        if typeof(entry_variant) != TYPE_DICTIONARY:
            continue
        total_resolvable += 1
    var state = _reward_selection_state_by_context.get(context_id, {})
    if typeof(state) != TYPE_DICTIONARY:
        return total_resolvable <= 0
    var dict_state = state as Dictionary
    var claimed = dict_state.get("claimed_reward_types", [])
    var skipped = dict_state.get("skipped_reward_types", [])
    var resolved_count: int = 0
    if typeof(claimed) == TYPE_ARRAY:
        resolved_count += (claimed as Array).size()
    if typeof(skipped) == TYPE_ARRAY:
        resolved_count += (skipped as Array).size()
    return resolved_count >= total_resolvable

func _apply_reward_claim(reward_type: String, selected_card_id: String, selected_index: int) -> void:
    var normalized_type = reward_type.strip_edges()
    if normalized_type.is_empty():
        _writeback_reward_card_to_run_deck(selected_card_id, selected_index)
        return
    var context_id = _reward_offer_active_context_id.strip_edges()
    var payload = _reward_offer_by_context.get(context_id, {})
    if typeof(payload) != TYPE_DICTIONARY:
        return
    var entries_variant = (payload as Dictionary).get("entries", [])
    if typeof(entries_variant) != TYPE_ARRAY:
        return
    for entry_variant in (entries_variant as Array):
        if typeof(entry_variant) != TYPE_DICTIONARY:
            continue
        var entry = entry_variant as Dictionary
        if str(entry.get("reward_type", "")).strip_edges() != normalized_type:
            continue
        if normalized_type == "gold":
            _run_gold += int((entry.get("config", {}) as Dictionary).get("amount", 0))
            _sync_hud_run_resources()
        elif normalized_type == "consumable":
            var consumable_id = str((entry.get("config", {}) as Dictionary).get("item_id", "")).strip_edges()
            if not consumable_id.is_empty():
                _run_consumable_ids.append(consumable_id)
        elif normalized_type == "relic":
            var relic_id = str((entry.get("config", {}) as Dictionary).get("relic_id", "")).strip_edges()
            if not relic_id.is_empty() and not _run_relic_ids.has(relic_id):
                _run_relic_ids.append(relic_id)
        elif normalized_type.ends_with("_card_choice"):
            _writeback_reward_card_to_run_deck(selected_card_id, selected_index)
        _mark_reward_type_claimed(normalized_type)
        return

func _mark_reward_type_claimed(reward_type: String) -> void:
    _mutate_reward_type_state(reward_type, "claimed_reward_types")

func _mark_reward_type_skipped(reward_type: String) -> void:
    _mutate_reward_type_state(reward_type, "skipped_reward_types")

func _mutate_reward_type_state(reward_type: String, bucket_key: String) -> void:
    var normalized_type = reward_type.strip_edges()
    if normalized_type.is_empty():
        return
    var context_id = _reward_offer_active_context_id.strip_edges()
    if context_id.is_empty():
        return
    var state = _reward_selection_state_by_context.get(context_id, {})
    if typeof(state) != TYPE_DICTIONARY:
        state = {}
    var dict_state = state as Dictionary
    var list_variant = dict_state.get(bucket_key, [])
    var list: Array = list_variant if typeof(list_variant) == TYPE_ARRAY else []
    if not list.has(normalized_type):
        list.append(normalized_type)
    dict_state[bucket_key] = list
    _reward_selection_state_by_context[context_id] = dict_state

func GetRunDeckCardIdsForTest() -> Array[String]:
    return _run_deck_card_ids.duplicate()

func GetRunStateForTest() -> Dictionary:
    return {
        "hp": _run_hp,
        "gold": _run_gold,
        "score": _score,
        "deck_card_ids": _run_deck_card_ids.duplicate(),
        "relic_ids": _run_relic_ids.duplicate(),
        "consumable_ids": _run_consumable_ids.duplicate()
    }

func _parse_reward_action_payload(action_payload) -> Dictionary:
    var parsed: Dictionary = {
        "action": "",
        "selected_card_id": "",
        "selected_index": -1,
        "selected_reward_type": "",
        "skip_reward_type": ""
    }
    if typeof(action_payload) == TYPE_DICTIONARY:
        var payload = action_payload as Dictionary
        parsed["action"] = str(payload.get("action", ""))
        parsed["selected_card_id"] = str(payload.get("selected_card_id", ""))
        parsed["selected_index"] = int(payload.get("selected_index", -1))
        parsed["selected_reward_type"] = str(payload.get("selected_reward_type", ""))
        parsed["skip_reward_type"] = str(payload.get("skip_reward_type", ""))
        return parsed
    parsed["action"] = str(action_payload)
    return parsed

func _writeback_reward_card_to_run_deck(selected_card_id: String, selected_index: int) -> void:
    var chosen_card_id = selected_card_id.strip_edges()
    if chosen_card_id.is_empty():
        chosen_card_id = _resolve_reward_card_id_from_active_offer(selected_index)
    if chosen_card_id.is_empty():
        return
    _run_deck_card_ids.append(chosen_card_id)

func _resolve_reward_card_id_from_active_offer(selected_index: int) -> String:
    if selected_index < 0:
        return ""
    var context_id = _reward_offer_active_context_id.strip_edges()
    if context_id.is_empty() or not _reward_offer_by_context.has(context_id):
        return ""
    var payload = _reward_offer_by_context.get(context_id, {})
    if typeof(payload) != TYPE_DICTIONARY:
        return ""
    var offers_variant = (payload as Dictionary).get("offers", [])
    if typeof(offers_variant) != TYPE_ARRAY:
        return ""
    var offers = offers_variant as Array
    if selected_index >= offers.size():
        return ""
    var offer_variant = offers[selected_index]
    if typeof(offer_variant) != TYPE_DICTIONARY:
        return ""
    var offer = offer_variant as Dictionary
    var card_id = str(offer.get("id", "")).strip_edges()
    if card_id.is_empty():
        card_id = str(offer.get("name", "")).strip_edges()
    return card_id

func _reset_run_deck_for_test() -> void:
    _run_deck_card_ids.clear()
    _run_relic_ids.clear()
    _run_consumable_ids.clear()

func _seed_run_deck_from_starting_deck_if_empty() -> void:
    if not _run_deck_card_ids.is_empty():
        return
    _run_deck_card_ids = _load_starting_deck_card_ids()

func _load_starting_deck_card_ids() -> Array[String]:
    for candidate_path in STARTING_DECK_CANDIDATE_PATHS:
        if not FileAccess.file_exists(candidate_path):
            continue
        var file := FileAccess.open(candidate_path, FileAccess.READ)
        if file == null:
            continue
        var payload := str(file.get_as_text()).strip_edges()
        file.close()
        if payload.is_empty():
            continue
        var parsed = JSON.parse_string(payload)
        if typeof(parsed) != TYPE_DICTIONARY:
            continue
        var root := parsed as Dictionary
        var cards_variant = root.get("cards", [])
        if typeof(cards_variant) != TYPE_ARRAY:
            continue
        var card_ids: Array[String] = []
        for entry_variant in cards_variant:
            if typeof(entry_variant) != TYPE_DICTIONARY:
                continue
            var entry := entry_variant as Dictionary
            var card_id := str(entry.get("card_id", "")).strip_edges()
            var count := maxi(0, int(entry.get("count", 0)))
            if card_id.is_empty() or count <= 0:
                continue
            for _i in range(count):
                card_ids.append(card_id)
        if not card_ids.is_empty():
            return card_ids
    return []

func GetExpectedM1RunEntryRouteForTest() -> Array:
    return [DIFFICULTY_SELECT_SCENE, CHARACTER_SELECT_SCENE, MAP_SCENE]

func GetLegacyRunEntryTargetsForTest() -> Array:
    return [LEGACY_START_SCENE, DEMO_SCENE]
