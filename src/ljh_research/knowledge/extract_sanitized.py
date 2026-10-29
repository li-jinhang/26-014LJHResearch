# coding: utf-8
"""Sanitized pypdf extraction replicating import_paper's per-page format.

Fixes UnicodeEncodeError from lone surrogates in the PDF text layer by
replacing invalid chars, then writes the repo's extraction file format:
  # <title> 读取内容
  - 原文件：`../源文件库/<pdf name>`
  - 导入日期：YYYY-MM-DD
  ## 第 N 页
"""
import datetime
import sys
from pathlib import Path

from pypdf import PdfReader

pdf = Path(sys.argv[1])
title = sys.argv[2]
out = Path(sys.argv[3])


def clean(text):
    return "".join(
        ch if (0 <= ord(ch) < 0xD800 or 0xE000 <= ord(ch) <= 0x10FFFF) else "\ufffd"
        for ch in text
    )


reader = PdfReader(str(pdf))
parts = [
    "# {} 读取内容\n".format(title),
    "",
    "- 原文件：`../源文件库/{}`".format(pdf.name),
    "- 导入日期：{}".format(datetime.date.today().isoformat()),
    "",
]
for idx, page in enumerate(reader.pages, start=1):
    text = clean(page.extract_text() or "")
    parts.append("## 第 {} 页\n".format(idx))
    parts.append(text)
    parts.append("")

out.write_text("\n".join(parts), encoding="utf-8")
print("wrote", out, "bytes=", out.stat().st_size)
