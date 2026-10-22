"""Behavior checks for malformed files and timing/reading diagnostics."""

import math
import unittest

from subcheck.core import analyze


def block(label="1", start="00:00:00,000", end="00:00:02,000", body="你好世界"):
    return "{}\n{} --> {}\n{}".format(label, start, end, body)


class AnalyzeTests(unittest.TestCase):
    def codes(self, result):
        return [issue["code"] for issue in result["issues"]]

    def issues_for(self, result, code):
        return [issue for issue in result["issues"] if issue["code"] == code]

    def test_valid_unicode_keeps_text_and_summary(self):
        content = block(body="你好，世界！\nHello 🌏")
        result = analyze(content, filename="中文字幕.srt")
        self.assertEqual(result["filename"], "中文字幕.srt")
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["summary"], {
            "total_cues": 1, "errors": 0, "warnings": 0, "duration_ms": 2000,
        })
        cue = result["cues"][0]
        self.assertEqual(cue["index"], 1)
        self.assertEqual(cue["label"], "1")
        self.assertEqual(cue["line"], 1)
        self.assertEqual(cue["start_ms"], 0)
        self.assertEqual(cue["end_ms"], 2000)
        self.assertEqual(cue["text"], "你好，世界！\nHello 🌏")

    def test_bom_and_crlf_parse_like_plain_utf8(self):
        plain = block() + "\n"
        expected = analyze(plain)
        actual = analyze("\ufeff" + plain.replace("\n", "\r\n"))
        self.assertEqual(actual, expected)

    def test_empty_input_is_an_error_not_a_successful_empty_report(self):
        result = analyze(" \n\t\n")
        self.assertEqual(result["cues"], [])
        self.assertEqual(result["summary"]["total_cues"], 0)
        self.assertIn("empty_input", self.codes(result))
        self.assertGreater(result["summary"]["errors"], 0)

    def test_timestamp_syntax_and_ranges_are_checked(self):
        invalid = [
            "00:60:00,000", "00:00:60,000", "00:00:00.000",
            "0:00:00,000", "00:00:00,00", "-01:00:00,000",
        ]
        for timestamp in invalid:
            with self.subTest(timestamp=timestamp):
                result = analyze(block(start=timestamp))
                self.assertIn("invalid_timestamp", self.codes(result))
                self.assertEqual(result["summary"]["total_cues"], 1)
                self.assertGreater(result["summary"]["errors"], 0)

    def test_large_hour_value_is_supported(self):
        result = analyze(block(start="100:00:00,000", end="100:00:02,000"))
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["cues"][0]["start_ms"], 360_000_000)

    def test_reversed_and_zero_duration_do_not_crash_or_compute_speed(self):
        for start, end in [("00:00:02,000", "00:00:01,000"),
                           ("00:00:02,000", "00:00:02,000")]:
            with self.subTest(start=start, end=end):
                result = analyze(block(start=start, end=end, body="字" * 100))
                self.assertIn("reversed_time", self.codes(result))
                self.assertNotIn("high_cps", self.codes(result))
                self.assertGreater(result["summary"]["errors"], 0)

    def test_empty_subtitle_body_is_reported(self):
        result = analyze(block(body=""))
        self.assertEqual(result["summary"]["total_cues"], 1)
        self.assertEqual(result["cues"][0]["text"], "")
        self.assertIn("empty_cue", self.codes(result))

    def test_malformed_block_is_retained_between_valid_cues(self):
        text = "\n\n".join([
            block(),
            "2\n这段没有时间轴\n还应该保留这一行",
            block(label="3", start="00:00:03,000", end="00:00:05,000"),
        ])
        result = analyze(text)
        self.assertEqual([cue["index"] for cue in result["cues"]], [1, 2, 3])
        self.assertEqual(result["summary"]["total_cues"], 3)
        self.assertIn("这段没有时间轴", result["cues"][1]["text"])
        self.assertIn("还应该保留这一行", result["cues"][1]["text"])
        self.assertIn("missing_timestamp", self.codes(result))
        self.assertEqual(result["cues"][2]["start_ms"], 3000)

    def test_missing_index_does_not_drop_timestamp_or_text(self):
        result = analyze("00:00:00,000 --> 00:00:02,000\n正文")
        self.assertIn("invalid_index", self.codes(result))
        self.assertEqual(result["cues"][0]["start_ms"], 0)
        self.assertEqual(result["cues"][0]["text"], "正文")

    def test_nested_overlap_checks_earlier_long_interval(self):
        text = "\n\n".join([
            block(start="00:00:00,000", end="00:00:10,000"),
            block(label="2", start="00:00:01,000", end="00:00:02,000"),
            block(label="3", start="00:00:03,000", end="00:00:04,000"),
        ])
        result = analyze(text)
        self.assertEqual([issue["cue"] for issue in self.issues_for(result, "overlap")], [2, 3])

    def test_touching_boundaries_do_not_overlap(self):
        result = analyze(block() + "\n\n" + block(
            label="2", start="00:00:02,000", end="00:00:04,000"))
        self.assertEqual(result["issues"], [])

    def test_out_of_order_nonoverlapping_cues_are_identified(self):
        text = block(start="00:00:04,000", end="00:00:06,000") + "\n\n" + block(label="2")
        result = analyze(text)
        self.assertIn("out_of_order", self.codes(result))
        self.assertNotIn("overlap", self.codes(result))
        self.assertEqual(self.issues_for(result, "out_of_order")[0]["cue"], 2)

    def test_numbering_checks_use_physical_block_position(self):
        result = analyze(block(label="7") + "\n\n" + block(
            label="7", start="00:00:03,000", end="00:00:05,000"))
        self.assertEqual([cue["index"] for cue in result["cues"]], [1, 2])
        self.assertEqual([cue["label"] for cue in result["cues"]], ["7", "7"])
        self.assertEqual([issue["cue"] for issue in self.issues_for(result, "unexpected_index")], [1, 2])

    def test_nonnumeric_index_is_an_error(self):
        result = analyze(block(label="first"))
        self.assertIn("invalid_index", self.codes(result))
        self.assertEqual(result["cues"][0]["start_ms"], 0)
        self.assertGreater(result["summary"]["errors"], 0)

    def test_threshold_boundaries_are_inclusive(self):
        result = analyze(block(end="00:00:01,000", body="四个汉字"),
                         max_chars=4, min_duration_ms=1000, max_cps=4.0)
        self.assertEqual(result["issues"], [])
        result = analyze(block(end="00:00:00,999", body="四个汉字"),
                         max_chars=3, min_duration_ms=1000, max_cps=4.0)
        self.assertIn("long_line", self.codes(result))
        self.assertIn("short_duration", self.codes(result))
        self.assertIn("high_cps", self.codes(result))

    def test_reading_speed_counts_all_lines_and_ignores_linebreaks(self):
        result = analyze(block(body="甲乙\n丙丁"), max_chars=2, max_cps=1.9)
        self.assertNotIn("long_line", self.codes(result))
        self.assertIn("high_cps", self.codes(result))

    def test_common_markup_entities_and_padding_use_visible_characters(self):
        body = '  <b>你好</b> &amp; <font color="red"><i>世界</i></font>  '
        result = analyze(block(body=body), max_chars=7, max_cps=3.5)
        self.assertNotIn("long_line", self.codes(result))
        self.assertNotIn("high_cps", self.codes(result))
        result = analyze(block(body=body), max_chars=6, max_cps=3.4)
        self.assertIn("long_line", self.codes(result))
        self.assertIn("high_cps", self.codes(result))
        self.assertEqual(result["cues"][0]["text"].strip(), body.strip())

    def test_source_lines_remain_correct_with_leading_and_extra_blank_lines(self):
        text = "\n\n" + block() + "\n\n\n" + block(
            label="2", start="00:00:03,000", end="00:00:05,000", body="短\n这是很长的一行")
        result = analyze(text, max_chars=4)
        self.assertEqual([cue["line"] for cue in result["cues"]], [3, 8])
        long_lines = self.issues_for(result, "long_line")
        self.assertEqual([(issue["cue"], issue["line"]) for issue in long_lines], [(2, 11)])

    def test_summary_counts_match_issue_severities(self):
        result = analyze(block(label="9", end="00:00:00,200", body="字" * 30))
        self.assertEqual(result["summary"]["errors"], sum(
            issue["severity"] == "error" for issue in result["issues"]))
        self.assertEqual(result["summary"]["warnings"], sum(
            issue["severity"] == "warning" for issue in result["issues"]))
        for issue in result["issues"]:
            self.assertIn(issue["severity"], ("error", "warning"))
            self.assertTrue(issue["message"])
            self.assertGreaterEqual(issue["line"], 1)

    def test_duration_is_valid_subtitle_span_including_gaps(self):
        text = "\n\n".join([
            block(start="00:00:02,000", end="00:00:04,000"),
            block(label="2", start="00:00:09,000", end="00:00:11,000"),
            block(label="3", start="00:00:20,000", end="00:00:15,000"),
        ])
        result = analyze(text)
        self.assertEqual(result["summary"]["duration_ms"], 9000)
        self.assertEqual(result["summary"]["total_cues"], 3)

    def test_invalid_threshold_values_are_rejected(self):
        invalid_values = {
            "max_chars": [0, -1, 1.5, True, "24", None],
            "min_duration_ms": [0, -1, 1.5, True, "800", None],
            "max_cps": [0, -1, math.nan, math.inf, -math.inf, True, "18", None],
        }
        for name, values in invalid_values.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        analyze(block(), **{name: value})


if __name__ == "__main__":
    unittest.main()
