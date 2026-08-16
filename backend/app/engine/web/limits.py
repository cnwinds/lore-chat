"""fetch_url 体积/超时默认值的单源（Settings 与 WebFetcher 共用）。"""

# 现代新闻站 HTML 常含大段 CSS/脚本在正文之前；100KiB 会截断后抽空正文（如 TechCrunch ~230KiB）
FETCH_URL_HTML_MAX_BYTES = 1 * 1024 * 1024
# PDF 远大于 HTML 正文；20MB 覆盖常见规则手册
FETCH_URL_PDF_MAX_BYTES = 20 * 1024 * 1024
# Content-Type / 魔数也可能判为 PDF，下载前无法预知；统一抬高超时下限
FETCH_URL_PDF_TIMEOUT_FLOOR = 60
