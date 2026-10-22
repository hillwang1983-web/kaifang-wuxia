import unittest

from jyserver.store import CharacterStore, decode_db_password


class Store(unittest.TestCase):
    def test_roundtrip_and_overwrite(self):
        s = CharacterStore()
        rows = {"renwu": [{"jyid": "1", "name": "游戏者", "zongxiaofei": "5"}]}
        s.put(1, "pw", rows)
        c = s.get(1)
        self.assertEqual((c.jyid, c.password, c.state, c.rows), (1, "pw", 1, rows))
        s.put(1, "pw2", rows, state=0)
        self.assertEqual((s.get(1).password, s.get(1).state), ("pw2", 0))
        self.assertIsNone(s.get(2))
        self.assertEqual(s.ids(), [1])

    def test_top_sponsor(self):
        s = CharacterStore()
        self.assertIsNone(s.top_sponsor())
        s.put(1, "a", {"renwu": [{"zongxiaofei": "0"}]})
        self.assertIsNone(s.top_sponsor())
        s.put(2, "a", {"renwu": [{"zongxiaofei": "10"}]})
        s.put(3, "a", {"renwu": [{"zongxiaofei": "10"}]})
        s.put(4, "a", {"renwu": [{"zongxiaofei": "9"}]})
        self.assertEqual(s.top_sponsor(), 2)  # 并列取 jyid 小的

    def test_db_password_decoding(self):
        self.assertEqual(decode_db_password("31 32 33 34 35 36"), "123456")
        self.assertEqual(decode_db_password("39 36 35 39 36 37 39 30 30"), "965967900")


if __name__ == "__main__":
    unittest.main()
