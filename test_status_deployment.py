"""Read-only status must describe the actual HTTP or HTTPS deployment."""
import unittest
from unittest.mock import Mock, patch
from maintenance import cli
from maintenance.security import MaintenanceError

class StatusDeploymentTests(unittest.TestCase):
    def report(self, https):
        host = Mock()
        host.https_gateway.return_value = https
        host.service.return_value = 'fischer-suite-web' if https else 'fischer-suite-dashboard'
        host.discover.return_value = {'suite', 'meter'}
        host.active.return_value = True
        engine = Mock()
        engine.state.return_value = {'schema':1, 'components':{'suite':{'version':'v1.0.0'}}}
        engine.pending.exists.return_value = False
        with patch.object(cli,'LinuxHost',return_value=host), patch.object(cli,'Engine',return_value=engine):
            result = cli.execute('status')
        return result, host, engine

    def test_https_status_uses_gateway_url_and_journal(self):
        result, host, engine = self.report(True)
        self.assertEqual(result['dashboard'], 'https://RASPBERRY_PI_ADDRESS/')
        self.assertIn('sudo journalctl -u fischer-suite-web -n 60 --no-pager',result['troubleshooting'])
        self.assertEqual(result['services'], {'meter':'active','suite':'active'})
        self.assertFalse(engine.apply.called)
        self.assertFalse(host.start.called)
        self.assertFalse(host.stop.called)

    def test_http_status_keeps_http_dashboard_and_service(self):
        result, host, engine = self.report(False)
        self.assertEqual(result['dashboard'], 'http://RASPBERRY_PI_ADDRESS:8080/')
        self.assertIn('sudo journalctl -u fischer-suite-dashboard -n 60 --no-pager',result['troubleshooting'])
        self.assertFalse(engine.apply.called)

    def test_unverified_deployment_policy_does_not_report_http_as_fallback(self):
        host=Mock()
        host.https_gateway.side_effect=MaintenanceError('Deployment policy requires review')
        with patch.object(cli,'LinuxHost',return_value=host), patch.object(cli,'Engine'):
            with self.assertRaisesRegex(MaintenanceError,'review'):
                cli.execute('status')
        self.assertFalse(host.start.called)
        self.assertFalse(host.stop.called)
