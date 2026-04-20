extends Control

@onready var _label: Label = $VBox/Output
var _score: int = 0
var _hp: int = 100
const DIFFICULTY_SELECT_SCENE := "res://Game.Godot/Scenes/UI/DifficultySelect.tscn"
const CHARACTER_SELECT_SCENE := "res://Game.Godot/Scenes/UI/CharacterSelect.tscn"
const MAP_SCENE := "res://Game.Godot/Scenes/Map/Map.tscn"
const LEGACY_START_SCENE := "res://Game.Godot/Scenes/Screens/StartScreen.tscn"
const DEMO_SCENE := "res://Game.Godot/Examples/Screens/DemoScreen.tscn"

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
    var nav = get_node_or_null("/root/Main/ScreenNavigator")
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

func GetExpectedM1RunEntryRouteForTest() -> Array:
    return [DIFFICULTY_SELECT_SCENE, CHARACTER_SELECT_SCENE, MAP_SCENE]

func GetLegacyRunEntryTargetsForTest() -> Array:
    return [LEGACY_START_SCENE, DEMO_SCENE]
