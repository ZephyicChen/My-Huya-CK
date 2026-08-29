import unittest

from huya_ck.platform.bus import event_id_for


class BusTest(unittest.TestCase):
    def test_gift_order_dedupes_raw_and_official_but_not_new_order(self) -> None:
        base = {
            "type": "gift",
            "uri": 6501,
            "sender_uid": 7,
            "sender_nick": "甲",
            "item_name": "磁铁",
            "order_id": "pay-1",
        }
        official = dict(base, group="official-taf")
        new_gift = dict(base, order_id="pay-2")
        self.assertEqual(event_id_for(base), event_id_for(official))
        self.assertNotEqual(event_id_for(base), event_id_for(new_gift))


if __name__ == "__main__":
    unittest.main()
