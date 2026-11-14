"""Regression coverage for the atlas pipeline; uses temporary synthetic inputs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from build_atlas import build, fit_frame, STANDARD_STATES, FRAME_COUNTS
from import_gif import despill, frames_from_strip

ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.atlas = self.folder / 'spritesheet.png'
        self.manifest = self.folder / 'pet.json'
        self.manifest.write_text(json.dumps({
            'id': 'test', 'displayName': 'Test', 'spriteVersionNumber': 2,
            'spritesheetPath': self.atlas.name,
        }), encoding='utf-8')

    def validate(self, expected):
        report = self.folder / 'report.json'
        result = subprocess.run([
            sys.executable, str(ROOT / 'tools/validate_atlas.py'), str(self.atlas),
            '--json-out', str(report),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return json.loads(report.read_text(encoding='utf-8'))

    def test_small_image_reports_failure(self):
        Image.new('RGBA', (10, 10)).save(self.atlas)
        self.assertFalse(self.validate(1)['ok'])

    def test_corrupt_and_missing_image(self):
        self.assertFalse(self.validate(1)['ok'])
        self.atlas.write_bytes(b'broken')
        self.assertFalse(self.validate(1)['ok'])

    def test_real_package_and_metadata_failures(self):
        with Image.open(ROOT / 'pets/salt/spritesheet.webp') as source:
            source.save(self.atlas)
        self.assertTrue(self.validate(0)['ok'])
        self.manifest.write_text('[]', encoding='utf-8')
        self.assertFalse(self.validate(1)['ok'])
        self.manifest.write_text('{', encoding='utf-8')
        self.assertFalse(self.validate(1)['ok'])
        self.manifest.unlink()
        self.assertFalse(self.validate(1)['ok'])

    def test_unused_faint_pixel_is_rejected(self):
        with Image.open(ROOT / 'pets/salt/spritesheet.webp') as source:
            img = source.convert('RGBA')
        img.putpixel((7 * 192 + 10, 10), (255, 0, 0, 1))
        img.save(self.atlas)
        report = self.validate(1)
        self.assertTrue(any('unused column' in e for e in report['errors']))

    def test_wrong_manifest_target_is_rejected(self):
        with Image.open(ROOT / 'pets/salt/spritesheet.webp') as source:
            source.save(self.atlas)
        data = json.loads(self.manifest.read_text())
        data['spritesheetPath'] = '../other.png'
        self.manifest.write_text(json.dumps(data), encoding='utf-8')
        self.assertFalse(self.validate(1)['ok'])

    def test_missing_frames_directory_does_not_silently_build_placeholder(self):
        with self.assertRaises(ValueError):
            build(self.folder / 'missing')

    def test_frame_fit_preserves_aspect_ratio(self):
        fitted = fit_frame(Image.new('RGBA', (400, 100), 'red'))
        self.assertEqual(fitted.size, (192, 208))
        self.assertEqual(fitted.getchannel('A').getbbox(), (0, 160, 192, 208))

    def test_invalid_strip_columns(self):
        Image.new('RGBA', (10, 10)).save(self.atlas)
        for cols in (0, 3, 11):
            with self.assertRaises(ValueError):
                frames_from_strip(self.atlas, cols)

    def test_despill_removes_white_matte_instead_of_adding_it(self):
        image = Image.new('RGBA', (1, 1), (255, 127, 127, 128))
        self.assertEqual(despill(image, (255, 255, 255), strength=1).getpixel((0, 0)),
                         (255, 0, 0, 128))

    def test_expression_sheet_contract(self):
        folder = ROOT / 'pets/salt'
        metadata = json.loads((folder / 'expressions.json').read_text(encoding='utf-8'))
        with Image.open(folder / metadata['spritesheetPath']) as image:
            self.assertEqual(image.size, (1536, 832))
            self.assertEqual(len(metadata['items']), 4)
            for item in metadata['items']:
                self.assertEqual(item['frames'], FRAME_COUNTS[STANDARD_STATES.index(item['state'])])
                for col in range(8):
                    alpha = image.crop((col * 192, item['row'] * 208,
                                        (col + 1) * 192, (item['row'] + 1) * 208)).getchannel('A')
                    if col < item['frames']:
                        self.assertIsNotNone(alpha.getbbox())
                    else:
                        self.assertIsNone(alpha.getbbox())


if __name__ == '__main__':
    unittest.main()
