import unittest
from generator_app import create_app

class GeneratorViews(unittest.TestCase):
    def setUp(self):
        self.app=create_app(simulated=True)
        self.app.config['TESTING']=True
        self.client=self.app.test_client()
        self.origin='http://localhost'

    def test_views_and_status(self):
        self.assertEqual(self.client.get('/generator/classic').status_code,200)
        self.assertEqual(self.client.get('/generator/modern').status_code,200)
        data=self.client.get('/api/generator/status').get_json()
        self.assertEqual(data['source'],'simulated')

    def test_control_requires_same_origin(self):
        response=self.client.post('/api/control/generator/configuration',json={})
        self.assertEqual(response.status_code,403)

    def test_apply_requires_acknowledgment(self):
        settings={'function':'SIN','frequency':1000,'amplitude':1,'offset':0,'load':'50'}
        response=self.client.post('/api/control/generator/apply',json={'settings':settings},headers={'Origin':self.origin})
        self.assertEqual(response.status_code,400)

    def test_apply_returns_verified_readback(self):
        settings={'function':'SIN','frequency':2000,'amplitude':1,'offset':0,'load':'50'}
        response=self.client.post('/api/control/generator/apply',json={'settings':settings,'confirm_output_change':True},headers={'Origin':self.origin})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['configuration']['frequency'],2000)

if __name__=='__main__':unittest.main()
