import time
import unittest

from inputs import InputHub


class InputTests(unittest.TestCase):
    def test_ownership_stale_packets_and_release(self):
        hub = InputHub(timeout=.01)
        hub.claim('alice', 0)
        hub.claim('bob', 1)
        with self.assertRaises(ValueError):
            hub.claim('bob', 0)
        self.assertEqual(hub.slots()[:2], ['alice', 'bob'])
        self.assertFalse(hub.update('spectator', 0, 1))
        self.assertTrue(hub.update('alice', 4, 1))
        self.assertTrue(hub.update('bob', 1, 64))
        self.assertFalse(hub.update('alice', 3, 128))
        self.assertFalse(hub.update('alice', 4, 128))
        self.assertEqual(hub.snapshot()[:2], [1, 64])
        hub.release('alice')
        self.assertEqual(hub.snapshot()[:2], [0, 64])
        time.sleep(.02)
        self.assertEqual(hub.snapshot(), [0, 0, 0, 0])

    def test_moving_slots_clears_old_input(self):
        hub = InputHub()
        hub.claim('alice', 0)
        hub.update('alice', 1, 32)
        hub.claim('alice', 2)
        self.assertEqual(hub.slots(), [None, None, 'alice', None])
        self.assertEqual(hub.snapshot(), [0, 0, 0, 0])
        self.assertFalse(hub.update('alice', 1, 32), 'old datagram cannot reactivate a changed slot')
        self.assertTrue(hub.update('alice', 2, 32))
        hub.clear('alice')
        self.assertFalse(hub.update('alice', 1, 32))
        self.assertEqual(hub.snapshot(), [0, 0, 0, 0])
        for seq, mask in [(True, 1), (1, True), (-1, 1), (1, -1), (1, 65536)]:
            self.assertFalse(hub.update('alice', seq, mask))


if __name__ == '__main__':
    unittest.main()


class AnalogTests(unittest.TestCase):
    def test_axes_follow_the_snapshot_rules(self):
        hub = InputHub(players=2, timeout=.01)
        hub.claim('alice', 0)
        self.assertTrue(hub.update('alice', 1, 0, [-32768, 32767, 0, 100]))
        self.assertEqual(hub.analog(), [(-32768, 32767, 0, 100), (0, 0, 0, 0)])
        self.assertTrue(hub.update('alice', 2, 1))
        self.assertEqual(hub.analog()[0], (0, 0, 0, 0), 'a message without axes centres the sticks')
        hub.update('alice', 3, 0, [5, 5, 5, 5])
        time.sleep(.02)
        self.assertEqual(hub.analog()[0], (0, 0, 0, 0), 'stale axes expire with the buttons')
        hub.update('alice', 4, 0, [5, 5, 5, 5])
        hub.release('alice')
        self.assertEqual(hub.analog()[0], (0, 0, 0, 0))

    def test_rejects_bad_axes(self):
        hub = InputHub()
        hub.claim('alice', 0)
        for axes in ([1, 2, 3], [0, 0, 0, 32768], [0, 0, 0, -32769], [0, 0, 0, 1.5], [0, 0, 0, True], 'abcd', {}):
            self.assertFalse(hub.update('alice', 1, 0, axes), axes)
