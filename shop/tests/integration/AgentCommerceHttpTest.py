"""真实 Agent HTTP/JWT → 商城 HTTP → PostgreSQL 回读；微信供应商在独立测试服务替代。"""
import json
import os
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

assert os.environ.get('PHP_DATABASE_DATABASE') == 'identity_commerce_test', 'Dedicated database required'
agent = os.environ.get('IDENTITY_TEST_AGENT_URL', 'http://127.0.0.1:19085')
shop = os.environ.get('IDENTITY_TEST_SHOP_URL', 'http://127.0.0.1:19086')
assert agent == 'http://127.0.0.1:19085' and shop == 'http://127.0.0.1:19086'


def call(base, path, body=None, headers=None):
    """发送实际 TCP 请求，凭据只保留在内存。"""
    request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def login(code):
    """微信外部供应商是唯一替身，其余认证链路使用实际实现。"""
    status, data = call(agent, '/api/auth/wechat/login', {'code': code})
    assert status == 200, (status, data)
    return data


def exchange(user, payload=None):
    """商城只接收业务 Bearer token，不接收客户端身份编号。"""
    return call(shop, '/api/v1/commerce/session/exchange', payload or {}, {'Authorization': 'Bearer ' + user['access_token']})


def fixture(action):
    """通过独立 PHP 进程读取实际保存的数据。"""
    path = Path(__file__).resolve().parents[1] / 'fixtures/AgentMemberFixture.php'
    return json.loads(subprocess.check_output(['php', str(path), action]))


before = fixture('seed')
a, b = login('member-a'), login('member-b')
assert exchange({'access_token': 'invalid-token'})[0] == 401
assert exchange(a, {'account':'identity_existing','password':'wrong'})[0] == 401
assert fixture('read')['mappings'] == 0
status, bound = exchange(a, {'account':'identity_existing','password':'synthetic-password'})
assert status == 200, (status, bound)
assert bound['data']['user']['id'] == before['id']
assert bound['data']['agent_account_id'] == str(a['account']['id'])
status, restored = call(shop, '/api/v1/commerce/session', headers={'token':bound['data']['user']['token']})
assert status == 200 and restored['data']['user']['id'] == before['id']
assert exchange(a)[1]['data']['user']['id'] == before['id']
assert exchange(a, {'account':'identity_existing','password':'wrong'})[0] == 401
assert exchange(a, {'account':'identity_other','password':'synthetic-password'})[0] == 409
assert exchange(a, {'account':'identity_existing','password':'synthetic-password'})[1]['data']['user']['id'] == before['id']
assert exchange(b, {'account':'identity_existing','password':'synthetic-password'})[0] == 409
assert exchange(a, {'user_id':before['id']})[0] == 400
status, created = exchange(b)
assert status == 200 and created['data']['user']['id'] != before['id'], (status, created)
racing = login('racing-member')
with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(lambda _: exchange(racing), range(4)))
assert all(status == 200 for status, _ in results), [(s, d.get('message')) for s,d in results]
assert len({d['data']['user']['id'] for _,d in results}) == 1
after = fixture('read')
assert before['credentials_hash'] == after['credentials_hash']
assert before['business_hash'] == after['business_hash']
assert after['members'] == before['members'] + 2
assert after['mappings'] == 3
print(json.dumps({'passed':True,'existing_credentials_preserved':True,'cart_address_order_preserved':True,
                  'binding_conflict_rejected':True,'concurrent_identity_count':1,'members':after['members'],'mappings':after['mappings']}))
