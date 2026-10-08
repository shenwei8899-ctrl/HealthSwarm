SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();

-- Detach products before replacing the legacy demo-store category tree.
UPDATE fa_shop_goods
SET category_id=0,attribute_ids=NULL,updatetime=@now;

DELETE FROM fa_shop_goods_attr;
DELETE FROM fa_shop_attribute_value;
DELETE FROM fa_shop_attribute;
DELETE FROM fa_shop_category;

ALTER TABLE fa_shop_goods_attr AUTO_INCREMENT=1;
ALTER TABLE fa_shop_attribute_value AUTO_INCREMENT=1;
ALTER TABLE fa_shop_attribute AUTO_INCREMENT=1;
ALTER TABLE fa_shop_category AUTO_INCREMENT=1;

INSERT INTO fa_shop_category
(`id`,`type`,`pid`,`isnav`,`name`,`nickname`,`outlink`,`flag`,`image`,`keywords`,`description`,`icon`,`diyname`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
(1,NULL,0,1,'新鲜食材','',NULL,'index','','蔬菜,肉禽,水产,水果','家庭日常采购的生鲜食材','','fresh-food',@now,@now,500,'normal'),
(2,NULL,0,1,'粮油主食','',NULL,'index','','谷物,米面,食用油','家庭常备粮油与主食','','staples',@now,@now,400,'normal'),
(3,NULL,0,1,'乳品豆制','',NULL,'index','','牛奶,乳品,豆制品','乳品与植物蛋白食品','','dairy-soy',@now,@now,300,'normal'),
(4,NULL,0,1,'调味辅料','',NULL,'','','调味品,香辛料','家庭烹饪调味与辅料','','seasoning',@now,@now,200,'normal'),
(5,NULL,0,1,'营养食材包','',NULL,'recommend','','早餐,家庭餐,食材包','按营养菜单组合的食材包','','meal-kits',@now,@now,100,'normal'),
(11,NULL,1,1,'蔬菜菌菇','',NULL,'','','叶菜,瓜果,菌菇','新鲜蔬菜与食用菌','','vegetables',@now,@now,490,'normal'),
(12,NULL,1,1,'水产海鲜','',NULL,'','','鱼,虾,贝类','鱼虾贝类等水产食材','','seafood',@now,@now,480,'normal'),
(13,NULL,1,1,'肉禽蛋','',NULL,'','','猪肉,牛肉,禽肉,蛋类','肉类、禽类与蛋类食材','','meat-eggs',@now,@now,470,'normal'),
(14,NULL,1,1,'新鲜水果','',NULL,'','','水果,鲜果','日常新鲜水果','','fruit',@now,@now,460,'normal'),
(15,NULL,1,1,'根茎薯类','',NULL,'','','土豆,红薯,山药','根茎类和薯类食材','','root-vegetables',@now,@now,450,'normal'),
(21,NULL,2,1,'谷物杂粮','',NULL,'','','燕麦,杂粮,全谷物','燕麦及杂粮等全谷物食品','','whole-grains',@now,@now,390,'normal'),
(22,NULL,2,1,'米面主食','',NULL,'','','大米,面粉,面食','大米、面粉及面食制品','','rice-noodles',@now,@now,380,'normal'),
(23,NULL,2,1,'食用油','',NULL,'','','植物油,食用油','家庭烹饪食用油','','cooking-oil',@now,@now,370,'normal'),
(31,NULL,3,1,'牛奶乳品','',NULL,'','','牛奶,酸奶,乳制品','牛奶及其他乳制品','','dairy',@now,@now,290,'normal'),
(32,NULL,3,1,'豆制品','',NULL,'','','豆腐,豆浆,大豆','豆腐等大豆制品','','soy-products',@now,@now,280,'normal'),
(41,NULL,4,1,'基础调味','',NULL,'','','盐,酱油,醋','盐、酱油、醋等基础调味品','','basic-seasoning',@now,@now,190,'normal'),
(42,NULL,4,1,'香辛料','',NULL,'','','葱,姜,蒜,香辛料','葱姜蒜及天然香辛料','','spices',@now,@now,180,'normal'),
(51,NULL,5,1,'早餐食材包','',NULL,'recommend','','早餐,食材包','按早餐菜单组合的食材包','','breakfast-kits',@now,@now,90,'normal'),
(52,NULL,5,1,'家庭餐食材包','',NULL,'recommend','','家庭餐,食材包','按家庭正餐菜单组合的食材包','','family-meal-kits',@now,@now,80,'normal');

UPDATE fa_shop_goods
SET category_id=CASE goods_sn
  WHEN 'MOCK_NUTRITION_OAT' THEN 21
  WHEN 'MOCK_NUTRITION_MILK' THEN 31
  WHEN 'MOCK_NUTRITION_EGG' THEN 13
  WHEN 'MOCK_NUTRITION_TOFU' THEN 32
  WHEN 'MOCK_NUTRITION_BANANA' THEN 14
  ELSE category_id
END,
updatetime=@now
WHERE goods_sn LIKE 'MOCK_NUTRITION_%';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_007','清空旧商城分类并重建家庭营养食材 MOCK 分类',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);
