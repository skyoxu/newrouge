extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

func before() -> void:
    var __ds = preload("res://Game.Godot/Adapters/DataStoreAdapter.cs").new()
    __ds.name = "DataStore"
    get_tree().get_root().add_child(auto_free(__ds))

func _open_datastore() -> bool:
    var ds = get_node_or_null("/root/DataStore")
    return ds != null

func test_inventory_save_and_load() -> void:
    assert_bool(_open_datastore()).is_true()
    var packed = load("res://Game.Godot/Examples/UI/InventoryPanel.tscn")
    assert_that(packed).is_not_null()
    var inv = packed.instantiate()
    add_child(auto_free(inv))
    inv.UseRepository = false
    # add two items
    var add_btn = inv.get_node("VBox/Buttons/AddBtn")
    add_btn.emit_signal("pressed")
    add_btn.emit_signal("pressed")
    # save
    var save_btn = inv.get_node("VBox/Buttons/SaveBtn")
    save_btn.emit_signal("pressed")
    var list = inv.get_node("VBox/Items")
    var saved_count = int(list.item_count)
    assert_int(saved_count).is_equal(2)
    # clear and load
    list.clear()
    assert_int(int(list.item_count)).is_equal(0)
    var load_btn = inv.get_node("VBox/Buttons/LoadBtn")
    load_btn.emit_signal("pressed")
    await get_tree().process_frame
    assert_int(int(list.item_count)).is_equal(saved_count)
    inv.queue_free()
