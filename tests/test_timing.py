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
        self.assertEqual(check.call_count, 2)

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
