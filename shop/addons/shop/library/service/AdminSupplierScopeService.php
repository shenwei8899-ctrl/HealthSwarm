<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class AdminSupplierScopeService
{
    public static function supplierIds($adminId)
    {
        return array_map('intval', Db::name('shop_admin_supplier_scope')->where('admin_id', (int)$adminId)->column('supplier_id'));
    }

    public static function apply($query, $adminId, $field = 'supplier_id')
    {
        $ids = self::supplierIds($adminId);
        if ($ids) {
            return $query->where($field, 'in', $ids);
        }
        return self::requiresScope($adminId) ? $query->where('1=0') : $query;
    }

    public static function assertAllowed($adminId, $supplierId)
    {
        $ids = self::supplierIds($adminId);
        if (($ids || self::requiresScope($adminId)) && !in_array((int)$supplierId, $ids, true)) {
            throw new RuntimeException('无权访问该供应商数据', 403);
        }
    }

    private static function requiresScope($adminId)
    {
        $adminId = (int)$adminId;
        if ($adminId === 1) {
            return false;
        }
        return (bool)Db::name('auth_group_access')->alias('access')
            ->join('__AUTH_GROUP__ group', 'group.id=access.group_id')
            ->where('access.uid', $adminId)
            ->where('group.name', '供应商运营')
            ->where('group.status', 'normal')
            ->count();
    }
}
