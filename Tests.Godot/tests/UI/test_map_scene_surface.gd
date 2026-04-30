extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const MAP_OWNER_ID := "map_surface_owner"


func _new_live_map_surface() -> Dictionary:
	return {
		"owner_id": MAP_OWNER_ID,
		"visual_convention": "map_route_v1",
		"path_style": {
			"line_width": 2,
			"palette": "default"
		},
		"nodes": {},
		"active_selection": ""
	}


func _generated_route_fixture() -> Dictionary:
	return {
		"node_a": {
			"reachable": true,
			"locked": false,
			"selected": false,
			"completed": false
		},
		"node_b": {
			"reachable": false,
			"locked": true,
			"selected": false,
			"completed": false
		},
		"node_c": {
			"reachable": true,
			"locked": false,
			"selected": true,
			"completed": false
		},
		"node_d": {
			"reachable": false,
			"locked": false,
			"selected": false,
			"completed": true
		}
	}


func _apply_generated_route_binding(live_surface: Dictionary, generated_route: Dictionary, requester_owner_id: String) -> void:
	var owner_id := String(live_surface.get("owner_id", ""))
	if requester_owner_id != owner_id:
		return

	var active_selection := ""
	for node_id in generated_route.keys():
		var route_state: Dictionary = generated_route[node_id]
		var selected := bool(route_state.get("selected", false))
		if selected:
			active_selection = String(node_id)
		live_surface["nodes"][node_id] = {
			"reachable": route_state.get("reachable", false),
			"locked": route_state.get("locked", false),
			"selected": selected,
			"completed": route_state.get("completed", false),
			"actionable": route_state.get("reachable", false) and not route_state.get("locked", false)
		}
	live_surface["active_selection"] = active_selection


func _is_visible(surface: Dictionary, node_id: String, state_key: String) -> bool:
	if not surface["nodes"].has(node_id):
		return false
	return bool(surface["nodes"][node_id].get(state_key, false))


func _activate_selected_node(surface: Dictionary) -> bool:
	var selected_id := String(surface.get("active_selection", ""))
	if selected_id == "":
		for node_id in surface["nodes"].keys():
			if _is_visible(surface, node_id, "selected"):
				selected_id = String(node_id)
				break
	if selected_id == "":
		return false

	var node_state: Dictionary = surface["nodes"][selected_id]
	if not node_state.get("actionable", false):
		return false

	surface["active_selection"] = selected_id
	return true


# ACC:T97.10
func test_route_surface_keeps_existing_visual_conventions_after_generated_binding() -> void:
	var surface := _new_live_map_surface()
	_apply_generated_route_binding(surface, _generated_route_fixture(), MAP_OWNER_ID)

	assert_str(surface["visual_convention"]).is_equal("map_route_v1")
	assert_int(surface["path_style"]["line_width"]).is_equal(2)
	assert_str(surface["path_style"]["palette"]).is_equal("default")


# ACC:T97.3
func test_generated_route_marks_reachable_nodes_on_live_surface() -> void:
	var surface := _new_live_map_surface()
	_apply_generated_route_binding(surface, _generated_route_fixture(), MAP_OWNER_ID)

	assert_bool(_is_visible(surface, "node_a", "reachable")).is_true()
	assert_bool(_is_visible(surface, "node_b", "reachable")).is_false()


# ACC:T97.4
func test_generated_route_marks_locked_nodes_on_live_surface() -> void:
	var surface := _new_live_map_surface()
	_apply_generated_route_binding(surface, _generated_route_fixture(), MAP_OWNER_ID)

	assert_bool(_is_visible(surface, "node_b", "locked")).is_true()
	assert_bool(_is_visible(surface, "node_a", "locked")).is_false()


# ACC:T97.5
func test_generated_route_marks_selected_node_on_live_surface() -> void:
	var surface := _new_live_map_surface()
	_apply_generated_route_binding(surface, _generated_route_fixture(), MAP_OWNER_ID)

	assert_bool(_is_visible(surface, "node_c", "selected")).is_true()


# ACC:T97.6
func test_generated_route_marks_completed_nodes_on_live_surface() -> void:
	var surface := _new_live_map_surface()
	_apply_generated_route_binding(surface, _generated_route_fixture(), MAP_OWNER_ID)

	assert_bool(_is_visible(surface, "node_d", "completed")).is_true()
	assert_bool(_is_visible(surface, "node_a", "completed")).is_false()


# ACC:T97.7
func test_generated_projection_refuses_non_owner_surface_takeover() -> void:
	var surface := _new_live_map_surface()
	var baseline_route := _generated_route_fixture()
	_apply_generated_route_binding(surface, baseline_route, MAP_OWNER_ID)
	var snapshot := surface.duplicate(true)

	var intruder_route := {
		"node_intruder": {
			"reachable": true,
			"locked": false,
			"selected": true,
			"completed": false
		}
	}
	_apply_generated_route_binding(surface, intruder_route, "intruder_owner")

	assert_str(surface["owner_id"]).is_equal(MAP_OWNER_ID)
	assert_dict(surface["nodes"]).is_equal(snapshot["nodes"])


# ACC:T97.8
func test_map_scene_binding_reflects_generated_route_states() -> void:
	var surface := _new_live_map_surface()
	var route := _generated_route_fixture()
	_apply_generated_route_binding(surface, route, MAP_OWNER_ID)

	assert_dict(surface["nodes"]).contains_keys(["node_a", "node_b", "node_c", "node_d"])
	assert_bool(_is_visible(surface, "node_a", "reachable")).is_equal(route["node_a"]["reachable"])
	assert_bool(_is_visible(surface, "node_b", "locked")).is_equal(route["node_b"]["locked"])
	assert_bool(_is_visible(surface, "node_d", "completed")).is_equal(route["node_d"]["completed"])


# ACC:T97.12
func test_first_bind_projects_precomputed_selected_and_completed_states_without_local_interaction() -> void:
	var surface := _new_live_map_surface()
	var route := _generated_route_fixture()

	_apply_generated_route_binding(surface, route, MAP_OWNER_ID)

	assert_str(surface["active_selection"]).is_equal("node_c")
	assert_bool(_is_visible(surface, "node_c", "selected")).is_true()
	assert_bool(_is_visible(surface, "node_d", "completed")).is_true()


# ACC:T97.9
func test_generated_route_selection_remains_actionable_on_live_surface() -> void:
	var surface := _new_live_map_surface()
	_apply_generated_route_binding(surface, _generated_route_fixture(), MAP_OWNER_ID)

	assert_bool(_activate_selected_node(surface)).is_true()
	assert_str(surface["active_selection"]).is_equal("node_c")
