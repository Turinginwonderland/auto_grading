"""题目入库流水线（PDF → OCR → 结构化 → 入库）。

- pdf_splitter: PyMuPDF 按章节拆页
- ocr_runner: 多后端 OCR（PaddleOCR / Tesseract / 云视觉 / Mock）
- llm_structurer: OCR 文本 → Problem JSON
- human_review: 抽 10% 人工抽检
- runner: 一键串联 + 写文件缓存
"""
