"""RapidOCR 返回值归一：numpy 数组不能直接做布尔判断。"""

from types import SimpleNamespace

import numpy as np

from app.engines.ocr import _unwrap


def test_unwrap_rapidocr_numpy_arrays():
    result = SimpleNamespace(
        txts=np.array(["第一行", "第二行"]),
        scores=np.array([0.9, 0.8]),
        boxes=np.array([[1, 2], [3, 4]]),
    )
    texts, scores, boxes = _unwrap(result)
    assert texts == ["第一行", "第二行"]
    assert scores == [0.9, 0.8]
    assert len(boxes) == 2


def test_unwrap_legacy_tuple_rows():
    box = [[0, 0], [1, 1]]
    result = ([[box, "x", 0.7]], 0.1)
    texts, scores, boxes = _unwrap(result)
    assert texts == ["x"]
    assert scores == [0.7]
    assert boxes == [box]
