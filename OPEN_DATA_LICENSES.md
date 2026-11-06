# 开放学习数据来源

本项目的批量词汇与双语例句只采用允许再利用的开放数据，应用界面和 API 会保留来源标识。

## ECDICT

- 项目：Free English to Chinese Dictionary Database
- 地址：https://github.com/skywind3000/ECDICT
- 许可：MIT License
- 用途：英文词条、音标、英中释义、考试标签与词频信息

## Tatoeba

- 项目：https://tatoeba.org/
- 下载说明：https://tatoeba.org/downloads
- 许可：Creative Commons Attribution 2.0 France（部分内容另以 CC0 发布）
- 用途：英中双语例句
- 署名：Sentence data contributed by the Tatoeba community. 每条语句保留英文原句 ID，可链接回 `https://tatoeba.org/en/sentences/show/{id}`。

构建脚本位于 `tools/content-builder/`。生成数据库不包含音频；音频仍使用平台自身的浏览器或服务端语音合成能力。
