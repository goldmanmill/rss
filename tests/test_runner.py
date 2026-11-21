"""Run locally with python -m unittest discover -s tests (no live network needed)."""
import importlib.util
from pathlib import Path
import unittest

src = Path(__file__).resolve().parents[1] / "rss_to_mastodon.py"
spec = importlib.util.spec_from_file_location("rss_to_mastodon", src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SAMPLE = b'''<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel><title>Test</title><link>https://example.org</link><description>Test</description>
<item><title>Peace news</title><link>https://example.org/p1</link><description>Nonviolence workshop</description>
<media:content url="https://example.org/photo.jpg" type="image/jpeg"/></item>
<item><title>Recipe news</title><link>https://example.org/p2</link><description>Kitchen</description></item>
</channel></rss>'''

class BasicTests(unittest.TestCase):
    def test_rss_parsing_and_images(self):
        items = mod.parse_items(SAMPLE)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[-1]["title"], "Peace news")
        self.assertEqual(items[-1]["image"]["url"], "https://example.org/photo.jpg")
        self.assertIsNone(items[0]["image"])

    def test_filters(self):
        items = mod.parse_items(SAMPLE)
        feed = {"include_any": ["nonviolence"], "exclude_any": []}
        self.assertTrue(mod.meets_filter(items[-1], feed))
        self.assertFalse(mod.meets_filter(items[0], feed))
        feed["exclude_any"] = ["workshop"]
        self.assertFalse(mod.meets_filter(items[-1], feed))

    def test_message_tags(self):
        msg = mod.compose(mod.parse_items(SAMPLE)[-1], ["#Peace", "#Nonviolence"])
        self.assertIn("#Peace #Nonviolence", msg)
        self.assertIn("https://example.org/p1", msg)
        self.assertLess(len(msg), 501)

    def test_url_validation(self):
        self.assertTrue(mod.valid_http_url("https://example.com/feed"))
        self.assertFalse(mod.valid_http_url("file:///etc/passwd"))
        self.assertFalse(mod.valid_http_url("https://foo:password@example.com/x"))

if __name__ == "__main__":
    unittest.main()
