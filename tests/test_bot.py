import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot


class Fake(bot.Bot):
    def __init__(self, runner):
        super().__init__("t", [1], runner=runner)
        self.sent = []

    def send(self, chat_id, text):
        self.sent.append(text)


class T(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(bot.parse_upgradable("Listing...\nfoo/stable 1 arm64 [upgradable from: 0]"), ["foo/stable 1 arm64 [upgradable from: 0]"])

    def test_unauthorized(self):
        b = Fake(lambda c: (0, ""))
        b.handle(2, "/reboot")
        self.assertEqual(b.sent, [])

    def test_reboot_needs_confirm(self):
        calls = []
        b = Fake(lambda c: calls.append(c) or (0, ""))
        b.handle(1, "/reboot", now=0)
        self.assertEqual(calls, [])
        b.handle(1, "/confirm", now=10)
        self.assertIn(["sudo", "systemctl", "reboot"], calls)

    def test_confirm_expired(self):
        calls = []
        b = Fake(lambda c: calls.append(c) or (0, ""))
        b.handle(1, "/shutdown", now=0)
        b.handle(1, "/confirm", now=1000)
        self.assertEqual(calls, [])

    def test_update_reboots(self):
        calls = []

        def r(c):
            calls.append(c)
            return (0, "Listing...\npkg/stable 1 arm64 [upgradable from: 0]" if c[0] == "apt" else "")

        b = Fake(r)
        b.do_update()
        self.assertIn(["sudo", "systemctl", "reboot"], calls)


if __name__ == "__main__":
    unittest.main()
