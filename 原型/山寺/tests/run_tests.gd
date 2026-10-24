## 无界面测试入口：跑 res://tests/ 下所有 test_*.gd 的 test_ 方法，有失败则退出码为 1。
## 脚本出错（编译失败、运行时报错中断）也算失败——GDScript 没有异常，靠挂一个日志接收器抓引擎报错。
##   Godot_v4.7.2-stable_win64_console.exe --headless --path . --script res://tests/run_tests.gd
extends SceneTree


class ErrorCatcher extends Logger:
	var errors: Array[String] = []
	var _mutex := Mutex.new()

	func _log_error(function: String, file: String, line: int, code: String, rationale: String,
			_editor_notify: bool, error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
		if error_type == ERROR_TYPE_WARNING:
			return
		_mutex.lock()
		errors.append("%s（%s:%d %s）" % [rationale if rationale != "" else code, file.get_file(), line, function])
		_mutex.unlock()

	func _log_message(_message: String, _error: bool) -> void:
		pass

	func take() -> Array[String]:
		_mutex.lock()
		var out := errors.duplicate()
		errors.clear()
		_mutex.unlock()
		return out


func _init() -> void:
	var catcher := ErrorCatcher.new()
	OS.add_logger(catcher)
	var total := 0
	var failed := 0
	var dir := DirAccess.open("res://tests")
	var files := Array(dir.get_files()).filter(func(f): return f.begins_with("test_") and f.ends_with(".gd") and f != "test_case.gd")
	files.sort()
	for file in files:
		catcher.take()
		var script: GDScript = load("res://tests/" + file)
		if script == null or not script.can_instantiate():
			total += 1
			failed += 1
			print("失败  %s · 脚本无法加载" % file)
			for e in catcher.take():
				print("      " + e)
			continue
		for method in script.get_script_method_list():
			if not method.name.begins_with("test_"):
				continue
			catcher.take()
			var case = script.new()
			case.call(method.name)
			total += 1
			var problems: Array = case.failures + catcher.take()
			if problems.is_empty():
				print("通过  %s · %s" % [file, method.name])
			else:
				failed += 1
				print("失败  %s · %s" % [file, method.name])
				for f in problems:
					print("      " + f)
	print("共 %d 项，失败 %d 项" % [total, failed])
	OS.remove_logger(catcher)
	quit(1 if failed > 0 or total == 0 else 0)
