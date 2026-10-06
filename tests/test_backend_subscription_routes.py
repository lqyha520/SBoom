"""订阅消息目标必须存在于小程序页面注册表。"""

import json
import unittest
from pathlib import Path

from app.services.wechat_notices import destination


class SubscriptionRouteContracts(unittest.TestCase):
    def test_every_message_target_is_registered(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] / "miniprogram/src/pages.json").read_text(encoding="utf-8"))
        registered = {page["path"] for page in manifest["pages"]}
        registered.update(package["root"] + "/" + page["path"]
                          for package in manifest.get("subPackages", []) for page in package["pages"])
        for kind in ("paper", "feedback", "membership", "request", "closure", "order", "", "unrecognized"):
            with self.subTest(kind=kind):
                target = destination({"target_type": kind, "target_id": "fixture-id"})
                self.assertIn(target.split("?")[0], registered)
                self.assertTrue(target.endswith("?id=fixture-id"))

    def test_invalid_identifiers_cannot_change_the_destination(self):
        for identifier in ("../orders", "a&redirect=evil", "a#fragment", "x" * 65):
            with self.subTest(identifier=identifier):
                self.assertEqual(destination({"target_type": "order", "target_id": identifier}), "subpages/orders/index")
