---
name: paper-analyze
description: 深度分析 arXiv 论文、公开 PDF URL、本地 PDF、研究项目页、技术博客或普通网页，自动识别来源类型并生成带证据与图片的 Obsidian 笔记。Use when the user provides an arXiv ID/link、public PDF URL、company research page、blog URL、local PDF or existing note and asks for analysis, summary, evaluation, or knowledge-base capture.
---

# 多来源深度分析

先确定来源类型，再选择论文或网页分析结构。不得因输入含数字就假定是 arXiv，也不得给博客、公司报告或普通 PDF 伪造 arXiv 元数据。

## 解析路径

1. 将当前 SKILL.md 的父目录视为 <skill-dir>。
2. 从 OBSIDIAN_VAULT_PATH 解析 <vault>；缺失时要求用户提供 Vault 路径。
3. 验证 <vault>/20_Research/Papers，读取研究配置中的 language；缺失时使用 zh。
4. 在系统临时目录创建本次 <work>，不在 skill 目录或 Vault 中保存临时下载。

## 识别来源

始终先运行：

    <python> "<skill-dir>/scripts/resolve_source.py" --input "<user-input>" --work-dir "<work>" --output "<work>/source.json"

读取 source.json，并按 source_type 分支：

- arxiv：仅当输入是合法的 YYMM.NNNN/NNNNN、arXiv:ID 或 arxiv.org 链接时使用。保留 arxiv_id、摘要页和 PDF 链接。
- pdf_url：公开 URL 返回 PDF 内容或 PDF Content-Type。使用原始 URL，分析下载到 <work> 的 local_pdf。
- local_pdf：分析用户提供的本地 PDF。
- project_page：研究项目页或公司页面中发现明确的 Paper/PDF 链接。联合分析页面与自动下载的 selected_pdf_url；同时保留项目页和 PDF URL。
- blog：具有文章日期/作者元数据，或 URL 路径含 blog/posts/article 的 HTML。按博客结构分析，不套论文评审模板。
- webpage：其他公开 HTML 页面。按网页资料分析并标注证据边界。
- title：既不是路径、URL，也不是 arXiv ID 的文本。仅在用户确实只给标题时再搜索一手来源。

若公开页面依赖 JavaScript，resolver 提取不完整时使用 当前 agent 的网页访问能力读取页面；仍以 source.json 的 URL 和来源类型为准。

## 获取与查重

1. 在 Vault 中按 document_id、arxiv_id、规范化标题和 source_url 查重。
2. 已有笔记时保留手工内容，只局部补充。
3. 论文/PDF 分支以 PDF 原文为主要证据；项目页可补充作者、机构、代码和演示。
4. blog/webpage 分支以页面正文为主要证据；区分作者主张、引用证据与 agent 推断。
5. 无法访问全文时只分析可见内容，并明确说明缺失范围。

## 图片

对 arxiv、pdf_url 或 local_pdf，需要图片时读取相邻 ../extract-paper-images/SKILL.md，并把 arXiv ID、直接 PDF URL 或 local_pdf 传给脚本。

对 blog/project_page/webpage，只保存能帮助理解内容且允许公开访问的页面图片；不要把导航图标、头像或品牌 logo 当作研究插图。

## 生成笔记

仅在目标笔记不存在时创建模板：

    <python> "<skill-dir>/scripts/generate_note.py" --title "<title>" --authors "<authors>" --domain "<domain>" --vault "<vault>" --language "<zh|en>" --source-type "<source_type>" --source-url "<source_url>" --document-id "<document_id>" --paper-id "<arxiv_id>" --published-date "<published_date>" --venue "<venue>"

模板分支：

- arxiv/pdf_url/local_pdf：研究文档结构，覆盖问题、方法、公式、实验、局限、相关工作和评分。
- blog/project_page/webpage：资料结构，覆盖核心论点、内容脉络、关键证据、技术细节、可信度、局限和实践启示；不要求会议、引用数或论文 ID。

替换全部占位符后再更新图谱：

    <python> "<skill-dir>/scripts/update_graph.py" --title "<title>" --domain "<domain>" --score <0-10> --vault "<vault>" --language "<zh|en>" --source-type "<source_type>" --source-url "<source_url>" --paper-id "<arxiv_id>" --document-id "<document_id>"

## 格式与证据规则

- frontmatter 至少保留 document_id、source_type、source_url、title、authors、published、domain。
- 只有 arxiv 类型才写 arxiv_id 与 arXiv/PDF 派生链接。
- 直接 PDF、博客与网页始终保留用户给出的原始 URL；重定向后的 canonical_url 可另外记录。
- 公式使用 Markdown LaTeX；图片使用 ![[filename.png|800]]；笔记链接使用 [[File_Name|Display Title]]。
- 未知作者、日期、机构、会议或数字写 --，不猜测。
- 不覆盖用户笔记，不删除旧图片，不把网页主张改写成已经复现的事实。
