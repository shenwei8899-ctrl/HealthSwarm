<?php
// 仅替代远端来源回调；使用真实 payload 校验代码，不访问商城或用户数据库。
$library = dirname(__DIR__, 2) . '/addons/shop/library/v5/';
foreach (['DomainException.php', 'Json.php', 'AgentMealSourceService.php'] as $file) require_once $library . $file;

use addons\shop\library\v5\{AgentMealSourceService, DomainException, Json};

class SyntheticReferenceSource extends AgentMealSourceService
{
    public function validateProof(array $proof)
    {
        if (($proof['signature'] ?? '') !== 'synthetic-server-receipt') throw new DomainException('invalid proof', 40301, 403);
        return ['available'=>true, 'selection_mode'=>'reference', 'items'=>[['sku_id'=>'101','quantity'=>2]]];
    }
}
function referenceAssert($value, $message) { if (!$value) throw new RuntimeException($message); }
function referenceReject($fn) {
    try { $fn(); } catch (DomainException $e) { return; }
    throw new RuntimeException('Expected reference protocol rejection');
}
$service = new SyntheticReferenceSource();
$proof = ['payload'=>Json::encode(['kind'=>'reference_plan','uid'=>'synthetic-owner','preview_id'=>'synthetic-preview']), 'signature'=>'synthetic-server-receipt'];
$payload = ['user_ref'=>'uid:synthetic-owner','menu_version_ref'=>'reference:synthetic-preview',
    'nutrition_validation'=>['status'=>'reference_only'], 'ingredient_requirements'=>[],
    'items'=>[['sku_id'=>'101','quantity'=>2]], 'agent_source_proof'=>$proof];
referenceAssert($service->validateReferencePayload($payload), 'Reference SKU selection must not require approved ingredient mappings');
$cases = [
    ['items'=>[['sku_id'=>'102','quantity'=>2]]],
    ['items'=>[['sku_id'=>'101','quantity'=>1]]],
    ['items'=>[['sku_id'=>'101','quantity'=>2],['sku_id'=>'101','quantity'=>2]]],
    ['items'=>[]], ['user_ref'=>'uid:another-owner'], ['menu_version_ref'=>'reference:other-preview'],
    ['nutrition_validation'=>['status'=>'passed']],
    ['agent_source_proof'=>array_merge($proof,['signature'=>'forged'])],
];
foreach ($cases as $changes) referenceReject(function () use ($service, $payload, $changes) { $service->validateReferencePayload(array_merge($payload, $changes)); });
referenceAssert(!AgentMealSourceService::nutritionAllowsTrade(['nutrition_status'=>'reference_only']), 'Reference label alone cannot authorize trade');
referenceAssert(AgentMealSourceService::nutritionAllowsTrade(['nutrition_status'=>'reference_only','agent_source_proof_json'=>Json::encode($proof)]), 'Verified reference source has separate trade status');
referenceAssert(!$service->validateReferencePayload(['agent_source_proof'=>[]]), 'Ordinary payload keeps its existing formal contract');

class SyntheticConversationSource extends AgentMealSourceService
{
    public function validateProof(array $proof)
    {
        if (($proof['signature'] ?? '') !== 'synthetic-conversation-receipt') throw new DomainException('invalid proof', 40301, 403);
        return ['available'=>true, 'selection_mode'=>'reference', 'items'=>[['sku_id'=>'101','quantity'=>1]]];
    }
}
$catalogService = new SyntheticConversationSource();
$catalogProof = ['payload'=>Json::encode(['kind'=>'conversation_catalog','uid'=>'synthetic-owner','request_id'=>'synthetic-request']), 'signature'=>'synthetic-conversation-receipt'];
$catalogPayload = ['user_ref'=>'uid:synthetic-owner','menu_version_ref'=>'conversation:synthetic-request',
    'nutrition_validation'=>['status'=>'reference_only'], 'ingredient_requirements'=>[],
    'items'=>[['sku_id'=>'101','quantity'=>1]], 'agent_source_proof'=>$catalogProof];
referenceAssert($catalogService->validateReferencePayload($catalogPayload), 'Conversation catalogue selection must share the verified reference trade contract');
referenceAssert(AgentMealSourceService::nutritionAllowsTrade(['nutrition_status'=>'reference_only','agent_source_proof_json'=>Json::encode($catalogProof)]), 'Conversation catalogue keeps its explicit unknown-nutrition trade state');
referenceReject(function () use ($catalogService, $catalogPayload) { $catalogService->validateReferencePayload(array_replace($catalogPayload, ['menu_version_ref'=>'reference:synthetic-request'])); });
referenceReject(function () use ($catalogService, $catalogPayload) { $catalogService->validateReferencePayload(array_replace($catalogPayload, ['user_ref'=>'uid:another-owner'])); });
referenceReject(function () use ($catalogService, $catalogPayload) { $catalogService->validateReferencePayload(array_replace($catalogPayload, ['items'=>[['sku_id'=>'101','quantity'=>2]]])); });
referenceReject(function () use ($catalogService, $catalogPayload) { $catalogService->validateReferencePayload(array_replace($catalogPayload, ['nutrition_validation'=>['status'=>'passed']])); });
echo json_encode(['passed'=>true,'rejected_cases'=>count($cases),'real_database_used'=>false]) . "\n";
