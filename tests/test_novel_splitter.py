import unittest

from huya_ck.features.novel.splitter import clean_text, split_segments


class SplitterTest(unittest.TestCase):
    def test_clean_strips_bom_and_normalizes_newlines(self) -> None:
        raw = "﻿第一行\r\n\r\n\r\n第二  行\r第三行\n"
        self.assertEqual(clean_text(raw), "第一行\n\n第二 行\n第三行")

    def test_splits_by_paragraph_and_primary_punctuation(self) -> None:
        text = "第一段。\n第二段？还有一句！"
        segments = split_segments(text, max_chars=20)
        # 段落优先：不超限的整段保持一条
        self.assertEqual(segments, ["第一段。", "第二段？还有一句！"])
        # 超限段落按句末标点切开
        self.assertEqual(split_segments(text, max_chars=5), ["第一段。", "第二段？", "还有一句！"])

    def test_long_sentence_falls_back_to_secondary_then_hard_cut(self) -> None:
        # 无任何标点的超长文本只能硬切
        segments = split_segments("字" * 55, max_chars=20)
        self.assertEqual([len(seg) for seg in segments], [20, 20, 15])
        # 次级标点优先于硬切
        segments2 = split_segments("一二三四五，六七八九十、十一十二", max_chars=8)
        self.assertEqual(segments2, ["一二三四五，", "六七八九十、", "十一十二"])

    def test_no_empty_segments(self) -> None:
        segments = split_segments("。。。！！！\n\n？？", max_chars=10)
        self.assertTrue(all(seg for seg in segments))

    def test_segments_are_plain_text(self) -> None:
        text = "。".join(f"第{i}句话内容" for i in range(30)) + "。"
        segments = split_segments(text, max_chars=30)
        self.assertGreater(len(segments), 1)
        for seg in segments:
            self.assertFalse(seg.startswith("【"))

    def test_every_segment_within_limit(self) -> None:
        paragraph = "深夜一栋乌漆墨黑的大楼某层房间依旧亮着灯盛夏的太阳路一个人影，高个儿的窈窕少女穿无袖的运动之中，坐太婆位置上留也就是挠痒痒。"
        for limit in (15, 20, 28):
            segments = split_segments(paragraph, max_chars=limit)
            self.assertGreater(len(segments), 1)
            for seg in segments:
                self.assertLessEqual(len(seg), limit)
            # 拼回去不丢字（去掉拆分处吞掉的换行即可完全还原）
            self.assertEqual("".join(segments), paragraph)


if __name__ == "__main__":
    unittest.main()
