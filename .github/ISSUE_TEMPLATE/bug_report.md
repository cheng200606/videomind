name: 缺陷报告
description: 提交一个系统缺陷 / 原型问题 / 文档错误
labels: bug
body:
  - type: textarea
    id: phenomenon
    attributes:
      label: 现象描述
      placeholder: 出现了什么不符合预期的情况？
    validations:
      required: true

  - type: textarea
    id: reproduce
    attributes:
      label: 复现步骤
      placeholder: |
        1.
        2.
        3.
    validations:
      required: true

  - type: dropdown
    id: module
    attributes:
      label: 所属模块
      options:
        - 视频接入 / 播放器
        - 音视频解析（ASR / OCR）
        - AI 结构化（章节 / 知识点 / 代码块）
        - 知识图谱
        - 笔记与导出
        - 原型（墨刀）
        - 文档 / UML 图
        - 其他
    validations:
      required: true

  - type: textarea
    id: impact
    attributes:
      label: 影响与期望
      placeholder: 期望结果是什么？严重程度（阻塞 / 一般 / 建议）？
    validations:
      required: true

  - type: input
    id: related
    attributes:
      label: 关联交付物
      placeholder: 如：原型页 5、图 6 ER 图、章节 3.2
