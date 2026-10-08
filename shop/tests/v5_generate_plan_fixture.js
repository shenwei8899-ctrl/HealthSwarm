const fs = require('fs');
const output = process.argv[2] || 'tests/fixtures/agent-plan-21-days.generated.json';
const days = Array.from({length: 21}, (_, index) => ({
  day_no: index + 1,
  display_title: `第${index + 1}天`,
  daily_summary: '本地联调示例',
  meals: [{
    meal_type: 'lunch', recipe_ref: `recipe-demo-${index + 1}`, recipe_name: `联调菜品${index + 1}`,
    ingredient_requirements: [{ingredient_code: 'tomato', required_value: '300.000', required_unit: 'g', is_optional: false}],
  }],
}));
const fixture = {
  agent_task_id: `agent-plan-demo-${Date.now()}`, family_ref: 'family-demo-001', user_ref: 'user-demo-001',
  member_refs: ['member-demo-001'], profile_version_refs: ['profile-demo-v1'], plan_name: '21天家庭营养联调计划',
  plan_days: 21, delivery_frequency: 'daily', requires_professional_review: false, days,
  nutrition_validation: {validation_id: 'nutrition-plan-demo-001', status: 'passed', rules_version: 'demo-v1', validated_at: new Date().toISOString(), summary: '演示数据：全计划校验通过'},
};
fs.writeFileSync(output, `${JSON.stringify(fixture, null, 2)}\n`);
console.log(output);
