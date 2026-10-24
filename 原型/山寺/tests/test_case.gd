## 测试基类：tests/test_*.gd 继承它，写 test_ 开头的方法，用 check() 断言。
extends RefCounted

var failures: Array[String] = []


func check(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)


func check_eq(actual, expected, message: String) -> void:
	if actual != expected:
		failures.append("%s：期望 %s，实际 %s" % [message, str(expected), str(actual)])
