import csv
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('probe', ROOT / 'probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def test_ramp_changes_every_message_including_turns_and_wrap_with_display_rounding(self):
        for decimals in (None, 2):
            previous = None
            for sequence in range(1, 1801):
                data = json.loads(probe.payload('dashboard', sequence / 2, 'run', sequence,
                                                decimals, 'ramp'))
                left = round(data['ultrasonic_left_m'], 2)
                right = round(data['ultrasonic_right_m'], 2)
                self.assertTrue(.5 <= left <= .8)
                self.assertAlmostEqual(right - left, .03)
                self.assertAlmostEqual(data['height_m'], left - .2)
                if previous is not None:
                    self.assertAlmostEqual(abs(left - previous), .02)
                previous = left

    def test_payload_contract_and_rounding_preserve_timestamps_and_coordinates(self):
        for elapsed, expected in ((0, .5), (5, .8), (10, .5)):
            data = json.loads(probe.payload('dashboard', elapsed, 'run', 7, 2))
            self.assertEqual(data['ultrasonic_left_m'], expected)
            self.assertTrue(data['ultrasonic_left_valid'])
            self.assertIsInstance(data['header']['stamp']['sec'], int)
            self.assertEqual(data['_probe']['sequence'], 7)
        raw_map = json.loads(probe.payload('map', 2, 'run', 1))
        rounded_map = json.loads(probe.payload('map', 2, 'run', 1, 2))
        self.assertEqual(raw_map['latitude_deg'], rounded_map['latitude_deg'])
        self.assertEqual(raw_map['longitude_deg'], rounded_map['longitude_deg'])
        self.assertFalse(json.loads(probe.payload('recording_state', 0, 'run', 1))['recording'])

    def test_analysis_detects_latency_growth_disconnects_and_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / 'run.json').write_text('{"rates_hz":{"dashboard":2}}')
            log = probe.Recorder(directory)
            log.event('publisher', 'publish', stream='dashboard', rc=0)
            log.event('publisher', 'publish', stream='dashboard', rc=None)
            log.event('tcp', 'disconnected', expected=False, code=128)
            log.event('tcp', 'disconnected', expected=True, code=0)
            log.close()
            with (directory / 'samples.csv').open('a', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerows([(0, 'tcp', 'dashboard', 1, 10, 900),
                                  (1, 'tcp', 'dashboard', 2, 12, 900),
                                  (180, 'tcp', 'dashboard', 3, 2000, 900),
                                  (181, 'tcp', 'dashboard', 3, 2002, 900)])
            summary = probe.analyze(directory)
            data = summary['streams']['tcp/dashboard']
            self.assertEqual(len(summary['disconnects']), 1)
            self.assertEqual(data['duplicates'], 1)
            self.assertEqual(data['first_minute_p50_ms'], 11)
            self.assertEqual(data['last_minute_p50_ms'], 2001)
            self.assertEqual(data['max_receive_gap_s'], 179)
            self.assertEqual(summary['publish_counts']['dashboard']['skipped_offline'], 1)
            self.assertTrue((directory / 'report.md').exists())

    def test_empty_run_is_explicitly_unsuccessful_in_report(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / 'run.json').write_text('{}')
            log = probe.Recorder(directory)
            log.event('test', 'startup_timeout', not_ready=['tcp'])
            log.close()
            summary = probe.analyze(directory)
            self.assertEqual(len(summary['failures']), 1)
            self.assertIn('not a successful test', (directory / 'report.md').read_text())

    def test_subscriber_credentials_override_inherited_boat_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            config = dict(publisher=dict(host='example.invalid', port=8883,
                                        username='boat', password='boat-test-only'),
                          subscribers=[dict(name='ws', port=8084, transport='websockets',
                                            username_env='TEST_SUB_USER', password_env='TEST_SUB_PASSWORD')])
            path = directory / 'config.json'
            path.write_text(json.dumps(config))
            with patch.dict(os.environ, TEST_SUB_USER='operator', TEST_SUB_PASSWORD='operator-test-only'):
                pub, subs = probe.load_config(path)
            self.assertEqual(pub['password'], 'boat-test-only')
            self.assertEqual(subs[0]['password'], 'operator-test-only')
            self.assertEqual(subs[0]['username'], 'operator')


if __name__ == '__main__':
    unittest.main()
