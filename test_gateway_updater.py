import unittest
from unittest.mock import patch
from flask import Flask
import suite_gateway
from maintenance import web_updates

class GatewayUpdaterRoutesTests(unittest.TestCase):
    def test_enrolled_gateway_exposes_update_page_and_fails_closed_when_disabled(self):
        app=Flask('enrolled-gateway')
        with patch.object(suite_gateway.Path,'is_file',return_value=True):
            suite_gateway.install_updater_routes(app)
        client=app.test_client()
        with patch.object(web_updates,'read_policy',return_value={'mode':'disabled'}), patch.object(web_updates,'helper') as helper:
            self.assertEqual(client.get('/software-updates').status_code,200)
            self.assertEqual(client.get('/api/software-updates').status_code,403)
            helper.assert_not_called()

    def test_existing_gateway_without_updater_retains_no_new_routes(self):
        app=Flask('legacy-gateway')
        with patch.object(suite_gateway.Path,'is_file',return_value=False):
            suite_gateway.install_updater_routes(app)
        self.assertEqual(app.test_client().get('/software-updates').status_code,404)
