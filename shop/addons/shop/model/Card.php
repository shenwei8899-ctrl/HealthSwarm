<?php

namespace addons\shop\model;

use think\Model;

class Card extends Model
{

    // 表名
    protected $name = 'shop_card';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [
        'status_text'
    ];

    public function getStatusList()
    {
        return ['normal' => __('Normal'), 'hidden' => __('Hidden')];
    }

    public function getStatusTextAttr($value, $data)
    {
        $value = $value ?: ($data['status'] ?? '');
        $list = $this->getStatusList();
        return $list[$value] ?? '';
    }

    public function setContentAttr($value, $data)
    {
        return htmlentities($value);
    }

    public function getContentAttr($value, $data)
    {
        return html_entity_decode($value);
    }
}
