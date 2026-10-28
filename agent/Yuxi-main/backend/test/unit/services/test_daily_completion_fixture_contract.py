"""仅核对每日 E2E fixture 的构造协议；fake 请求不代表真实 HTTP 验收。"""

import ast
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError


@pytest.fixture
def contract():
    """原样加载目标 helper 与真实 DTO，避免导入 E2E 服务 fixture。"""
    backend = Path(__file__).resolve().parents[3]
    namespace = {
        "__name__": __name__,
        "ROOT": "/api/health/v1",
        "uuid4": uuid4,
        "BaseModel": BaseModel,
        "ConfigDict": ConfigDict,
        "Field": Field,
        "Literal": Literal,
        "UUID": UUID,
    }
    sources = (
        ("package/yuxi/services/miniapp_profile_types.py", {"MiniappAnalysisInput"}),
        ("package/yuxi/services/health_vision_types.py", {"HealthDTO", "MemberInput"}),
        (
            "test/e2e/test_daily_arrangement_completion_e2e.py",
            {"meal_plan_consent", "create_daily_actors", "prepare_daily_members"},
        ),
    )
    for relative, names in sources:
        path = backend / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        nodes = [node for node in tree.body if getattr(node, "name", None) in names]
        assert {node.name for node in nodes} == names
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def test_meal_plan_consent_is_explicit_and_drops_unrelated_fields(contract):
    """只带当前餐单用途、处理方和政策，不把 accepted 或其它用途透传。"""
    consent = {"purpose": "meal_plan", "processor": "synthetic", "policy_version": "v1", "accepted": True}
    assert contract["meal_plan_consent"](consent) == {
        "purpose": "meal_plan",
        "processor": "synthetic",
        "policy_version": "v1",
    }
    assert consent["accepted"] is True


@pytest.mark.parametrize(
    "consent",
    [
        {},
        {"processor": "synthetic", "policy_version": "v1"},
        {"purpose": "consultation", "processor": "synthetic", "policy_version": "v1"},
        {"purpose": "meal_plan", "policy_version": "v1"},
        {"purpose": "meal_plan", "processor": "synthetic"},
        {"purpose": "meal_plan", "processor": "", "policy_version": "v1"},
        {"purpose": "meal_plan", "processor": "synthetic", "policy_version": 1},
    ],
)
def test_meal_plan_consent_rejects_legacy_or_incomplete_policy(contract, consent):
    """旧无用途 consent 和不完整配置必须在发请求之前失败。"""
    with pytest.raises(AssertionError):
        contract["meal_plan_consent"](consent)


@pytest.mark.asyncio
async def test_daily_actors_are_two_new_ordinary_accounts_in_original_department(contract):
    """只追加两个新身份供既有 fixture 清理，保留原账号及管理员角色。"""
    original = [{"uid": f"original-{index}", "headers": {}} for index in range(3)]
    users = list(original)
    rows = []
    db = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(department_id=37)), add=rows.append)

    async def flush():
        """模拟数据库分配身份 ID，不制造业务成员或健康来源。"""
        rows[-1].id = len(rows) + 100

    @asynccontextmanager
    async def session():
        """仅提供身份 helper 需要的事务边界。"""
        yield db

    db.flush = flush
    user_model = Mock(side_effect=lambda **values: SimpleNamespace(**values))
    contract.update(
        pg_manager=SimpleNamespace(get_async_session_context=session),
        User=user_model,
        select=Mock(),
        AuthUtils=SimpleNamespace(create_access_token=lambda payload: "synthetic-" + payload["sub"]),
    )
    actors = await contract["create_daily_actors"](users)
    assert users[:3] == original and users[3:] == actors and len(actors) == len(rows) == 2
    assert len({actor["uid"] for actor in users}) == 5
    for row, actor in zip(rows, actors, strict=True):
        assert row.role == "user" and row.department_id == 37 and row.username == row.uid == actor["uid"]
        assert actor["headers"] == {"Authorization": f"Bearer synthetic-{row.id}"}


@pytest.mark.asyncio
async def test_prepare_members_uses_self_consent_then_shares_with_owner(contract):
    """严格请求 oracle 保证先本人建档/确认，再共享、owner 独立同意及最终回读。"""
    client = DailyFixtureHTTP(contract)
    result = await client.prepare()
    assert result == client.final_profile and len(client.calls) == 9
    assert len(client.analysis_ids) == 2 and client.analysis_ids[0] != client.analysis_ids[1]
    assert client.profile["members"][1]["healthMemberId"] is None


@pytest.mark.parametrize(
    ("step", "status", "body"),
    [
        (0, 200, {}),
        (0, 403, {"code": "wrong_denial"}),
        (1, 403, {}),
        (2, 200, {"id": "wrong-family"}),
        (3, 200, {"selfMemberId": "wrong-member"}),
        (4, 403, {}),
        (5, 403, {}),
        (5, 200, {"members": [{"id": "peer-placeholder", "healthMemberId": "wrong-health"}]}),
        (6, 403, {}),
        (7, 403, {}),
        (8, 200, {"defaultDiners": ["only-one"], "members": []}),
    ],
)
@pytest.mark.asyncio
async def test_prepare_members_stops_at_denial_or_identity_mismatch(contract, step, status, body):
    """拒绝、错家庭、错本人或错来源不能继续授予后续权限。"""
    client = DailyFixtureHTTP(contract)
    if step == 5 and status == 200:
        body = {"members": [{"id": client.peer_id, "healthMemberId": "wrong-health"}]}
    client.overrides[step] = (status, body)
    with pytest.raises(AssertionError):
        await client.prepare()
    assert len(client.calls) == step + 1


def test_actual_analysis_and_member_schemas_reject_missing_purpose_and_authorization(contract):
    """真实 DTO 接受明确用途，但不接受旧无用途分析或未确认健康建档。"""
    analysis = {
        "action": "start_analysis",
        "client_request_id": str(uuid4()),
        "member_id": str(uuid4()),
        "expected_version": 7,
        "accepted": True,
        "purpose": "meal_plan",
        "processor": "synthetic",
        "policy_version": "v1",
    }
    assert contract["MiniappAnalysisInput"].model_validate(analysis).purpose == "meal_plan"
    for missing in ("purpose", "processor", "policy_version"):
        with pytest.raises(ValidationError):
            contract["MiniappAnalysisInput"].model_validate({k: v for k, v in analysis.items() if k != missing})
    member = {"display_name": "合成家人", "relationship_label": "本人", "authorized": True}
    assert contract["MemberInput"].model_validate(member).relationship_label == "本人"
    with pytest.raises(ValidationError):
        contract["MemberInput"].model_validate({**member, "authorized": False})


class DailyFixtureHTTP:
    """独立固定九步协议，任何其它路径、顺序、身份或正文立即失败。"""

    def __init__(self, contract):
        """准备可区分的旧/新来源版本，以及独立正式档案和健康成员 ID。"""
        self.contract = contract
        self.owner = {"uid": "synthetic-owner", "headers": {"Authorization": "Bearer synthetic-owner"}}
        self.peer = {"uid": "synthetic-peer", "headers": {"Authorization": "Bearer synthetic-peer"}}
        self.users = [self.owner, self.peer]
        self.fid, self.owner_id, self.peer_id, self.health_id = (str(uuid4()) for _ in range(4))
        self.path = f"/api/family/{self.fid}/miniapp-profile"
        self.policy = {"purpose": "meal_plan", "processor": "synthetic", "policy_version": "v1"}
        self.profile = {
            "selfMemberId": self.owner_id,
            "defaultDiners": [self.owner_id, self.peer_id],
            "members": [
                {"id": self.owner_id, "name": "合成本人", "version": 2, "healthMemberId": str(uuid4())},
                {"id": self.peer_id, "name": "合成家人", "version": 3, "healthMemberId": None},
            ],
        }
        claimed = deepcopy(self.profile)
        claimed["selfMemberId"] = self.peer_id
        claimed["members"][1]["version"] = 7
        confirmed = deepcopy(claimed)
        confirmed["members"][1]["healthMemberId"] = self.health_id
        self.final_profile = {**deepcopy(confirmed), "selfMemberId": self.owner_id}
        health_path = f"/api/health/v1/members/{self.health_id}"
        self.steps = [
            ("post", self.path, self.owner, "analysis", 403, {"code": "member_consent_required"}),
            (
                "post",
                f"/api/family/{self.fid}/members/{self.peer_id}/invite",
                self.owner,
                None,
                200,
                {"code": "synthetic-invitation"},
            ),
            ("post", "/api/family/join", self.peer, {"code": "synthetic-invitation"}, 200, {"id": self.fid}),
            ("get", self.path, self.peer, None, 200, claimed),
            (
                "post",
                "/api/health/v1/members",
                self.peer,
                {"display_name": "合成家人", "relationship_label": "本人", "authorized": True},
                201,
                {"id": self.health_id},
            ),
            ("post", self.path, self.peer, "analysis", 200, confirmed),
            (
                "put",
                health_path + "/grants",
                self.peer,
                {"actor_uid": self.owner["uid"], "scopes": ["ai_use", "diet_edit", "profile_view"]},
                200,
                {"saved": True},
            ),
            (
                "post",
                health_path + "/processing-consents",
                self.owner,
                {**self.policy, "accepted": True},
                200,
                {"accepted": True},
            ),
            ("get", self.path, self.owner, None, 200, self.final_profile),
        ]
        self.calls, self.analysis_ids, self.overrides = [], [], {}

    async def prepare(self):
        """执行实际 E2E helper，不在测试中重写业务准备链。"""
        return await self.contract["prepare_daily_members"](
            self, self.users, self.owner, self.peer, self.fid, self.path, self.profile, self.policy
        )

    async def post(self, path, **kwargs):
        """校验 POST 请求。"""
        return self.request("post", path, kwargs)

    async def get(self, path, **kwargs):
        """校验 GET 请求。"""
        return self.request("get", path, kwargs)

    async def put(self, path, **kwargs):
        """校验 PUT 请求。"""
        return self.request("put", path, kwargs)

    def request(self, method, path, kwargs):
        """请求必须匹配固定独立 oracle，并在边界使用真实 DTO 校验。"""
        index = len(self.calls)
        expected_method, expected_path, actor, expected_body, status, body = self.steps[index]
        assert (method, path) == (expected_method, expected_path)
        expected_headers = dict(actor["headers"])
        if expected_body == "analysis":
            data = kwargs["json"]
            request_id = data["client_request_id"]
            assert str(UUID(request_id)) == request_id
            expected_headers["Idempotency-Key"] = request_id
            assert data == {
                "action": "start_analysis",
                "client_request_id": request_id,
                "member_id": self.peer_id,
                "expected_version": 3 if index == 0 else 7,
                "accepted": True,
                **self.policy,
            }
            self.contract["MiniappAnalysisInput"].model_validate(data)
            self.analysis_ids.append(request_id)
        elif expected_body is None:
            assert "json" not in kwargs
        else:
            assert kwargs["json"] == expected_body
            if index == 4:
                self.contract["MemberInput"].model_validate(kwargs["json"])
        assert kwargs["headers"] == expected_headers
        assert set(kwargs) == ({"headers"} if expected_body is None else {"headers", "json"})
        self.calls.append((method, path, deepcopy(kwargs)))
        status, body = self.overrides.get(index, (status, body))
        return SimpleNamespace(status_code=status, text="synthetic fixture response", json=lambda: deepcopy(body))
