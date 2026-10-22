"""仅内存模型校验，不创建模拟业务数据。"""

import unittest
from types import SimpleNamespace
from pydantic import ValidationError
from yuxi.services.miniapp_profile_types import MiniappMemberInput, miniapp_onboarding_ready


def complete_input():
    """构造无持久化的契约边界输入。"""
    return {
        "client_ref": "00000000-0000-4000-8000-000000000001",
        "name": "校验边界",
        "relation": "本人",
        "birth_date": "2000-01-01",
        "dietary": {
            "healthStatus": "none",
            "allergyStatus": "none",
            "intoleranceStatus": "none",
            "avoidanceStatus": "none",
            "doctorStatus": "none",
            "goals": ["饮食均衡"],
            "tastePreferences": ["清淡"],
            "cuisines": [],
        },
    }


class OptionalCuisineTest(unittest.TestCase):
    """菜系可后补，但安全与身份相关完整性规则不放松。"""

    def test_empty_cuisine_stays_unknown(self):
        """空数组不转换成明确无偏好。"""
        result = MiniappMemberInput.model_validate(complete_input())
        self.assertEqual(result.dietary.cuisines, [])

    def test_explicit_no_preference_is_preserved(self):
        """本人明确选择与未填写保持区别。"""
        value = complete_input()
        value["dietary"]["cuisines"] = ["无特别要求"]
        self.assertEqual(MiniappMemberInput.model_validate(value).dietary.cuisines, ["无特别要求"])

    def test_placeholders_are_not_real_preferences(self):
        """其他与自定义仍须补具体文本。"""
        for placeholder in ("其他", "自定义"):
            with self.subTest(placeholder=placeholder):
                value = complete_input()
                value["dietary"]["cuisines"] = [placeholder]
                with self.assertRaises(ValidationError):
                    MiniappMemberInput.model_validate(value)

    def test_missing_birthday_is_rejected(self):
        """不放松出生日期完整性。"""
        value = complete_input()
        value["birth_date"] = None
        with self.assertRaises(ValidationError):
            MiniappMemberInput.model_validate(value)

    def test_unknown_safety_status_is_rejected(self):
        """未知疾病、过敏、不耐受、忌口和医嘱仍要求作答。"""
        for field in ("healthStatus", "allergyStatus", "intoleranceStatus", "avoidanceStatus", "doctorStatus"):
            with self.subTest(field=field):
                value = complete_input()
                value["dietary"][field] = "unknown"
                with self.assertRaises(ValidationError):
                    MiniappMemberInput.model_validate(value)

    def test_goal_and_taste_remain_required(self):
        """仅菜系允许后补，饮食目标与口味规则保持原样。"""
        for field in ("goals", "tastePreferences"):
            with self.subTest(field=field):
                value = complete_input()
                value["dietary"][field] = []
                with self.assertRaises(ValidationError):
                    MiniappMemberInput.model_validate(value)

    def test_cuisine_text_bounds_still_apply(self):
        """空条目、超长文本和超量条目仍被拒绝。"""
        for cuisines in ([""], ["x" * 201], ["家常菜"] * 31):
            with self.subTest(count=len(cuisines)):
                value = complete_input()
                value["dietary"]["cuisines"] = cuisines
                with self.assertRaises(ValidationError):
                    MiniappMemberInput.model_validate(value)

    def test_completion_reuses_same_rules_and_requires_confirmation(self):
        """保存与完成判定一致，并保留本人版本确认。"""
        value = complete_input()
        member = SimpleNamespace(
            id=value["client_ref"],
            name=value["name"],
            is_active=True,
            version=2,
            confirmed_version=2,
            profile={"birth_date": value["birth_date"], "dietary_details": value["dietary"]},
        )
        self.assertTrue(miniapp_onboarding_ready(member, None))
        member.confirmed_version = 1
        self.assertFalse(miniapp_onboarding_ready(member, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
