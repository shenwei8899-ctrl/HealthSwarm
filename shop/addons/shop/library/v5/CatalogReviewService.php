<?php
namespace addons\shop\library\v5;

use think\Db;

/** 商业资料审核保留证据、操作者及版本，不替代 Agent 营养审核。 */
class CatalogReviewService
{
    public function save($resource, $id, array $data, $version, $adminId)
    {
        $tables = ['ingredient_maps'=>'shop_ingredient_sku_map', 'nutrition'=>'shop_sku_nutrition_fact', 'components'=>'shop_sku_ingredient_component'];
        if (!isset($tables[$resource])) throw new DomainException('资料类型无效', 40001, 400);
        Db::startTrans();
        try {
            $table = $tables[$resource];
            $old = $id ? Db::name($table)->where('id', $id)->lock(true)->find() : null;
            if ($id && !$old) throw new DomainException('记录不存在', 40401, 404);
            $versionKey = $resource === 'components' ? 'updatetime' : 'version';
            if ($id && (string)($old[$versionKey] ?? '') !== (string)$version) throw new DomainException('资料已变化，请刷新后重试', 40906, 409);
            $data = $this->validate($resource, $data);
            $now = time();
            $data['updatetime'] = $resource === 'components' && $old ? max($now, (int)$old['updatetime'] + 1) : $now;
            if ($resource !== 'components') {
                $data['version'] = $old ? (int)$old['version'] + 1 : 1;
                $data['reviewed_at'] = $data['review_status'] === 'approved' ? $now : 0;
                if ($resource === 'ingredient_maps') $data['reviewer_id'] = $data['review_status'] === 'approved' ? (int)$adminId : 0;
            }
            if ($id) Db::name($table)->where('id', $id)->update($data);
            else { $data['createtime'] = $now; $id = Db::name($table)->insertGetId($data); }
            Db::name('shop_catalog_review_log')->insert([
                'resource_type'=>$resource, 'resource_id'=>$id, 'admin_id'=>$adminId,
                'before_json'=>Json::encode($old ?: []), 'after_json'=>Json::encode($data), 'createtime'=>$now,
            ]);
            (new CatalogService())->touchVersion($resource, $id, '资料维护与审核');
            Db::commit();
            return $id;
        } catch (\Throwable $e) { Db::rollback(); throw $e; }
    }

    public function validate($resource, array $data)
    {
        $sku = Db::name('shop_goods_sku')->where('id', (int)($data['sku_id'] ?? 0))->find();
        if (!$sku) throw new DomainException('请选择有效 SKU', 40001, 400);
        if ($resource !== 'components' && !in_array($data['status'] ?? '', ['normal','hidden'], true)) throw new DomainException('资料状态无效', 40001, 400);
        if ($resource !== 'components') {
            if (!in_array($data['review_status'] ?? '', ['pending','approved','rejected'], true)) throw new DomainException('审核状态无效', 40001, 400);
            foreach (['valid_from','valid_to'] as $key) {
                $value = trim((string)($data[$key] ?? ''));
                $time = $value === '' ? 0 : (ctype_digit($value) ? (int)$value : strtotime($value));
                if ($time === false || $time < 0) throw new DomainException('有效期格式无效', 40001, 400);
                $data[$key] = $time;
            }
            if ($data['valid_to'] && $data['valid_from'] && $data['valid_to'] <= $data['valid_from']) throw new DomainException('结束时间必须晚于开始时间', 40001, 400);
            if ($data['review_status'] === 'approved' && (!$data['valid_to'] || $data['valid_to'] <= time())) throw new DomainException('审核通过前须填写未来的有效截止时间', 40001, 400);
        }
        if (in_array($resource, ['ingredient_maps','components'], true)) {
            if (!Db::name('shop_ingredient')->where('id', (int)($data['ingredient_id'] ?? 0))->where('status','normal')->find()) throw new DomainException('请选择有效食材', 40001, 400);
        }
        if ($resource === 'ingredient_maps') {
            if (!in_array($data['role'] ?? '', ['primary','component','alternative'], true)) throw new DomainException('食材角色无效', 40001, 400);
            if ((int)$data['goods_id'] !== (int)$sku['goods_id']) throw new DomainException('SKU 与商品不一致', 40001, 400);
            foreach (['net_value','convert_ratio','loss_rate'] as $key) $this->number($data[$key] ?? null, $key, $key === 'loss_rate');
            if ((float)$data['loss_rate'] >= 1) throw new DomainException('损耗率应小于 1', 40001, 400);
            if (!in_array($data['net_unit'] ?? '', ['g','kg','ml','l','piece','pack'], true)) throw new DomainException('计量单位无效', 40001, 400);
            if ($data['review_status'] === 'approved' && trim($data['source_ref'] ?? '') === '') throw new DomainException('审核通过前须填写真实换算来源或证明文件', 40001, 400);
        } elseif ($resource === 'nutrition') {
            if (!in_array($data['basis_type'] ?? '', ['per_100g','per_serving'], true)) throw new DomainException('营养基准类型无效', 40001, 400);
            $this->number($data['basis_value'] ?? null, '基准值');
            if (!in_array($data['basis_unit'] ?? '', ['g','kg','ml','l','piece','pack'], true)) throw new DomainException('营养基准单位无效', 40001, 400);
            if ($data['basis_type'] === 'per_100g' && ((float)$data['basis_value'] !== 100.0 || $data['basis_unit'] !== 'g')) throw new DomainException('每100克基准必须为100 g', 40001, 400);
            foreach (['energy_kcal','protein_g','fat_g','carbohydrate_g','fiber_g','sodium_mg'] as $key) {
                if (!isset($data[$key]) || $data[$key] === '') $data[$key] = null;
                else $this->number($data[$key], $key, true);
            }
            if ($data['review_status'] === 'approved') {
                foreach (['source_name','source_version','energy_kcal','protein_g','fat_g','carbohydrate_g','sodium_mg'] as $key) {
                    if (!isset($data[$key]) || trim((string)$data[$key]) === '') throw new DomainException('资料不完整，不能审核通过：'.$key, 40001, 400);
                }
            }
        } else {
            // 成分表没有审核状态字段，保存来源不表示已经完成专业审核。
            unset($data['status']);
            if (trim($data['data_source'] ?? '') === '' || trim($data['data_version'] ?? '') === '') throw new DomainException('成分资料必须有来源和版本', 40001, 400);
            $this->number($data['component_value'] ?? null, '成分数量');
            if (!in_array($data['component_unit'] ?? '', ['g','kg','ml','l','piece','pack'], true)) throw new DomainException('成分单位无效', 40001, 400);
            if (!in_array((string)($data['allergen_flag'] ?? ''), ['0','1'], true)) throw new DomainException('过敏原标记无效', 40001, 400);
        }
        return $data;
    }

    private function number($value, $field, $allowZero = false)
    {
        if (!is_numeric($value) || !is_finite((float)$value) || ($allowZero ? (float)$value < 0 : (float)$value <= 0)) throw new DomainException($field.'必须为有效'.($allowZero ? '非负' : '正').'数', 40001, 400);
    }
}
