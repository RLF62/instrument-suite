"""The signed candidate must retain the suite installer's reviewed supply UI."""
from pathlib import Path
import tempfile
import unittest

from tools.build_candidate import apply_suite_templates


class CandidateTemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.suite = self.root/'suite'
        self.payload = self.root/'payload'
        (self.suite/'integration/templates').mkdir(parents=True)
        (self.payload/'templates').mkdir(parents=True)
        for name, content in [('index.html', b'preserved chart and layout'),
                              ('classic_dual_preview.html', b'preserved mobile width and layout')]:
            (self.suite/'integration/templates'/name).write_bytes(content)
            (self.payload/'templates'/name).write_bytes(b'older controller template')

    def test_both_preserved_templates_replace_older_package_views_exactly(self):
        apply_suite_templates(self.suite, self.payload)
        for name in ('index.html', 'classic_dual_preview.html'):
            self.assertEqual((self.payload/'templates'/name).read_bytes(),
                             (self.suite/'integration/templates'/name).read_bytes())

    def test_overlay_leaves_control_code_settings_and_other_views_unchanged(self):
        paths = ['app.py', 'config.json', 'templates/control_confirmation.html',
                 'templates/software_updates.html']
        for name in paths:
            (self.payload/name).write_bytes(('retained '+name).encode())
        before = {name:(self.payload/name).read_bytes() for name in paths}
        apply_suite_templates(self.suite, self.payload)
        self.assertEqual({name:(self.payload/name).read_bytes() for name in paths}, before)

    def test_missing_reviewed_template_blocks_before_overwriting_either_view(self):
        (self.suite/'integration/templates/classic_dual_preview.html').unlink()
        before = (self.payload/'templates/index.html').read_bytes()
        with self.assertRaisesRegex(SystemExit, 'missing'):
            apply_suite_templates(self.suite, self.payload)
        self.assertEqual((self.payload/'templates/index.html').read_bytes(), before)

    def test_symlinked_template_is_rejected(self):
        path = self.suite/'integration/templates/index.html'
        path.unlink()
        try:
            path.symlink_to(self.suite/'integration/templates/classic_dual_preview.html')
        except OSError:
            self.skipTest('Symlink creation unavailable')
        with self.assertRaisesRegex(SystemExit, 'symlinked'):
            apply_suite_templates(self.suite, self.payload)
