## 无界面测试入口：跑 res://tests/ 下所有 test_*.gd 的 test_ 方法，有失败则退出码为 1。
##   Godot_v4.7.2-stable_win64_console.exe --headless --path . --script res://tests/run_tests.gd
extends SceneTree


func _init() -> void:
	var total := 0
	var failed := 0
	var dir := DirAccess.open("res://tests")
	var files := Array(dir.get_files()).filter(func(f): return f.begins_with("test_") and f.ends_with(".gd") and f != "test_case.gd")
	files.sort()
	for file in files:
		var script: GDScript = load("res://tests/" + file)
		for method in script.get_script_method_list():
			if not method.name.begins_with("test_"):
				continue
			var case = script.new()
			case.call(method.name)
			total += 1
			if case.failures.is_empty():
				print("通过  %s · %s" % [file, method.name])
			else:
				failed += 1
				print("失败  %s · %s" % [file, method.name])
				for f in case.failures:
					print("      " + f)
	print("共 %d 项，失败 %d 项" % [total, failed])
	quit(1 if failed > 0 or total == 0 else 0)
