import unittest

import emotion


class GestureTests(unittest.TestCase):
    def test_practice_presses_match_their_names(self):
        for name, script in emotion.DEMOS.items():
            finished, _seen = emotion.play(script)
            self.assertIsNotNone(finished, name)
            self.assertEqual(finished["emotion"], name, finished["evidence"])

    def test_a_slow_hard_pinch_is_angry(self):
        script = [(emotion.press(1600, [(2, 2)]), 0.50), (emotion.ZEROS, 0.40)]
        finished, _seen = emotion.play(script)
        self.assertEqual(finished["emotion"], "angry")

    def test_noise_alone_is_not_a_press(self):
        script = [(emotion.press(5, [(0, 0)]), 0.40), (emotion.ZEROS, 0.40)]
        finished, seen = emotion.play(script)
        self.assertIsNone(finished)
        self.assertFalse(any(frame["touching"] for frame in seen))

    def test_upright_rotation_matches_the_sensor_comment(self):
        # Imported lazily so this file stays about the gesture math.
        import sensx25

        flat = list(range(25))
        grid = sensx25.to_upright(flat)
        for r in range(5):
            for c in range(5):
                self.assertEqual(grid[r][c], flat[5 * (4 - c) + r])


if __name__ == "__main__":
    unittest.main()
