"""fetch_url 体积/超时默认值的单源（Settings 与 WebFetcher 共用）。"""

# PDF 远大于 HTML 正文；20MB 覆盖常见规则手册
FETCH_URL_PDF_MAX_BYTES = 20 * 1024 * 1024
# Content-Type / 魔数也可能判为 PDF，下载前无法预知；统一抬高超时下限
FETCH_URL_PDF_TIMEOUT_FLOOR = 60
