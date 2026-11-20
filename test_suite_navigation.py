"""The server-rendered header must not split JavaScript in a page body."""
import unittest

from flask import Flask
from suite_navigation import install


class HeaderInjectionTests(unittest.TestCase):
    def test_literal_closing_body_in_script_is_preserved(self):
        app = Flask(__name__)

        @app.get('/')
        def page():
            return '<!doctype html><body><script>const marker="</body>";</script><p>Ready</p></body>'

        install(app, current='scope', default=('scope',))
        with app.test_client() as client:
            response = client.get('/')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('const marker="</body>";', body)
        self.assertEqual(body.count('/api/suite/navigation.js?v='), 1)
        self.assertLess(body.index('<p>Ready</p>'), body.index('<script defer src="/api/suite/navigation.js'))


if __name__ == '__main__':
    unittest.main()
