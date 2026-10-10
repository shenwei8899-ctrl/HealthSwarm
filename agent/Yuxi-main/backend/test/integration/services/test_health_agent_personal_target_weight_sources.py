"""私有PG/TCP本人实测变化后，Agent目标绑定Owner明确失效不退旧来源。"""

from types import SimpleNamespace

import pytest

from test.integration.services.test_health_family_profile_http import (
    cleanup_test_knowledge_resources,  # noqa: F401
    cleanup_test_sandboxes,  # noqa: F401
    ensure_live_api_schema,  # noqa: F401
    family_profile_http,  # noqa: F401
)
from test.integration.services.test_health_weight_targets_http import (
    import_selected_profile,
    mutate_weight,
    publish_weight_rules,
    selected_weight,  # noqa: F401
    target_read,
)
from yuxi.services.health_agent_personal_target_service import (
    authorize_personal_target_binding,
    target_public_projection,
)
from yuxi.services.health_vision_types import HealthVisionError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("change", ["correct", "void"])
async def test_agent_binding_reuses_current_selected_measurement_guard(selected_weight, change):  # noqa: F811
    """真实本人60/v1算330；更正或作废后旧绑定410，不暴露身体字段。"""
    case = selected_weight
    await import_selected_profile(case)
    rules = await publish_weight_rules(case)
    current = await target_read(case, rules)
    assert current["energy_kcal"] == "330"
    assert current["attestations"]["profile"]["weight_measurement_source"]["record_id"] == case.record["id"]
    projected = target_public_projection(current)
    binding = SimpleNamespace(
        actor_uid="self",
        member_id=case.member,
        personal_target_selection={
            "selection": {"profile_version": 1, "rule_version": 1, "rule_code": rules["rule_code"]},
            "source_hash": projected["source_hash"],
        },
    )
    async with case.sessions() as session:
        assert await authorize_personal_target_binding(session, binding) == current
    assert not {"inputs", "attestations", "formula", "formula_bounds", "weight_measurement_source"} & projected.keys()
    await mutate_weight(case, case.record, change)
    changed = await target_read(case, rules)
    assert changed["status"] == "not_ready" and "bounds" not in changed
    async with case.sessions() as session:
        with pytest.raises(HealthVisionError, match="source_invalidated") as error:
            await authorize_personal_target_binding(session, binding)
    assert error.value.status == 410
