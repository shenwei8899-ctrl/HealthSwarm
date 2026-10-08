<?php

namespace addons\shop\library\v5;

use PhpOffice\PhpSpreadsheet\Cell\Coordinate;
use PhpOffice\PhpSpreadsheet\IOFactory;
use PhpOffice\PhpSpreadsheet\Spreadsheet;
use PhpOffice\PhpSpreadsheet\Style\Fill;
use PhpOffice\PhpSpreadsheet\Style\NumberFormat;
use PhpOffice\PhpSpreadsheet\Writer\Xlsx;
use think\Db;

class MasterDataImportService
{
    protected $sheets = [
        '分类' => ['分类编码', '分类名称', '上级分类编码', 'Agent可见', '排序', '状态'],
        '商品' => ['商品编码', '商品名称', '商品分类', '销售类型', '副标题', '销售价', '市场价', '重量kg', '商品图片', 'Agent可见', '上架状态'],
        '规格' => ['规格名称'],
        '规格值' => ['规格名称', '规格值'],
        'SKU' => ['SKU编码', '商品编码', '规格名称', '规格值', '销售价', '市场价', '库存', '安全库存', '净含量', '净含量单位', '图片URL'],
        '食材' => ['食材编码', '食材名称', '类别编码', '默认单位', '说明', '状态'],
        '营养资料' => ['SKU编码', '基准类型', '基准值', '基准单位', '能量kcal', '蛋白质g', '脂肪g', '碳水g', '膳食纤维g', '钠mg', '资料来源', '来源版本', '审核状态', '状态'],
        '食材SKU映射' => ['食材编码', 'SKU编码', '角色', '可用净量', '单位', '换算率', '损耗率', '优先级', '审核状态', '状态'],
    ];

    public function createTemplate()
    {
        $book = new Spreadsheet();
        $book->removeSheetByIndex(0);
        foreach ($this->sheets as $sheetName => $headers) {
            $sheet = $book->createSheet();
            $sheet->setTitle($sheetName);
            foreach ($headers as $index => $header) {
                $cell = Coordinate::stringFromColumnIndex($index + 1) . '1';
                $sheet->setCellValueExplicit($cell, $header, \PhpOffice\PhpSpreadsheet\Cell\DataType::TYPE_STRING);
            }
            $lastColumn = Coordinate::stringFromColumnIndex(count($headers));
            $sheet->getStyle('A1:' . $lastColumn . '1')->applyFromArray([
                'font' => ['bold' => true, 'color' => ['rgb' => 'FFFFFF']],
                'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => '287D5A']],
                'alignment' => ['horizontal' => 'center', 'vertical' => 'center'],
            ]);
            $sheet->freezePane('A2');
            $sheet->setAutoFilter('A1:' . $lastColumn . '1');
            $sheet->getRowDimension(1)->setRowHeight(24);
            for ($column = 1; $column <= count($headers); $column++) {
                $letter = Coordinate::stringFromColumnIndex($column);
                $sheet->getColumnDimension($letter)->setWidth($column <= 3 ? 20 : 16);
                $sheet->getStyle($letter . '2:' . $letter . '2000')->getNumberFormat()->setFormatCode(NumberFormat::FORMAT_TEXT);
            }
            $this->addTemplateNotes($sheetName, $sheet);
        }
        $book->setActiveSheetIndex(0);
        $path = tempnam(sys_get_temp_dir(), 'healthflow_master_');
        $xlsxPath = $path . '.xlsx';
        @unlink($path);
        (new Xlsx($book))->save($xlsxPath);
        $book->disconnectWorksheets();
        return $xlsxPath;
    }

    public function preview($filePath, $originalName, $adminId)
    {
        if (!is_file($filePath)) {
            throw new DomainException('上传文件不存在', 40060, 400);
        }
        $extension = strtolower(pathinfo($originalName, PATHINFO_EXTENSION));
        if (!in_array($extension, ['xlsx', 'xls'], true)) {
            throw new DomainException('仅支持 .xlsx 或 .xls 文件', 40061, 400);
        }
        if (filesize($filePath) > 10 * 1024 * 1024) {
            throw new DomainException('导入文件不能超过 10MB', 40062, 400);
        }
        $hash = hash_file('sha256', $filePath);
        $existing = Db::name('shop_master_data_import')->where('file_hash', $hash)->find();
        if ($existing) {
            return $this->batchResult($existing, true);
        }

        try {
            $reader = IOFactory::createReaderForFile($filePath);
            $reader->setReadDataOnly(true);
            $book = $reader->load($filePath);
        } catch (\Exception $e) {
            throw new DomainException('Excel文件无法读取：' . $e->getMessage(), 40063, 400);
        }

        $rows = [];
        $sheetData = [];
        foreach ($this->sheets as $sheetName => $expectedHeaders) {
            $sheet = $book->getSheetByName($sheetName);
            if (!$sheet) {
                $rows[] = $this->resultRow($sheetName, 1, '', [], ['缺少工作表：' . $sheetName]);
                $sheetData[$sheetName] = [];
                continue;
            }
            $actualHeaders = [];
            for ($column = 1; $column <= count($expectedHeaders); $column++) {
                $actualHeaders[] = trim((string)$sheet->getCellByColumnAndRow($column, 1)->getFormattedValue());
            }
            if ($actualHeaders !== $expectedHeaders) {
                $rows[] = $this->resultRow($sheetName, 1, '', [], ['表头不匹配，请重新下载标准模板']);
                $sheetData[$sheetName] = [];
                continue;
            }
            $sheetRows = [];
            $highestRow = min(10001, (int)$sheet->getHighestDataRow());
            for ($rowNo = 2; $rowNo <= $highestRow; $rowNo++) {
                $values = [];
                $hasValue = false;
                foreach ($expectedHeaders as $column => $header) {
                    $value = $sheet->getCellByColumnAndRow($column + 1, $rowNo)->getFormattedValue();
                    $value = is_string($value) ? trim($value) : $value;
                    if ($value !== '' && $value !== null) {
                        $hasValue = true;
                    }
                    $values[$header] = $value;
                }
                if (!$hasValue) {
                    continue;
                }
                $normalized = $this->normalizeRow($sheetName, $values);
                $sheetRows[] = ['row_no' => $rowNo, 'data' => $normalized];
            }
            $sheetData[$sheetName] = $sheetRows;
        }
        $book->disconnectWorksheets();

        $known = $this->knownKeys($sheetData);
        foreach ($sheetData as $sheetName => $sheetRows) {
            $seen = [];
            foreach ($sheetRows as $item) {
                $data = $item['data'];
                $key = $this->businessKey($sheetName, $data);
                $errors = $this->validateRow($sheetName, $data, $known);
                if ($key !== '' && isset($seen[$key])) {
                    $errors[] = '业务编码在当前工作表内重复，首次出现于第 ' . $seen[$key] . ' 行';
                } elseif ($key !== '') {
                    $seen[$key] = $item['row_no'];
                }
                $action = $errors ? 'pending' : ($this->recordExists($sheetName, $data) ? 'update' : 'insert');
                $rows[] = $this->resultRow($sheetName, $item['row_no'], $key, $data, $errors, $action);
            }
        }
        if (!$rows) {
            $rows[] = $this->resultRow('商品', 2, '', [], ['模板中没有可导入的数据']);
        }

        $total = count($rows);
        $invalid = count(array_filter($rows, function ($row) { return $row['status'] === 'invalid'; }));
        $summary = $this->summarize($rows);
        $now = time();
        $batchId = Db::name('shop_master_data_import')->insertGetId([
            'batch_sn' => Identifiers::make('import'),
            'original_name' => mb_substr($originalName, 0, 255),
            'file_hash' => $hash,
            'status' => $invalid ? 'invalid' : 'validated',
            'total_rows' => $total,
            'valid_rows' => $total - $invalid,
            'invalid_rows' => $invalid,
            'error_count' => $invalid,
            'summary_json' => json_encode($summary, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_by' => (int)$adminId,
            'createtime' => $now,
            'updatetime' => $now,
        ]);
        $storedCount = 0;
        foreach (array_chunk($rows, 300) as $chunk) {
            $records = [];
            foreach ($chunk as $row) {
                $records[] = [
                    'batch_id' => $batchId,
                    'sheet_name' => $row['sheet_name'],
                    'row_no' => (int)$row['row_no'],
                    'business_key' => $row['business_key'],
                    'action' => $row['action'],
                    'status' => $row['status'],
                    'error_message' => $row['error_message'],
                    'data_json' => json_encode($row['data'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                    'createtime' => $now,
                    'updatetime' => $now,
                ];
            }
            foreach ($records as $record) {
                if (Db::name('shop_master_data_import_row')->insert($record) === false) {
                    throw new DomainException('导入明细写入失败，请检查 PostgreSQL 表结构和连接', 50060, 500);
                }
                $storedCount++;
            }
        }
        if ($storedCount !== $total) {
            Db::name('shop_master_data_import_row')->where('batch_id', $batchId)->delete();
            Db::name('shop_master_data_import')->where('id', $batchId)->update(['status' => 'failed', 'updatetime' => time()]);
            throw new DomainException('导入明细写入数量不一致，预检失败，请重新上传模板', 50061, 500);
        }
        return $this->batchResult(Db::name('shop_master_data_import')->where('id', $batchId)->find());
    }

    public function confirm($batchId, $adminId)
    {
        Db::startTrans();
        try {
            $batch = Db::name('shop_master_data_import')->where('id', (int)$batchId)->lock(true)->find();
            if (!$batch) {
                throw new DomainException('导入批次不存在', 40460, 404);
            }
            if ($batch['status'] === 'imported') {
                Db::commit();
                return $this->batchResult($batch);
            }
            if ($batch['status'] !== 'validated' || (int)$batch['invalid_rows'] > 0) {
                throw new DomainException('导入仍有校验错误，不能写入业务数据', 40960, 409);
            }
            $storedRows = Db::name('shop_master_data_import_row')->where('batch_id', $batch['id'])->order('id', 'asc')->select();
            if (!$storedRows || count($storedRows) !== (int)$batch['total_rows']) {
                throw new DomainException('导入明细不存在或数量不完整，不能确认导入，请重新预检', 40962, 409);
            }
            $grouped = [];
            foreach ($storedRows as $stored) {
                if ($stored['status'] !== 'valid') {
                    throw new DomainException('导入行状态异常，请重新预检', 40961, 409);
                }
                $grouped[$stored['sheet_name']][] = ['id' => $stored['id'], 'data' => json_decode($stored['data_json'], true) ?: []];
            }

            $inserted = 0;
            $updated = 0;
            foreach (isset($grouped['分类']) ? $grouped['分类'] : [] as $item) {
                $data = $item['data'];
                $category = [
                    'name' => $data['name'], 'business_category_code' => $data['category_code'],
                    'agent_visible' => $data['agent_visible'], 'weigh' => $data['weigh'],
                    'status' => $data['status'], 'updatetime' => time(), 'row_version' => 1,
                ];
                $action = $this->upsert('shop_category', ['business_category_code' => $data['category_code']], $category);
                $action === 'inserted' ? $inserted++ : $updated++;
                $this->markRow($item['id'], $action);
            }
            foreach (isset($grouped['分类']) ? $grouped['分类'] : [] as $item) {
                $data = $item['data'];
                $pid = 0;
                if ($data['parent_category_code'] !== '') {
                    $pid = (int)Db::name('shop_category')->where('business_category_code', $data['parent_category_code'])->value('id');
                }
                Db::name('shop_category')->where('business_category_code', $data['category_code'])->update(['pid' => $pid, 'updatetime' => time()]);
            }
            foreach (isset($grouped['规格']) ? $grouped['规格'] : [] as $item) {
                $data = $item['data'];
                $action = $this->upsert('shop_spec', ['name' => $data['name']], ['name' => $data['name'], 'updatetime' => time()]);
                $action === 'inserted' ? $inserted++ : $updated++;
                $this->markRow($item['id'], $action);
            }
            foreach (isset($grouped['规格值']) ? $grouped['规格值'] : [] as $item) {
                $data = $item['data'];
                $specId = (int)Db::name('shop_spec')->where('name', $data['spec_name'])->value('id');
                $action = $this->upsert('shop_spec_value', ['spec_id' => $specId, 'value' => $data['value']], ['spec_id' => $specId, 'value' => $data['value'], 'updatetime' => time()]);
                $action === 'inserted' ? $inserted++ : $updated++;
                $this->markRow($item['id'], $action);
            }
            foreach (isset($grouped['商品']) ? $grouped['商品'] : [] as $item) {
                $data = $item['data'];
                $category = Db::name('shop_category')->where('name', $data['category_name'])->find();
                $categoryId = $category ? (int)$category['id'] : 0;
                $goods = [
                    'category_id' => $categoryId, 'goods_sn' => $data['goods_sn'], 'title' => $data['title'],
                    'subtitle' => $data['subtitle'], 'price' => $data['price'], 'marketprice' => $data['marketprice'],
                    'weight' => $data['weight'], 'image' => $data['image'], 'sale_type' => $data['sale_type'],
                    'business_category_code' => $category ? $category['business_category_code'] : '', 'agent_visible' => $data['agent_visible'],
                    'catalog_status' => 'published', 'status' => $data['status'],
                    'data_completeness' => 'partial', 'updatetime' => time(), 'row_version' => 1,
                ];
                $action = $this->upsert('shop_goods', ['goods_sn' => $data['goods_sn']], $goods);
                $action === 'inserted' ? $inserted++ : $updated++;
                $this->markRow($item['id'], $action);
            }
            foreach (isset($grouped['SKU']) ? $grouped['SKU'] : [] as $item) {
                $data = $item['data'];
                $goods = Db::name('shop_goods')->where('goods_sn', $data['goods_sn'])->find();
                $spec = Db::name('shop_spec')->where('name', $data['spec_name'])->find();
                $specValue = Db::name('shop_spec_value')->where(['spec_id' => (int)$spec['id'], 'value' => $data['spec_value']])->find();
                // SKU code is an integration identifier, but a product/specification
                // pair is the business identity. Never create a second SKU for it.
                $sameSpec = Db::name('shop_goods_sku')->where('goods_id', (int)$goods['id'])
                    ->whereRaw('LOWER(TRIM(sku_id)) = ?', [strtolower(trim((string)$data['spec_value']))])
                    ->where('sku_code', '<>', $data['sku_code'])->find();
                if ($sameSpec) {
                    throw new \RuntimeException('商品 ' . $data['goods_sn'] . ' 的规格「' . $data['spec_value'] . '」已存在，导入已停止，请使用原SKU编码更新');
                }
                $sku = [
                    'goods_id' => $goods['id'], 'goods_sn' => $data['goods_sn'], 'sku_code' => $data['sku_code'],
                    'sku_id' => $data['spec_value'], 'price' => $data['price'], 'marketprice' => $data['marketprice'],
                    'stocks' => $data['stocks'], 'safety_stock' => $data['safety_stock'],
                    'net_content_value' => $data['net_content_value'], 'net_content_unit' => $data['net_content_unit'],
                    'image' => $data['image'], 'stock_updated_at' => time(), 'updatetime' => time(), 'row_version' => 1,
                ];
                $action = $this->upsert('shop_goods_sku', ['sku_code' => $data['sku_code']], $sku);
                $skuId = (int)Db::name('shop_goods_sku')->where('sku_code', $data['sku_code'])->value('id');
                if ($specValue) {
                    $this->upsert('shop_goods_sku_spec', ['goods_id' => (int)$goods['id'], 'spec_id' => (int)$spec['id'], 'spec_value_id' => (int)$specValue['id']], ['goods_id' => (int)$goods['id'], 'spec_id' => (int)$spec['id'], 'spec_value_id' => (int)$specValue['id'], 'updatetime' => time()]);
                }
                $action === 'inserted' ? $inserted++ : $updated++;
                $this->markRow($item['id'], $action);
            }
            foreach (isset($grouped['食材']) ? $grouped['食材'] : [] as $item) {
                $data = $item['data'];
                $ingredient = [
                    'ingredient_code' => $data['ingredient_code'], 'name' => $data['name'],
                    'category_code' => $data['category_code'], 'default_unit' => $data['default_unit'],
                    'description' => $data['description'], 'status' => $data['status'], 'updatetime' => time(), 'version' => 1,
                ];
                $action = $this->upsert('shop_ingredient', ['ingredient_code' => $data['ingredient_code']], $ingredient);
                $action === 'inserted' ? $inserted++ : $updated++;
                $this->markRow($item['id'], $action);
            }
            foreach (isset($grouped['营养资料']) ? $grouped['营养资料'] : [] as $item) {
                $data = $item['data'];
                $skuId = (int)Db::name('shop_goods_sku')->where('sku_code', $data['sku_code'])->value('id');
                $nutrition = $data;
                unset($nutrition['sku_code']);
                $nutrition['sku_id'] = $skuId;
                $nutrition['updatetime'] = time();
                $nutrition['version'] = 1;
                $action = $this->upsert('shop_sku_nutrition_fact', ['sku_id' => $skuId, 'basis_type' => $data['basis_type']], $nutrition);
                $action === 'inserted' ? $inserted++ : $updated++;
                $this->markRow($item['id'], $action);
            }
            foreach (isset($grouped['食材SKU映射']) ? $grouped['食材SKU映射'] : [] as $item) {
                $data = $item['data'];
                $ingredientId = (int)Db::name('shop_ingredient')->where('ingredient_code', $data['ingredient_code'])->value('id');
                $sku = Db::name('shop_goods_sku')->where('sku_code', $data['sku_code'])->find();
                $map = $data;
                unset($map['ingredient_code'], $map['sku_code']);
                $map['ingredient_id'] = $ingredientId;
                $map['sku_id'] = (int)$sku['id'];
                $map['goods_id'] = (int)$sku['goods_id'];
                $map['updatetime'] = time();
                $map['version'] = 1;
                $action = $this->upsert('shop_ingredient_sku_map', ['ingredient_id' => $ingredientId, 'sku_id' => $sku['id'], 'role' => $data['role']], $map);
                $action === 'inserted' ? $inserted++ : $updated++;
                $this->markRow($item['id'], $action);
            }

            $goodsCodes = [];
            foreach (isset($grouped['商品']) ? $grouped['商品'] : [] as $item) $goodsCodes[$item['data']['goods_sn']] = true;
            foreach (isset($grouped['SKU']) ? $grouped['SKU'] : [] as $item) $goodsCodes[$item['data']['goods_sn']] = true;
            foreach (array_keys($goodsCodes) as $goodsCode) {
                $goods = Db::name('shop_goods')->where('goods_sn', $goodsCode)->find();
                if (!$goods) continue;
                $skuIds = Db::name('shop_goods_sku')->where('goods_id', $goods['id'])->column('id');
                $stocks = (int)Db::name('shop_goods_sku')->where('goods_id', $goods['id'])->sum('stocks');
                $nutritionCount = $skuIds ? (int)Db::name('shop_sku_nutrition_fact')->where('sku_id', 'in', $skuIds)->where('status', 'normal')->count() : 0;
                $mappingCount = $skuIds ? (int)Db::name('shop_ingredient_sku_map')->where('sku_id', 'in', $skuIds)->where('status', 'normal')->count() : 0;
                $completeness = $skuIds && $nutritionCount >= count($skuIds) && $mappingCount >= count($skuIds) ? 'complete' : ($skuIds ? 'partial' : 'insufficient');
                Db::name('shop_goods')->where('id', $goods['id'])->update(['stocks' => $stocks, 'data_completeness' => $completeness, 'updatetime' => time()]);
            }

            if ($inserted === 0 && $updated === 0) {
                throw new DomainException('没有实际写入任何业务数据，不能标记为已导入', 40963, 409);
            }
            (new CatalogService())->touchVersion('master_import', $batch['batch_sn'], 'Excel平台主数据导入');
            Db::name('shop_master_data_import')->where('id', $batch['id'])->update([
                'status' => 'imported', 'inserted_count' => $inserted, 'updated_count' => $updated,
                'confirmed_by' => (int)$adminId, 'imported_at' => time(), 'updatetime' => time(),
            ]);
            Db::commit();
            return $this->batchResult(Db::name('shop_master_data_import')->where('id', $batch['id'])->find());
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
    }

    public function detail($batchId)
    {
        $batch = Db::name('shop_master_data_import')->where('id', (int)$batchId)->find();
        if (!$batch) {
            throw new DomainException('导入批次不存在', 40460, 404);
        }
        $result = $this->batchResult($batch);
        $result['rows'] = Db::name('shop_master_data_import_row')
            ->where('batch_id', $batch['id'])
            ->field('sheet_name,row_no,business_key,status,action,error_message')
            ->order('sheet_name asc,row_no asc')
            ->limit(300)
            ->select();
        if (!$result['rows'] && (int)$batch['total_rows'] > 0) {
            $result['detail_warning'] = '该批次记录了 ' . (int)$batch['total_rows'] . ' 行，但导入明细未写入，请重新上传并预检文件。';
        }
        return $result;
    }

    protected function normalizeRow($sheet, array $row)
    {
        if ($sheet === '分类') {
            return ['category_code' => $this->text($row['分类编码']), 'name' => $this->text($row['分类名称']), 'parent_category_code' => $this->text($row['上级分类编码']), 'agent_visible' => $this->boolean($row['Agent可见']), 'weigh' => $this->number($row['排序'], true), 'status' => $this->enum($row['状态'], ['启用' => 'normal', '停用' => 'hidden'], 'normal')];
        }
        if ($sheet === '商品') {
            return ['goods_sn' => $this->text($row['商品编码']), 'title' => $this->text($row['商品名称']), 'category_name' => $this->text($row['商品分类']), 'sale_type' => $this->enum($row['销售类型'], ['普通商品' => 'normal', '固定食材包' => 'bundle', '服务商品' => 'service'], 'normal'), 'subtitle' => $this->text($row['副标题']), 'price' => $this->number($row['销售价']), 'marketprice' => $this->number($row['市场价']), 'weight' => $this->number($row['重量kg']), 'image' => $this->text($row['商品图片']), 'agent_visible' => $this->boolean($row['Agent可见']), 'status' => $this->enum($row['上架状态'], ['上架' => 'normal', '下架' => 'hidden'], 'normal')];
        }
        if ($sheet === '规格') return ['name' => $this->text($row['规格名称'])];
        if ($sheet === '规格值') return ['spec_name' => $this->text($row['规格名称']), 'value' => $this->text($row['规格值'])];
        if ($sheet === 'SKU') {
            return ['sku_code' => $this->text($row['SKU编码']), 'goods_sn' => $this->text($row['商品编码']), 'spec_name' => $this->text($row['规格名称']), 'spec_value' => $this->text($row['规格值']), 'price' => $this->number($row['销售价']), 'marketprice' => $this->number($row['市场价']), 'stocks' => $this->number($row['库存'], true), 'safety_stock' => $this->number($row['安全库存'], true), 'net_content_value' => $this->number($row['净含量']), 'net_content_unit' => $this->unit($row['净含量单位']), 'image' => $this->text($row['图片URL'])];
        }
        if ($sheet === '食材') {
            return ['ingredient_code' => $this->text($row['食材编码']), 'name' => $this->text($row['食材名称']), 'category_code' => $this->text($row['类别编码']), 'default_unit' => $this->unit($row['默认单位']), 'description' => $this->text($row['说明']), 'status' => $this->enum($row['状态'], ['启用' => 'normal', '停用' => 'hidden'], 'normal')];
        }
        if ($sheet === '营养资料') {
            return ['sku_code' => $this->text($row['SKU编码']), 'basis_type' => $this->enum($row['基准类型'], ['每100克' => 'per_100g', '每份' => 'per_serving'], 'per_100g'), 'basis_value' => $this->number($row['基准值']), 'basis_unit' => $this->text($row['基准单位']), 'energy_kcal' => $this->nullableNumber($row['能量kcal']), 'protein_g' => $this->nullableNumber($row['蛋白质g']), 'fat_g' => $this->nullableNumber($row['脂肪g']), 'carbohydrate_g' => $this->nullableNumber($row['碳水g']), 'fiber_g' => $this->nullableNumber($row['膳食纤维g']), 'sodium_mg' => $this->nullableNumber($row['钠mg']), 'source_name' => $this->text($row['资料来源']), 'source_version' => $this->text($row['来源版本']), 'review_status' => $this->enum($row['审核状态'], ['待审核' => 'pending', '已通过' => 'approved', '已拒绝' => 'rejected'], 'pending'), 'status' => $this->enum($row['状态'], ['启用' => 'normal', '停用' => 'hidden'], 'normal')];
        }
        return ['ingredient_code' => $this->text($row['食材编码']), 'sku_code' => $this->text($row['SKU编码']), 'role' => $this->enum($row['角色'], ['主食材' => 'primary', '组成' => 'component', '备选' => 'alternative'], 'primary'), 'net_value' => $this->number($row['可用净量']), 'net_unit' => $this->unit($row['单位']), 'convert_ratio' => $this->number($row['换算率'], false, 1), 'loss_rate' => $this->number($row['损耗率']), 'priority' => $this->number($row['优先级'], true), 'review_status' => $this->enum($row['审核状态'], ['待审核' => 'pending', '已通过' => 'approved', '已拒绝' => 'rejected'], 'pending'), 'status' => $this->enum($row['状态'], ['启用' => 'normal', '停用' => 'hidden'], 'normal')];
    }

    protected function validateRow($sheet, array $data, array $known)
    {
        $errors = [];
        $required = [
            '分类' => ['category_code' => '分类编码', 'name' => '分类名称'],
            '商品' => ['goods_sn' => '商品编码', 'title' => '商品名称', 'category_name' => '商品分类'],
            '规格' => ['name' => '规格名称'],
            '规格值' => ['spec_name' => '规格名称', 'value' => '规格值'],
            'SKU' => ['sku_code' => 'SKU编码', 'goods_sn' => '商品编码', 'spec_name' => '规格名称', 'spec_value' => '规格值', 'net_content_unit' => '净含量单位'],
            '食材' => ['ingredient_code' => '食材编码', 'name' => '食材名称', 'default_unit' => '默认单位'],
            '营养资料' => ['sku_code' => 'SKU编码', 'basis_unit' => '基准单位', 'source_name' => '资料来源'],
            '食材SKU映射' => ['ingredient_code' => '食材编码', 'sku_code' => 'SKU编码', 'net_unit' => '单位'],
        ];
        foreach ($required[$sheet] as $field => $label) {
            if (!isset($data[$field]) || $data[$field] === '') {
                $errors[] = $label . '不能为空';
            }
        }
        if ($sheet === '分类' && $data['parent_category_code'] !== '' && !isset($known['categories'][$data['parent_category_code']])) {
            $errors[] = '上级分类编码不存在';
        }
        if ($sheet === '分类' && $data['parent_category_code'] === $data['category_code']) {
            $errors[] = '分类不能以自身作为上级分类';
        }
        if ($sheet === '商品' && $data['category_name'] !== '' && !isset($known['categories'][$data['category_name']])) {
            $errors[] = '商品分类不存在，请先维护分类';
        }
        if ($sheet === '规格值' && $data['spec_name'] !== '' && !isset($known['specs'][$data['spec_name']])) $errors[] = '规格名称不存在，请先维护规格';
        if ($sheet === 'SKU' && $data['goods_sn'] !== '' && !isset($known['goods'][$data['goods_sn']])) {
            $errors[] = '商品编码不存在';
        }
        if ($sheet === 'SKU' && $data['spec_name'] !== '' && !isset($known['specs'][$data['spec_name']])) $errors[] = '规格名称不存在，请先维护规格';
        if ($sheet === 'SKU' && $data['spec_name'] !== '' && $data['spec_value'] !== '') {
            $valueKey = $data['spec_name'] . '|' . $data['spec_value'];
            if (!isset($known['spec_values'][$valueKey])) $errors[] = '规格值不存在，请先维护规格值';
        }
        if ($sheet === '营养资料' && $data['sku_code'] !== '' && !isset($known['skus'][$data['sku_code']])) {
            $errors[] = 'SKU编码不存在';
        }
        if ($sheet === '食材SKU映射') {
            if ($data['ingredient_code'] !== '' && !isset($known['ingredients'][$data['ingredient_code']])) $errors[] = '食材编码不存在';
            if ($data['sku_code'] !== '' && !isset($known['skus'][$data['sku_code']])) $errors[] = 'SKU编码不存在';
            if ((float)$data['convert_ratio'] <= 0) $errors[] = '换算率必须大于0';
            if ((float)$data['loss_rate'] < 0 || (float)$data['loss_rate'] > 1) $errors[] = '损耗率必须在0到1之间';
        }
        $nonNegative = [
            '分类' => ['weigh'],
            '商品' => ['price', 'marketprice', 'weight'],
            'SKU' => ['price', 'marketprice', 'stocks', 'safety_stock', 'net_content_value'],
            '营养资料' => ['basis_value', 'energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g', 'fiber_g', 'sodium_mg'],
            '食材SKU映射' => ['net_value', 'priority'],
        ];
        foreach (isset($nonNegative[$sheet]) ? $nonNegative[$sheet] : [] as $field) {
            if ($data[$field] !== null && is_numeric($data[$field]) && (float)$data[$field] < 0) {
                $errors[] = $field . '不能为负数';
            }
        }
        $enumRules = [
            '分类' => ['status' => ['normal', 'hidden']],
            '商品' => ['sale_type' => ['normal', 'bundle', 'service'], 'status' => ['normal', 'hidden']],
            'SKU' => ['net_content_unit' => ['g', 'kg', 'ml', 'piece', 'pack']],
            '食材' => ['default_unit' => ['g', 'kg', 'ml', 'piece'], 'status' => ['normal', 'hidden']],
            '营养资料' => ['basis_type' => ['per_100g', 'per_serving'], 'review_status' => ['pending', 'approved', 'rejected'], 'status' => ['normal', 'hidden']],
            '食材SKU映射' => ['role' => ['primary', 'component', 'alternative'], 'review_status' => ['pending', 'approved', 'rejected'], 'status' => ['normal', 'hidden']],
        ];
        foreach (isset($enumRules[$sheet]) ? $enumRules[$sheet] : [] as $field => $allowed) {
            if (!in_array($data[$field], $allowed, true)) {
                $errors[] = $field . '取值无效，可选值：' . implode('/', $allowed);
            }
        }
        foreach ($data as $field => $value) {
            if (is_string($value) && strpos($value, '__INVALID_NUMBER__') === 0) {
                $errors[] = str_replace('__INVALID_NUMBER__', '', $value) . '必须是有效数字';
            } elseif (is_string($value) && strpos($value, '__INVALID_BOOLEAN__') === 0) {
                $errors[] = str_replace('__INVALID_BOOLEAN__', '', $value) . '必须填写1/0、是/否或true/false';
            }
        }
        return array_values(array_unique($errors));
    }

    protected function knownKeys(array $sheetData)
    {
        $known = ['categories' => [], 'goods' => [], 'skus' => [], 'ingredients' => [], 'specs' => [], 'spec_values' => []];
        foreach (Db::name('shop_category')->where('name', '<>', '')->column('name') as $value) $known['categories'][(string)$value] = true;
        foreach (Db::name('shop_category')->where('business_category_code', '<>', '')->column('business_category_code') as $value) $known['categories'][(string)$value] = true;
        foreach (Db::name('shop_spec')->where('name', '<>', '')->column('name') as $value) $known['specs'][(string)$value] = true;
        $existingSpecValues = Db::name('shop_spec_value')->alias('v')->join('shop_spec s', 's.id=v.spec_id', 'LEFT')->field('s.name,v.value')->select();
        foreach ($existingSpecValues as $value) $known['spec_values'][(string)$value['name'] . '|' . (string)$value['value']] = true;
        foreach (Db::name('shop_goods')->where('goods_sn', '<>', '')->column('goods_sn') as $value) $known['goods'][(string)$value] = true;
        foreach (Db::name('shop_goods_sku')->where('sku_code', '<>', '')->column('sku_code') as $value) $known['skus'][(string)$value] = true;
        foreach (Db::name('shop_ingredient')->where('ingredient_code', '<>', '')->column('ingredient_code') as $value) $known['ingredients'][(string)$value] = true;
        foreach (isset($sheetData['分类']) ? $sheetData['分类'] : [] as $item) if ($item['data']['name'] !== '') $known['categories'][$item['data']['name']] = true;
        foreach (isset($sheetData['规格']) ? $sheetData['规格'] : [] as $item) if ($item['data']['name'] !== '') $known['specs'][$item['data']['name']] = true;
        foreach (isset($sheetData['规格值']) ? $sheetData['规格值'] : [] as $item) if ($item['data']['spec_name'] !== '' && $item['data']['value'] !== '') $known['spec_values'][$item['data']['spec_name'] . '|' . $item['data']['value']] = true;
        foreach (isset($sheetData['商品']) ? $sheetData['商品'] : [] as $item) if ($item['data']['goods_sn'] !== '') $known['goods'][$item['data']['goods_sn']] = true;
        foreach (isset($sheetData['SKU']) ? $sheetData['SKU'] : [] as $item) if ($item['data']['sku_code'] !== '') $known['skus'][$item['data']['sku_code']] = true;
        foreach (isset($sheetData['食材']) ? $sheetData['食材'] : [] as $item) if ($item['data']['ingredient_code'] !== '') $known['ingredients'][$item['data']['ingredient_code']] = true;
        return $known;
    }

    protected function recordExists($sheet, array $data)
    {
        if ($sheet === '规格') return (bool)Db::name('shop_spec')->where('name', $data['name'])->find();
        if ($sheet === '规格值') {
            $specId = Db::name('shop_spec')->where('name', $data['spec_name'])->value('id');
            return $specId && Db::name('shop_spec_value')->where(['spec_id' => $specId, 'value' => $data['value']])->find();
        }
        if ($sheet === '分类') return (bool)Db::name('shop_category')->where('business_category_code', $data['category_code'])->find();
        if ($sheet === '商品') return (bool)Db::name('shop_goods')->where('goods_sn', $data['goods_sn'])->find();
        if ($sheet === 'SKU') return (bool)Db::name('shop_goods_sku')->where('sku_code', $data['sku_code'])->find();
        if ($sheet === '食材') return (bool)Db::name('shop_ingredient')->where('ingredient_code', $data['ingredient_code'])->find();
        if ($sheet === '营养资料') {
            $skuId = Db::name('shop_goods_sku')->where('sku_code', $data['sku_code'])->value('id');
            return $skuId && Db::name('shop_sku_nutrition_fact')->where(['sku_id' => $skuId, 'basis_type' => $data['basis_type']])->find();
        }
        $ingredientId = Db::name('shop_ingredient')->where('ingredient_code', $data['ingredient_code'])->value('id');
        $skuId = Db::name('shop_goods_sku')->where('sku_code', $data['sku_code'])->value('id');
        return $ingredientId && $skuId && Db::name('shop_ingredient_sku_map')->where(['ingredient_id' => $ingredientId, 'sku_id' => $skuId, 'role' => $data['role']])->find();
    }

    protected function businessKey($sheet, array $data)
    {
        if ($sheet === '规格') return $data['name'];
        if ($sheet === '规格值') return $data['spec_name'] . '|' . $data['value'];
        if ($sheet === '分类') return $data['category_code'];
        if ($sheet === '商品') return $data['goods_sn'];
        if ($sheet === 'SKU' || $sheet === '营养资料') return $data['sku_code'];
        if ($sheet === '食材') return $data['ingredient_code'];
        return $data['ingredient_code'] . '|' . $data['sku_code'] . '|' . $data['role'];
    }

    protected function upsert($table, array $where, array $data)
    {
        $existing = Db::name($table)->where($where)->find();
        if ($existing) {
            if (array_key_exists('row_version', $existing)) $data['row_version'] = (int)$existing['row_version'] + 1;
            if (array_key_exists('version', $existing)) $data['version'] = (int)$existing['version'] + 1;
            Db::name($table)->where('id', $existing['id'])->update($data);
            return 'updated';
        }
        if (!isset($data['createtime'])) $data['createtime'] = time();
        Db::name($table)->insert($data);
        return 'inserted';
    }

    protected function markRow($id, $action)
    {
        Db::name('shop_master_data_import_row')->where('id', $id)->update(['action' => $action, 'updatetime' => time()]);
    }

    protected function batchResult(array $batch, $duplicate = false)
    {
        $errors = Db::name('shop_master_data_import_row')->where('batch_id', $batch['id'])->where('status', 'invalid')->field('sheet_name,row_no,business_key,error_message')->order('id', 'asc')->limit(100)->select();
        return [
            'batch_id' => (int)$batch['id'], 'batch_sn' => $batch['batch_sn'], 'status' => $batch['status'],
            'duplicate' => $duplicate, 'total_rows' => (int)$batch['total_rows'], 'valid_rows' => (int)$batch['valid_rows'],
            'invalid_rows' => (int)$batch['invalid_rows'], 'inserted_count' => (int)$batch['inserted_count'],
            'updated_count' => (int)$batch['updated_count'], 'summary' => json_decode($batch['summary_json'], true) ?: [],
            'errors' => $errors,
        ];
    }

    protected function summarize(array $rows)
    {
        $summary = [];
        foreach ($this->sheets as $sheet => $headers) $summary[$sheet] = ['total' => 0, 'valid' => 0, 'invalid' => 0];
        foreach ($rows as $row) {
            if (!isset($summary[$row['sheet_name']])) $summary[$row['sheet_name']] = ['total' => 0, 'valid' => 0, 'invalid' => 0];
            $summary[$row['sheet_name']]['total']++;
            $summary[$row['sheet_name']][$row['status']]++;
        }
        return $summary;
    }

    protected function resultRow($sheet, $rowNo, $key, array $data, array $errors, $action = 'pending')
    {
        return ['sheet_name' => $sheet, 'row_no' => (int)$rowNo, 'business_key' => mb_substr($key, 0, 255), 'action' => $action, 'status' => $errors ? 'invalid' : 'valid', 'error_message' => mb_substr(implode('；', $errors), 0, 2000), 'data' => $data];
    }

    protected function text($value) { return trim((string)$value); }
    protected function unit($value) { return $this->enum($value, ['克'=>'g','千克'=>'kg','毫升'=>'ml','件'=>'piece','包'=>'pack'], ''); }
    protected function boolean($value)
    {
        $normalized = strtolower(trim((string)$value));
        if (in_array($normalized, ['1', 'true', 'yes', '是', '启用'], true)) return 1;
        if (in_array($normalized, ['0', 'false', 'no', '否', '停用', ''], true)) return 0;
        return '__INVALID_BOOLEAN__' . (string)$value;
    }
    protected function enum($value, array $translations, $default) { $value = trim((string)$value); return $value === '' ? $default : (isset($translations[$value]) ? $translations[$value] : $value); }
    protected function nullableNumber($value) { return trim((string)$value) === '' ? null : $this->number($value); }
    protected function number($value, $integer = false, $default = 0)
    {
        if ($value === '' || $value === null) return $default;
        if (!is_numeric($value)) return '__INVALID_NUMBER__' . (string)$value;
        return $integer ? (int)$value : round((float)$value, 6);
    }

    protected function addTemplateNotes($sheetName, $sheet)
    {
        $notes = [
            '分类' => ['D1' => '填写 1/0 或 是/否', 'F1' => 'normal/hidden 或 启用/停用'],
            '商品' => ['D1' => '普通商品/固定食材包/服务商品', 'J1' => '填写 是/否', 'K1' => '填写 上架/下架'],
            '规格' => ['A1' => '例如：净含量、包装数量'],
            '规格值' => ['A1' => '必须填写已存在的规格名称', 'B1' => '例如：500克、1千克、10个'],
            'SKU' => ['K1' => 'g、kg、ml、piece、pack 等统一单位'],
            '食材' => ['D1' => 'g、kg、ml、piece 等统一单位', 'F1' => 'normal/hidden'],
            '营养资料' => ['B1' => 'per_100g 或 per_serving', 'M1' => 'pending/approved/rejected', 'N1' => 'normal/hidden'],
            '食材SKU映射' => ['C1' => 'primary/component/alternative', 'G1' => '0 到 1 之间的小数', 'I1' => 'pending/approved/rejected', 'J1' => 'normal/hidden'],
        ];
        foreach (isset($notes[$sheetName]) ? $notes[$sheetName] : [] as $cell => $note) {
            $sheet->getComment($cell)->getText()->createTextRun($note);
        }
    }
}
