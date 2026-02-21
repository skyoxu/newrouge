extends "res://addons/gdUnit4/src/GdUnitTestSuite.gd"

const REQUIRED_ROOT_DIRS := [
    "Game.Core",
    "Game.Godot",
    "Game.Core.Tests",
    "Tests.Godot"
]


func _find_repo_root() -> String:
    var candidates: Array = [
        ProjectSettings.globalize_path("res://.."),
        ProjectSettings.globalize_path("res://"),
    ]
    for candidate in candidates:
        var sln_path: String = candidate.path_join("NewRouge.sln")
        if FileAccess.file_exists(sln_path):
            return candidate
    return ProjectSettings.globalize_path("res://")


func _list_root_directories(root_path: String) -> Array:
    var root_dirs: Array = []
    var dir := DirAccess.open(root_path)
    if dir == null:
        return root_dirs

    dir.list_dir_begin()
    var entry := dir.get_next()
    while entry != "":
        if dir.current_is_dir() and entry != "." and entry != "..":
            root_dirs.append(entry)
        entry = dir.get_next()
    dir.list_dir_end()
    return root_dirs


func _find_csproj_in_directory(directory_path: String) -> String:
    var csproj_files: Array = _collect_files_with_extension(directory_path, ".csproj")
    if csproj_files.size() == 0:
        return ""
    return str(csproj_files[0])


func _read_text_file(path: String) -> String:
    var file := FileAccess.open(path, FileAccess.READ)
    if file == null:
        return ""
    var content := file.get_as_text()
    file.close()
    return content


func _compact_xml(content: String) -> String:
    return content.replace(" ", "").replace("\t", "").replace("\r", "").replace("\n", "")


func _collect_files_with_extension(root_path: String, extension: String) -> Array:
    var files: Array = []
    _collect_files_with_extension_recursive(root_path, extension.to_lower(), files)
    return files


func _collect_files_with_extension_recursive(current_path: String, extension: String, out_files: Array) -> void:
    var dir := DirAccess.open(current_path)
    if dir == null:
        return

    dir.list_dir_begin()
    var entry := dir.get_next()
    while entry != "":
        if entry != "." and entry != "..":
            var child_path := current_path.path_join(entry)
            if dir.current_is_dir():
                _collect_files_with_extension_recursive(child_path, extension, out_files)
            elif entry.to_lower().ends_with(extension):
                out_files.append(child_path)
        entry = dir.get_next()
    dir.list_dir_end()


func _extract_namespace_declarations(source: String) -> Array:
    var namespaces: Array = []
    for raw_line in source.split("\n"):
        var line := raw_line.strip_edges()
        if not line.begins_with("namespace "):
            continue

        var namespace_name := line.substr("namespace ".length()).strip_edges()
        if namespace_name.ends_with(";") or namespace_name.ends_with("{"):
            namespace_name = namespace_name.left(namespace_name.length() - 1).strip_edges()
        if namespace_name != "":
            namespaces.append(namespace_name)
    return namespaces


func _file_has_godot_using(source: String) -> bool:
    for raw_line in source.split("\n"):
        var line := raw_line.strip_edges()
        if line.begins_with("using Godot") or line.begins_with("global using Godot"):
            return true
    return false


func _file_has_godot_alias_using(source: String) -> bool:
    for raw_line in source.split("\n"):
        var line := raw_line.strip_edges()
        if line.begins_with("global using "):
            line = "using " + line.substr("global using ".length())
        if not line.begins_with("using ") or not line.contains("="):
            continue
        var parts := line.split("=", false, 1)
        if parts.size() != 2:
            continue
        var rhs: String = str(parts[1]).replace(";", "").strip_edges()
        if rhs == "Godot" or rhs.begins_with("Godot."):
            return true
    return false


func _collect_task2_scope_files(repo_root: String) -> Array:
    var manifest_path: String = repo_root.path_join("taskdoc").path_join("task-0002-change-set.json")
    var manifest_text: String = _read_text_file(manifest_path)
    if manifest_text == "":
        return []

    var parsed = JSON.parse_string(manifest_text)
    if typeof(parsed) != TYPE_DICTIONARY:
        return []

    var csharp_files_variant = parsed.get("csharp_files", [])
    if typeof(csharp_files_variant) != TYPE_ARRAY:
        return []

    var scoped: Array = []
    for relative_path_raw in csharp_files_variant:
        var relative_path: String = str(relative_path_raw)
        if relative_path == "":
            continue
        var absolute_path: String = repo_root.path_join(relative_path)
        if FileAccess.file_exists(absolute_path):
            scoped.append(absolute_path)

    return scoped


# acceptance: ACC:T2.1
func test_root_contains_required_project_directories() -> void:
    var repo_root: String = _find_repo_root()
    var root_dirs: Array = _list_root_directories(repo_root)
    for dir_name: String in REQUIRED_ROOT_DIRS:
        assert_bool(root_dirs.has(dir_name)).is_true()


# acceptance: ACC:T2.2
func test_required_csproj_files_target_net8_and_enable_nullable() -> void:
    var repo_root: String = _find_repo_root()
    var csproj_expected_dirs: Array[String] = ["Game.Core", "Game.Core.Tests", "Tests.Godot"]
    var script_only_dirs: Array[String] = ["Game.Godot"]

    for dir_name: String in csproj_expected_dirs:
        var project_path: String = repo_root.path_join(dir_name)
        var csproj_path: String = _find_csproj_in_directory(project_path)
        assert_bool(csproj_path != "").is_true()

        var normalized: String = _compact_xml(_read_text_file(csproj_path))
        assert_bool(normalized.contains("<TargetFramework>net8.0</TargetFramework>")).is_true()
        assert_bool(normalized.contains("<Nullable>enable</Nullable>")).is_true()

    # Game.Godot is a script/resource directory under the root project, not a standalone .csproj.
    for dir_name: String in script_only_dirs:
        var project_path: String = repo_root.path_join(dir_name)
        var csproj_path: String = _find_csproj_in_directory(project_path)
        assert_bool(csproj_path == "").is_true()


# acceptance: ACC:T2.3
func test_game_core_is_godot_free_and_namespaces_use_newrouge_prefix() -> void:
    var repo_root: String = _find_repo_root()
    var game_core_path: String = repo_root.path_join("Game.Core")
    var core_csproj: String = _find_csproj_in_directory(game_core_path)
    assert_bool(core_csproj != "").is_true()
    var manifest_path: String = repo_root.path_join("taskdoc").path_join("task-0002-change-set.json")
    assert_bool(FileAccess.file_exists(manifest_path)).is_true()

    var compact_project_text: String = _compact_xml(_read_text_file(core_csproj)).to_lower()
    assert_bool(compact_project_text.contains("godot")).is_false()
    assert_bool(_file_has_godot_using("global using Godot;")).is_true()
    assert_bool(_file_has_godot_alias_using("global using G = Godot;")).is_true()

    var cs_files: Array = _collect_files_with_extension(game_core_path, ".cs")
    for path: String in cs_files:
        var source: String = _read_text_file(path)
        var lower_source: String = source.to_lower()
        assert_bool(_file_has_godot_using(source)).is_false()
        assert_bool(_file_has_godot_alias_using(source)).is_false()
        assert_bool(lower_source.contains("godot.")).is_false()

    var scoped_files: Array = _collect_task2_scope_files(repo_root)
    assert_int(scoped_files.size()).is_greater(0)
    var normalized_scoped_files: Array = []
    for scoped_path_raw in scoped_files:
        normalized_scoped_files.append(str(scoped_path_raw).replace("\\", "/"))
    var required_manifest_files: Array[String] = [
        repo_root.path_join("Game.Core/Conventions/NamespaceConventions.cs").replace("\\", "/"),
        repo_root.path_join("Game.Core.Tests/Tasks/Task2NamespaceCoexistenceTests.cs").replace("\\", "/"),
        repo_root.path_join("Game.Core.Tests/Tasks/Task2RootBuildGateTests.cs").replace("\\", "/"),
    ]
    for required_file in required_manifest_files:
        assert_bool(normalized_scoped_files.has(required_file)).is_true()

    var expected_scope_files: Array = []
    expected_scope_files.append_array(_collect_files_with_extension(repo_root.path_join("Game.Core").path_join("Conventions"), ".cs"))
    for path_raw in _collect_files_with_extension(repo_root.path_join("Game.Core.Tests").path_join("Tasks"), ".cs"):
        var path: String = str(path_raw)
        if path.get_file().begins_with("Task2"):
            expected_scope_files.append(path)
    for path_raw in _collect_files_with_extension(repo_root.path_join("Tests.Godot").path_join("tests").path_join("Tasks"), ".cs"):
        var path: String = str(path_raw)
        if path.get_file().begins_with("task0002"):
            expected_scope_files.append(path)
    for expected_file_raw in expected_scope_files:
        var expected_file: String = str(expected_file_raw).replace("\\", "/")
        assert_bool(normalized_scoped_files.has(expected_file)).is_true()

    for scoped_path: String in scoped_files:
        var scoped_source: String = _read_text_file(scoped_path)
        var scoped_namespaces: Array = _extract_namespace_declarations(scoped_source)
        assert_int(scoped_namespaces.size()).is_greater(0)
        for namespace_name_raw in scoped_namespaces:
            var namespace_name: String = str(namespace_name_raw)
            var is_newrouge: bool = namespace_name == "NewRouge" or namespace_name.begins_with("NewRouge.")
            assert_bool(is_newrouge).is_true()
