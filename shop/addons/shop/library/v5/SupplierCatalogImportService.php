<?php

namespace addons\shop\library\v5;

use PhpOffice\PhpSpreadsheet\Cell\Coordinate;
use PhpOffice\PhpSpreadsheet\IOFactory;
use PhpOffice\PhpSpreadsheet\Spreadsheet;
use PhpOffice\PhpSpreadsheet\Style\Fill;
use PhpOffice\PhpSpreadsheet\Worksheet\Drawing;
use PhpOffice\PhpSpreadsheet\Worksheet\MemoryDrawing;
use PhpOffice\PhpSpreadsheet\Writer\Xlsx;
use think\Db;

/** Supplier-facing catalog import. One row is one supplier SKU. */
class SupplierCatalogImportService
{
    const SHEET = '供应商商品目录';
    // These names are deliberately shared with the product and SKU screens.
    // A supplier row represents one supplier-provided SKU, not one product.
    const HEADERS = ['供应商编码*','供应商名称*','供应商商品编码','供应商SKU编码*','商品名称*','商品分类*','销售类型*','规格名称*','规格值*','供货价(元)*','售价(元)*','供应商可供库存*','安全库存','净含量*','净含量单位*','食材标准名称*','商品图片*','最小起订量','交付天数','备注'];

    public function createTemplate()
    {
        $book = new Spreadsheet();
        $sheet = $book->getActiveSheet();
        $sheet->setTitle(self::SHEET);
        foreach (self::HEADERS as $i => $header) $sheet->setCellValue(Coordinate::stringFromColumnIndex($i + 1) . '1', $header);
        $last = Coordinate::stringFromColumnIndex(count(self::HEADERS));
        $sheet->getStyle('A1:' . $last . '1')->applyFromArray(['font'=>['bold'=>true,'color'=>['rgb'=>'FFFFFF']], 'fill'=>['fillType'=>Fill::FILL_SOLID,'startColor'=>['rgb'=>'287D5A']]]);
        $sheet->freezePane('A2'); $sheet->setAutoFilter('A1:' . $last . '1');
        for ($i=1; $i<=count(self::HEADERS); $i++) $sheet->getColumnDimension(Coordinate::stringFromColumnIndex($i))->setWidth($i <= 6 ? 20 : 16);
        $sheet->getColumnDimension('Q')->setWidth(22);
        $sheet->setCellValue('A2', 'SUP001'); $sheet->setCellValue('B2', '示例供应商'); $sheet->setCellValue('C2', 'BROCCOLI'); $sheet->setCellValue('D2', 'BROCCOLI-500G');
        $sheet->setCellValue('E2', '西兰花'); $sheet->setCellValue('F2', '蔬菜类'); $sheet->setCellValue('G2', '普通商品'); $sheet->setCellValue('H2', '包装规格'); $sheet->setCellValue('I2', '500克');
        $sheet->setCellValue('J2', '6.50'); $sheet->setCellValue('K2', '9.90'); $sheet->setCellValue('L2', '100'); $sheet->setCellValue('M2', '20'); $sheet->setCellValue('N2', '500'); $sheet->setCellValue('O2', '克'); $sheet->setCellValue('P2', '西兰花'); $sheet->setCellValue('R2', '1'); $sheet->setCellValue('S2', '1');
        $sheet->getRowDimension(2)->setRowHeight(90);
        $this->addInstructionsSheet($book);
        $path=tempnam(sys_get_temp_dir(),'supplier_catalog_'); $xlsx=$path.'.xlsx'; @unlink($path); (new Xlsx($book))->save($xlsx); $book->disconnectWorksheets(); return $xlsx;
    }

    /** Give suppliers and operators one unambiguous field dictionary. */
    protected function addInstructionsSheet(Spreadsheet $book)
    {
        $sheet = $book->createSheet();
        $sheet->setTitle('字段说明');
        $sheet->fromArray(['字段','是否必填','填写责任','导入后位置或作用','填写规则'], null, 'A1');
        $rows = [
            ['供应商编码*','是','供应商','供应商档案','同一供应商保持唯一且固定'],
            ['供应商名称*','是','供应商','供应商档案','企业或门店对外名称'],
            ['供应商商品编码','否','供应商','商品管理 > 供应商供货信息','供应商自己的商品编码'],
            ['供应商SKU编码*','是','供应商','商品管理 > 供应商供货信息','同一供应商内不可重复'],
            ['商品名称*','是','供应商','商品管理 > 商品名称','同一分类下同名商品会合并到同一商品'],
            ['商品分类*','是','供应商','商品管理 > 商品分类','填写分类名称，例如“蔬菜类”'],
            ['销售类型*','是','供应商','商品管理 > 销售类型','只能填“普通商品”“固定食材包”或“服务商品”'],
            ['规格名称*','是','供应商','商品管理 > 商品详情 > SKU规格','例如“包装规格”'],
            ['规格值*','是','供应商','商品管理 > 商品详情 > SKU规格','例如“500克”；同一商品内不可重复'],
            ['供货价(元)*','是','供应商','商品管理 > 供应商供货信息','大于或等于 0 的数字'],
            ['售价(元)*','是','供应商','商品管理 > 商品详情 > SKU售价','大于或等于 0 的数字'],
            ['供应商可供库存*','是','供应商','商品管理 > 供应商供货信息','大于或等于 0 的整数；平台总库存由所有供应商库存汇总'],
            ['安全库存','否','供应商','商品管理 > 商品详情 > SKU安全库存','空白时按 0 处理'],
            ['净含量*','是','供应商','商品管理 > 商品详情 > SKU净含量','大于或等于 0 的数字'],
            ['净含量单位*','是','供应商','商品管理 > 商品详情 > SKU净含量','只能填“克”“千克”“毫升”“件”或“包”'],
            ['食材标准名称*','是','供应商','商品与食材库 > 食材标准及商品食材关联','用于营养计算与 Agent 选品，例如“西兰花”'],
            ['商品图片*','是','供应商','商品管理 > 商品图片','在该列对应单元格直接插入 JPG、PNG、WEBP 或 GIF 图片，不填写链接；每行必须有图片'],
            ['最小起订量','否','供应商','商品管理 > 供应商供货信息','空白时按 1 处理'],
            ['交付天数','否','供应商','商品管理 > 供应商供货信息','从确认采购至可交付的天数，空白时按 0 处理'],
            ['备注','否','供应商','商品管理 > 供应商供货信息','补充供货限制或说明'],
        ];
        $sheet->fromArray($rows, null, 'A2');
        $sheet->getStyle('A1:E1')->applyFromArray(['font'=>['bold'=>true,'color'=>['rgb'=>'FFFFFF']], 'fill'=>['fillType'=>Fill::FILL_SOLID,'startColor'=>['rgb'=>'287D5A']]]);
        $sheet->freezePane('A2'); $sheet->setAutoFilter('A1:E' . (count($rows) + 1));
        foreach (['A'=>24,'B'=>12,'C'=>14,'D'=>38,'E'=>58] as $column=>$width) $sheet->getColumnDimension($column)->setWidth($width);
        $sheet->getStyle('A1:E' . (count($rows) + 1))->getAlignment()->setWrapText(true);
        for ($row=2; $row<=count($rows)+1; $row++) $sheet->getRowDimension($row)->setRowHeight(32);
        $sheet->setCellValue('A24', '图片插入方法：在“供应商商品目录”工作表的“商品图片*”列中，选中对应商品行，然后在 Excel/WPS 使用“插入图片”功能插入本地图片。图片须放在对应单元格区域内，支持 JPG、PNG、WEBP、GIF，单张不超过 5MB。');
        $sheet->mergeCells('A24:E24'); $sheet->getStyle('A24')->getAlignment()->setWrapText(true); $sheet->getRowDimension(24)->setRowHeight(52);
    }

    public function preview($filePath, $name, $adminId)
    {
        $hash=hash_file('sha256',$filePath); $existing=Db::name('shop_master_data_import')->where('file_hash',$hash)->find(); if($existing) return $this->result($existing,true);
        $book=IOFactory::load($filePath); $sheet=$book->getSheetByName(self::SHEET); if (!$sheet) throw new DomainException('缺少工作表：'.self::SHEET, 40070, 400);
        $headers=[]; foreach (self::HEADERS as $i=>$unused) $headers[]=trim((string)$sheet->getCellByColumnAndRow($i+1,1)->getFormattedValue());
        if ($headers!==self::HEADERS) {
            $legacyHeaders=self::HEADERS; $legacyHeaders[16]='商品图片链接';
            if ($headers===$legacyHeaders) throw new DomainException('您上传的是旧版模板，第17列仍为“商品图片链接”。请下载“嵌入图片版”模板，在“商品图片*”列直接插入图片后再上传。',40071,400);
            throw new DomainException('表头不匹配。请下载“嵌入图片版”模板，并保持第17列“商品图片*”、工作表名称和首行字段顺序不变。',40071,400);
        }
        [$imageRows,$imageErrors]=$this->extractEmbeddedImages($sheet,$hash);
        $rows=[]; $seen=[]; $max=min(10001,(int)$sheet->getHighestDataRow());
        for($r=2;$r<=$max;$r++) { $raw=[];$has=false; foreach(self::HEADERS as $i=>$header){$v=trim((string)$sheet->getCellByColumnAndRow($i+1,$r)->getFormattedValue());$raw[$header]=$v;if($v!=='')$has=true;} if(!$has)continue;
            $data=$this->normalize($raw); $data['image']=$imageRows[$r]??''; $key=$data['supplier_code'].'|'.$data['supplier_sku_code']; $errors=array_merge($this->validate($data),$imageErrors[$r]??[]); if(isset($seen[$key]))$errors[]='同一供应商的SKU编码重复，首次出现于第 '.$seen[$key].' 行'; else $seen[$key]=$r;
            $rows[]=['sheet_name'=>self::SHEET,'row_no'=>$r,'business_key'=>$key,'data'=>$data,'status'=>$errors?'invalid':'valid','action'=>$errors?'pending':'insert','error_message'=>implode('；',$errors)];
        }
        $book->disconnectWorksheets(); if(!$rows) throw new DomainException('模板中没有可导入的数据',40072,400);
        $invalid=count(array_filter($rows,function($row){return $row['status']==='invalid';})); $now=time(); $batchId=Db::name('shop_master_data_import')->insertGetId(['batch_sn'=>Identifiers::make('supplier_import'),'original_name'=>mb_substr($name,0,255),'file_hash'=>$hash,'status'=>$invalid?'invalid':'validated','total_rows'=>count($rows),'valid_rows'=>count($rows)-$invalid,'invalid_rows'=>$invalid,'error_count'=>$invalid,'summary_json'=>json_encode(['import_type'=>'supplier_catalog','supplier_sku_count'=>count($rows)],JSON_UNESCAPED_UNICODE),'created_by'=>(int)$adminId,'createtime'=>$now,'updatetime'=>$now]);
        foreach($rows as $row) Db::name('shop_master_data_import_row')->insert(['batch_id'=>$batchId,'sheet_name'=>$row['sheet_name'],'row_no'=>$row['row_no'],'business_key'=>$row['business_key'],'action'=>$row['action'],'status'=>$row['status'],'error_message'=>$row['error_message'],'data_json'=>json_encode($row['data'],JSON_UNESCAPED_UNICODE),'createtime'=>$now,'updatetime'=>$now]);
        return $this->result(Db::name('shop_master_data_import')->where('id',$batchId)->find());
    }

    public function confirm($batchId,$adminId)
    {
        Db::startTrans(); try { $batch=Db::name('shop_master_data_import')->where('id',(int)$batchId)->lock(true)->find(); if(!$batch)throw new DomainException('导入批次不存在',40460,404); $summary=json_decode($batch['summary_json'],true)?:[]; if(($summary['import_type']??'')!=='supplier_catalog')throw new DomainException('不是供应商商品导入批次',40073,400); if($batch['status']!=='validated')throw new DomainException('仅预检通过的批次可以确认写入',40074,400);
            $inserted=0;$updated=0; $rows=Db::name('shop_master_data_import_row')->where('batch_id',$batch['id'])->order('row_no','asc')->select(); foreach($rows as $row){$result=$this->ingest(json_decode($row['data_json'],true)?:[]); $result==='inserted'?$inserted++:$updated++; Db::name('shop_master_data_import_row')->where('id',$row['id'])->update(['action'=>$result,'status'=>'valid','error_message'=>'已写入','updatetime'=>time()]);}
            Db::name('shop_master_data_import')->where('id',$batch['id'])->update(['status'=>'imported','inserted_count'=>$inserted,'updated_count'=>$updated,'confirmed_by'=>(int)$adminId,'imported_at'=>time(),'updatetime'=>time()]);
            (new CatalogService())->touchVersion('supplier_catalog_import', $batch['batch_sn'], '供应商商品目录导入');
            Db::commit(); return $this->result(Db::name('shop_master_data_import')->where('id',$batch['id'])->find());
        } catch(\Exception $e){Db::rollback();throw $e;}
    }

    protected function ingest(array $d)
    {
        $now=time(); $supplier=Db::name('shop_supplier')->where('supplier_code',$d['supplier_code'])->find(); if(!$supplier){$supplierId=(int)Db::name('shop_supplier')->insertGetId(['supplier_code'=>$d['supplier_code'],'name'=>$d['supplier_name'],'company_name'=>$d['supplier_name'],'status'=>'normal','version'=>1,'createtime'=>$now,'updatetime'=>$now]);}else{$supplierId=(int)$supplier['id'];Db::name('shop_supplier')->where('id',$supplierId)->update(['name'=>$d['supplier_name'],'company_name'=>$d['supplier_name'],'updatetime'=>$now]);}
        $category=Db::name('shop_category')->where('name',$d['category_name'])->find(); if(!$category){$code='CAT-'.strtoupper(substr(hash('sha256',$d['category_name']),0,12));$categoryId=(int)Db::name('shop_category')->insertGetId(['name'=>$d['category_name'],'business_category_code'=>$code,'agent_visible'=>1,'status'=>'normal','createtime'=>$now,'updatetime'=>$now]);}else{$categoryId=(int)$category['id'];$code=$category['business_category_code'];Db::name('shop_category')->where('id',$categoryId)->update(['agent_visible'=>1,'status'=>'normal','updatetime'=>$now]);}
        $goods=Db::name('shop_goods')->where('category_id',$categoryId)->where('title',$d['title'])->find(); if(!$goods){$goodsId=(int)Db::name('shop_goods')->insertGetId(['category_id'=>$categoryId,'business_category_code'=>$code,'goods_sn'=>'AUTO-'.strtoupper(substr(hash('sha256',$d['category_name'].'|'.$d['title']),0,14)),'title'=>$d['title'],'price'=>$d['retail_price'],'marketprice'=>$d['retail_price'],'stocks'=>0,'image'=>$d['image'],'status'=>'normal','sale_type'=>$d['sale_type'],'agent_visible'=>1,'catalog_status'=>'published','data_completeness'=>'partial','createtime'=>$now,'updatetime'=>$now]);}else{$goodsId=(int)$goods['id'];Db::name('shop_goods')->where('id',$goodsId)->update(['business_category_code'=>$code,'price'=>$d['retail_price'],'marketprice'=>$d['retail_price'],'image'=>$d['image']?:$goods['image'],'status'=>'normal','agent_visible'=>1,'catalog_status'=>'published','updatetime'=>$now]);}
        $spec=Db::name('shop_spec')->where('name',$d['spec_name'])->find();if(!$spec){$specId=(int)Db::name('shop_spec')->insertGetId(['name'=>$d['spec_name'],'createtime'=>$now,'updatetime'=>$now]);}else $specId=(int)$spec['id']; $specValue=Db::name('shop_spec_value')->where('spec_id',$specId)->where('value',$d['spec_value'])->find();if(!$specValue)Db::name('shop_spec_value')->insert(['spec_id'=>$specId,'value'=>$d['spec_value'],'createtime'=>$now,'updatetime'=>$now]);
        $sku=Db::name('shop_goods_sku')->where('goods_id',$goodsId)->where('sku_id',$d['spec_value'])->find();$isNew=!$sku; if(!$sku){$skuId=(int)Db::name('shop_goods_sku')->insertGetId(['goods_id'=>$goodsId,'goods_sn'=>'PSKU-'.strtoupper(substr(hash('sha256',$goodsId.'|'.$d['spec_value']),0,14)),'sku_code'=>'PSKU-'.strtoupper(substr(hash('sha256',$goodsId.'|'.$d['spec_value']),0,14)),'sku_id'=>$d['spec_value'],'image'=>$d['image'],'price'=>$d['retail_price'],'marketprice'=>$d['retail_price'],'stocks'=>$d['stock_quantity'],'safety_stock'=>$d['safety_stock'],'net_content_value'=>$d['net_content_value'],'net_content_unit'=>$d['net_content_unit'],'stock_updated_at'=>$now,'createtime'=>$now,'updatetime'=>$now]);}else{$skuId=(int)$sku['id'];Db::name('shop_goods_sku')->where('id',$skuId)->update(['price'=>$d['retail_price'],'marketprice'=>$d['retail_price'],'stocks'=>$d['stock_quantity'],'safety_stock'=>$d['safety_stock'],'net_content_value'=>$d['net_content_value'],'net_content_unit'=>$d['net_content_unit'],'stock_updated_at'=>$now,'updatetime'=>$now]);}
        $supply=Db::name('shop_supplier_sku')->where('supplier_id',$supplierId)->where('supplier_sku_code',$d['supplier_sku_code'])->find();$supplyData=['sku_id'=>$skuId,'supplier_goods_code'=>$d['supplier_goods_code'],'supplier_sku_name'=>$d['title'].' '.$d['spec_value'],'purchase_price_cent'=>(int)round($d['supply_price']*100),'minimum_order_quantity'=>$d['min_order_qty'],'delivery_days'=>$d['delivery_days'],'source_note'=>$d['source_note'],'stock_quantity'=>$d['stock_quantity'],'stock_status'=>$d['stock_quantity']>0?'sufficient':'out','stock_updated_at'=>$now,'status'=>'normal','updatetime'=>$now];if($supply){Db::name('shop_supplier_sku')->where('id',$supply['id'])->update($supplyData);}else{Db::name('shop_supplier_sku')->insert(array_merge($supplyData,['supplier_id'=>$supplierId,'supplier_sku_code'=>$d['supplier_sku_code'],'priority'=>0,'version'=>1,'createtime'=>$now]));}
        // Platform stock is the combined available quantity across all active
        // suppliers mapped to this platform SKU, not the last supplier row.
        $platformStock=(int)Db::name('shop_supplier_sku')->where('sku_id',$skuId)->where('status','normal')->sum('stock_quantity');
        Db::name('shop_goods_sku')->where('id',$skuId)->update(['stocks'=>$platformStock,'stock_updated_at'=>$now,'updatetime'=>$now]);
        $ingredient=Db::name('shop_ingredient')->where('name',$d['ingredient_name'])->find();if(!$ingredient){$ingredientId=(int)Db::name('shop_ingredient')->insertGetId(['ingredient_code'=>'ING-'.strtoupper(substr(hash('sha256',$d['ingredient_name']),0,12)),'name'=>$d['ingredient_name'],'default_unit'=>$d['net_content_unit'],'status'=>'normal','version'=>1,'createtime'=>$now,'updatetime'=>$now]);}else $ingredientId=(int)$ingredient['id']; $map=Db::name('shop_ingredient_sku_map')->where('ingredient_id',$ingredientId)->where('sku_id',$skuId)->find();if(!$map)Db::name('shop_ingredient_sku_map')->insert(['ingredient_id'=>$ingredientId,'goods_id'=>$goodsId,'sku_id'=>$skuId,'role'=>'primary','net_value'=>$d['net_content_value'],'net_unit'=>$d['net_content_unit'],'convert_ratio'=>1,'loss_rate'=>0,'priority'=>0,'review_status'=>'pending','status'=>'normal','version'=>1,'createtime'=>$now,'updatetime'=>$now]);
        return $isNew?'inserted':'updated';
    }

    /** Extract images anchored in the 商品图片 column and keep a stable upload URL for confirm-import. */
    protected function extractEmbeddedImages($sheet,$fileHash)
    {
        $images=[];$errors=[];$imageColumn=Coordinate::stringFromColumnIndex(array_search('商品图片*',self::HEADERS,true)+1);
        foreach($sheet->getDrawingCollection() as $drawing){
            [$column,$row]=Coordinate::coordinateFromString($drawing->getCoordinates()); if($column!==$imageColumn)continue;
            try{$bytes=$this->drawingBytes($drawing); if($bytes==='')throw new \RuntimeException('图片内容为空'); if(strlen($bytes)>5*1024*1024)throw new \RuntimeException('图片不能超过5MB'); $mime=(new \finfo(FILEINFO_MIME_TYPE))->buffer($bytes); $extensions=['image/jpeg'=>'jpg','image/png'=>'png','image/gif'=>'gif','image/webp'=>'webp']; if(!isset($extensions[$mime]))throw new \RuntimeException('仅支持JPG、PNG、WEBP或GIF图片');
                $relative='/uploads/supplier_catalog/'.substr($fileHash,0,16).'_'.$row.'_'.substr(hash('sha256',$bytes),0,12).'.'.$extensions[$mime]; $directory=ROOT_PATH.'public'.DS.'uploads'.DS.'supplier_catalog'; if(!is_dir($directory)&&!mkdir($directory,0755,true)&&!is_dir($directory))throw new \RuntimeException('图片目录创建失败'); if(file_put_contents(ROOT_PATH.'public'.$relative,$bytes)===false)throw new \RuntimeException('图片保存失败'); $images[(int)$row]=$relative;
            }catch(\Exception $e){$errors[(int)$row][]='商品图片无效：'.$e->getMessage();}
        }
        return [$images,$errors];
    }

    protected function drawingBytes($drawing)
    {
        if($drawing instanceof Drawing){$bytes=@file_get_contents($drawing->getPath()); return $bytes===false?'':$bytes;}
        if($drawing instanceof MemoryDrawing){ob_start();call_user_func($drawing->getRenderingFunction(),$drawing->getImageResource());return (string)ob_get_clean();}
        return '';
    }

    protected function normalize(array $r){$unit=['克'=>'g','千克'=>'kg','毫升'=>'ml','件'=>'piece','包'=>'pack'];$sale=['普通商品'=>'normal','固定食材包'=>'bundle','服务商品'=>'service'];return ['supplier_code'=>trim($r['供应商编码*']),'supplier_name'=>trim($r['供应商名称*']),'supplier_goods_code'=>trim($r['供应商商品编码']),'supplier_sku_code'=>trim($r['供应商SKU编码*']),'title'=>trim($r['商品名称*']),'category_name'=>trim($r['商品分类*']),'sale_type'=>$sale[trim($r['销售类型*'])]??'','spec_name'=>trim($r['规格名称*']),'spec_value'=>trim($r['规格值*']),'supply_price'=>$this->number($r['供货价(元)*']),'retail_price'=>$this->number($r['售价(元)*']),'stock_quantity'=>$this->integer($r['供应商可供库存*']),'safety_stock'=>$this->integer($r['安全库存']?:0),'net_content_value'=>$this->number($r['净含量*']),'net_content_unit'=>$unit[trim($r['净含量单位*'])]??'','ingredient_name'=>trim($r['食材标准名称*']),'image'=>'','min_order_qty'=>max(1,$this->integer($r['最小起订量']?:1)),'delivery_days'=>max(0,$this->integer($r['交付天数']?:0)),'source_note'=>trim($r['备注'])];}
    protected function validate(array $d){$errors=[];foreach(['supplier_code'=>'供应商编码','supplier_name'=>'供应商名称','supplier_sku_code'=>'供应商SKU编码','title'=>'商品名称','category_name'=>'商品分类','spec_name'=>'规格名称','spec_value'=>'规格值','ingredient_name'=>'食材标准名称','image'=>'商品图片'] as $k=>$n)if($d[$k]==='')$errors[]=$n.'不能为空';if($d['sale_type']==='')$errors[]='销售类型只能填写“普通商品”“固定食材包”或“服务商品”';if($d['net_content_unit']==='')$errors[]='净含量单位只能填写“克”“千克”“毫升”“件”或“包”';foreach(['supply_price'=>'供货价','retail_price'=>'售价','stock_quantity'=>'供应商可供库存','net_content_value'=>'净含量'] as $k=>$n)if($d[$k]===null||$d[$k]<0)$errors[]=$n.'必须是大于等于0的数字';if($d['safety_stock']<0)$errors[]='安全库存不能为负数';return $errors;}
    protected function number($v){return trim((string)$v)===''?null:(is_numeric($v)?(float)$v:null);} protected function integer($v){return is_numeric($v)?(int)$v:0;}
    protected function result(array $b,$duplicate=false){return ['batch_id'=>(int)$b['id'],'batch_sn'=>$b['batch_sn'],'status'=>$b['status'],'total_rows'=>(int)$b['total_rows'],'valid_rows'=>(int)$b['valid_rows'],'invalid_rows'=>(int)$b['invalid_rows'],'inserted_count'=>(int)$b['inserted_count'],'updated_count'=>(int)$b['updated_count'],'rows'=>Db::name('shop_master_data_import_row')->where('batch_id',$b['id'])->order('row_no','asc')->select(),'duplicate'=>$duplicate];}
}
