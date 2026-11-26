"""日记手动补记未知克数的真实HTTP和数据库回归。"""
from uuid import uuid4

import pytest

from test.integration.services.test_health_meal_plan_pagination_http import (  # noqa: F401
    cleanup_test_sandboxes, cleanup_test_knowledge_resources, ensure_live_api_schema, meal_pagination_http,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_unknown_manual_intake_is_saved_once_and_visible_in_calendar(meal_pagination_http):
    """空白克数保持未知，重试不重复记餐，个人日期读到同一记录。"""
    c=meal_pagination_http
    request_id=str(uuid4())
    data={"member_id":c.member,"client_request_id":request_id,"accept_incomplete":True,"meal":{"meal_type":"lunch","eaten_at":"2026-11-25T12:30:00+08:00","photos":[],"items":[{"item_id":str(uuid4()),"name":"合成蒸蛋","grams":None,"share_ratio":None,"portion_source":"unknown","uncertainties":["本人粗略份量：一般"],"locations":[]}]}}
    headers={**c.identities['owner'],'Idempotency-Key':request_id}
    a=await c.client.post('/api/health/v1/diet-journal-recordings',headers=headers,json=data)
    assert a.status_code==201,a.text
    b=await c.client.post('/api/health/v1/diet-journal-recordings',headers=headers,json=data)
    assert b.status_code==201,b.text
    assert a.json()['id']==b.json()['id']
    item=a.json()['snapshot']['meal']['items'][0]
    assert item['grams'] is None and item['share_ratio'] is None
    records=(await c.client.get(f'/api/health/v1/members/{c.member}/diet-journal?day=2026-11-25',headers=c.identities['owner'])).json()['records']
    assert sum(row['id']==a.json()['id'] for row in records)==1
    invalid={**data,'client_request_id':str(uuid4())}
    invalid['meal']={**data['meal'],'items':[{**data['meal']['items'][0],'share_ratio':.5}]}
    response=await c.client.post('/api/health/v1/diet-journal-recordings',headers={**c.identities['owner'],'Idempotency-Key':invalid['client_request_id']},json=invalid)
    assert response.status_code==422
    strict=await c.client.post('/api/health/v1/meal-recordings',headers=headers,json=data)
    assert strict.status_code==422


async def test_journal_recording_cannot_write_an_unrelated_member(meal_pagination_http):
    """新入口保留正式记餐服务的成员授权。"""
    c=meal_pagination_http
    request_id=str(uuid4())
    data={"member_id":str(uuid4()),"client_request_id":request_id,"accept_incomplete":True,"meal":{"meal_type":"dinner","eaten_at":"2026-11-25T18:30:00+08:00","items":[{"item_id":str(uuid4()),"name":"合成青菜","grams":None,"share_ratio":None,"portion_source":"unknown"}]}}
    response=await c.client.post('/api/health/v1/diet-journal-recordings',headers={**c.identities['owner'],'Idempotency-Key':request_id},json=data)
    assert response.status_code in {403,404}
