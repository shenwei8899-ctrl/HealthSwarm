<?php
namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\MediaUrl;
use app\common\library\Upload;

class CommerceMedia extends Base
{
    public function evidence()
    {
        return $this->execute(function () {
            $this->requireMethod('POST'); $this->userId();
            $file = $this->request->file('file');
            if (!$file || $file->getSize() > 5 * 1024 * 1024) throw new DomainException('请选择不超过5MB的照片', 40001, 400);
            $info = @getimagesize($file->getPathname());
            if (!$info || !in_array($info['mime'], ['image/jpeg', 'image/png', 'image/webp'], true)) throw new DomainException('照片格式需为 JPG、PNG 或 WebP', 40001, 400);
            \think\Config::set('upload.mimetype', 'jpg,jpeg,png,webp');
            \think\Config::set('upload.maxsize', '5mb');
            try { $attachment = (new Upload($file))->upload(); }
            catch (\app\common\exception\UploadException $e) { throw new DomainException($e->getMessage(), 40001, 400); }
            return ['url' => MediaUrl::absolute($attachment->url)];
        });
    }
}
