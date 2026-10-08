"""独立矩形 oracle 验证像素框坐标归属，未知输入仍保留原文。"""

import copy

import pytest

from yuxi.services.health_vision_provider import normalize_report_blocks, verify_report_fields


def report_input():
    """非方形处理页与像素框由测试显式定义，不共享转换 helper。"""
    page = {"page_index": 5, "width": 200, "height": 400}
    pruned = {
        "width": 200,
        "height": 400,
        "page_index": None,
        "page_count": None,
        "model_settings": {"use_doc_preprocessor": False},
        "parsing_res_list": [{"block_content": "葡萄糖 6.8 mmol/L 3.9-6.1", "block_bbox": [20, 80, 160, 120]}],
    }
    rows = [{"result": {"layoutParsingResults": [{"prunedResult": pruned}]}}]
    return rows, page, pruned


@pytest.mark.parametrize(
    "pixels,expected",
    [
        ([20, 80, 160, 120], [0.1, 0.2, 0.8, 0.3]),
        ([0, 0, 200, 400], [0, 0, 1, 1]),
        ([0, 0, 1, 1], [0, 0, 0.005, 0.0025]),
        ([0.1, 0.2, 0.8, 0.3], [0.0005, 0.0005, 0.004, 0.00075]),
    ],
)
def test_verified_pixel_box_uses_processed_page_dimensions_even_for_tiny_values(pixels, expected):
    """不能根据小于一的值猜单位；一像素框不会放大到整页。"""
    rows, page, pruned = report_input()
    pruned["parsing_res_list"][0]["block_bbox"] = pixels
    blocks = normalize_report_blocks(rows, page)
    assert blocks == [{"block_id": "p5_b0", "page_index": 5, "raw_text": "葡萄糖 6.8 mmol/L 3.9-6.1", "bbox": expected}]
    fields = verify_report_fields(
        [
            {
                "name": "葡萄糖",
                "value_raw": "6.8",
                "value_numeric": "6.8",
                "unit_raw": "mmol/L",
                "reference_raw": "3.9-6.1",
                "block_id": "p5_b0",
            }
        ],
        blocks,
    )
    assert fields[0]["evidence"] == blocks[0] and fields[0]["value_numeric"] == "6.8"
    assert pruned["parsing_res_list"][0]["block_bbox"] == pixels


@pytest.mark.parametrize(
    "case",
    [
        "no_width",
        "no_height",
        "wrong_width",
        "wrong_height",
        "zero_width",
        "boolean_width",
        "float_height",
        "float_width",
        "list_width",
        "no_settings",
        "wrong_settings",
        "missing_preprocessor",
        "enabled_preprocessor",
        "numeric_preprocessor",
        "contradictory_preprocessor",
        "empty_dict_preprocessor",
        "empty_list_preprocessor",
        "false_preprocessor",
        "zero_preprocessor",
        "empty_text_preprocessor",
        "null_preprocessor",
        "multiple_rows",
        "multiple_layouts",
        "wrong_page",
        "boolean_page",
        "multiple_pages",
        "boolean_count",
        "no_bbox",
        "short_bbox",
        "nested_bbox",
        "text_coordinate",
        "boolean_coordinate",
        "nan",
        "infinite",
        "negative",
        "overflow_x",
        "overflow_y",
        "inverted_x",
        "inverted_y",
        "zero_area",
        "zero_height",
        "normalized_without_frame",
    ],
)
def test_unknown_or_invalid_coordinate_frame_preserves_text_without_fabricated_box(case):
    """每项页归属、无变换及框校验均有缺陷负控，不裁切或猜测。"""
    rows, page, pruned = report_input()
    pixels = pruned["parsing_res_list"][0]["block_bbox"]
    if case == "no_width":
        del pruned["width"]
    elif case == "no_height":
        del pruned["height"]
    elif case == "wrong_width":
        pruned["width"] = 400
    elif case == "wrong_height":
        pruned["height"] = 200
    elif case == "zero_width":
        pruned["width"] = 0
    elif case == "boolean_width":
        pruned["width"] = True
    elif case == "float_height":
        pruned["height"] = 400.0
    elif case == "float_width":
        pruned["width"] = 200.0
    elif case == "list_width":
        pruned["width"] = [200]
    elif case == "no_settings":
        del pruned["model_settings"]
    elif case == "wrong_settings":
        pruned["model_settings"] = []
    elif case == "missing_preprocessor":
        pruned["model_settings"] = {}
    elif case == "enabled_preprocessor":
        pruned["model_settings"]["use_doc_preprocessor"] = True
    elif case == "numeric_preprocessor":
        pruned["model_settings"]["use_doc_preprocessor"] = 0
    elif case == "contradictory_preprocessor":
        pruned["doc_preprocessor_res"] = {"angle": 180}
    elif case in {
        "empty_dict_preprocessor",
        "empty_list_preprocessor",
        "false_preprocessor",
        "zero_preprocessor",
        "empty_text_preprocessor",
        "null_preprocessor",
    }:
        pruned["doc_preprocessor_res"] = {
            "empty_dict_preprocessor": {},
            "empty_list_preprocessor": [],
            "false_preprocessor": False,
            "zero_preprocessor": 0,
            "empty_text_preprocessor": "",
            "null_preprocessor": None,
        }[case]
    elif case == "multiple_rows":
        rows.append(copy.deepcopy(rows[0]))
    elif case == "multiple_layouts":
        rows[0]["result"]["layoutParsingResults"].append({"prunedResult": copy.deepcopy(pruned)})
    elif case == "wrong_page":
        pruned["page_index"] = 1
    elif case == "boolean_page":
        pruned["page_index"] = False
    elif case == "multiple_pages":
        pruned["page_count"] = 2
    elif case == "boolean_count":
        pruned["page_count"] = True
    elif case == "no_bbox":
        del pruned["parsing_res_list"][0]["block_bbox"]
    elif case == "short_bbox":
        pixels.pop()
    elif case == "nested_bbox":
        pixels[0] = [20]
    elif case == "text_coordinate":
        pixels[0] = "20"
    elif case == "boolean_coordinate":
        pixels[0] = False
    elif case == "nan":
        pixels[0] = float("nan")
    elif case == "infinite":
        pixels[2] = float("inf")
    elif case == "negative":
        pixels[0] = -1
    elif case == "overflow_x":
        pixels[2] = 201
    elif case == "overflow_y":
        pixels[3] = 401
    elif case == "inverted_x":
        pixels[0] = 180
    elif case == "inverted_y":
        pixels[1] = 130
    elif case == "zero_area":
        pixels[2] = 20
    elif case == "zero_height":
        pixels[3] = 80
    elif case == "normalized_without_frame":
        pruned.pop("width")
        pruned.pop("height")
        pruned["parsing_res_list"][0]["block_bbox"] = [0.1, 0.2, 0.8, 0.3]
    blocks = normalize_report_blocks(rows, page)
    assert blocks
    assert all(block["raw_text"] == "葡萄糖 6.8 mmol/L 3.9-6.1" and block["bbox"] is None for block in blocks)
    assert blocks[0]["block_id"] == "p5_b0" and blocks[0]["page_index"] == 5


def test_single_image_provider_local_index_zero_is_not_the_global_report_index():
    """单页 API 的 0 页正确关联报告全局第六页。"""
    rows, page, pruned = report_input()
    pruned.update(page_index=0, page_count=1)
    assert normalize_report_blocks(rows, page)[0]["bbox"] == [0.1, 0.2, 0.8, 0.3]
