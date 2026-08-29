import unittest

from huya_ck.features.template import render


class TemplateTest(unittest.TestCase):
    def test_plain_variables(self) -> None:
        self.assertEqual(render("谢谢{nick}的{item_name}", {"nick": "乙", "item_name": "火箭"}), "谢谢乙的火箭")

    def test_unknown_token_is_literal(self) -> None:
        self.assertEqual(render("哈哈{x}哈", {"nick": "乙"}), "哈哈x哈")

    def test_variable_with_empty_value_is_empty(self) -> None:
        self.assertEqual(render("a{nick}b", {"nick": ""}), "ab")

    def test_variable_with_none_value_is_empty(self) -> None:
        self.assertEqual(render("a{nick}b", {"nick": None}), "ab")

    def test_fallback_first_non_empty(self) -> None:
        data = {"guard_prefix": "", "noble_prefix": "公爵", "nick": "甲"}
        self.assertEqual(render("欢迎{guard_prefix|noble_prefix}{nick}哥", data), "欢迎公爵甲哥")

    def test_fallback_literal_default(self) -> None:
        self.assertEqual(render("欢迎{guard_prefix|贵宾}{nick}", {"guard_prefix": "", "nick": "甲"}), "欢迎贵宾甲")

    def test_fallback_all_variables_empty(self) -> None:
        self.assertEqual(render("欢迎{guard_prefix|noble_prefix}{nick}", {"guard_prefix": "", "noble_prefix": "", "nick": "甲"}), "欢迎甲")

    def test_bool_variable(self) -> None:
        self.assertEqual(render("{has_guard}", {"has_guard": "yes"}), "yes")
        self.assertEqual(render("{has_guard|路人}{nick}", {"has_guard": "", "nick": "甲"}), "路人甲")

    def test_empty_template(self) -> None:
        self.assertEqual(render("", {"nick": "甲"}), "")


if __name__ == "__main__":
    unittest.main()
