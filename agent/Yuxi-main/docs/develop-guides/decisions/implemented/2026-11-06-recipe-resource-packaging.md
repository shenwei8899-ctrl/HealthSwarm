# 菜谱资源打包与受控回填入口

状态：implemented
类型：bug-fix
Owner：backend/package/pyproject.toml

## 问题

服务读取 `yuxi/services/data` 中的菜谱封面和受限做法资料。仅在工作区保留 JSON 文件不能保证构建后的 Python wheel 包含这些资源，历史报告关联与译文回填脚本也需要纳入版本管理。

## 决策

Setuptools 显式包含 `services/data/*.json`。回填入口沿用 `backend/scripts`，默认只统计或导出，写入要求显式 `--apply`。译文回填在保存前重新读取原文版本并执行既有译文校验，模型翻译复用既有费用登记。

## 替代方案

依赖服务器手工复制资源会使独立安装结果随部署方式变化。脚本默认自动写入会扩大运维误操作影响，因此采用明确资源声明和默认只读入口。

## 后果

Wheel 安装包含当前服务所需的 JSON 数据。回填操作仍需要运行环境中的数据库与业务权限，脚本入库不代表已对生产数据执行回填。

## 验证

执行 `uv build --wheel` 并读取生成的 ZIP 目录，确认 `recipe_covers.json` 和 `restricted_cooking_references_v1.json` 均位于 `yuxi/services/data`。两个回填脚本通过 Python 语法解析。生产回填未执行。
