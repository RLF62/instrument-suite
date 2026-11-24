"""The server-rendered header must not split JavaScript in a page body."""
import unittest
import importlib.util
from pathlib import Path

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


    def test_scope_link_follows_classic_and_modern_view_in_each_header(self):
        records = {'scope': {'scheme': 'http', 'port': 8081}}
        for name, source in (
            ('suite', Path('suite_navigation.py')),
            ('meter', Path('controllers/meter/suite_navigation.py')),
            ('generator', Path('controllers/generator/suite_navigation.py')),
        ):
            spec = importlib.util.spec_from_file_location(name + '_navigation_test', source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            app = Flask(__name__ + name)
            for current, classic, modern in (
                ('meter', '/multimeter/classic', '/multimeter/modern'),
                ('generator', '/generator/classic', '/generator/modern'),
                ('supply', '/classic-dual', '/'),
            ):
                with app.test_request_context('http://192.168.1.108:8082/'):
                    classic_header = module.header_html(current, classic, '192.168.1.108', records)
                    modern_header = module.header_html(current, modern, '192.168.1.108', records)
                self.assertIn('href="http://192.168.1.108:8081/classic">Tektronix', classic_header, (name, current))
                self.assertIn('href="http://192.168.1.108:8081/">Tektronix', modern_header, (name, current))


if __name__ == '__main__':
    unittest.main()
