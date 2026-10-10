#!/usr/bin/env python3
"""Independently check canonical claims against source fields, without reference facts/expect.

This establishes provenance integrity only, never full answer or benchmark correctness.
"""
import argparse
import json
from pathlib import Path


def audit(files, observations):
    inputs = {}
    for path in files:
        corpus = json.loads(Path(path).read_text())
        for case in corpus['cases']:
            if case['id'] in inputs:
                raise ValueError('duplicate case ID')
            inputs[case['id']] = corpus['scenarios'][case['scenario']]['sources']
    errors, claims = [], 0
    seen = set()
    for observation in observations:
        cid = observation['case_id']
        if cid not in inputs or cid in seen:
            errors.append(f'{cid}: unknown or duplicate observation'); continue
        seen.add(cid)
        if observation['effects'] or observation['facts'] or observation['approval']['granted'] or observation['approval']['approved_effects']:
            errors.append(f'{cid}: unexpected effect/approval/oracle fact')
        if observation['metrics']['inference_executed']:
            errors.append(f'{cid}: unexpected inference')
        sources = inputs[cid]
        for claim in observation['metrics'].get('source_claims', []):
            claims += 1
            try:
                source = sources[claim['source']]
                assert claim['source'] in observation['reads'] and source['state'] in ('ready', 'partial')
                record = next(r for r in source['records'] if r['id'] == claim['record_id'])
                assert claim['source_ids'] == [record['id']] and claim['context'] == 'record'
                value = record
                for component in claim['path'].split('/')[1:]:
                    component = component.replace('~1', '/').replace('~0', '~')
                    value = value[int(component)] if isinstance(value, list) else value[component]
                if claim['predicate'] == 'open_items':
                    assert claim['path'] == '/items' and isinstance(value, list)
                    value = [item for item in value if isinstance(item, dict) and item.get('completed') is False]
                else:
                    assert claim['predicate'] == 'field'
                # JSON booleans and numbers are distinct, unlike Python's default equality.
                assert json.dumps(value, sort_keys=True) == json.dumps(claim['value'], sort_keys=True)
            except (AssertionError, KeyError, IndexError, StopIteration, ValueError, TypeError):
                errors.append(f'{cid}: invalid canonical claim {claim.get("record_id")}/{claim.get("path")}')
    if set(inputs) != seen:
        errors.append('observation coverage differs from input cases')
    return {'pass': not errors, 'cases': len(seen), 'claims_checked': claims, 'errors': errors,
            'meaning': 'Source-value/provenance integrity only; not semantic completion or shared grader pass.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(sorted(args.fixtures.glob('*.json')), json.loads(args.observations.read_text()))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    raise SystemExit(0 if report['pass'] else 1)
