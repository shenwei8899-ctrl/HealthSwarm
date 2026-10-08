<?php

namespace addons\shop\controller\api;

use addons\shop\model\Goods as GoodsModel;
use addons\shop\model\Guarantee;
use addons\shop\model\SkuSpec;
use addons\shop\model\Collect;
use addons\shop\model\Comment;
use addons\shop\model\AttributeValue;
use addons\shop\model\Coupon;
use addons\shop\model\CouponCondition;
use addons\shop\model\UserCoupon;
use fast\Http;
use think\Log;

/**
 * 商品接口
 */
class Goods extends Base
{
    protected $noNeedLogin = ['index', 'detail', 'lists', 'getWxCode'];

    //首页推荐商品
    public function index()
    {
        $hots = GoodsModel::where('status', 'normal')
            ->where("find_in_set('hot',\"flag\") > 0")
            ->order('weigh desc')
            ->limit(12)
            ->cache(false)
            ->select();
        $recommends = GoodsModel::getIndexGoodsList();
        foreach ($hots as $item) {
            $item->visible(explode(',', 'id,title,price,marketprice,sales,views,image'));
        }
        foreach ($recommends as $item) {
            $item->visible(explode(',', 'id,title,price,marketprice,sales,views,image'));
        }
        $this->success('获取成功', [
            'hots'       => $hots,
            'recommends' => $recommends
        ]);
    }

    //详情
    public function detail()
    {
        $id = $this->request->param('id/d');
        if (!$id) {
            $this->error('参数错误');
        }
        $row = (new GoodsModel())->with([
            'Sku',
            'Comment' => function ($query) {
                $query->relation([
                    'reply' => function ($user) {
                        $user->with([
                            'manage' => function ($u) {
                                $u->field('id,nickname');
                            }
                        ]);
                    }
                ])->where('status', 'normal')->where('pid', 0)->field('id,goods_id,content,star,user_id,images,comments,createtime')->with([
                    'User' => function ($u) {
                        $u->field('id,nickname,avatar');
                    }
                ])->order('createtime', 'desc')->limit(10);
            }
        ])->where('status', '<>', 'hidden')->where('id', $id)->find();

        if (!$row) {
            $this->error('未找到该商品');
        }
        $row->setInc('views');
        //收藏
        if ($this->auth->isLogin()) {
            $row->is_collect = !!(Collect::where('user_id', $this->auth->id)->where('goods_id', $id)->where('status', 1)->find());
        } else {
            $row->is_collect = false;
        }
        $row->sku_spec = SkuSpec::getGoodsSkuSpec($id);
        //服务保障
        $row->guarantee = $row->guarantee_ids ? Guarantee::field('id,name,intro')->where('id', 'IN', $row->guarantee_ids)->where('status', 'normal')->select() : [];
        //属性
        $row->attributes = AttributeValue::getAttributeList($row->attribute_ids);
        //好评度
        $row->favor_rate = Comment::degree($id);

        //评论
        $comment = collection($row->comment)->toArray();
        foreach ($comment as &$item) {
            if ($item['user']) {
                $item['user']['avatar'] = cdnurl($item['user']['avatar'], true);
            }
        }
        $row->setRelation('comment', $comment);
        unset($item);
        //优惠券
        $conditions = CouponCondition::getGoodsCondition($id, $row->category_id, $row->brand_id);
        $sql = "condition_ids IS NULL OR condition_ids=''";
        foreach ($conditions as $key => $item) {
            $sql .= " OR FIND_IN_SET('{$item['id']}',condition_ids)";
        }
        $couponList = Coupon::field('id,name,result,result_data,allow_num,begintime,endtime,use_times,received_num,give_num,mode,createtime')
            ->where($sql)
            ->where('is_open', 1)
            ->where('is_private', 'no')
            ->where('endtime', '>', time())
            ->select();
        //已经登录，渲染已领的优惠券
        $coupon_ids = [];
        if ($this->auth->isLogin()) {
            $coupon_ids = UserCoupon::where('user_id', $this->auth->id)->column('coupon_id');
        }
        foreach ($couponList as $key => &$item) {
            Coupon::render($item, $coupon_ids);
            $item->hidden(['received_num', 'give_num', 'condition_ids']);
        }
        $row->coupon = $couponList;

        $row->visible(explode(',', 'id,title,subtitle,category_id,price,marketprice,sales,views,image,content,images,sku_spec,sku,comment,is_collect,guarantee,attributes,favor_rate,coupon'));
        $row = $row->toArray();
        $row['content'] = \addons\shop\library\Service::formatTplToUniapp($row['content']);
        $this->success('获取成功', $row);
    }

    //列表
    public function lists()
    {
        $param = $this->request->param();
        $pageNum = (int)$this->request->param('pageNum', 10);
        $orderby = $this->request->param('orderby', 'weigh');
        $orderway = $this->request->param('orderway', 'desc');

        $list = GoodsModel::where(function ($query) use ($param) {
            $query->where('status', 'normal');
            //关键词
            if (isset($param['keyword']) && !empty($param['keyword'])) {
                $query->where('title|keywords', 'like', '%' . $param['keyword'] . '%');
                $log = \addons\shop\model\SearchLog::getByKeywords($param['keyword']);
                if ($log) {
                    $log->setInc("nums");
                } else {
                    \addons\shop\model\SearchLog::create(['keywords' => $param['keyword'], 'nums' => 1, 'status' => 'hidden']);
                }
            }
            //分类
            if (isset($param['category_id']) && !empty($param['category_id'])) {
                $query->where('category_id', 'IN', \addons\shop\model\Category::getCategoryChildrenIds($param['category_id']));
            }
            //属性
            if (isset($param['attributes']) && !empty($param['attributes'])) {
                $query->where('id', 'IN', \addons\shop\model\GoodsAttr::getGoodsIds($param['attributes']));
            }
            //品牌
            if (isset($param['brand_id']) && !empty($param['brand_id'])) {
                $query->where('brand_id', 'IN', $param['brand_id']);
            }
            //价格
            if (isset($param['price']) && !empty($param['price'])) {
                $priceArr = explode('-', $param['price']);
                if (count($priceArr) == 2) {
                    if (isset($priceArr[0])) {
                        $priceArr[0] = (float)$priceArr[0];
                    }
                    if (isset($priceArr[1])) {
                        $priceArr[1] = (float)$priceArr[1];
                    }
                    $query->where('price', 'BETWEEN', $priceArr);
                }
            }
        })->order("{$orderby} {$orderway}")->paginate($pageNum);

        foreach ($list as $item) {
            $item->visible(explode(',', 'id,title,image,price,sales,views,description,marketprice,createtime'));
        }

        $this->success('', $list);
    }

    //获取小程序码
    public function getWxCode()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $goods_id = $this->request->post('goods_id');
        $version = $this->request->post('version', 'release');
        if (empty($goods_id)) {
            $this->error('参数错误');
        }
        $user_id = '';
        if ($this->auth->isLogin()) {
            $user_id = $this->auth->id;
        }
        $resource = '';
        $fileStream = (new \addons\shop\library\message\Mini)->getWxCodeUnlimited([
            'scene'       => "invite_id={$user_id}&goods_id={$goods_id}",
            'env_version' => $version, //要打开的小程序版本。正式版为 release，体验版为 trial，开发版为 develop
            'page'        => 'pages/goods/detail',
            'check_path'  => false
        ]);
        if (is_null(json_decode($fileStream))) {
            try {
                $img = imagecreatefromstring($fileStream);
                ob_start();
                imagepng($img);
                $resource = ob_get_clean();
            } catch (\Exception $e) {
                \think\Log::write($e->getMessage());
                $this->error("获取微信二维码失败！");
            }
        } else {
            $config = get_addon_config('shop');
            if ($config['wxapp']) {
                $localFile = ROOT_PATH . 'public' . $config['wxapp'];
                if (is_file($localFile)) {
                    $resource = file_get_contents($localFile);
                } else {
                    $resource = Http::get(cdnurl($config['wxapp'], true));
                }
            }
            if (config('app_debug')) {
                Log::write($fileStream);
            }
        }
        if (!$resource) {
            Log::write($fileStream);
            $this->error("获取二维码失败！");
        }
        $base64_data = base64_encode($resource);
        $base64_file = 'data:image/jpg;base64,' . $base64_data;
        $this->success('获取成功', $base64_file);
    }
}
