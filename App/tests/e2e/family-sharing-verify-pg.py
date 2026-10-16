"""直接回读本次隔离 schema，验证正式客户端操作的持久化事实。"""
import asyncio,json,os,re
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from yuxi.storage.postgres.models_business import FamilyMember,FamilyMeasurement,FamilyProfileRevision,FamilyAudit,FamilyArchive
from yuxi.services.family_service import authorized_fields
root=Path('/app/formal-client-evidence');f=json.loads((root/'fixture.json').read_text())
assert re.fullmatch('formal_client_[0-9a-f]{32}',f['schema'])
async def main():
 engine=create_async_engine(os.environ['POSTGRES_URL'],connect_args={'server_settings':{'search_path':f['schema']}})
 async with async_sessionmaker(engine)() as db:
  target=await db.get(FamilyMember,f['target_id']);peer=await db.get(FamilyMember,f['peer_member_id']);family=await db.get(FamilyArchive,f['family_id'])
  assert target.name=='共享验收成员' and target.version==4 and target.relationship_version==2
  assert target.profile['goal']=='户主并发修改' and target.profile['height_cm']==166
  assert target.profile['allergens']==['合成过敏原A','合成过敏原B']
  assert target.profile['meal_habits']['weekday']=='合成工作日安排' and target.profile['lifestyle']['sleep_schedule']=='合成作息安排'
  assert target.confirmed_version is None and not peer.is_active
  assert not authorized_fields(family,target,'formal_peer') and not authorized_fields(family,target,'formal_owner')
  records=(await db.scalars(select(FamilyMeasurement).where(FamilyMeasurement.member_id==target.id))).all()
  assert len(records)==5 and {r.kind for r in records}=={'weight','height','blood_pressure','blood_glucose','blood_lipids'}
  assert all(r.created_by=='formal_peer' for r in records)
  weight=next(r for r in records if r.kind=='weight')
  assert weight.version==3 and weight.values=={'weight':61} and len(weight.previous)==2 and weight.voided_at
  assert weight.voided_by=='formal_peer' and weight.void_reason=='合成作废'
  revisions=(await db.scalars(select(FamilyProfileRevision).where(FamilyProfileRevision.member_id==target.id).order_by(FamilyProfileRevision.version))).all()
  assert [(r.version,r.actor_uid) for r in revisions]==[(2,'formal_owner'),(3,'formal_peer'),(4,'formal_owner')]
  audits=(await db.scalars(select(FamilyAudit).where(FamilyAudit.member_id==target.id,FamilyAudit.actor_uid=='formal_peer'))).all()
  actions={r.action for r in audits};assert {'profile.update','member.update','measurement.create','measurement.correct','measurement.void'}<=actions
  result={'status':'passed','schema':f['schema'],'profile_version':target.version,'relationship_version':target.relationship_version,'measurements':5,'weight_version':weight.version,'weight_previous':len(weight.previous),'profile_actors':[(r.version,r.actor_uid) for r in revisions],'peer_write_actions':sorted(actions),'independent_source_fields':0,'confirmed_version':None,'peer_inactive':True}
  (root/'pg-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result))
 await engine.dispose()
asyncio.run(main())
