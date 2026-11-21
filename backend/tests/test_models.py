"""数据模型口径守卫（v0.17 P0-1）。

表数长期是「11 表 vs 文档 9–10 表」的口径冲突：docs/产品定义.md §六 的表格把 `Tag` 与
`TagBinding` 合写成一行，代码里却是两张独立的表。差异纯属文档计数，不是代码漏了表，
也没有「后加的表」。这里用一条断言把这个事实钉住：以后真要加表/并表，这条用例先红，
提醒同步改 models.py 的 docstring 与 docs 口径。
"""

from sqlmodel import SQLModel

from app import models  # noqa: F401  导入即注册到 SQLModel.metadata


EXPECTED_TABLES = {
    "video_batch",
    "video",
    "segment",
    "evidence",
    "knowledge_item",
    "artifact",
    "conflict_record",
    "tag",
    "tag_binding",
    "note",
    "revision",
}


def test_model_registers_exactly_eleven_tables():
    """table=True 的类共 11 个，与 docs 的 11 表口径（及图 6）一致。"""
    actual = set(SQLModel.metadata.tables)
    assert actual == EXPECTED_TABLES, f"表集合变了：多 {actual - EXPECTED_TABLES}，少 {EXPECTED_TABLES - actual}"
    assert len(actual) == 11


def test_tag_and_tag_binding_are_separate_tables():
    """9–10 表的成因就是这两张被文档合成一行；这里点名钉住。"""
    assert "tag" in SQLModel.metadata.tables
    assert "tag_binding" in SQLModel.metadata.tables
    assert "tag" != "tag_binding"


def test_models_docstring_states_eleven_tables():
    """docstring 是这套口径的上游：它还写 9–10 表，下游文档就会跟着漂。"""
    doc = models.__doc__ or ""
    assert "11 张表" in doc
    assert "9–10 表" in doc, "保留历史口径说明，读者才知道差异是怎么来的"
