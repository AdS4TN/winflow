from __future__ import annotations

import json
import unittest


class IconMapPrivacyTests(unittest.TestCase):
    def test_serialized_icon_map_uses_relative_paths(self) -> None:
        from app.config import PROJECT_ROOT
        from app.icon_map import serialize_icon_map

        payload = serialize_icon_map()
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertEqual("data/icon_map.json", payload["path"])
        self.assertEqual("static/icons", payload["static_icon_root"])
        self.assertNotIn(str(PROJECT_ROOT), serialized)
        self.assertNotIn("\\Users\\", serialized)
        self.assertNotIn("C:\\", serialized)


if __name__ == "__main__":
    unittest.main()
