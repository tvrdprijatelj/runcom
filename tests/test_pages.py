from html.parser import HTMLParser
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.ids=[]; self.labels=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if 'id' in attrs: self.ids.append(attrs['id'])
        if tag=='label': self.labels.append(attrs.get('for'))
        for name in ('href','src'):
            if name in attrs: self.links.append(attrs[name])
class PageTests(unittest.TestCase):
    def test_local_links_fragments_and_labels(self):
        for path in ROOT.glob('*.html'):
            with self.subTest(page=path.name):
                page=Page();page.feed(path.read_text(encoding='utf-8'))
                self.assertEqual(len(page.ids),len(set(page.ids)))
                for label in page.labels: self.assertIn(label,page.ids)
                for link in page.links:
                    if link.startswith('https:'):continue
                    if link.startswith('#'):self.assertIn(link[1:],page.ids)
                    else:self.assertTrue((ROOT/link).is_file(),link)
