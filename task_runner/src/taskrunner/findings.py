"""Pure findings transitions. Invalid answers never mutate the ledger.

The engine owns persistence and applies reviewers in workflow order. Versions distinguish a
finding kept open from an author response that has not yet been reviewed.
"""
import copy
import re

from . import validate

OPEN = {'open', 'disputed', 'escalated'}


class ProtocolError(ValueError):
    pass


def empty(producer):
    return {'producer': producer, 'findings': [], 'reviewers': {}, 'next_ids': {}}


def blockers(ledger, reviewer=None):
    return [f for f in ledger['findings'] if f['severity'] == 'blocking'
            and f['status'] in OPEN and (reviewer is None or f['reviewer'] == reviewer)]


def needing_response(ledger):
    return [f for f in blockers(ledger) if f.get('response_version') != f['version']]


def feedback(ledger):
    needed = needing_response(ledger)
    ids = {f['id'] for f in needed}
    return {'needing': copy.deepcopy(needed),
            'info': copy.deepcopy([f for f in ledger['findings'] if f['id'] not in ids
                                  and (f['status'] in OPEN or f['status'] == 'noted')])}


def respond(ledger, answer, attempt):
    errors = validate.check_produce(answer, [f['id'] for f in needing_response(ledger)])
    by_id = {f['id']: f for f in ledger['findings']}
    if not errors:
        for r in answer['responses']:
            if r['action'] == 'disputed' and by_id[r['finding']].get('upheld'):
                errors.append(f"{r['finding']} was upheld by a person and cannot be disputed again")
    if errors:
        raise ProtocolError('; '.join(errors))
    result = copy.deepcopy(ledger)
    by_id = {f['id']: f for f in result['findings']}
    if answer['outcome'] != 'blocked':
        for response in answer['responses']:
            f = by_id[response['finding']]
            f['response'] = dict(response, attempt=attempt)
            f['response_version'] = f['version']
            f['status'] = 'disputed' if response['action'] == 'disputed' else 'open'
            f['history'].append(dict(event='response', **f['response']))
    return result


def inside(location, changes):
    """Locations are path or path:line[-line]. Unknown sections are not evidence of causality."""
    match = re.fullmatch(r'(.+?):(?:L)?(\d+)(?:-(?:L)?(\d+))?', location)
    if match:
        path, start, end = match.groups()
        start, end = int(start), int(end or start)
        return start > 0 and end >= start and any(start <= hi and end >= lo
                                                 for lo, hi in changes.get(path, []))
    return location in changes


def apply_review(ledger, reviewer, answer, candidate, changes):
    errors = validate.check_shape(answer, validate.REVIEW)
    if errors:
        raise ProtocolError('; '.join(errors))
    rid = reviewer['id']
    required = {f['id'] for f in blockers(ledger, rid)}
    supplied = [r['finding'] for r in answer['resolutions']]
    if len(supplied) != len(set(supplied)) or set(supplied) != required:
        raise ProtocolError('resolutions must cover exactly this reviewer\'s open blocking findings, each once')
    result = copy.deepcopy(ledger)
    previous = result['reviewers'].get(rid, {})
    round_no = previous.get('round', 0) + 1
    by_id = {f['id']: f for f in result['findings']}
    for resolution in answer['resolutions']:
        f = by_id[resolution['finding']]
        if resolution['status'] == 'resolved':
            f['status'] = 'resolved'
        elif f.get('response', {}).get('action') == 'disputed':
            f['status'] = 'escalated'
        else:
            f['status'] = 'open'
        f['version'] += 1
        f['history'].append(dict(event='resolution', round=round_no, **resolution))
    for finding in answer['findings']:
        severity = finding['severity']
        if reviewer.get('advisory') or (round_no > 1 and severity == 'blocking'
                and not inside(finding['location'], changes)
                and not inside(finding['caused_by'], changes)):
            severity = 'advisory'
        code = reviewer['persona_code']
        number = result['next_ids'].get(code, 0) + 1
        result['next_ids'][code] = number
        f = dict(finding, id=f"{result['producer']}/{code}-{number}", reviewer=rid,
                 severity=severity, status='open' if severity == 'blocking' else 'noted',
                 version=1, history=[{'event': 'raised', 'round': round_no,
                                     'candidate': candidate, 'reported': copy.deepcopy(finding)}])
        result['findings'].append(f)
    verdict = 'block' if blockers(result, rid) else 'pass'
    if answer['verdict'] != verdict:
        raise ProtocolError(f"verdict disagrees with ledger: expected {verdict}")
    result['reviewers'][rid] = {'round': round_no, 'last_seen_candidate': candidate,
                               'verdict': verdict}
    return result, verdict


def resolve(ledger, fid, decision, note='', who=''):
    result = copy.deepcopy(ledger)
    f = next((f for f in result['findings'] if f['id'] == fid), None)
    if f is None or f['status'] != 'escalated':
        raise ValueError(f'{fid} is not an escalated finding')
    if decision not in ('resolved', 'advisory', 'upheld'):
        raise ValueError('decision must be resolved, advisory or upheld')
    f['status'] = {'resolved': 'resolved', 'advisory': 'noted', 'upheld': 'open'}[decision]
    if decision == 'advisory':
        f['severity'] = 'advisory'
    if decision == 'upheld':
        f['upheld'] = True
        f['version'] += 1
    f['history'].append({'event': 'human', 'decision': decision, 'note': note, 'by': who})
    return result


def restart(ledger):
    result = copy.deepcopy(ledger)
    for f in blockers(result):
        f['status'] = 'superseded'
        f['history'].append({'event': 'retry', 'status': 'superseded'})
    result['reviewers'] = {}
    return result
