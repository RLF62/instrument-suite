import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import standalone_app
import suite_navigation
from flask import Flask, send_file

class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        registry_patch=patch.object(suite_navigation,'REGISTRY',Path(self.directory.name)/'registry.json')
        registry_patch.start();self.addCleanup(registry_patch.stop)
        self.client=standalone_app.app.test_client()

    def test_meter_host_has_no_supply_routes_or_hardware_on_page_load(self):
        with patch('hp34401a.execute') as execute:
            self.assertEqual(self.client.get('/').status_code,302)
            for path in ['/multimeter/classic','/multimeter/modern','/api/multimeter/status']:
                self.assertEqual(self.client.get(path).status_code,200)
            self.assertEqual(self.client.get('/api/status').status_code,404)
            execute.assert_not_called()

    def test_cross_origin_control_is_refused(self):
        with patch('hp34401a.execute') as execute:
            self.assertEqual(self.client.post('/api/control/meter/identify',json={},headers={'Origin':'http://other'}).status_code,403)
            execute.assert_not_called()

    def test_same_origin_control_uses_shared_backend(self):
        with patch('hp34401a.execute',side_effect=[{'identity':'HP,34401A,0,1'},{'function':'dcv'}]) as execute:
            r=self.client.post('/api/control/meter/identify',json={},headers={'Origin':'http://localhost'})
            self.assertEqual(r.status_code,200)
            self.assertEqual([c.args for c in execute.call_args_list],[('meter','identify'),('meter','configuration')])

    def test_navigation_defaults_to_meter_only_and_follows_explicit_selection(self):
        with tempfile.TemporaryDirectory() as d,patch.object(suite_navigation,'CONFIG',Path(d)/'tools.json'):
            self.assertEqual(suite_navigation.selected(),['meter'])
            suite_navigation.CONFIG.write_text(json.dumps({'instruments':['meter','scope']}))
            self.assertEqual(suite_navigation.selected(),['meter','scope'])
            script=self.client.get('/api/suite/navigation.js').text
            self.assertIn('"instruments": ["meter", "scope"]',script)
            suite_navigation.CONFIG.write_text('{"instruments":["unknown"]}')
            self.assertIn('"instruments": []',self.client.get('/api/suite/navigation.js').text)

    def test_shared_header_does_not_become_the_legacy_page_nav(self):
        app=Flask('legacy-nav-test')
        app.add_url_rule('/',view_func=lambda:'<html><body><nav aria-label="Instrument navigation"><strong>OLD</strong></nav><main>Controls</main></body></html>')
        suite_navigation.install(app,current='supply')
        html=app.test_client().get('/').text
        self.assertIn('<div id="suite-unified-header" role="navigation"',html)
        self.assertIn('<body data-suite-page="supply"><style>',html)
        self.assertIn('<nav aria-label="Instrument navigation"><strong>OLD</strong></nav>',html)
        self.assertNotIn('<nav id="suite-unified-header"',html)

    def test_counter_modern_navigation_uses_fresh_url(self):
        app=Flask('counter-nav-test')
        with app.test_request_context('http://192.168.1.108:8085/classic'):
            html=suite_navigation.header_html('counter','/classic','192.168.1.108',{})
        self.assertIn('href="http://192.168.1.108:8085/modern?header=2"',html)
        with app.test_request_context('http://192.168.1.108:8082/multimeter/modern'):
            html=suite_navigation.header_html('meter','/multimeter/modern','192.168.1.108',{'counter':{'scheme':'http','port':8085}})
        self.assertIn('href="http://192.168.1.108:8085/modern?header=2"',html)

    def test_packaged_scope_keeps_layout_button_outside_hidden_header(self):
        page=(Path(__file__).parent/'controllers/scope/index.html').read_text()
        toolbar='<div class="layoutbar suite-layoutbar">'
        self.assertEqual(page.count(toolbar),1)
        self.assertIn('id="editLayout"',page)
        self.assertIn('id="layout-customize"',page)
        self.assertLess(page.index('</nav>'),page.index(toolbar))
        self.assertNotIn('const tekHead=',page)
        self.assertNotIn('192.168.1.108',page)

    def test_file_served_scope_page_gets_navigation_without_stale_etag(self):
        with tempfile.TemporaryDirectory() as d:
            page=Path(d)/'index.html';page.write_text('<html><body><nav class="suite-direct-header">OLD</nav><main>Scope</main></body></html>')
            app=Flask('scope-test')
            app.add_url_rule('/',view_func=lambda:send_file(page))
            suite_navigation.install(app,current='scope')
            response=app.test_client().get('/')
            self.assertIn('/api/suite/navigation.js',response.text)
            self.assertEqual(response.text.count('id="suite-unified-header"'),1)
            self.assertIn('body[data-suite-page=scope] nav.suite-direct-header{display:none!important}',response.text)
            self.assertIn('<nav class="suite-direct-header">OLD</nav>',response.text)
            self.assertNotIn('ETag',response.headers)
