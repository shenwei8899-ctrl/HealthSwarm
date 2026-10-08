<?php

namespace addons\shop\model;

use think\Model;


class Exchange extends Model
{


    // 表名
    protected $name = 'shop_exchange';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    protected static $config = [];

    // 追加属性
    protected $append = [
        'type_text',
        'status_text',
        'url'
    ];

    public function getUrlAttr($value, $data)
    {
        return $this->buildUrl($value, $data);
    }

    public function getFullurlAttr($value, $data)
    {
        return $this->buildUrl($value, $data, true);
    }

    private function buildUrl($value, $data, $domain = false)
    {
        $vars = [
            ':id' => $data['id']
        ];
        $suffix = static::$config['moduleurlsuffix']['exchange'] ?? static::$config['urlsuffix'];
        return addon_url('shop/exchange/show', $vars, $suffix, $domain);
    }


    protected static function init()
    {
        $config = get_addon_config('shop');
        self::$config = $config;

        self::afterInsert(function ($row) {
            $pk = $row->getPk();
            $row->getQuery()->where($pk, $row[$pk])->update(['weigh' => $row[$pk]]);
        });
    }


    public function getTypeList()
    {
        return ['virtual' => __('Type virtual'), 'reality' => __('Type reality')];
    }

    public function getStatusList()
    {
        return ['normal' => __('Normal'), 'hidden' => __('Hidden')];
    }


    public function getTypeTextAttr($value, $data)
    {
        $value = $value ?: ($data['type'] ?? '');
        $list = $this->getTypeList();
        return $list[$value] ?? '';
    }


    public function getStatusTextAttr($value, $data)
    {
        $value = $value ?: ($data['status'] ?? '');
        $list = $this->getStatusList();
        return $list[$value] ?? '';
    }

    public function getImageAttr($value)
    {
        return cdnurl($value, true);
    }

    //获取列表
    public static function tableList($param)
    {
        $pageNum = 15;
        if (!empty($param['num'])) {
            $pageNum = $param['num'];
        }

        $orderby = 'createtime';
        $orderway = 'desc';

        if (!empty($param['orderby']) && in_array($param['orderby'], ['createtime', 'score', 'sales', 'weigh'])) {
            $orderby = $param['orderby'];
        }
        if (!empty($param['orderway']) && in_array($param['orderway'], ['asc', 'desc'])) {
            $orderway = $param['orderway'];
        }

        return self::where(function ($query) use ($param) {

            $query->where('stocks', '>', 0)->where('status', 'normal');

            if (!empty($param['type'])) {
                $query->where('type', $param['type']);
            }

            if (isset($param['keyword']) && $param['keyword'] != '') {
                $query->where('title', 'like', '%' . $param['keyword'] . '%');
            }
        })->order("$orderby $orderway")->paginate($pageNum);
    }
}
