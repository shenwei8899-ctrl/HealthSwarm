<?php

namespace addons\shop\library\v5;

use think\Db;

class IdentityService
{
    public function resolveUserId($clientId, $userRef)
    {
        $row = Db::name('shop_external_identity')->where([
            'client_id'         => $clientId,
            'external_user_ref' => (string)$userRef,
            'status'            => 'normal',
        ])->find();
        if (!$row) {
            throw new DomainException('外部用户尚未绑定商城会员', 40405, 404, [
                'client_id' => $clientId,
                'user_ref'  => (string)$userRef,
            ]);
        }
        return (int)$row['user_id'];
    }

    public function assertOwner($userId, $resourceUserId)
    {
        if ((int)$userId !== (int)$resourceUserId) {
            throw new DomainException('无权访问该资源', 40301, 403);
        }
    }
}
