"""FND ledger scenarios, independent of scheduling and model calls."""
import copy
import unittest
from helpers import done
from taskrunner import findings as f

R = {'id': 'review-pe', 'persona_code': 'PE', 'advisory': False}
S = {'id': 'review-sc', 'persona_code': 'SC', 'advisory': False}


def finding(location='src/a:2', severity='blocking', caused_by=''):
    return dict(severity=severity, title='Fix this', detail='Evidence', location=location, caused_by=caused_by)


def review(items=(), resolutions=(), verdict=None):
    if verdict is None:
        verdict = 'block' if any(x['severity'] == 'blocking' for x in items) or any(
            x['status'] == 'unresolved' for x in resolutions) else 'pass'
    return dict(verdict=verdict, summary='Reviewed.', findings=list(items), resolutions=list(resolutions))


def resolution(fid='make/PE-1', status='resolved'):
    return dict(finding=fid, status=status, note='Checked')


class Findings(unittest.TestCase):
    def initial(self):
        return f.apply_review(f.empty('make'), R, review([finding()]), 'C1', {})[0]

    def test_unique_ids_and_complete_history(self):
        a = self.initial()
        b, _ = f.apply_review(f.empty('other'), R, review([finding()]), 'C1', {})
        self.assertNotEqual(a['findings'][0]['id'], b['findings'][0]['id'])
        a = f.respond(a, done(responses=[dict(finding='make/PE-1', action='fixed', note='Fixed')]), 2)
        a, verdict = f.apply_review(a, R, review(resolutions=[resolution()]), 'C2', {})
        self.assertEqual(verdict, 'pass')
        self.assertEqual([x['event'] for x in a['findings'][0]['history']], ['raised','response','resolution'])
        self.assertEqual(a['reviewers'][R['id']]['last_seen_candidate'], 'C2')

    def test_advisory_override_and_noted_resolutions(self):
        a, verdict = f.apply_review(f.empty('make'), dict(R, advisory=True),
                                  review([finding()], verdict='pass'), 'C1', {})
        self.assertEqual((verdict, a['findings'][0]['status']), ('pass','noted'))
        self.assertEqual(f.needing_response(a), [])
        a, _ = f.apply_review(a, R, review(), 'C2', {})
        self.assertEqual(a['reviewers'][R['id']]['round'], 2)

    def test_invalid_verdict_and_resolution_are_atomic(self):
        a = self.initial(); original = copy.deepcopy(a)
        for answer in [review(), review(resolutions=[resolution(), resolution()]),
                       review(resolutions=[resolution('foreign/SC-1')]),
                       review(resolutions=[resolution(status='unresolved')], verdict='pass')]:
            with self.assertRaises(f.ProtocolError):
                f.apply_review(a, R, answer, 'C2', {})
            self.assertEqual(a, original)
        a, verdict = f.apply_review(a, R, review(resolutions=[resolution(status='unresolved')]), 'C2', {})
        self.assertEqual(verdict, 'block')

    def test_later_blockers_require_changed_location_or_cause(self):
        for location, cause, expected in [('src/a:2','','blocking'),('src/a:9','','advisory'),
                                          ('caller:8','src/a:2','blocking'),
                                          ('caller:8','src/a:9','advisory')]:
            with self.subTest(location=location,cause=cause):
                a, _ = f.apply_review(f.empty('make'), R, review(), 'C1', {})
                a, _ = f.apply_review(a, R, review([finding(location,caused_by=cause)],
                                     verdict='block' if expected=='blocking' else 'pass'),
                                     'C4', {'src/a': [(2,3)]})
                self.assertEqual(a['findings'][0]['severity'], expected)
        self.assertFalse(f.inside('src/a#made-up-section', {'src/a': [(1,2)]}))

    def test_responses_survive_gate_failure_and_renew_on_unresolved(self):
        a = self.initial()
        a = f.respond(a, done(responses=[dict(finding='make/PE-1',action='fixed',note='fixed')]), 2)
        self.assertEqual(f.needing_response(a), [])
        self.assertEqual(len(f.feedback(a)['info']), 1)
        a = f.respond(a, done(), 3)
        a, _ = f.apply_review(a,R,review(resolutions=[resolution(status='unresolved')]),'C3',{})
        self.assertEqual(len(f.needing_response(a)),1)

    def test_dispute_escalation_and_human_decisions(self):
        a = self.initial()
        a = f.respond(a, done(responses=[dict(finding='make/PE-1',action='disputed',note='why')]), 2)
        a, _ = f.apply_review(a,R,review(resolutions=[resolution(status='unresolved')]),'C2',{})
        self.assertEqual(a['findings'][0]['status'],'escalated')
        for decision in ('resolved','advisory'):
            self.assertEqual(f.blockers(f.resolve(a,'make/PE-1',decision)),[])
        b = f.resolve(a,'make/PE-1','upheld')
        self.assertEqual(len(f.needing_response(b)),1)
        with self.assertRaises(f.ProtocolError):
            f.respond(b,done(responses=[dict(finding='make/PE-1',action='disputed',note='again')]),3)

    def test_retry_supersedes_and_preserves_id_sequence(self):
        a = f.restart(self.initial())
        self.assertEqual(a['findings'][0]['status'],'superseded')
        a, _ = f.apply_review(a,R,review([finding()]),'C5',{})
        self.assertEqual(a['findings'][-1]['id'],'make/PE-2')
        self.assertEqual(a['reviewers'][R['id']]['round'],1)
