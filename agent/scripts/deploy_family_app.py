"""发布独立家庭档案 H5，保留商城入口和当前后端；失败恢复原代理与链接。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

COMMERCE = Path('/opt/healthswarm-commerce')
GATEWAY = Path('/opt/healthswarm-public-gateway/nginx.conf')
CONFIG = COMMERCE / 'nginx.conf'
LINK = COMMERCE / 'shared/family-app'
ROOT = Path(sys.argv[1]).resolve()
MODE = sys.argv[2]

def run(*args):
    """执行固定命令且只返回所需的运维结果。"""
    return subprocess.check_output(args, text=True).strip()

def digest(path):
    """记录文件摘要，不输出环境配置内容。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()

def http(path):
    """通过现有网关读取发布事实。"""
    with urllib.request.urlopen('http://127.0.0.1' + path, timeout=20) as response:
        return response.read()

def snapshot():
    """固定已有容器、业务入口与敏感配置摘要。"""
    ready = json.loads(http('/api/system/ready'))
    assert ready['status'] == 'ready' and not ready['degraded']
    return {
        'containers': run('docker', 'ps', '--format', '{{.Names}} {{.ID}} {{.Image}}').splitlines(),
        'env_sha256': digest(Path('/opt/healthswarm-agent/.env.prod')),
        'mall_sha256': hashlib.sha256(http('/mall/')).hexdigest(),
        'web_sha256': hashlib.sha256(http('/')).hexdigest(),
    }

def write_config(path, content):
    """保留单文件 bind mount 的 inode，使 nginx reload 看到新配置。"""
    with path.open('wb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())

def nginx(action):
    """检查或热加载两个已有静态网关。"""
    for container in ('healthswarm-commerce-web', 'healthswarm-public-gateway'):
        args = ['nginx', '-t'] if action == 'test' else ['nginx', '-s', 'reload']
        run('docker', 'exec', container, *args)

assert ROOT.parent == COMMERCE / 'releases' and ROOT.name.startswith('family-app-')
manifest = json.loads((ROOT / 'manifest.json').read_text())
assert ROOT.name == 'family-app-' + manifest['revision'][:12]
for name, expected in manifest['files'].items():
    path = (ROOT / 'h5' / name).resolve()
    assert path.is_relative_to(ROOT / 'h5') and not path.is_symlink() and digest(path) == expected, name
assert b'/family-app/assets/' in (ROOT / 'h5/index.html').read_bytes()
assert not LINK.exists() and not LINK.is_symlink(), 'Existing release requires an explicitly prepared update'
assert b'/family-app/' not in CONFIG.read_bytes() and b'/family-app/' not in GATEWAY.read_bytes()
before = snapshot()
old_config, old_gateway = CONFIG.read_bytes(), GATEWAY.read_bytes()
commerce_block = b'''        location = /family-app { return 302 /family-app/; }
        location ^~ /family-app/ {
            alias /opt/healthswarm-commerce/shared/family-app/;
            index index.html;
            try_files $uri $uri/ =404;
            add_header Cache-Control no-store;
            add_header X-Content-Type-Options nosniff always;
        }
'''
gateway_block = b'''        location = /family-app { return 302 /family-app/; }
        location ^~ /family-app/ {
            proxy_pass http://127.0.0.1:18082;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
'''
anchor = b'        location = /mall { return 302 /mall/; }'
assert old_config.count(anchor) == 1 and old_gateway.count(anchor) == 1
if MODE == 'check':
    print(json.dumps({'status': 'ready_to_deploy', 'revision': manifest['revision'], 'files': len(manifest['files']), 'baseline': before}))
elif MODE == 'deploy':
    backup = ROOT / 'proxy-backup'
    backup.mkdir(mode=0o700)
    (backup / 'commerce.conf').write_bytes(old_config)
    (backup / 'gateway.conf').write_bytes(old_gateway)
    try:
        LINK.symlink_to(ROOT / 'h5', target_is_directory=True)
        write_config(CONFIG, old_config.replace(anchor, commerce_block + anchor))
        write_config(GATEWAY, old_gateway.replace(anchor, gateway_block + anchor))
        nginx('test')
        nginx('reload')
        import time
        for attempt in range(20):
            try:
                assert hashlib.sha256(http('/family-app/')).hexdigest() == manifest['files']['index.html']
                break
            except Exception:
                if attempt == 19:
                    raise
                time.sleep(0.5)
        after = snapshot()
        assert after == before, 'Unrelated containers, environment or entrypoints changed'
        result = {'status': 'deployed', 'revision': manifest['revision'], 'files': len(manifest['files']), 'baseline_unchanged': True, 'url': 'http://8.136.134.29/family-app/'}
        (ROOT / 'deployment-result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    except Exception:
        write_config(CONFIG, old_config)
        write_config(GATEWAY, old_gateway)
        nginx('test')
        nginx('reload')
        if LINK.is_symlink() and LINK.resolve() == ROOT / 'h5':
            LINK.unlink()
        raise
else:
    raise ValueError('Expected check or deploy')
