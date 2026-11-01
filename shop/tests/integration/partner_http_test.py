"""Run against the isolated partner fixture through the actual shipping routes."""
import concurrent.futures
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import uuid

base = os.environ['PARTNER_TEST_BASE_URL']
if not base.startswith('http://127.0.0.1:') or os.environ.get('HEALTHFLOW_RELEASE_TEST') != '1':
    raise RuntimeError('Only an explicit local isolated test server is allowed')
fixture = json.loads((Path(__file__).parents[1]/'fixtures/partner-http-state.json').read_text())


def request(path, payload=None, token=None, key=None):
    headers = {'Accept': 'application/json'}
    if token:
        headers['token'] = token
    if key:
        headers['Idempotency-Key'] = key
    body = None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(payload).encode()
    req = urllib.request.Request(base+'/api/v1/commerce/'+path, data=body, headers=headers)
    try:
        response = urllib.request.urlopen(req, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    raw = response.read().decode()
    try:
        parsed = json.loads(raw)
    except ValueError as error:
        raise AssertionError(f'{path}: expected JSON, received {raw[:300]}') from error
    return response.status, parsed


assert request('supplier-applications/policy')[1]['code'] != 0
token = fixture['owner_token']
status, policy = request('supplier-applications/policy', token=token)
assert status == 200 and policy['code'] == 0, policy
assert policy['data']['policy_version'] == 'partner-contact-20261101'
receipts = []
for kind in ['supplier', 'channel', 'distributor']:
    payload = dict(fixture['payload'], partner_type=kind)
    key = 'http-'+uuid.uuid4().hex
    status, first = request('supplier-applications', payload, token, key)
    assert status == 200 and first['code'] == 0, first
    status, replay = request('supplier-applications', payload, token, key)
    assert replay['data'] == first['data'], replay
    receipts.append(first['data'])
    conflict = request('supplier-applications', dict(payload, capacity_summary='changed'), token, key)
    assert conflict[0] == 409, conflict
    own = request('supplier-applications/'+first['data']['application_sn'], token=token)
    assert int(own[1]['data']['user_id']) == int(fixture['owner_id']), own
    assert 'contact_mobile_encrypted' not in own[1]['data']
    assert 'follow_up_note' not in own[1]['data']
    denied = request('supplier-applications/'+first['data']['application_sn'], token=fixture['other_token'])
    assert denied[0] == 404 and 'data' in denied[1], denied

key = 'concurrent-'+uuid.uuid4().hex
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(lambda _: request('supplier-applications', fixture['payload'], token, key), range(8)))
assert all(status == 200 and body['code'] == 0 for status, body in results), results
assert len({body['data']['application_sn'] for _, body in results}) == 1
for field in ['partner_type', 'location_area_id', 'capacity_summary', 'privacy_consent_version']:
    payload = dict(fixture['payload']); payload.pop(field)
    status, body = request('supplier-applications', payload, token, 'missing-'+uuid.uuid4().hex)
    assert status == 400 and body['code'] != 0, (field, status, body)
print(json.dumps({'real_http': True, 'types': 3, 'concurrent_requests': 8, 'one_receipt': True,
                  'replay': True, 'payload_conflict': True, 'ownership': True, 'required_fields': True}))
