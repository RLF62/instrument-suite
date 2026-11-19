"""New tools begin with one server-rendered header and a mobile-safe panel."""
import unittest
from pathlib import Path
from instrument_starter.app import app

class StarterPageTests(unittest.TestCase):
    def test_both_views_have_one_shared_header_and_working_navigation(self):
        client = app.test_client()
        for path, other in (('/classic', '/modern'), ('/modern', '/classic')):
            html = client.get(path).get_data(as_text=True)
            self.assertEqual(html.count('id="suite-unified-header"'), 1)
            self.assertIn('href="http://localhost:8080/"', html)
            self.assertIn('href="http://localhost' + other + '"', html)
            self.assertIn('href="http://localhost/docs/"', html)
            self.assertNotIn('<nav ', html)
            self.assertIn('width=device-width, initial-scale=1', html)
            self.assertIn('disabled', html)
        self.assertEqual(client.get('/docs/').status_code, 200)

    def test_mobile_panel_styles_do_not_override_desktop(self):
        css = (Path(__file__).parent / 'instrument_starter/static/starter.css').read_text()
        self.assertIn('@media(max-width:700px)', css)
        self.assertIn('minmax(0,1fr)', css)
        self.assertIn('max-width:100%', css)

if __name__ == '__main__':
    unittest.main()
