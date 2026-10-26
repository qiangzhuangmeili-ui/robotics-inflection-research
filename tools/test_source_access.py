"""Meaningful fault-path checks for the P03 full-universe incident guard."""
import json, unittest, uuid
from pathlib import Path
import requests
from source_access import SourceAccess, CircuitOpen, SourceFailure, DocumentUnavailable

class Response:
    def __init__(self,status=200,value=None,content=b''):self.status_code=status;self.value=value;self.content=content
    def json(self):
        if self.value is None:raise ValueError('bad json')
        return self.value

class FaultTests(unittest.TestCase):
    def setUp(self):
        self.state=Path(__file__).resolve().parents[1]/'sources/p03_tests'/(uuid.uuid4().hex+'.json')
        self.calls=0;self.now=1000
    def adapter(self,fn):return SourceAccess(self.state,transport=fn,sleeper=lambda _:None,clock=lambda:self.now)
    def test_global_proxy_failure_stops_1054_company_queue(self):
        def fail(*a,**k):self.calls+=1;raise requests.exceptions.ProxyError()
        access=self.adapter(fail)
        with self.assertRaises(SourceFailure):access.request('provider','GET','https://example.test')
        for _ in range(1054):
            with self.assertRaises(CircuitOpen):access.request('provider','GET','https://example.test')
        self.assertEqual(self.calls,2);self.assertEqual(len(json.loads(self.state.read_text())),1)
    def test_circuit_persists_across_resume_and_requires_known_good_after_cooldown(self):
        access=self.adapter(lambda *a,**k:Response(429))
        with self.assertRaises(SourceFailure):access.request('provider','GET','https://example.test')
        resumed=self.adapter(lambda *a,**k:Response(value={'ok':True}))
        self.now+=901
        with self.assertRaises(CircuitOpen):resumed.request('provider','GET','https://example.test')
        self.assertEqual(resumed.request('provider','GET','https://example.test',known_good_probe=True),{'ok':True})
        self.assertIsNone(resumed.states['provider'].opened_at)
    def test_404_does_not_mark_whole_source_down(self):
        access=self.adapter(lambda *a,**k:Response(404))
        with self.assertRaises(DocumentUnavailable):access.request('provider','GET','https://example.test')
        self.assertIsNone(access.states['provider'].opened_at);self.assertEqual(access.states['provider'].failures,0)
    def test_empty_known_report_index_is_not_a_missing_report(self):
        access=self.adapter(lambda *a,**k:Response(value={'announcements':[],'totalAnnouncement':0}))
        with self.assertRaisesRegex(SourceFailure,'NOT_MISSING_REPORT'):access.annual_index_probe('BJ:920207','org')
        with self.assertRaises(CircuitOpen):access.annual_index_probe('BJ:920207','org')
    def test_bj_routes_explicitly_and_wrong_issuer_is_rejected(self):
        seen=[]
        def route(*a,**k):seen.append(k['data']);return Response(value={'announcements':[{'secCode':'000001'}]})
        access=self.adapter(route)
        with self.assertRaisesRegex(SourceFailure,'ISSUER_MISMATCH'):access.annual_index_probe('BJ:920207','org')
        self.assertEqual(seen[0]['column'],'szse');self.assertEqual(seen[0]['stock'],'920207,org')
    def test_html_instead_of_pdf_never_counts_as_download(self):
        access=self.adapter(lambda *a,**k:Response(content=b'<html>login</html>'))
        with self.assertRaisesRegex(SourceFailure,'NON_PDF_RESPONSE'):access.request('pdf','GET','https://example.test',kind='pdf')

if __name__=='__main__':unittest.main(verbosity=2)
