"""日记补记保留未知份量，原精确记餐协议不放宽。"""
from uuid import uuid4
import pytest
from pydantic import ValidationError
from yuxi.services.health_meal_recording_types import JournalMealRecordingInput, MealRecordingInput


def payload():
    """构造手动确认的未知克数食物。"""
    return {"member_id":str(uuid4()),"client_request_id":str(uuid4()),"meal":{"meal_type":"lunch","eaten_at":"2026-11-25T12:30:00+08:00","items":[{"item_id":str(uuid4()),"name":"合成蒸蛋","grams":None,"share_ratio":None,"portion_source":"unknown","uncertainties":["本人粗略份量：一般"]}]}}


def test_unknown_is_preserved_and_strict_input_is_unchanged():
    data=payload()
    assert JournalMealRecordingInput.model_validate(data).meal.items[0].grams is None
    with pytest.raises(ValidationError):MealRecordingInput.model_validate(data)


@pytest.mark.parametrize('changes',[{'share_ratio':.5},{'grams':100},{'portion_source':'manual'},{'excluded':True}])
def test_ambiguous_or_forged_intake_is_rejected(changes):
    data=payload();data['meal']['items'][0].update(changes)
    with pytest.raises(ValidationError):JournalMealRecordingInput.model_validate(data)
