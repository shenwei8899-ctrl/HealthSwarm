"""手写 HTML 与独立逐行 oracle，不使用生产解析器生成预期值。"""

import copy

import pytest

from yuxi.services.health_vision_provider import normalize_report_blocks, redact_report_blocks, verify_report_fields
from yuxi.services.health_vision_types import HealthVisionError


def table_input(html):
    """明确页面和整表框，身份行也保留在私有原始响应。"""
    return [
        {
            "result": {
                "layoutParsingResults": [
                    {
                        "prunedResult": {
                            "width": 200,
                            "height": 400,
                            "model_settings": {"use_doc_preprocessor": False},
                            "parsing_res_list": [{"block_content": html, "block_bbox": [20, 80, 160, 120]}],
                        }
                    }
                ]
            }
        }
    ]


def test_html_table_rows_preserve_cells_identity_is_not_outbound_and_bbox_is_whole_table():
    """同一表格身份行不会丢弃指标；数字、单位和区间仍属于自己的行。"""
    html = (
        '<table><thead><tr><th colspan="4">合成检验</th></tr>'
        "<tr><th>项目</th><th>结果</th><th>单位</th><th>参考范围</th></tr></thead><tbody>"
        '<tr><td>姓名</td><td colspan="3">合成张三</td></tr>'
        "<tr><td><b>葡萄糖</b></td><td>6.8</td><td>mmol/L</td><td>3.9-6.1</td></tr>"
        "<tr><td>甘油三酯</td><td>1.7</td><td>mmol/L</td><td>0.0-1.7</td></tr></tbody></table>"
    )
    rows = table_input(html)
    original = copy.deepcopy(rows)
    blocks = normalize_report_blocks(rows, {"page_index": 5, "width": 200, "height": 400})
    assert [b["raw_text"] for b in blocks] == [
        "合成检验",
        "项目\t结果\t单位\t参考范围",
        "姓名\t合成张三",
        "葡萄糖\t6.8\tmmol/L\t3.9-6.1",
        "甘油三酯\t1.7\tmmol/L\t0.0-1.7",
    ]
    assert [b["block_id"] for b in blocks] == [f"p5_b0_r{i}" for i in range(5)]
    assert all(b["page_index"] == 5 and b["bbox"] == [0.1, 0.2, 0.8, 0.3] for b in blocks)
    safe = redact_report_blocks(blocks, "父亲")
    assert safe == blocks[3:]
    assert (
        rows == original
        and rows[0]["result"]["layoutParsingResults"][0]["prunedResult"]["parsing_res_list"][0]["block_content"] == html
    )
    fields = verify_report_fields(
        [
            {
                "name": "葡萄糖",
                "value_raw": "6.8",
                "value_numeric": "6.8",
                "unit_raw": "mmol/L",
                "reference_raw": "3.9-6.1",
                "block_id": "p5_b0_r3",
            }
        ],
        safe,
    )
    assert fields[0]["value_numeric"] == "6.8"
    assert fields[0]["evidence"] == {key: value for key, value in blocks[3].items() if key != "table_columns"}


@pytest.mark.parametrize(
    "html,expected",
    [
        ("<TABLE><TR><TD>血糖</TD><TD>&lt;0.1</TD><TD>mmol/L</TD></TR></TABLE>", "血糖\t<0.1\tmmol/L"),
        ("<table>\n<tr><td>血糖</td><td> 6.8\n </td><td> mmol/<span>L</span> </td></tr></table>", "血糖\t6.8\tmmol/L"),
        ("<table><tr><td>白细胞</td><td>8</td><td>10<sup>9</sup>/L</td></tr></table>", "白细胞\t8\t10^9/L"),
        ("<table><tr><td>白细胞</td><td>8</td><td>10<sub>9</sub>/L</td></tr></table>", "白细胞\t8\t10_9/L"),
        ("<table><tr><td>血糖</td><td>6.8</td><td>mmol/L<br/>复核</td></tr></table>", "血糖\t6.8\tmmol/L 复核"),
    ],
)
def test_table_entities_inline_formatting_and_whitespace_are_cell_local(html, expected):
    """标签与换行不构成新指标行，比较符号仍保留。"""
    blocks = normalize_report_blocks(table_input(html), {"page_index": 0, "width": 200, "height": 400})
    assert len(blocks) == 1 and blocks[0]["raw_text"] == expected


@pytest.mark.parametrize(
    "html",
    [
        "<table><tr><td>血糖</td><td>6.8",
        "<table><tr><td>血糖</td></tr></td></table>",
        "<table><tr><td>血糖<table><tr><td>6.8</td></tr></table></td></tr></table>",
        "<table><tr><td>血糖</td><td><script>6.8</script></td></tr></table>",
        '<table><tr><td>血糖</td><td><img src="https://example.invalid/6.8"/></td></tr></table>',
        "<table><tr>血糖 6.8<td>mmol/L</td></tr></table>",
        "<table><td>血糖 6.8</td></table>",
        '<table><tr><td rowspan="2">血糖</td><td>6.8</td></tr><tr><td>7.1</td></tr></table>',
        '<table><tr><td colspan="0">血糖 6.8</td></tr></table>',
        "<table></table>",
        "<table><tr><td>血糖 6.8</td></tr></table><table><tr><td>血糖 7.1</td></tr></table>",
        "<table><tr><td>血糖 6.8</td></tr></table><span",
        "<table><tr><td>血糖 6.8</td></tr></table><!-- unclosed",
        "<table><tr><td>血糖 6.8</td></tr></table><?broken",
        "<table><tr><td></td></tr></table>",
        "<table><tr><td> </td><td>\n</td></tr></table>",
        "<!DOCTYPE html><table><tr><td>血糖 6.8</td></tr></table>",
        "<?instruction?><table><tr><td>血糖 6.8</td></tr></table>",
        "<![CDATA[hidden]]><table><tr><td>血糖 6.8</td></tr></table>",
        "<![broken]><table><tr><td>血糖 6.8</td></tr></table>",
        "<!--><table><tr><td>血糖 6.8</td></tr></table>",
        "<!-- passive --><table><tr><td>血糖 6.8</td></tr></table>",
        "<table><tr>" + "<td>x</td>" * 101 + "</tr></table>",
        "<table><tr><td>" + "x" * 10000 + "</td></tr></table>",
    ],
)
def test_unprovable_table_structure_is_explicit_page_parse_failure(html):
    """不自动修复、执行主动内容或继承跨行单元格。"""
    with pytest.raises(HealthVisionError, match="parser_contract_invalid"):
        normalize_report_blocks(table_input(html), {"page_index": 0, "width": 200, "height": 400})


@pytest.mark.parametrize(
    "changes",
    [
        {"value_raw": "1.7", "value_numeric": "1.7"},
        {"unit_raw": "g/L"},
        {"reference_raw": "0.0-1.7"},
        {"value_raw": "3.9", "value_numeric": "3.9"},
    ],
)
def test_field_cannot_borrow_adjacent_table_row_or_reference_number(changes):
    """同页相邻行和本行参考范围都不是结果值来源。"""
    html = (
        "<table><tr><th>项目</th><th>结果</th><th>单位</th><th>参考范围</th></tr>"
        "<tr><td>葡萄糖</td><td>6.8</td><td>mmol/L</td><td>3.9-6.1</td></tr>"
        "<tr><td>甘油三酯</td><td>1.7</td><td>g/L</td><td>0.0-1.7</td></tr></table>"
    )
    blocks = normalize_report_blocks(table_input(html), {"page_index": 0, "width": 200, "height": 400})
    item = {
        "name": "葡萄糖",
        "value_raw": "6.8",
        "value_numeric": "6.8",
        "unit_raw": "mmol/L",
        "reference_raw": "3.9-6.1",
        "block_id": "p0_b0_r1",
        **changes,
    }
    field = verify_report_fields([item], blocks)[0]
    assert field["value_numeric"] is None and "row_evidence_mismatch" in field["review_flags"]


@pytest.mark.parametrize(
    "header,cells,numeric",
    [
        (
            "<th>项目</th><th>参考范围</th><th>结果</th><th>单位</th>",
            "<td>葡萄糖</td><td>3.9</td><td>6.8</td><td>mmol/L</td>",
            "6.8",
        ),
        (
            "<th>单位</th><th>结果</th><th>项目</th><th>参考范围</th>",
            "<td>mmol/L</td><td>6.8</td><td>葡萄糖</td><td>3.9</td>",
            "6.8",
        ),
        (
            "<th>项目</th><th>参考上限</th><th>结果</th><th>单位</th>",
            "<td>葡萄糖</td><td>3.9</td><td>6.8</td><td>mmol/L</td>",
            None,
        ),
    ],
)
def test_column_roles_follow_explicit_headers_instead_of_position(header, cells, numeric):
    """列序可以变化；未识别参考列不声称已核验参考范围。"""
    blocks = normalize_report_blocks(
        table_input(f"<table><tr>{header}</tr><tr>{cells}</tr></table>"), {"page_index": 0, "width": 200, "height": 400}
    )
    safe = redact_report_blocks(blocks, "父亲")
    assert safe == [blocks[1]]
    item = {
        "name": "葡萄糖",
        "value_raw": "6.8",
        "value_numeric": "6.8",
        "unit_raw": "mmol/L",
        "reference_raw": "3.9",
        "block_id": "p0_b0_r1",
    }
    assert verify_report_fields([item], safe)[0]["value_numeric"] == numeric
    wrong = {**item, "value_raw": "3.9", "value_numeric": "3.9"}
    result = verify_report_fields([wrong], safe)[0]
    assert result["value_numeric"] is None and "row_evidence_mismatch" in result["review_flags"]


@pytest.mark.parametrize("header", ["", "<tr><th>项目</th><th>结果</th><th>结果</th></tr>"])
def test_missing_or_ambiguous_columns_keep_candidate_without_verified_numeric(header):
    """无表头或重复结果列仍可人工查看原行，不能伪造结果列归属。"""
    html = f"<table>{header}<tr><td>葡萄糖</td><td>6.8</td><td>3.9</td></tr></table>"
    blocks = normalize_report_blocks(table_input(html), {"page_index": 0, "width": 200, "height": 400})
    safe = redact_report_blocks(blocks, "父亲")
    assert len(safe) == 1 and safe[0]["table_columns"] is None
    result = verify_report_fields(
        [{"name": "葡萄糖", "value_raw": "6.8", "value_numeric": "6.8", "block_id": safe[0]["block_id"]}], safe
    )[0]
    assert result["value_numeric"] is None and "row_evidence_mismatch" in result["review_flags"]


@pytest.mark.parametrize(
    "new_header",
    [
        "<tr><th>项目</th><th>参考范围</th><th>测量结果</th><th>单位</th></tr>",
        "<tr><td>项目</td><td>参考范围</td><td>测量结果</td><td>单位</td></tr>",
        "<tr><th>未知项目</th><th>未知区间</th><th>未知结果</th><th>未知单位</th></tr>",
        "<tr><th>检验名称</th><td>参考范围</td><td>实测数值</td><td>单位</td></tr>",
        "<tr><th>检验名称</th><th>参考上限</th><th>2026</th><th>浓度单位</th></tr>",
        "<tr><th>检验名称</th><td>参考上限</td><td>2026</td><td>浓度单位</td></tr>",
    ],
)
def test_new_unknown_header_never_reuses_previous_result_column(new_header):
    """同表第二组表头未知时清除旧映射，不跨表头误认结果。"""
    html = (
        "<table><tr><th>项目</th><th>结果</th><th>参考范围</th><th>单位</th></tr>"
        + new_header
        + "<tr><td>葡萄糖</td><td>3.9</td><td>6.8</td><td>mmol/L</td></tr></table>"
    )
    blocks = normalize_report_blocks(table_input(html), {"page_index": 0, "width": 200, "height": 400})
    safe = redact_report_blocks(blocks, "父亲")
    assert len(safe) == 1 and safe[0]["table_columns"] is None
    result = verify_report_fields(
        [
            {
                "name": "葡萄糖",
                "value_raw": "3.9",
                "value_numeric": "3.9",
                "unit_raw": "mmol/L",
                "reference_raw": "6.8",
                "block_id": "p0_b0_r2",
            }
        ],
        safe,
    )[0]
    assert result["value_numeric"] is None and "row_evidence_mismatch" in result["review_flags"]


def test_mixed_header_cell_metric_row_keeps_explicit_columns():
    """指标名称使用 th 而数值使用 td 时仍按明确表头核验。"""
    html = (
        "<table><tr><th>项目</th><th>结果</th><th>单位</th></tr>"
        "<tr><th>葡萄糖</th><td>6.8</td><td>mmol/L</td></tr></table>"
    )
    blocks = normalize_report_blocks(table_input(html), {"page_index": 0, "width": 200, "height": 400})
    field = verify_report_fields(
        [{"name": "葡萄糖", "value_raw": "6.8", "value_numeric": "6.8", "unit_raw": "mmol/L", "block_id": "p0_b0_r1"}],
        redact_report_blocks(blocks, "父亲"),
    )[0]
    assert field["value_numeric"] == "6.8"
