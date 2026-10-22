import unittest

from jyserver.manage import add_account
from jyserver.store import CharacterStore


class Manage(unittest.TestCase):
    def test_add_account_creates_character_less_account(self):
        s = CharacterStore()
        add_account(s, 9000001, "secret", points=500)
        c = s.get(9000001)
        self.assertEqual((c.password, c.state, c.has_character), ("secret", 1, False))
        self.assertEqual(c.rows["account"][0]["shangchengdianshu"], "500")

    def test_duplicate_and_bad_password_are_refused(self):
        s = CharacterStore()
        add_account(s, 1, "a")
        with self.assertRaises(SystemExit):
            add_account(s, 1, "b")
        with self.assertRaises(SystemExit):
            add_account(s, 2, "密码")

    def test_name_lookup_and_old_db_upgrade(self):
        s = CharacterStore()
        s.put(1, "p", {"renwu": [{"name": "甲", "zongxiaofei": "0"}]})
        self.assertTrue(s.name_taken("甲"))
        self.assertFalse(s.name_taken("乙"))


if __name__ == "__main__":
    unittest.main()
