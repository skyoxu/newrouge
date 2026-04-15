extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const REQUIRED_NODE_TYPES := ["combat", "event", "shop", "rest"]

# acceptance: ACC:T17.5
func test_map_scene_exposes_all_required_node_icon_types() -> void:
	var map_scene_path := _find_map_scene_path()
	assert_that(map_scene_path.is_empty()).is_false()

	var map_scene := load(map_scene_path) as PackedScene
	assert_that(map_scene).is_not_null()

	var map_root := map_scene.instantiate()
	add_child(map_root)
	var recognized := _collect_recognized_types(map_root)
	var missing := _missing_required_types(recognized)
	map_root.queue_free()

	assert_that(missing).is_empty()

func test_red_first_incomplete_fixture_still_fails_required_icon_type_gate() -> void:
	var incomplete_root := _build_fixture_without_rest()
	var recognized := _collect_recognized_types(incomplete_root)
	var missing := _missing_required_types(recognized)
	incomplete_root.queue_free()

	assert_that(missing.has("rest")).is_true()

func test_missing_any_required_type_is_rejected() -> void:
	var incomplete_root := _build_fixture_without_rest()
	var recognized := _collect_recognized_types(incomplete_root)
	var missing := _missing_required_types(recognized)
	incomplete_root.queue_free()

	assert_that(missing.has("rest")).is_true()
	assert_that(_has_all_required_types(recognized)).is_false()

func _build_fixture_without_rest() -> Node:
	var root := Node.new()
	root.name = "MapRoot"

	var combat := Node.new()
	combat.name = "combat_icon"
	root.add_child(combat)

	var event := Node.new()
	event.set_meta("map_node_type", "event")
	root.add_child(event)

	var shop := Node.new()
	shop.name = "shop_marker"
	shop.add_to_group("map_node_shop")
	root.add_child(shop)

	return root

func _find_map_scene_path() -> String:
	var candidates := [
		"res://Game.Godot/Scenes/Map/Map.tscn",
		"res://Game.Godot/Scenes/Map.tscn",
		"res://Scenes/Map/Map.tscn",
		"res://Scenes/Map.tscn",
		"res://Map.tscn"
	]
	for candidate in candidates:
		if ResourceLoader.exists(candidate):
			return candidate
	return ""

func _collect_recognized_types(root: Node) -> Dictionary:
	var found := {}
	_collect_recognized_types_recursive(root, found)
	return found

func _collect_recognized_types_recursive(node: Node, found: Dictionary) -> void:
	var token := _resolve_node_type(node)
	if token != "":
		found[token] = true
	for child in node.get_children():
		if child is Node:
			_collect_recognized_types_recursive(child, found)

func _resolve_node_type(node: Node) -> String:
	if node.has_meta("map_node_type"):
		return _normalize_token(str(node.get_meta("map_node_type")))

	for raw_group in node.get_groups():
		var group_name := str(raw_group).to_lower()
		if group_name.begins_with("map_node_"):
			return _normalize_token(group_name.trim_prefix("map_node_"))

	return _normalize_token(node.name)

func _normalize_token(raw_value: String) -> String:
	var normalized := raw_value.strip_edges().to_lower()
	if normalized.find("combat") != -1:
		return "combat"
	if normalized.find("event") != -1:
		return "event"
	if normalized.find("shop") != -1:
		return "shop"
	if normalized.find("rest") != -1:
		return "rest"
	return ""

func _missing_required_types(found: Dictionary) -> Array:
	var missing := []
	for required_type in REQUIRED_NODE_TYPES:
		if not found.has(required_type):
			missing.append(required_type)
	return missing

func _has_all_required_types(found: Dictionary) -> bool:
	return _missing_required_types(found).is_empty()
