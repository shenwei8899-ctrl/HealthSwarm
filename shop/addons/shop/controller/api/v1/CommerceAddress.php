<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\AddressService;
use addons\shop\library\v5\IdempotencyService;

class CommerceAddress extends Base
{
    public function index() { return $this->execute(function () { return (new AddressService())->listRows($this->userId()); }); }
    public function areas() { return $this->execute(function () { return (new AddressService())->areas($this->request->get('pid', 0), $this->request->get('tree/d', 0) === 1); }); }
    public function create() { return $this->mutate('create'); }
    public function update($id = null) {
        $id = $id ?? $this->request->route('id'); return $this->mutate('update', $id); }
    public function remove($id = null) {
        $id = $id ?? $this->request->route('id'); return $this->mutate('remove', $id); }
    public function selectDefault($id = null) {
        $id = $id ?? $this->request->route('id'); return $this->mutate('default', $id); }

    private function mutate($action, $id = null)
    {
        return $this->execute(function () use ($action, $id) {
            $uid = $this->userId(); $p = $this->input();
            return (new IdempotencyService())->run('commerce.address.' . $action, 'miniapp:' . $uid, $this->request->header('idempotency-key'), ['id' => $id] + $p, function () use ($uid, $p, $action, $id) {
                $service = new AddressService();
                if ($action === 'remove') return $service->remove($uid, $id);
                if ($action === 'default') return $service->selectDefault($uid, $id);
                return $service->save($uid, $p, $id);
            });
        });
    }
}
