<?php

namespace addons\shop\controller\api;

use addons\shop\library\Theme;
use think\Config;
use think\Hook;
use addons\shop\model\Navigation;
use addons\shop\model\Area;
use addons\shop\model\Block;
use addons\shop\model\SearchLog;

/**
 * 公共
 */
class Common extends Base
{
    protected $noNeedLogin = ['init', 'area'];

    /**
     * 初始化
     */
    public function init()
    {
        //配置信息
        $upload = Config::get('upload');

        //如果非服务端中转模式需要修改为中转
        if ($upload['storage'] != 'local' && isset($upload['uploadmode']) && $upload['uploadmode'] != 'server') {
            //临时修改上传模式为服务端中转
            set_addon_config($upload['storage'], ["uploadmode" => "server"], false);

            $upload = \app\common\model\Config::upload();
            // 上传信息配置后
            Hook::listen("upload_config_init", $upload);

            $upload = Config::set('upload', array_merge(Config::get('upload'), $upload));
        }

        $upload['cdnurl'] = $upload['cdnurl'] ? $upload['cdnurl'] : cdnurl('', true);
        //上传地址强制切换为使用本地上传，云存储插件会自动处理
        $upload['uploadurl'] = url('/api/common/upload', '', false, true);

        //支付列表和默认支付方式
        $paytypearr = array_filter(explode(',', Config::get('shop.paytypelist')));
        $defaultPaytype = Config::get('shop.defaultpaytype');
        $defaultPaytype = in_array($defaultPaytype, $paytypearr) ? $defaultPaytype : reset($paytypearr);

        //登录类型列表
        $logintypearr = array_filter(explode(',', Config::get('shop.logintypelist')));

        $config = [
            'upload'         => $upload,
            //登录类型列表
            'logintypearr'   => $logintypearr,
            'paytypelist'    => implode(',', $logintypearr),
            'defaultpaytype' => $defaultPaytype,
            '__token__'      => $this->request->token()
        ];

        //焦点图
        $bannerList = [];
        $list = Block::getBlockListByName('uniappfocus', 5);
        foreach ($list as $index => $item) {
            $bannerList[] = ['image' => cdnurl($item['image'], true), 'url' => $item['url'], 'title' => $item['title']];
        }
        $config['swiper'] = $bannerList;

        $config['order_timeout'] = Config::get('shop.order_timeout');
        $config['sitename'] = Config::get('shop.sitename');
        $config['notice'] = Config::get('shop.notice');
        $config['phone'] = Config::get('shop.phone');
        $config['logisticstype'] = Config::get('shop.logisticstype');

        $config['category_mode'] = (int)Config::get('shop.category_mode');
        $config['money_score'] = Config::get('shop.money_score');
        $config['comment_score'] = Config::get('shop.comment_score');

        $config['default_goods_img'] = cdnurl(Config::get('shop.default_goods_img'), true);
        $config['default_category_img'] = cdnurl(Config::get('shop.default_category_img'), true);

        $config['navigate'] = Navigation::tableList();
        $config['brands'] = \addons\shop\model\Brand::field('id,name')->order('weigh desc')->select();

        //消息订阅模板id
        $config['tpl_ids'] = \addons\shop\model\TemplateMsg::getTplIds();

        //热门搜索关键词
        $config['hot_keyword'] = SearchLog::order('nums desc')->limit(10)->column('keywords');

        //合并主题样式，判断是否预览模式
        $isPreview = stripos($this->request->SERVER("HTTP_REFERER"), "mode=preview") !== false;
        $themeConfig = $isPreview && \think\Session::get("previewtheme-shop") ? \think\Session::get("previewtheme-shop") : Theme::get();

        $themeConfig = Theme::render($themeConfig);
        $data = array_merge($config, $themeConfig);

        $this->success('', $data);
    }

    /**
     * 读取省市区数据,联动列表
     */
    public function area()
    {
        $province = $this->request->param('province', '');
        $city = $this->request->param('city', '');
        $where = ['pid' => 0, 'level' => 1];
        $provincelist = null;
        if ($province !== '') {
            $where['pid'] = $province;
            $where['level'] = 2;
        }
        if ($city !== '') {
            $where['pid'] = $city;
            $where['level'] = 3;
        }
        $provincelist = Area::where($where)->field('id as value,name as label')->where('status', 'normal')->select();
        $this->success('', $provincelist);
    }
}
