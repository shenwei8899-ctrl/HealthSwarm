
-- ----------------------------
-- Table structure for __PREFIX__shop_address
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_address`  (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '编号',
  `user_id` int(10) NULL DEFAULT NULL COMMENT '用户ID',
  `province_id` int(10) NULL DEFAULT NULL COMMENT '省id',
  `city_id` int(10) NULL DEFAULT NULL COMMENT '市id',
  `area_id` int(10) NULL DEFAULT NULL COMMENT '区域ID',
  `receiver` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '收货人',
  `mobile` varchar(20) CHARACTER SET utf8mb4 NULL DEFAULT NULL,
  `address` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '地址详情',
  `zipcode` varchar(60) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '邮编',
  `usednums` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '使用次数',
  `createtime` bigint(16) UNSIGNED NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) UNSIGNED NULL DEFAULT NULL COMMENT '更新时间',
  `deletetime` bigint(16) UNSIGNED NULL DEFAULT NULL COMMENT '删除时间',
  `isdefault` tinyint(1) UNSIGNED NULL DEFAULT 0 COMMENT '是否默认',
  `status` varchar(30) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `user_id`(`user_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '收货地址';

-- ----------------------------
-- Table structure for __PREFIX__shop_area
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_area` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `pid` int(10) DEFAULT NULL COMMENT '父ID',
  `level` tinyint(1) DEFAULT '0' COMMENT '等级',
  `name` varchar(100) DEFAULT '' COMMENT '名称',
  `pinyin` varchar(100) DEFAULT '' COMMENT '拼音',
  `py` varchar(50) DEFAULT '' COMMENT '拼音前缀',
  `adcode` varchar(50) DEFAULT '' COMMENT '唯一ID',
  `zipcode` varchar(50) DEFAULT '' COMMENT '邮编',
  `lng` varchar(30) DEFAULT NULL COMMENT '经度',
  `lat` varchar(30) DEFAULT NULL COMMENT '纬度',
  `status` enum('normal','hidden') DEFAULT 'normal' COMMENT '状态',
  PRIMARY KEY (`id`),
  KEY `pid` (`pid`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT='地区表';

-- ----------------------------
-- Table structure for __PREFIX__shop_block
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_block`  (
  `id` smallint(8) UNSIGNED NOT NULL AUTO_INCREMENT,
  `type` varchar(30) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '类型',
  `name` varchar(50) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '名称',
  `title` varchar(100) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '标题',
  `image` varchar(255) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '图片',
  `url` varchar(255) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '链接',
  `content` mediumtext CHARACTER SET utf8mb4 NULL COMMENT '内容',
  `parsetpl` tinyint(1) unsigned DEFAULT '0' COMMENT '解析模板标签',
  `weigh` int(10) NOT NULL DEFAULT 0 COMMENT '权重',
  `begintime` bigint(16) DEFAULT NULL COMMENT '开始时间',
  `endtime` bigint(16) DEFAULT NULL COMMENT '结束时间',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  `status` enum('normal','hidden') CHARACTER SET utf8mb4 NOT NULL DEFAULT 'normal' COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '区块表';

-- ----------------------------
-- Table structure for __PREFIX__shop_carts
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_carts`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增长id',
  `user_id` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '用户id',
  `goods_id` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '商品id',
  `goods_sku_id` int(10) NULL DEFAULT 0 COMMENT '商品属性id',
  `sceneval` tinyint(1) NULL DEFAULT 1 COMMENT '类型:1=加入购物车,2=立即购买',
  `nums` smallint(6) UNSIGNED NOT NULL DEFAULT 0 COMMENT '商品购买件数',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `user_id`(`user_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '购物车';

-- ----------------------------
-- Table structure for __PREFIX__shop_category
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_category`  (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `type` tinyint(1) DEFAULT NULL,
  `pid` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '父ID',
  `isnav` tinyint(1) DEFAULT '0',
  `name` varchar(30) NOT NULL DEFAULT '',
  `nickname` varchar(50) NOT NULL DEFAULT '',
  `outlink` varchar(255) DEFAULT NULL,
  `flag` set('hot','index','recommend') NOT NULL DEFAULT '',
  `image` varchar(255) NOT NULL DEFAULT '' COMMENT '图片',
  `keywords` varchar(255) NOT NULL DEFAULT '' COMMENT '关键字',
  `description` varchar(255) NOT NULL DEFAULT '' COMMENT '描述',
  `icon` varchar(50) NOT NULL DEFAULT '' COMMENT '图标',
  `diyname` varchar(30) NOT NULL DEFAULT '' COMMENT '自定义名称',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  `weigh` int(10) NOT NULL DEFAULT '0' COMMENT '权重',
  `status` varchar(30) NOT NULL DEFAULT '' COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `weigh`(`weigh`, `id`) USING BTREE,
  INDEX `pid`(`pid`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '分类表';

-- ----------------------------
-- Table structure for __PREFIX__shop_collect
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_collect`  (
  `id` int(10) NOT NULL AUTO_INCREMENT,
  `user_id` int(10) NULL DEFAULT NULL COMMENT '用户id',
  `goods_id` int(10) NULL DEFAULT NULL COMMENT '商品id',
  `status` tinyint(1) NULL DEFAULT 1 COMMENT '状态:0=已取消,1=已收藏',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '收藏表';

-- ----------------------------
-- Table structure for __PREFIX__shop_comment
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_comment`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `pid` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '父评论ID',
  `user_id` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '会员ID',
  `order_id` int(10) NULL DEFAULT NULL COMMENT '订单ID',
  `goods_id` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '关联ID',
  `star` tinyint(1) UNSIGNED NOT NULL DEFAULT 0 COMMENT '评分',
  `content` text CHARACTER SET utf8mb4 NULL COMMENT '内容',
  `comments` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '评论数',
  `images` varchar(1500) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '评论图片',
  `ip` varchar(50) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT 'IP',
  `useragent` varchar(255) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT 'User Agent',
  `subscribe` tinyint(1) UNSIGNED NOT NULL DEFAULT 0 COMMENT '订阅',
  `createtime` bigint(16) UNSIGNED DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) UNSIGNED DEFAULT NULL COMMENT '更新时间',
  `status` enum('normal','hidden') CHARACTER SET utf8mb4 NOT NULL DEFAULT 'normal' COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `post_id`(`goods_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '评论表';


-- ----------------------------
-- Table structure for __PREFIX__shop_freight
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_freight`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '名称',
  `type` tinyint(1) NULL DEFAULT NULL COMMENT '是否包邮:1=按件计,2=按重计',
  `weigh` int(10) NOT NULL DEFAULT 0 COMMENT '权重',
  `switch` tinyint(1) NOT NULL DEFAULT 0 COMMENT '开关',
  `num` decimal(10, 2) NULL DEFAULT 0 COMMENT '默认件/重',
  `price` decimal(10, 2) NULL DEFAULT 0.00 COMMENT '默认价格',
  `continue_num` decimal(10, 2) NULL DEFAULT 0 COMMENT '续件/续重',
  `continue_price` decimal(10, 2) NULL DEFAULT 0.00 COMMENT '续费',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '运费模板';

-- ----------------------------
-- Table structure for __PREFIX__shop_freight_items
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_freight_items`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `freight_id` int(10) NULL DEFAULT NULL COMMENT '模板id',
  `first_num` decimal(10, 2) NULL DEFAULT 0 COMMENT '首件/首重',
  `first_price` decimal(10, 2) NULL DEFAULT 0.00 COMMENT '首费',
  `continue_num` decimal(10, 2) NULL DEFAULT 0 COMMENT '续件/续重',
  `continue_price` decimal(10, 2) NULL DEFAULT 0.00 COMMENT '续费',
  `area_ids` mediumtext COMMENT '地区ids',
  `type` tinyint(1) NOT NULL DEFAULT 0 COMMENT '指定地区包邮:0=否,1=按件,2=按金额',
  `postage_area_ids` mediumtext COMMENT '包邮地区ids',
  `postage_num` decimal(10, 2) NULL DEFAULT 0 COMMENT '满几件包邮',
  `postage_price` decimal(10, 2) NULL DEFAULT 0.00 COMMENT '满金额包邮',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '运费模板字表';

-- ----------------------------
-- Table structure for __PREFIX__shop_goods
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_goods`  (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT COMMENT '商品id',
  `category_id` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '类别ID',
  `subtitle` varchar(255) DEFAULT NULL COMMENT '子标题',
  `attribute_ids` varchar(255) DEFAULT NULL COMMENT '属性值ids',
  `brand_id` int(10) DEFAULT NULL COMMENT '品牌ID',
  `goods_sn` varchar(100) NOT NULL DEFAULT '' COMMENT '货号',
  `title` varchar(100) NOT NULL DEFAULT '' COMMENT '商品标题',
  `keywords` varchar(100) DEFAULT '' COMMENT '关键字',
  `description` varchar(255) DEFAULT '' COMMENT '描述',
  `marketprice` decimal(10,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '市场售价',
  `price` decimal(10,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '商城售价',
  `stocks` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '库存',
  `sales` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '销量',
  `guarantee_ids` varchar(50) DEFAULT NULL COMMENT '服务保障',
  `star` int(10) DEFAULT '0' COMMENT '星级',
  `views` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '浏览次数',
  `comments` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '评论数',
  `shares` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '分享次数',
  `image` varchar(255) DEFAULT '' COMMENT '缩略图',
  `images` varchar(1500) DEFAULT '' COMMENT '预览图',
  `content` mediumtext COMMENT '商品内容详情',
  `corner` varchar(10) DEFAULT NULL COMMENT '角标文字',
  `flag` set('recommend','hot','new','best','index') DEFAULT '' COMMENT '标志',
  `spectype` tinyint(1) DEFAULT '0' COMMENT '规格类型:0=单规格,1=多规格',
  `weight` decimal(10,2) DEFAULT '0.00' COMMENT '重量(kg)',
  `isvirtual` tinyint(1) unsigned NOT NULL DEFAULT '0' COMMENT '虚拟物品',
  `freight_id` int(10) DEFAULT NULL COMMENT '运费模板ID',
  `weigh` int(10) NOT NULL DEFAULT '1' COMMENT '排序',
  `createtime` bigint(16) unsigned DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) unsigned DEFAULT NULL COMMENT '更新时间',
  `deletetime` bigint(16) DEFAULT NULL COMMENT '删除时间',
  `status` enum('normal','hidden','soldout') NOT NULL DEFAULT 'normal' COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `category_id`(`category_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '商品表';

-- ----------------------------
-- Table structure for __PREFIX__shop_goods_sku
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_goods_sku`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `goods_id` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '商品ID',
  `goods_sn` varchar(100) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '货号',
  `sku_id` varchar(100) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT 'SKU',
  `image` varchar(255) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '规格封面',
  `price` decimal(10, 2) UNSIGNED NOT NULL DEFAULT 0.00 COMMENT '价格',
  `marketprice` decimal(10, 2) UNSIGNED NOT NULL DEFAULT 0.00 COMMENT '市场价',
  `stocks` int(10) NOT NULL DEFAULT 0 COMMENT '库存数量',
  `sales` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '销量',
  `weigh` int(10) NOT NULL DEFAULT 0 COMMENT '权重',
  `createtime` bigint(16) UNSIGNED DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) UNSIGNED DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '商品SKU表';

-- ----------------------------
-- Table structure for __PREFIX__shop_goods_sku_spec
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_goods_sku_spec`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `goods_id` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '商品ID',
  `spec_id` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '规格ID',
  `spec_value_id` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '规格值ID',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4;

-- ----------------------------
-- Table structure for __PREFIX__shop_menu
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_menu`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `pid` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '父ID',
  `name` varchar(50) CHARACTER SET utf8mb4  NULL DEFAULT '' COMMENT '名称',
  `url` varchar(255) CHARACTER SET utf8mb4  NULL DEFAULT '' COMMENT '链接',
  `weigh` int(10) NOT NULL DEFAULT 0 COMMENT '排序',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  `status` varchar(30) CHARACTER SET utf8mb4  NULL DEFAULT '' COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '菜单表';

-- ----------------------------
-- Table structure for __PREFIX__shop_navigation
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_navigation`  (
  `id` int(10) NOT NULL AUTO_INCREMENT,
  `name` varchar(50) CHARACTER SET utf8mb4  NULL DEFAULT NULL COMMENT '名称',
  `size` int(2) NULL DEFAULT 60 COMMENT '图标大小',
  `image` varchar(255) CHARACTER SET utf8mb4  NULL DEFAULT NULL COMMENT '图片',
  `path` varchar(255) CHARACTER SET utf8mb4  NULL DEFAULT NULL COMMENT '路径',
  `switch` tinyint(1) NOT NULL DEFAULT 0 COMMENT '开关',
  `weigh` int(10) NOT NULL DEFAULT 0 COMMENT '权重',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '导航配置';

-- ----------------------------
-- Table structure for __PREFIX__shop_order
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_order`  (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT COMMENT '自增ID',
  `order_sn` varchar(50) NOT NULL DEFAULT '' COMMENT ' 订单号,唯一',
  `user_id` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '用户id,',
  `address_id` int(10) unsigned DEFAULT NULL COMMENT '收款地址ID',
  `province_id` int(10) NULL DEFAULT NULL COMMENT '省id',
  `city_id` int(10) NULL DEFAULT NULL COMMENT '市id',
  `area_id` int(10) NULL DEFAULT NULL COMMENT '区域ID',
  `user_coupon_id` int(10) DEFAULT NULL COMMENT '优惠券记录ID',
  `openid` varchar(100) DEFAULT NULL COMMENT 'Openid',
  `receiver` varchar(60) NOT NULL DEFAULT '' COMMENT '收货人的姓名',
  `address` varchar(255) NOT NULL DEFAULT '' COMMENT '收货人的地址',
  `zipcode` varchar(60) DEFAULT '' COMMENT '收货人的邮编',
  `mobile` varchar(60) DEFAULT '' COMMENT '收货人的手机',
  `amount` decimal(10,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '订单总金额',
  `discount` decimal(10,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '优惠金额',
  `shippingfee` decimal(10,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '配送费用',
  `goodsprice` decimal(10,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '商品总费用',
  `saleamount` decimal(10,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '应付款金额',
  `payamount` decimal(10,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '实际付款金额',
  `paytype` varchar(100) NOT NULL DEFAULT '' COMMENT '用户选择的支付方式名称',
  `method` varchar(50) CHARACTER SET utf8mb4 DEFAULT NULL COMMENT '支付方法',
  `transactionid` varchar(100) DEFAULT NULL COMMENT '交易流水号',
  `expressname` varchar(50) DEFAULT '' COMMENT '快递名称',
  `expressno` varchar(50) DEFAULT '' COMMENT '快递单号',
  `createtime` bigint(16) unsigned DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) unsigned DEFAULT NULL COMMENT '更新时间',
  `expiretime` bigint(16) unsigned DEFAULT NULL COMMENT '过期时间',
  `paytime` bigint(16) unsigned DEFAULT NULL COMMENT '支付时间',
  `refundtime` bigint(16) unsigned DEFAULT NULL COMMENT '退货时间',
  `shippingtime` bigint(16) unsigned DEFAULT NULL COMMENT '配送时间',
  `receivetime` bigint(16) unsigned DEFAULT NULL COMMENT '收货时间',
  `canceltime` bigint(16) unsigned DEFAULT NULL COMMENT '取消时间',
  `deletetime` bigint(16) unsigned DEFAULT NULL COMMENT '删除时间',
  `orderstate` tinyint(1) unsigned NOT NULL DEFAULT '0' COMMENT '订单状态:0=正常,1=已取消,2=已失效,3=已完成,4=退货退款中',
  `shippingstate` tinyint(1) unsigned NOT NULL DEFAULT '0' COMMENT '配送状态:0=未发货,1=已发货,2=已收货',
  `paystate` tinyint(1) unsigned NOT NULL DEFAULT '0' COMMENT '支付状态:0=未付款,1=已付款',
  `memo` varchar(255) DEFAULT NULL COMMENT '备注',
  `status` enum('normal','hidden') NOT NULL DEFAULT 'normal' COMMENT '状态:normal=正常,hidden=隐藏',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `order_sn`(`order_sn`) USING BTREE,
  KEY `user_id`(`user_id`),
  KEY `orderstate`(`orderstate`),
  KEY `paytime` (`paytime`),
  KEY `createtime` (`createtime`),
  KEY `province_city_area` (`province_id`,`city_id`,`area_id`)
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '订单表';



CREATE TABLE IF NOT EXISTS `__PREFIX__shop_order_aftersales` (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '编号',
  `order_id` int(10) DEFAULT NULL COMMENT '订单id',
  `order_goods_id` int(10) DEFAULT NULL COMMENT '订单商品id',
  `user_id` int(10) unsigned DEFAULT NULL COMMENT '用户ID',
  `type` tinyint(1) unsigned NOT NULL DEFAULT '1' COMMENT '售后类型:1=仅退款,2=退款退货',
  `nums` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '数量',
  `realprice` decimal(10,2) NULL DEFAULT '0.00' COMMENT '商品实付金额',
  `shippingfee` tinyint(1) NULL DEFAULT 0 COMMENT '邮费',
  `refund` decimal(10,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '退款金额',
  `reason` varchar(255) NOT NULL COMMENT '退款原因',
  `images` varchar(2500) DEFAULT NULL COMMENT '补充图片',
  `mark` varchar(255) DEFAULT NULL COMMENT '卖家备注',
  `status` tinyint(1) unsigned DEFAULT '1' COMMENT '状态:1=待审核,2=审核通过,3=审核拒绝',
  `expressname` varchar(50) CHARACTER SET utf8 DEFAULT '' COMMENT '快递名称',
  `expressno` varchar(50) CHARACTER SET utf8 DEFAULT '' COMMENT '快递单号',
  `createtime` bigint(16) unsigned NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) unsigned NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT='退货单表';

-- ----------------------------
-- Table structure for __PREFIX__shop_order_action
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_order_action`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '流水号',
  `order_sn` varchar(50) CHARACTER SET utf8mb4 NOT NULL DEFAULT '0' COMMENT '订单编号',
  `operator` varchar(30) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '操作人',
  `memo` varchar(255) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '操作记录(备注)',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '操作时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `order_id`(`order_sn`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '订单操作记录表';

-- ----------------------------
-- Table structure for __PREFIX__shop_order_goods
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_order_goods`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键id',
  `order_sn` varchar(50) CHARACTER SET utf8mb4 NOT NULL DEFAULT '0' COMMENT '订单号',
  `goods_sn` varchar(100) NOT NULL DEFAULT '' COMMENT '货号',
  `goods_id` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '商品id',
  `goods_sku_id` int(10) NULL DEFAULT NULL COMMENT 'skuid',
  `title` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '物品标题',
  `nums` smallint(6) UNSIGNED NOT NULL DEFAULT 1 COMMENT '购买商品数量',
  `marketprice` decimal(10, 2) UNSIGNED NOT NULL DEFAULT 0.00 COMMENT '市场价',
  `price` decimal(10, 2) UNSIGNED NOT NULL DEFAULT 0.00 COMMENT '商城售价',
  `realprice` decimal(10,2) DEFAULT 0.00 COMMENT '实付金额',
  `salestate` tinyint(1) DEFAULT '0' COMMENT '销售状态:0=待申请,1=已申请,2=退款中,3=退货中,4=已退款,5=已退货退款,6=已拒绝',
  `commentstate` tinyint(1) unsigned DEFAULT '0' COMMENT '评论状态:0=未评论,1=已评论',
  `attrdata` varchar(1500) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '属性信息',
  `image` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '图片',
  `weight` decimal(10,2) DEFAULT '0.00' COMMENT '重量(kg)',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `order_id`(`order_sn`) USING BTREE,
  INDEX `goods_id`(`goods_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '订单商品表';

-- ----------------------------
-- Table structure for __PREFIX__shop_spec
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_spec`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 NOT NULL DEFAULT '' COMMENT '名称',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '商品规格表';

-- ----------------------------
-- Table structure for __PREFIX__shop_spec_value
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_spec_value`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `spec_id` int(10) NOT NULL COMMENT '规格ID',
  `value` varchar(255) CHARACTER SET utf8mb4 NOT NULL COMMENT '规格值',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '规格数据表';


-- ----------------------------
-- Table structure for __PREFIX__shop_electronics_order
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_electronics_order`  (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '主键id',
  `shipper_id` int(10) NULL DEFAULT NULL COMMENT '快递公司id',
  `paytype` tinyint(1) NULL DEFAULT 1 COMMENT '运费支付方式:1=现付,2=到付,3=月结,4=第三方付(仅SF支持)',
  `customer_name` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '线下网点客户号',
  `customer_pwd` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '线下网点密码',
  `send_site` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '网点名称',
  `send_staff` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '网点快递员',
  `month_code` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '月结编号',
  `is_notice` tinyint(1) NULL DEFAULT 0 COMMENT '是否通知揽件:0=通知揽件,1=不通知揽件',
  `is_return_temp` tinyint(1) NULL DEFAULT NULL COMMENT '是否返回电子面单模板:0=不返回,1=返回',
  `is_send_message` tinyint(1) NULL DEFAULT NULL COMMENT '是否需要短信提醒:0=否,1=是',
  `template_size` varchar(10) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '模板尺寸',
  `operate_require` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '签回单操作要求(如：签名、盖章、身份证复印件等)',
  `logistic_code` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '快递单号(仅宅急送可用)',
  `start_date` int(10) NULL DEFAULT NULL COMMENT '上门揽件开始时间',
  `end_date` int(10) NULL DEFAULT NULL COMMENT '上门揽件结束时间',
  `remark` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '备注',
  `exp_type` tinyint(1) NULL DEFAULT NULL COMMENT '快递类型:1=标准快件',
  `is_return_sign_bill` tinyint(1) NULL DEFAULT NULL COMMENT '是否要签回单:0=否,1=是',
  `company` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '发件人公司',
  `province_name` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '发件人省',
  `city_name` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '发件人市',
  `exp_area_name` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '发件人区',
  `address` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '发件人详细地址',
  `name` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '发件人姓名',
  `tel` varchar(20) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '发件人电话',
  `mobile` varchar(15) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '发件人手机号码',
  `post_code` varchar(15) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '发件地邮编',
  `title` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '自定义名称',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '电子面单';

-- ----------------------------
-- Table structure for __PREFIX__shop_shipper
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_shipper`  (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '主键',
  `name` varchar(120) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '快递名称',
  `shipper_code` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '快递公司编码',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 648 CHARACTER SET = utf8mb4 COMMENT = '快递公司';


-- ----------------------------
-- Table structure for __PREFIX__shop_order_electronics
-- ----------------------------
CREATE TABLE IF NOT EXISTS `__PREFIX__shop_order_electronics`  (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '主键id',
  `order_sn` varchar(50) CHARACTER SET utf8mb4  NULL DEFAULT NULL COMMENT '订单编号',
  `print_template` longtext CHARACTER SET utf8mb4  NULL COMMENT '模板',
  `kdn_order_code` varchar(100) CHARACTER SET utf8mb4  NULL DEFAULT NULL COMMENT 'KDNOrderCode',
  `logistic_code` varchar(50) CHARACTER SET utf8mb4  NULL DEFAULT NULL COMMENT '物流单号',
  `shipper_code` varchar(30) CHARACTER SET utf8mb4  NULL DEFAULT NULL COMMENT '快递编号',
  `order` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL,
  `customer_name` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '线下网点客户号',
  `customer_pwd` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '线下网点密码',
  `status` tinyint(1) NULL DEFAULT 0 COMMENT '状态:0=正常,1=已取消',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '订单电子面单记录';


-- ----------------------------
-- Table structure for __PREFIX__shop_sku_template
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_sku_template`  (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '主键id',
  `name` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '名称',
  `spec_names` varchar(150) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '规格名称',
  `spec_values` varchar(250) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '规格值名称',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '规格模板';


-- ----------------------------
-- Table structure for __PREFIX__shop_guarantee
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_guarantee`  (
  `id` int(10) NOT NULL AUTO_INCREMENT,
  `name` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '名称',
  `image` varchar(255) NOT NULL DEFAULT '' COMMENT '图片',
  `intro` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '服务保障',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  `status` enum('normal','hidden') CHARACTER SET utf8mb4 NOT NULL DEFAULT 'normal' COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '服务保障';

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_page` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `category_id` int(10) NOT NULL DEFAULT '0' COMMENT '分类ID',
  `admin_id` int(10) unsigned DEFAULT '0' COMMENT '管理员ID',
  `type` varchar(50) DEFAULT '' COMMENT '类型',
  `title` varchar(50) DEFAULT '' COMMENT '标题',
  `seotitle` varchar(255) DEFAULT '' COMMENT 'SEO标题',
  `keywords` varchar(255) DEFAULT '' COMMENT '关键字',
  `description` varchar(255) DEFAULT '' COMMENT '描述',
  `flag` varchar(100) DEFAULT '' COMMENT '标志',
  `image` varchar(255) DEFAULT '' COMMENT '头像',
  `content` longtext COMMENT '内容',
  `icon` varchar(50) DEFAULT '' COMMENT '图标',
  `views` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '点击',
  `likes` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '点赞',
  `dislikes` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '点踩',
  `diyname` varchar(100) DEFAULT '' COMMENT '自定义',
  `showtpl` varchar(50) DEFAULT '' COMMENT '视图模板',
  `parsetpl` tinyint(1) unsigned DEFAULT '0' COMMENT '解析模板标签',
  `createtime` bigint(16) DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) DEFAULT NULL COMMENT '更新时间',
  `deletetime` bigint(16) DEFAULT NULL COMMENT '删除时间',
  `weigh` int(10) NOT NULL DEFAULT '0' COMMENT '权重',
  `status` varchar(30) DEFAULT '' COMMENT '状态',
  PRIMARY KEY (`id`),
  KEY `diyname` (`diyname`),
  KEY `type` (`type`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT='单页表';


-- ----------------------------
-- Table structure for __PREFIX__shop_brand
-- ----------------------------
CREATE TABLE IF NOT EXISTS `__PREFIX__shop_brand`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键id',
  `name` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '名称',
  `image` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT '' COMMENT '图片',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  `weigh` int(10) NOT NULL DEFAULT 0 COMMENT '权重',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '品牌管理';

-- ----------------------------
-- Table structure for __PREFIX__shop_search_log
-- ----------------------------
CREATE TABLE `__PREFIX__shop_search_log` (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '主键id',
  `nums` int(10) DEFAULT NULL,
  `keywords` varchar(100) DEFAULT NULL,
  `createtime` bigint(16) DEFAULT NULL COMMENT '创建时间',
  `status` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4;


INSERT INTO `__PREFIX__shop_block` VALUES (1, '焦点图', 'indexfocus', '首页焦点图1', 'https://images.unsplash.com/photo-1606787366850-de6330128bfc?ixid=MnwxMjA3fDF8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8&ixlib=rb-1.2.1&auto=format&fit=crop&w=1500&q=80', '/', '<h2 class=\"animated bounceInDown\">\r\n	畅享你的水果下午茶\r\n</h2>\r\n<p class=\"animated slideInRight\">\r\n	无限量应季水果供应<br />\r\n精选水果菠萝橙子牛油果猕猴桃\r\n</p>', 0, 2, NULL, NULL, 1624603959, 1625108648, 'normal');
INSERT INTO `__PREFIX__shop_block` VALUES (2, '焦点图', 'indexfocus', '首页焦点图2', 'https://images.unsplash.com/photo-1504754524776-8f4f37790ca0?ixid=MnwxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8&ixlib=rb-1.2.1&auto=format&fit=crop&w=2100&q=80', '/', '<h2 class=\"animated bounceInDown\">\r\n	美味点心大集合\r\n</h2>\r\n<p class=\"animated slideInRight\">\r\n	家庭自制美味小点心<br />\r\n在家也能吃到蓝莓咖啡蓝莓鸡蛋\r\n</p>', 0, 1, NULL, NULL, 1624603959, 1625108843, 'normal');
INSERT INTO `__PREFIX__shop_block` VALUES (3, 'uniapp焦点图', 'uniappfocus', 'uniapp焦点图1', '/assets/addons/shop/img/swiper1.jpg', '/pages/category/index', '', 0, 4, NULL, NULL, 1625556492, 1625556891, 'normal');
INSERT INTO `__PREFIX__shop_block` VALUES (4, 'uniapp焦点图', 'uniappfocus', 'uniapp焦点图2', '/assets/addons/shop/img/swiper2.jpg', '/pages/goods/goods', '', 0, 5, NULL, NULL, 1625556518, 1625556882, 'normal');

INSERT INTO `__PREFIX__shop_electronics_order` VALUES (1, 2, 1, '', '', '', '', '', 0, 1, 0, '130', '签名', '', 0, 0, '', 1, 0, '公司名称', '广东省', '深圳市', '罗湖区', '建设路', '阿良', '18333333333', '18333333333', '518000', '百世快递电子面单', 1623392763, 1625560310);

INSERT INTO `__PREFIX__shop_freight` VALUES (1, '按件', 1, 1, 1, 1.00, 12.00, 1.00, 5.00, 1623309170, 1625558947);
INSERT INTO `__PREFIX__shop_freight` VALUES (2, '按重量', 2, 2, 1, 1.00, 12.00, 1.00, 5.00, 1623309192, 1625558936);

INSERT INTO `__PREFIX__shop_guarantee` VALUES (1, '放心购', '','7天无理由退货', 1624071780, 1624071780, 'normal');
INSERT INTO `__PREFIX__shop_guarantee` VALUES (2, '在线客服','','7*24小时在线客服', 1624071795, 1624071795, 'normal');

INSERT INTO `__PREFIX__shop_menu` VALUES (1, 0, '首页', '/shop', 5, 1625024797, 1625024797, 'normal');
INSERT INTO `__PREFIX__shop_menu` VALUES (2, 0, '会员中心', '/index/user', 4, 1625024797, 1625045590, 'normal');
INSERT INTO `__PREFIX__shop_menu` VALUES (3, 0, '外部链接', 'javascript:', 3, 1625024797, 1625120775, 'normal');
INSERT INTO `__PREFIX__shop_menu` VALUES (4, 3, '京东商城', 'https://www.jd.com', 2, 1625024797, 1625024845, 'normal');
INSERT INTO `__PREFIX__shop_menu` VALUES (5, 3, '淘宝', 'https://www.taobao.com', 1, 1625024797, 1625024774, 'normal');
INSERT INTO `__PREFIX__shop_menu` VALUES (6, 0, '关于我们', '/shop/p/aboutus', 1, 1625024797, 1625024774, 'normal');
INSERT INTO `__PREFIX__shop_menu` VALUES (7, 0, '优惠券', '/shop/coupon', 1, 1625024797, 1625024774, 'normal');
INSERT INTO `__PREFIX__shop_menu` VALUES (8, 0, '积分兑换', '/shop/exchange', 1, 1625024797, 1625024774, 'normal');

INSERT INTO `__PREFIX__shop_navigation` VALUES (1, '我的评论', 60, '/assets/addons/shop/navigation/comment.svg', '/pages/remark/comment', 1, 13, 1609402165, 1625555529);
INSERT INTO `__PREFIX__shop_navigation` VALUES (2, '商品列表', 60, '/assets/addons/shop/navigation/commodity.svg', '/pages/goods/goods', 1, 2, 1609402235, 1625555571);
INSERT INTO `__PREFIX__shop_navigation` VALUES (3, '优惠券', 60, '/assets/addons/shop/navigation/coupon.svg', '/pages/coupon/coupon', 1, 2, 1609402235, 1625555584);
INSERT INTO `__PREFIX__shop_navigation` VALUES (4, '单页文章', 60, '/assets/addons/shop/navigation/page-template.svg', '/pages/page/page?id=2', 1, 2, 1609402235, 1625555594);
INSERT INTO `__PREFIX__shop_navigation` VALUES (5, '积分兑换', 60, '/assets/addons/shop/navigation/exchange.svg', '/pages/score/exchange', 1, 2, 1609402235, 1625555608);
INSERT INTO `__PREFIX__shop_navigation` VALUES (6, '订单列表', 60, '/assets/addons/shop/navigation/order.svg', '/pages/order/list', 1, 2, 1609402235, 1625555614);
INSERT INTO `__PREFIX__shop_navigation` VALUES (7, '外部链接', 60, '/assets/addons/shop/navigation/copy-link.svg', 'https://www.baidu.com', 1, 2, 1609402235, 1625555630);
INSERT INTO `__PREFIX__shop_navigation` VALUES (8, '签到排行', 60, '/assets/addons/shop/navigation/local.svg', '/pages/signin/ranking', 1, 2, 1609402235, 1625555641);
INSERT INTO `__PREFIX__shop_navigation` VALUES (9, '测试导航', 60, '/assets/addons/shop/navigation/application-one.svg', '/pages/signin/signin', 1, 1, 1623308082, 1625555654);

INSERT INTO `__PREFIX__shop_page` VALUES (1, 0, 0, 'page', '关于我们', '', '', '', '', '', '<p>\r\n	关于我们的内容\r\n</p>', '', 1, 225, 0, 'aboutus', 'page', 0, 1508933935, 1625557767, NULL, 1, 'normal');
INSERT INTO `__PREFIX__shop_page` VALUES (2, 0, 0, 'page', '用户注册协议', '', '', '', '', '', '<p>\r\n	用户注册协议\r\n</p>', '', 1, 225, 0, 'agreement', 'page', 0, 1508933935, 1625557772, NULL, 1, 'normal');

INSERT INTO `__PREFIX__shop_shipper` VALUES (1, '顺丰速运', 'SF', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (2, '百世快递', 'HTKY', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (3, '中通快递', 'ZTO', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (4, '申通快递', 'STO', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (5, '圆通速递', 'YTO', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (6, '韵达速递', 'YD', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (7, '邮政快递包裹', 'YZPY', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (8, 'EMS', 'EMS', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (9, '天天快递', 'HHTT', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (10, '京东快递', 'JD', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (11, '优速快递', 'UC', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (12, '德邦快递', 'DBL', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (36, '百世快运', 'BTWL', 1623320171, 1623320171);
INSERT INTO `__PREFIX__shop_shipper` VALUES (135, '极兔速递', 'JTSD', 1623320171, 1623320171);


-- ----------------------------
-- 1.1.0 表结构变更
-- ----------------------------

ALTER TABLE `__PREFIX__shop_guarantee` ADD COLUMN `image` VARCHAR(255) NULL COMMENT '图片' AFTER `name`;
ALTER TABLE `__PREFIX__shop_address` ADD COLUMN `deletetime` bigint(16) NULL COMMENT '删除时间' AFTER `updatetime`;
ALTER TABLE `__PREFIX__shop_order` ADD COLUMN `goodsprice` decimal(10, 2) UNSIGNED NOT NULL DEFAULT 0 COMMENT '商品总费用' AFTER `shippingfee`;
ALTER TABLE `__PREFIX__shop_order` DROP INDEX `order_status`,DROP INDEX `shipping_status`,DROP INDEX `pay_status`;
ALTER TABLE `__PREFIX__shop_order` ADD INDEX `orderstate`(`orderstate`),ADD INDEX `paytime`(`paytime`),ADD INDEX `createtime`(`createtime`),ADD INDEX `province_city_area`(`province_id`, `city_id`, `area_id`);
ALTER TABLE `__PREFIX__shop_order_aftersales` ADD COLUMN `nums` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '数量' AFTER `type`,ADD COLUMN `realprice` decimal(10, 2) NULL DEFAULT 0 COMMENT '商品实付金额' AFTER `nums`,ADD COLUMN `shippingfee` decimal(10,2) NULL DEFAULT '0.00' COMMENT '邮费' AFTER `realprice`;

-- ----------------------------
-- Table structure for __PREFIX__shop_attribute
-- ----------------------------
CREATE TABLE IF NOT EXISTS `__PREFIX__shop_attribute`  (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `category_id` int(10) NULL DEFAULT NULL COMMENT '分类ID',
  `is_search` tinyint(1) NULL DEFAULT 0 COMMENT '是否可搜索:0=否,1=是',
  `is_must` tinyint(1) NULL DEFAULT 0 COMMENT '是否必填:0=可选,1=必选',
  `type` enum('radio','checkbox') CHARACTER SET utf8mb4 NULL DEFAULT 'radio' COMMENT '类型:radio=单选,checkbox=多选',
  `name` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '名称',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '商品属性';

-- ----------------------------
-- Table structure for __PREFIX__shop_attribute_value
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_attribute_value`  (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `attribute_id` int(10) NULL DEFAULT NULL COMMENT '属性ID',
  `name` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '名称',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '商品属性值';

-- ----------------------------
-- Table structure for __PREFIX__shop_coupon
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_coupon`  (
  `id` int(10) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '名称',
  `condition_ids` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '条件ids',
  `result` tinyint(2) NULL DEFAULT NULL COMMENT '结果:0=订单满xx打x折,1=订单满xx减x元',
  `result_data` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '结果补充',
  `mode` enum('fixation','dates') CHARACTER SET utf8mb4 NULL DEFAULT 'dates' COMMENT '有效期模式:fixation=固定天数,dates=日期范围',
  `is_private` enum('yes','no') CHARACTER SET utf8mb4 NULL DEFAULT 'no' COMMENT '是否私有:yes=是,no=否',
  `is_open` tinyint(1) NULL DEFAULT 1 COMMENT '是否开启:0=关闭,1=开启',
  `allow_num` int(10) NULL DEFAULT 1 COMMENT '一人可领取数量',
  `give_num` int(10) NULL DEFAULT 1 COMMENT '发放总量',
  `received_num` int(10) NULL DEFAULT 0 COMMENT '已经领取数量',
  `receive_times` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '领取时间段',
  `begintime` bigint(16) NULL DEFAULT NULL COMMENT '领取开始时间',
  `endtime` bigint(16) NULL DEFAULT NULL COMMENT '领取结束时间',
  `use_times` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '使用时间段',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '优惠券表';

-- ----------------------------
-- Table structure for __PREFIX__shop_coupon_condition
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_coupon_condition`  (
  `id` int(10) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '条件名称',
  `type` tinyint(2) NULL DEFAULT NULL COMMENT '类型:1=指定商品,2=新用户专享,3=老用户专享',
  `content` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '条件补充内容',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '优惠券条件';

-- ----------------------------
-- Table structure for __PREFIX__shop_exchange
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_exchange`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `type` enum('virtual','reality') CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '类型:virtual=虚拟物品,reality=实物商品',
  `title` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '标题',
  `description` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '描述',
  `content` mediumtext CHARACTER SET utf8mb4 COMMENT '商品内容详情',
  `image` varchar(225) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '图片',
  `score` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '积分',
  `stocks` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '库存',
  `sales` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '销量',
  `weigh` int(10) NOT NULL DEFAULT 0 COMMENT '权重',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  `status` enum('normal','hidden') CHARACTER SET utf8mb4 NULL DEFAULT 'normal' COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '积分兑换';

-- ----------------------------
-- Table structure for __PREFIX__shop_exchange_order
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_exchange_order`  (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '会员ID',
  `exchange_id` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '兑换ID',
  `type` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '类型',
  `orderid` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '订单号',
  `nums` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '数量',
  `score` int(10) UNSIGNED NULL DEFAULT 0 COMMENT '兑换积分',
  `receiver` varchar(30) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '收件人',
  `mobile` varchar(30) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '电话',
  `address` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '地址',
  `memo` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '备注',
  `reason` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '原因',
  `expressname` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '快递名称',
  `expressno` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '快递单号',
  `ip` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT 'IP',
  `useragent` varchar(255) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT 'UserAgent',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  `status` enum('created','inprogress','rejected','delivered','completed') CHARACTER SET utf8mb4 NULL DEFAULT 'created' COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '积分兑换订单';

-- ----------------------------
-- Table structure for __PREFIX__shop_goods_attr
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_goods_attr`  (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `attribute_id` int(10) NULL DEFAULT NULL COMMENT '属性id',
  `value_id` int(10) NULL DEFAULT NULL COMMENT '属性值id',
  `goods_id` int(11) NULL DEFAULT NULL COMMENT '商品id',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '添加时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `attribute` (`attribute_id`,`value_id`, `goods_id`)
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '商品属性';

-- ----------------------------
-- Table structure for __PREFIX__shop_subscribe_log
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_subscribe_log`  (
  `id` int(10) NOT NULL AUTO_INCREMENT,
  `user_id` int(10) NULL DEFAULT NULL COMMENT '用户id',
  `order_sn` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '订单id',
  `tpl_id` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '模板id',
  `status` tinyint(1) NULL DEFAULT 0 COMMENT '状态:0=未发送,1=已发送',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '订阅记录';

-- ----------------------------
-- Table structure for __PREFIX__shop_template_msg
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_template_msg`  (
  `id` int(10) NOT NULL AUTO_INCREMENT,
  `type` tinyint(1) NULL DEFAULT 1 COMMENT '类型:1=公众号,2=小程序,3=邮箱通知,4=短信通知',
  `event` tinyint(1) NOT NULL DEFAULT 0 COMMENT '事件:0=付款成功,1=发货通知,2=退款通知,3=售后拒绝,4=兑换通知',
  `title` varchar(150) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '标题',
  `tpl_id` varchar(50) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '模板ID',
  `content` varchar(500) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '内容',
  `extend` longtext CHARACTER SET utf8mb4 NOT NULL COMMENT '扩展属性',
  `page` varchar(100) CHARACTER SET utf8mb4 NULL DEFAULT NULL COMMENT '页面路径',
  `switch` tinyint(1) NOT NULL DEFAULT 0 COMMENT '开关',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '模板消息';

-- ----------------------------
-- Table structure for __PREFIX__shop_user_coupon
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_user_coupon`  (
  `id` int(10) NOT NULL AUTO_INCREMENT,
  `coupon_id` int(10) NULL DEFAULT NULL COMMENT '优惠券id',
  `user_id` int(10) NULL DEFAULT NULL COMMENT '用户id(领取)',
  `is_used` tinyint(1) NULL DEFAULT 1 COMMENT '是否使用:1=未使用,2=已使用',
  `begin_time` bigint(16) NULL DEFAULT NULL COMMENT '开始时间',
  `expire_time` bigint(16) NULL DEFAULT NULL COMMENT '失效时间',
  `createtime` bigint(16) NULL DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COMMENT = '优惠券领取记录表';


-- ----------------------------
-- Table structure for __PREFIX__shop_card
-- ----------------------------

CREATE TABLE IF NOT EXISTS `__PREFIX__shop_card` (
  `id` int(10) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `type` tinyint(1) DEFAULT '0' COMMENT '类型:0=商品,1=优惠券',
  `title` varchar(100) DEFAULT NULL COMMENT '标题',
  `content` longtext COMMENT '内容',
  `createtime` bigint(16) DEFAULT NULL COMMENT '创建时间',
  `updatetime` bigint(16) DEFAULT NULL COMMENT '更新时间',
  `status` enum('normal','hidden') NOT NULL DEFAULT 'normal' COMMENT '状态',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT='商品卡片模板';

-- ----------------------------
-- 1.1.1 表结构变更
-- ----------------------------
ALTER TABLE `__PREFIX__shop_order_goods` ADD COLUMN `realprice` decimal(10, 2) NULL DEFAULT 0.00 COMMENT '实付金额' AFTER `price`;
ALTER TABLE `__PREFIX__shop_goods_attr` ADD INDEX `attribute` (`attribute_id`, `value_id`, `goods_id`);

-- ----------------------------
-- 1.1.4 表结构变更
-- ----------------------------
ALTER TABLE `__PREFIX__shop_freight_items` MODIFY COLUMN `area_ids` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '地区ids' AFTER `continue_price`;
ALTER TABLE `__PREFIX__shop_freight_items` MODIFY COLUMN `postage_area_ids` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '包邮地区ids' AFTER `type`;

-- ----------------------------
-- 1.1.6 表结构变更
-- ----------------------------
ALTER TABLE `__PREFIX__shop_freight` CHANGE COLUMN `nums` `num` decimal(10, 2) NULL DEFAULT 0 COMMENT '默认件/重' AFTER `switch`;
ALTER TABLE `__PREFIX__shop_freight` MODIFY COLUMN `price` decimal(10, 2) NULL DEFAULT 0 COMMENT '默认价格' AFTER `num`;
ALTER TABLE `__PREFIX__shop_freight` MODIFY COLUMN `continue_num` decimal(10, 2) NULL DEFAULT 0 COMMENT '续件/续重' AFTER `price`;
ALTER TABLE `__PREFIX__shop_freight` MODIFY COLUMN `continue_price` decimal(10, 2) NULL DEFAULT 0 COMMENT '续费' AFTER `continue_num`;
ALTER TABLE `__PREFIX__shop_freight_items` MODIFY COLUMN `first_num` decimal(10, 2) NULL DEFAULT 0 COMMENT '首件/首重' AFTER `freight_id`;
ALTER TABLE `__PREFIX__shop_freight_items` MODIFY COLUMN `first_price` decimal(10, 2) NULL DEFAULT 0 COMMENT '首费' AFTER `first_num`;
ALTER TABLE `__PREFIX__shop_freight_items` MODIFY COLUMN `continue_num` decimal(10, 2) NULL DEFAULT 0 COMMENT '续件/续重' AFTER `first_price`;
ALTER TABLE `__PREFIX__shop_freight_items` MODIFY COLUMN `continue_price` decimal(10, 2) NULL DEFAULT 0 COMMENT '续费' AFTER `continue_num`;
ALTER TABLE `__PREFIX__shop_freight_items` MODIFY COLUMN `postage_num` decimal(10, 2) NULL DEFAULT 0 COMMENT '满几件包邮' AFTER `postage_area_ids`;
ALTER TABLE `__PREFIX__shop_freight_items` MODIFY COLUMN `postage_price` decimal(10, 2) NULL DEFAULT 0 COMMENT '满金额包邮' AFTER `postage_num`;
ALTER TABLE `__PREFIX__shop_goods` MODIFY COLUMN `flag` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '标志' AFTER `corner`;

-- ----------------------------
-- 1.1.8 表结构变更
-- ----------------------------
ALTER TABLE `__PREFIX__shop_order` ADD COLUMN `openid` varchar(100) NULL DEFAULT '' COMMENT 'Openid' AFTER `user_coupon_id`;
ALTER TABLE `__PREFIX__shop_block` CHANGE `weigh` `weigh` INT(10) NOT NULL DEFAULT 0 COMMENT '权重';
ALTER TABLE `__PREFIX__shop_goods_sku` CHANGE `weigh` `weigh` INT(10)  UNSIGNED  NOT NULL DEFAULT 0 COMMENT '权重';


--
-- 1.2.9 表结构变更
--
ALTER TABLE `__PREFIX__shop_order_aftersales` CHANGE `shippingfee` `shippingfee` DECIMAL(10,2)  NULL  DEFAULT 0  COMMENT '邮费';