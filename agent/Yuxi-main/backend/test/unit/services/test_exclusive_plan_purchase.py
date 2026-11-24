"""整周7天采购范围、缺口与回源失效。"""
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager
import time
import pytest
from yuxi.services import exclusive_plan_purchase as purchase
from yuxi.services.health_vision_types import HealthVisionError


def plan(line='大米100克'):
    return {'group_id':'group','tier_code':'economy','days':[
        {'day_no':n,'plan_date':'2026-11-'+str(23+n),'meals':[{'meal_type':'lunch','recipe_name':'米饭','source':{'file_id':'rice'},'ingredients':[line,'菠菜适量']}]}
        for n in range(1,8)]}


def catalog(**changes):
    return {'version':'catalog','items':[{'sku_id':'rice','product_id':'rice','product_name':'大米','sku_name':'500g',
        'price_cent':500,'sale_status':'available','available_quantity':100,'allergen_codes':[], 'data_completeness':'complete',
        'ingredients':[{'ingredient_id':'rice','ingredient_name':'大米','ingredient_code':'大米','net_unit':'g','net_value':500,'review_status':'approved'}],**changes}]}


def test_aggregates_all_days_before_rounding_packages():
    result = purchase.assemble_purchase(plan(),catalog(),[])
    assert result['items'][0]['quantity']==2
    assert len(result['gaps'])==1
    assert result['gaps'][0]['price_cent'] is None
    assert result['days']==7


def test_unknown_quantity_uses_explicit_adjustable_default():
    result = purchase.assemble_purchase(plan('大米适量'),catalog(),[])
    assert result['items'][0]['quantity']==1
    assert result['items'][0]['quantity_confirmed'] is False
    assert '不代表已核定' in result['notice']


@pytest.mark.parametrize('change',[{'price_cent':None},{'available_quantity':0},{'sale_status':'unavailable'}])
def test_missing_trade_facts_remain_gaps(change):
    result = purchase.assemble_purchase(plan(),catalog(**change),[])
    assert result['items']==[]
    assert result['available'] is False
    assert result['gaps']


def test_incomplete_days_and_other_tier_identity():
    incomplete=plan();incomplete['days'].pop()
    with pytest.raises(HealthVisionError):purchase.assemble_purchase(incomplete,catalog(),[])
    changed=plan();changed['days'][0]['meals'][0]['ingredients']=['大米200克']
    assert purchase.assemble_purchase(plan(),catalog(),[])['scope_hash']!=purchase.assemble_purchase(changed,catalog(),[])['scope_hash']


@pytest.mark.asyncio
async def test_read_returns_purchase_page_metadata_without_loading_candidate_documents(monkeypatch):
    """单次采购读取保留来源校验，仅取成员限制而不扫描候选库。"""
    from yuxi.services import exclusive_plan_service, exclusive_reference_plan
    from yuxi.storage.postgres.manager import pg_manager

    saved = {**plan(), 'tier_name': '经济型', 'members': [{'display_alias': '合成成员'}]}
    read = AsyncMock(return_value=saved)
    context = AsyncMock(return_value={'current': {'members': []}})
    monkeypatch.setattr(exclusive_plan_service, 'read_exclusive_plan', read)
    monkeypatch.setattr(exclusive_reference_plan, 'exclusive_reference_context', context)
    monkeypatch.setattr(exclusive_reference_plan, 'optional_exclusive_catalog', AsyncMock(return_value=catalog()))
    session = object()

    @asynccontextmanager
    async def transaction():
        """用合成会话隔离纯服务编排。"""
        yield session

    monkeypatch.setattr(pg_manager, 'get_async_session_context', transaction)
    result = await purchase.read_purchase('user', 'family', 'group', 'economy')
    read.assert_awaited_once_with('user', 'family', 'group', tier='economy')
    from datetime import date
    context.assert_awaited_once_with(session, 'user', 'family', day=date(2026,11,24), start_date='2026-11-24', load_documents=False)
    assert result['tier_name'] == '经济型'
    assert result['members'] == saved['members']
    assert result['items'][0]['quantity'] == 2

    read.side_effect = HealthVisionError('source_invalidated', '来源已更新', 410)
    with pytest.raises(HealthVisionError):
        await purchase.read_purchase('user', 'family', 'group', 'economy')


@pytest.mark.asyncio
async def test_source_revalidation_and_expiry(monkeypatch):
    monkeypatch.setattr(purchase,'read_purchase',AsyncMock(return_value={'scope_hash':'new','items':[{'sku_id':'rice','quantity':1}]}))
    source={'uid':'user','family_id':'family','group_id':'group','tier_code':'economy','scope_hash':'old','expires_at':int(time.time())+100}
    with pytest.raises(HealthVisionError):await purchase.validate_purchase_source(source)
    source['scope_hash']='new'
    assert (await purchase.validate_purchase_source(source))['selection_mode']=='reference'
    source['expires_at']=1
    with pytest.raises(HealthVisionError):await purchase.validate_purchase_source(source)


@pytest.mark.asyncio
async def test_unknown_amount_and_missing_storage_preserve_original_package_purchase(monkeypatch):
    from yuxi.services import daily_commerce_service as commerce
    monkeypatch.setenv('HEALTH_COMMERCE_SOURCE_SECRET', 'synthetic-secret-'*4)
    result = purchase.assemble_purchase(plan('大米适量'), catalog(), [])
    assert result['items'][0]['quantity'] == 1
    assert result['items'][0]['quantity_confirmed'] is False
    assert result['delivery_suggestions']['pending'] == []
    assert len(result['delivery_suggestions']['batches']) == 7
    monkeypatch.setattr(purchase, 'read_purchase', AsyncMock(return_value=result))
    call = AsyncMock(return_value={'package_sn':'synthetic', 'package_version':1})
    monkeypatch.setattr(commerce, 'commerce_request', call)
    with pytest.raises(HealthVisionError, match='exclusive_purchase_changed'):
        await purchase.publish_purchase('user','family','group','economy','wrong')
    assert not call.called
    await purchase.publish_purchase('user','family','group','economy',result['scope_hash'])
    assert call.await_args.args[2]['items'] == [{'sku_id':'rice','quantity':1}]
    assert '未匹配食材需自行准备' in result['notice']
    assert all(item['food'] == '大米' for batch in result['delivery_suggestions']['batches'] for item in batch['items'])
