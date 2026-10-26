import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT = 'healthswarm-nutrition-20261019'
ROOT = Path('/opt/healthswarm-agent/releases/nutrition-20261019-test')
DELETING = ROOT.with_name('nutrition-20261019-test.deleting-20261019')
AUDIT = Path('/tmp/nutrition-removal-20261019-audit.json')

def run(args):
    p = subprocess.run(args, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError(f'{args[0:3]}: {p.stderr[:500]}')
    return p.stdout

def containers():
    ids = run(['docker', 'ps', '-aq']).split()
    return json.loads(run(['docker', 'inspect', *ids])) if ids else []

def target(c):
    return (c['Config'].get('Labels') or {}).get('com.docker.compose.project') == PROJECT

def under(path):
    p = Path(path).resolve()
    return p == ROOT or ROOT in p.parents

def public(c):
    return {'id': c['Id'], 'name': c['Name'], 'image': c['Config']['Image'],
            'status': c['State']['Status'], 'health': c['State'].get('Health', {}).get('Status'),
            'mounts': [{'type': m['Type'], 'source': m['Source'], 'name': m.get('Name')}
                       for m in c.get('Mounts', [])]}

assert ROOT.as_posix() == '/opt/healthswarm-agent/releases/nutrition-20261019-test'
assert ROOT.is_dir() and not ROOT.is_symlink() and ROOT.resolve() == ROOT
assert not DELETING.exists()
cfg = json.loads((ROOT / 'compose.json').read_text())
before = containers()
targets = [c for c in before if target(c)]
assert targets and all(c['Name'].startswith('/' + PROJECT + '-') for c in targets)
others = [c for c in before if not target(c)]
for c in others:
    assert not any(m['Type'] == 'bind' and under(m['Source']) for m in c.get('Mounts', [])), c['Name']
volume_names = {m['Name'] for c in targets for m in c.get('Mounts', []) if m['Type'] == 'volume'}
for c in others:
    assert not any(m.get('Name') in volume_names for m in c.get('Mounts', [])), c['Name']
for c in targets:
    for m in c.get('Mounts', []):
        if m['Type'] == 'bind':
            assert under(m['Source']), m['Source']
network_ids = run(['docker', 'network', 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + PROJECT]).split()
networks = json.loads(run(['docker', 'network', 'inspect', *network_ids])) if network_ids else []
target_ids = {c['Id'] for c in targets}
for n in networks:
    assert n['Name'].startswith(PROJECT + '_')
    assert set(n.get('Containers') or {}).issubset(target_ids)
mounts = run(['findmnt', '-rn', '-o', 'TARGET']).splitlines()
assert not any(p == str(ROOT) or p.startswith(str(ROOT) + '/') for p in mounts)
images = []
for line in run(['docker', 'image', 'ls', '--format', '{{.Repository}}:{{.Tag}}']).splitlines():
    if line.startswith(('healthswarm-agent-api:nutrition-20261019-', 'healthswarm-agent-web:nutrition-20261019-')):
        info = json.loads(run(['docker', 'image', 'inspect', line]))[0]
        assert not any(c['Image'] == info['Id'] for c in others), line
        images.append(line)
assert images
audit = {'project': PROJECT, 'root': str(ROOT), 'before': [public(c) for c in targets],
         'protected_before': [public(c) for c in others if c['State']['Running']],
         'volumes': sorted(volume_names), 'networks': [n['Name'] for n in networks],
         'images': images, 'removed_containers': [], 'removed_volumes': [],
         'removed_networks': [], 'removed_images': [], 'root_deleted': False}

def save():
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2))

save()
print(json.dumps({'preflight_passed': True, 'containers': len(targets), 'volumes': len(volume_names),
                  'networks': len(networks), 'image_tags': len(images), 'root': str(ROOT)}), flush=True)
if '--execute' not in sys.argv:
    sys.exit(0)

# Remove the original config path first so the active, project-specific test loop
# cannot launch another compose run while this environment is being removed.
ROOT.rename(DELETING)
assert DELETING.resolve() == DELETING and DELETING.parent == Path('/opt/healthswarm-agent/releases')
audit['directory_quarantined'] = True
save()
for attempt in range(3):
    current = [c for c in containers() if target(c)]
    if not current:
        break
    ids = [c['Id'] for c in current]
    running = [c['Id'] for c in current if c['State']['Running']]
    if running:
        run(['docker', 'stop', '--time', '15', *running])
    # --rm test runners may disappear after stopping; re-observe before rm.
    existing = [c['Id'] for c in containers() if target(c)]
    if existing:
        run(['docker', 'rm', *existing])
    audit['removed_containers'] += [i for i in ids if i not in audit['removed_containers']]
    save()
assert not any(target(c) for c in containers())
for name in sorted(volume_names):
    assert not run(['docker', 'ps', '-aq', '--filter', 'volume=' + name]).strip()
    run(['docker', 'volume', 'rm', name])
    audit['removed_volumes'].append(name)
    save()
for n in networks:
    current = json.loads(run(['docker', 'network', 'inspect', n['Id']]))[0]
    assert not current.get('Containers')
    run(['docker', 'network', 'rm', n['Id']])
    audit['removed_networks'].append(n['Name'])
    save()
for ref in images:
    run(['docker', 'image', 'rm', ref])
    audit['removed_images'].append(ref)
    save()
assert not ROOT.exists() and not DELETING.is_symlink()
assert DELETING.resolve() == Path('/opt/healthswarm-agent/releases/nutrition-20261019-test.deleting-20261019')
shutil.rmtree(DELETING)
audit['root_deleted'] = not ROOT.exists() and not DELETING.exists()
after = containers()
protected_ids = {c['id'] for c in audit['protected_before']}
after_by_id = {c['Id']: c for c in after}
audit['protected_readback'] = [{'name': p['name'], 'same_container_present': p['id'] in after_by_id,
    'running': after_by_id.get(p['id'], {}).get('State', {}).get('Running', False),
    'health': after_by_id.get(p['id'], {}).get('State', {}).get('Health', {}).get('Status')}
    for p in audit['protected_before']]
audit['no_target_containers'] = not any(target(c) for c in after)
audit['completed_at_unix'] = time.time()
save()
assert audit['root_deleted'] and audit['no_target_containers']
assert all(p['same_container_present'] and p['running'] for p in audit['protected_readback'])
print(json.dumps({'removal_passed': True, 'removed_containers': len(audit['removed_containers']),
    'removed_volumes': len(audit['removed_volumes']), 'removed_networks': len(audit['removed_networks']),
    'removed_image_tags': len(audit['removed_images']), 'directory_removed': audit['root_deleted'],
    'other_running_containers_preserved': len(audit['protected_readback'])}), flush=True)
