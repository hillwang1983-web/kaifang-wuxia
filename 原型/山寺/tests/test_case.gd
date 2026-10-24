## 测试基类：tests/test_*.gd 继承它，写 test_ 开头的方法，用 check() 断言。
extends RefCounted

var failures: Array[String] = []
var tree: SceneTree   # 运行器在调用前塞进来：要把节点挂进场景树的用例用它（运行器在 _init 里跑，拿不到 get_main_loop）


func check(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)


func check_eq(actual, expected, message: String) -> void:
	if actual != expected:
		failures.append("%s：期望 %s，实际 %s" % [message, str(expected), str(actual)])
