import unittest
from unittest.mock import Mock, patch

from lockedin.browser import BrowserSessionError
from lockedin.timing import TimerUnavailable, prepare_timer, read_game_time, wait_for_game_time


class TimerTests(unittest.TestCase):
    def test_time_formats(self):
        for text, seconds in (("0:05", 5), ("12:34", 754), ("1:02:03", 3723)):
            self.assertEqual(read_game_time(Mock(evaluate=Mock(return_value=[text]))), seconds)

    def test_missing_ambiguous_and_invalid_timers(self):
        for values, error in (([], TimerUnavailable), (["0:01", "0:02"], BrowserSessionError),
                              (["0:99"], BrowserSessionError), (["bad"], BrowserSessionError)):
            with self.subTest(values=values), self.assertRaises(error):
                read_game_time(Mock(evaluate=Mock(return_value=values)))

    def test_zero_skips_timer_and_time_already_reached_does_not_wait(self):
        frame = Mock()
        self.assertFalse(prepare_timer(frame, 0))
        frame.evaluate.assert_not_called()
        frame.evaluate.return_value = ["0:09"]
        page, check = Mock(), Mock()
        wait_for_game_time(page, frame, 5, check)
        page.wait_for_timeout.assert_not_called()
        self.assertGreaterEqual(check.call_count, 2)

    def test_backward_or_frozen_timer_fails_closed(self):
        for values, expected in (([["0:05"], ["0:04"]], "backwards"),
                                 ([["0:05"], ["0:05"]], "not advancing")):
            frame = Mock()
            frame.evaluate.side_effect = values
            with patch("lockedin.timing.monotonic", side_effect=[0, 20]):
                with self.assertRaisesRegex(BrowserSessionError, expected):
                    wait_for_game_time(Mock(), frame, 10, Mock())

    def test_stop_check_interrupts_wait(self):
        frame = Mock(evaluate=Mock(return_value=["0:01"]))
        check = Mock(side_effect=[None, BrowserSessionError("cancelled")])
        with self.assertRaisesRegex(BrowserSessionError, "cancelled"):
            wait_for_game_time(Mock(), frame, 5, check)

    def test_missing_timer_waits_from_board_readiness(self):
        frame = Mock(evaluate=Mock(return_value=[]))
        page = Mock()
        statuses = []
        with patch("lockedin.timing.monotonic", side_effect=[11, 12, 14, 15]):
            timer = prepare_timer(frame, 5, started_at=10, status=statuses.append)
            wait_for_game_time(page, frame, 5, Mock(), timer=timer, status=statuses.append)
        self.assertEqual(page.wait_for_timeout.call_count, 3)
        self.assertIn("estimated timer", statuses[0])

    def test_disappearing_timer_uses_last_displayed_value_and_elapsed_time(self):
        frame = Mock()
        frame.evaluate.side_effect = [["0:03"], ["0:04"], [], []]
        page = Mock()
        statuses = []
        with patch("lockedin.timing.monotonic", side_effect=[10, 11, 12, 13, 14]):
            timer = prepare_timer(frame, 7, status=statuses.append)
            wait_for_game_time(page, frame, 7, Mock(), timer=timer, status=statuses.append)
        self.assertEqual(page.wait_for_timeout.call_count, 3)
        self.assertEqual(frame.evaluate.call_count, 3)
        self.assertTrue(any("estimated timer" in message for message in statuses))

    def test_missing_timer_cancellation_and_changed_board_are_not_ignored(self):
        frame = Mock(evaluate=Mock(return_value=[]))
        for error in ("cancelled", "board changed"):
            check = Mock(side_effect=[None, BrowserSessionError(error)])
            timer = prepare_timer(frame, 5, started_at=0, status=Mock())
            with self.assertRaisesRegex(BrowserSessionError, error):
                wait_for_game_time(Mock(), frame, 5, check, timer=timer)

    def test_ambiguous_timer_does_not_fall_back(self):
        frame = Mock(evaluate=Mock(return_value=["0:01", "0:02"]))
        with self.assertRaisesRegex(BrowserSessionError, "ambiguous"):
            prepare_timer(frame, 5, status=Mock())
