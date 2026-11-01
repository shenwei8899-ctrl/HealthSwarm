<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\PartnerApplicationService;
use think\Db;

class CommerceSupplierApplication extends Base
{
    public function policy()
    {
        return $this->execute(function () {
            $this->userId();
            return (new PartnerApplicationService())->policy();
        });
    }

    public function create()
    {
        return $this->execute(function () {
            return (new PartnerApplicationService())->submit($this->userId(), $this->request->header('idempotency-key'), $this->input());
        });
    }

    public function detail($application_sn = null)
    {
        header('Cache-Control: private, no-store');
        $application_sn = $application_sn ?? $this->request->route('application_sn');
        return $this->execute(function () use ($application_sn) {
            $row = Db::name('shop_supplier_application')->where('application_sn', $application_sn)->where('user_id', $this->userId())->find();
            if (!$row) {
                throw new DomainException('合作申请不存在', 40413, 404);
            }
            unset($row['contact_mobile_encrypted'], $row['submission_key'], $row['submission_hash'],
                $row['follow_up_note'], $row['follow_up_admin_id'], $row['follow_up_status'], $row['follow_up_at']);
            return $row;
        });
    }
}
