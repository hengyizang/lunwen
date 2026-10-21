---
name: extract-paper-images
description: 从 arXiv ID/link、公开直接 PDF URL 或本地论文 PDF 提取架构图、方法图和实验图，保存到 Obsidian images 目录并生成索引。Use when the user asks to extract figures or another research skill needs embeddable images.
---

# 提取研究文档图片

## 输入识别

1. 将当前 SKILL.md 的父目录视为 <skill-dir>。
2. 从 OBSIDIAN_VAULT_PATH 解析 <vault>；缺失时要求用户提供 Vault 路径。
3. 接受：
   - 合法 arXiv ID、arXiv:ID 或 arxiv.org 链接；
   - 返回 PDF 内容的公开 HTTP(S) URL；
   - 已存在的本地 PDF。
4. 非 arXiv 网页不能直接传给图片脚本。先使用 paper-analyze/scripts/resolve_source.py；若其返回 selected_pdf_url 或 local_pdf，再传该值。
5. 确认输出目录位于 <vault>/20_Research/Papers/<domain>/<note-stem>/images。已有图片默认保留，除非用户要求刷新。

## 执行

    <python> "<skill-dir>/scripts/extract_images.py" "<arxiv-id-or-pdf-url-or-local-pdf>" "<images-dir>" "<images-dir>/index.md"

脚本自动执行：

- arXiv：源码图片优先，源码中的 figure PDF 次之，论文 PDF 回退。
- 直接 PDF URL：下载到临时目录后从 PDF 提取。
- 本地 PDF：直接提取，不进行网络访问。

## 验证

1. 确认 index.md 中的文件实际存在。
2. 优先架构、方法、主结果与消融图，过滤 logo、小图标和重复内容。
3. 检查 PNG 可读性；裁剪错误或文本过小时不要推荐嵌入。
4. 返回目录、索引、数量和 3–5 张最有价值的文件名。
5. Obsidian 使用 ![[filename.png|800]]。

## 失败处理

- URL 返回 HTML 而非 PDF：停止并提示先运行来源解析器，不把 URL 当 arXiv ID。
- 公开下载失败：报告 HTTP 状态或内容类型，不尝试登录或绕过访问控制。
- 输出路径越出 Vault：停止。
- 不删除已有图片，不把临时下载留在 Vault。
