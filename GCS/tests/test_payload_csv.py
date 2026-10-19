import asyncio
import json
import os
import sys
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from backend.payload_csv import fetch_capture, parse_capture, sample_key, watch
from backend.payload_csv_remote import read_capture

SAMPLE = dict(request_id='8', sample=1, time=1000, mcu_uid='0000000000000001', mcu_boot=2,
              values={'PCA model': {'value': 'DEMO_ONLY'}})
RESULT = 'PCA,DEMO_ONLY,1,1000,6000,10,9,1,34,27,28,0.1,0.2,0.3,0,DEMO_ONLY'
RAW = '1500,1,2,3,34,25,27,12000,110,28,1,1,1,0x00\n'


class PayloadCSVTests(unittest.TestCase):
    def test_sensor_mapping_faults_and_sequence_window(self):
        csv = ('500,1,2,3,34,25,27,12000,110,28,1,1,1,0x00\n' + RAW +
               '2000,1,2,3,34,25,nan,12000,110,28,1,0,1,0x04\n' +
               '5000,1,2,3,35,25,27,12000,110,29,1,1,1,0x00\n' + RESULT)
        trace = parse_capture(csv, SAMPLE)
        self.assertEqual(trace['key'], sample_key(SAMPLE))
        self.assertEqual(trace['duration_s'], 5)
        self.assertEqual(trace['sample_count'], 3)
        self.assertEqual(trace['points'][0]['values'], [27,28,34])
        self.assertEqual(trace['points'][1]['values'], [None,None,34])
        self.assertTrue(trace['points'][2]['gap_before'])
        json.dumps(trace, allow_nan=False)

    def test_millis_wrap(self):
        csv = RAW.replace('1500,', '100,') + RESULT.replace(',1000,6000,', ',4294967000,1000,')
        trace = parse_capture(csv, SAMPLE)
        self.assertAlmostEqual(trace['points'][0]['t'], .396)

    def test_unfinished_or_wrong_model_is_rejected(self):
        for csv in [RAW, RAW+RESULT.replace('PCA,DEMO_ONLY,','PCA,other,')]:
            with self.assertRaises(ValueError): parse_capture(csv, SAMPLE)

    def test_matching_request_boot_and_sequence_not_latest_filename(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            csv = root / 'payload-uid-boot000002-seq000001-100.csv'
            csv.write_text(RAW+RESULT)
            event = dict(event='END', payload_seq_id=1, request_id=8, mcu_uid=SAMPLE['mcu_uid'],
                         mcu_boot_id=2, stamp_ns=1)
            csv.with_suffix('.events.jsonl').write_text(json.dumps(event)+'\n')
            found = read_capture(SAMPLE, [root])
            self.assertEqual(found['csv'], RAW+RESULT)
            self.assertEqual(found['bytes'], len(RAW+RESULT))
            self.assertIn('error', read_capture(dict(SAMPLE, mcu_boot=3), [root]))
            self.assertIn('error', read_capture(dict(SAMPLE, request_id='9',mcu_uid=None,mcu_boot=None), [root]))
            self.assertEqual(read_capture(dict(SAMPLE,request_id='9'),[root])['filename'],csv.name)
            recovered = root / 'payload-uid-boot000002-seq000001-200-recovered.csv'
            recovered.write_text(RESULT)
            recovered.with_suffix('.events.jsonl').write_text(json.dumps(dict(event, event='RESULT_RECOVERED',stamp_ns=2)))
            self.assertEqual(read_capture(SAMPLE,[root])['filename'],csv.name)


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_once_and_keep_trace_for_next_active_sequence(self):
        state = SimpleNamespace(host='pi', payload_sample=SAMPLE, payload_trace=None,
                                payload_trace_status={})
        calls = []
        async def fetch(host, sample):
            calls.append(sample)
            return parse_capture(RAW+RESULT,sample)
        task = asyncio.create_task(watch(state,fetch))
        try:
            await asyncio.sleep(.01)
            self.assertEqual(state.payload_trace_status['state'],'ready')
            await asyncio.sleep(1.05)
            self.assertEqual(len(calls),1)
            self.assertEqual(state.payload_trace['sample'],1)
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)

    async def test_stdin_reader_and_parser_roundtrip(self):
        with TemporaryDirectory() as directory:
            csv = Path(directory) / 'payload-uid-boot000002-seq000001-100.csv'
            csv.write_text(RAW+RESULT)
            csv.with_suffix('.events.jsonl').write_text(json.dumps(dict(
                event='END',payload_seq_id=1,request_id=8,mcu_uid=SAMPLE['mcu_uid'],
                mcu_boot_id=2,stamp_ns=1)))
            with patch.dict(os.environ, {'LOONAR_PAYLOAD_CSV_DIR':directory}), patch(
                    'backend.payload_csv.ssh_command',return_value=([sys.executable,'-'],dict(os.environ))):
                result = await fetch_capture('fixture',SAMPLE)
            self.assertEqual(result['bytes'],len(RAW+RESULT))
            self.assertEqual(result['points'][0]['values'],[27,28,34])

    async def test_old_fetch_cannot_replace_new_result(self):
        state = SimpleNamespace(host='pi', payload_sample=SAMPLE, payload_trace=None,
                                payload_trace_status={})
        started, finish = asyncio.Event(), asyncio.Event()
        async def fetch(host, sample):
            started.set()
            await finish.wait()
            return parse_capture(RAW+RESULT,sample)
        task = asyncio.create_task(watch(state,fetch))
        try:
            await started.wait()
            state.payload_sample = None
            finish.set()
            await asyncio.sleep(.01)
            self.assertIsNone(state.payload_trace)
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)


if __name__ == '__main__': unittest.main()
