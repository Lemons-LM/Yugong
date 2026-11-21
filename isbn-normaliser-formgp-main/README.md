[![Update Range File](https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP/actions/workflows/update-rangemessage.yml/badge.svg?event=schedule)](https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP/actions/workflows/update-rangemessage.yml)

[中文](README.md) | [English](README.en.md)

# ISBN 规范化器

为萌娘百科 wikitext中的{{[ISBN](https://mzh.moegirl.org.cn/Template:ISBN)}}模板提供独立的规范化工具和 MediaWiki 机器人，规范化脚本可以单独运行。

## 核心功能

- **isbn_normalise.py** — 纯 ISBN 规范化库
  - 按国际标准书号规则对 ISBN-10/13 进行连字符规范化
  - 可选：将 ISBN-10 转换为 ISBN-13

- **isbn_template_normalise.py** — wikitext 模板规范化工具
  - 批量处理 `{{ISBN}}` 模板参数
  - 可选：将 ISBN-10 转换为 ISBN-13
  - 可选：当参数1和参数2语义相同时，将模板替换为 `{{ISBNT|$1}}`，其中 `$1` 为连字符化 ISBN

- **mw_bot_core.py** — 通用 MediaWiki 基础设施层
  - 环境变量加载、HTTP 封装、登录/CSRF 鉴权、页面读写
  - 无任何 ISBN 特定逻辑，可被其他 MediaWiki 机器人复用

- **mw_isbn_bot.py** — MediaWiki 机器人运行时
  - 支持多种页面查询策略（通过 `--query` / `-q` 选择）
  - `transcludedin`：使用 `generator=transcludedin` 拉取嵌入 Template:ISBN 的页面及其修订版本
  - `booksource-search`：通过 `insource:` 全文检索，找出含 `Special:BookSources/` 链接的页面
  - 自动处理 API 分页（continue）和修订版本续取（rvcontinue）
  - 当 API 返回结果超过大小限制时，打印警告信息并继续拉取后续数据
  - 检查 Allowbots 规则后再编辑
  - 支持编辑数量上限控制
  - 根据实际改动类型逐页自动拼接编辑摘要

## 依赖资源

- `RangeMessage.xml` — 国际 ISBN 中心提供的范围消息文件

## 环境与依赖

- Python 3.10+（推荐 3.11，与 GitHub Actions 一致）
- 第三方依赖（若只需处理单个 ISBN 而非 wikitext 则不需要）：
  - `requests`
  - `brotli`
  - `mwparserfromhell`

快速安装：

```bash
python -m pip install --upgrade pip
pip install requests brotli mwparserfromhell
```

## 快速开始

```bash
git clone https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP.git
cd ISBN-normaliser-forMGP
python -m pip install --upgrade pip
pip install requests brotli mwparserfromhell
```

然后准备 `RangeMessage.xml`（仓库已包含），即可按下文命令运行。

## 工作方式

### 命令行工具

**单个 ISBN 规范化：**
```bash
python isbn_normalise.py \
  --xml RangeMessage.xml \
  9787302511625
```

**单文件模板格式化：**
```bash
python isbn_template_normalise.py \
  --xml RangeMessage.xml \
  --text-file your_wikitext.txt \
  -format \
  --in-place
```

**转换 + 转换为 ISBN-13：**
```bash
python isbn_template_normalise.py \
  --xml RangeMessage.xml \
  --text-file your_wikitext.txt \
  -format -to13 \
  --in-place
```

**转换 + 相同语义参数转为 ISBNT：**
```bash
python isbn_template_normalise.py \
  --xml RangeMessage.xml \
  --text-file your_wikitext.txt \
  -format \
  --rehyphenate-equal-label \
  --in-place
```

### MediaWiki 机器人

配置好 `.env.pwd`（见下文）后，只需：

```bash
# 干运行（测试，不保存）
python mw_isbn_bot.py --dry-run

# 正式运行，限制编辑数量
python mw_isbn_bot.py --max-edits 10

# 指定查询方式
python mw_isbn_bot.py -q ti --dry-run          # transcludedin，使用简写
python mw_isbn_bot.py -q bs --dry-run          # booksource-search，使用简写
```

也可在命令行中临时覆盖凭据（不建议常用）：

```bash
python mw_isbn_bot.py \
  --bot-username MyBot \
  --bot-password MyBotPassword \
  --max-edits 10
```

#### 查询策略（`--query` / `-q`）

| 参数值 | 简写 | 说明 |
|--------|------|------|
| `transcludedin` | `ti` | 拉取所有嵌入 Template:ISBN 的页面（默认） |
| `booksource-search` | `booksource`、`bs` | 通过全文检索找含 `Special:BookSources/` 链接的页面 |

默认查询方式由 `.env` 中的 `DEFAULT_QUERY` 决定，未配置时回落到 `transcludedin`。

## GitHub Actions 自动化

### 1) ISBN 机器人工作流

文件：`.github/workflows/isbn-normaliser-bot.yml`

1. **手动触发（workflow_dispatch）**
  - `query` — 查询策略（留空则使用 `.env` 中的 `DEFAULT_QUERY`）
  - `dry_run` — 是否仅干运行（不保存编辑）
  - `max_edits` — 本次最多编辑数量（留空则不限）
  - 访问 Actions 标签页点击"运行工作流"

2. **定时执行**
  - 每两个月的 1 日 UTC `20:15` 自动执行（cron: `15 20 1 */2 *`）

3. **多策略并行（可选）**
  - 如需同时运行多种查询策略，可在 GHA 中使用矩阵策略：
    ```yaml
    strategy:
      matrix:
        query: [transcludedin, booksource-search]
    steps:
      - run: python mw_isbn_bot.py --query ${{ matrix.query }}
    ```

### 2) RangeMessage 自动更新工作流

文件：`.github/workflows/update-rangemessage.yml`

1. **触发方式**
  - 支持手动触发（`workflow_dispatch`）
  - 每周三 UTC `03:05` 自动执行（cron: `05 3 * * 3`）

2. **行为说明**
  - 下载最新 `RangeMessage.xml`
  - 若文件有变化，自动提交并推送到当前分支

3. **权限要求**
  - 工作流已声明 `contents: write`，用于提交更新

### 3) BookSource 别名更新工作流

文件：`.github/workflows/update-booksource-aliases.yml`

1. **触发方式**
  - 支持手动触发（`workflow_dispatch`）
  - 每年 1 月 1 日和 7 月 1 日 UTC `03:05` 自动执行（cron: `05 3 1 1,7 *`）

2. **行为说明**
  - 从萌娘百科 API 拉取 `Booksources` 特殊页面的全部本地化别名
  - 规范化（casefold、去除空格与下划线）后，原地更新 `isbn_template_normalise.py` 中的 `BOOKSOURCE_PAGE_ALIASES` 常量
  - 若常量值无变化，不产生提交

3. **权限要求**
  - 工作流已声明 `contents: write`，用于提交更新

## 文件说明

- `isbn_normalise.py`：
  - ISBN 规范化核心逻辑
  - 仅处理单个 ISBN 输入输出

- `isbn_template_normalise.py`：
  - wikitext 中 `{{ISBN}}` 模板批量处理逻辑
  - `ChangeReport` 数据类追踪四类改动：BookSources 链接替换、连字符规范化、ISBN-10 转换、ISBNT 合并
  - 被 `mw_isbn_bot.py` 与命令行模板处理场景复用

- `mw_bot_core.py`：
  - 通用 MediaWiki 基础设施（env 加载、HTTP、鉴权、页面读写）
  - 无任何 ISBN 特定依赖，可供其他机器人脚本直接复用

- `mw_isbn_bot.py`：
  - MediaWiki 机器人入口
  - 负责登录、分页拉取页面、检查 Allowbots、逐页拼接编辑摘要、提交编辑

- `RangeMessage.xml`：
  - ISBN 号段规则来源文件
  - 由国际 ISBN 中心发布，供规范化算法使用

- `.env`：
  - 公共配置（Wiki 地址、UA、模板名称、默认查询方式），纳入版本控制

- `.env.pwd`：
  - 私密凭据（Bot 用户名、密码），已在 `.gitignore` 中，**不提交**

- `.env.pwd.example`：
  - `.env.pwd` 的填写模板，纳入版本控制

- `.github/workflows/isbn-normaliser-bot.yml`：
  - 机器人执行工作流（手动触发 + 每两个月定时）

- `.github/workflows/update-rangemessage.yml`：
  - 自动更新 `RangeMessage.xml` 的工作流（每周三）

- `.github/workflows/update-booksource-aliases.yml`：
  - 自动更新 `BOOKSOURCE_PAGE_ALIASES` 的工作流（每半年）

## 环境变量配置

项目采用双层配置方案，将公共设置与私密凭据分离：

| 文件 | 是否纳入版本控制 | 用途 |
|------|----------------|------|
| `.env` | ✅ 提交到仓库 | Wiki 地址、UA、模板名称、默认查询方式 |
| `.env.pwd` | ❌ 已在 `.gitignore` 中 | Bot 账号凭据 |

### `.env`（公共，随仓库分发）

仓库中已内置适配萌娘百科的默认值：

```ini
WIKI_API=https://mzh.moegirl.org.cn/api.php
USER_AGENT=ISBNNormaliser-Bot/1.1 (...)
TEMPLATE_TITLE=Template:ISBN|Template:ISBNT|Template:Cite book
DEFAULT_QUERY=transcludedin
XML_PATH=RangeMessage.xml
REHYPHENATE_EQUAL_LABEL=false
TO13=false
SUMMARY=根据 ISO 2108:2017（...）自动调整ISBN（...）
EDIT_TAGS=Bot
```

| 变量 | 对应 CLI 参数 | 说明 |
|------|-------------|------|
| `WIKI_API` | `--wiki-api` | MediaWiki API 地址 |
| `USER_AGENT` | `--user-agent` | HTTP User-Agent |
| `TEMPLATE_TITLE` | `--template-title` | 模板名称（可多个，`\|` 分隔） |
| `DEFAULT_QUERY` | `--query` / `-q` | 默认查询策略 |
| `XML_PATH` | `--xml` | RangeMessage.xml 路径 |
| `REHYPHENATE_EQUAL_LABEL` | `--rehyphenate-equal-label` | 语义相同时合并为 ISBNT |
| `TO13` | `-to13` | 将 ISBN-10 转换为 ISBN-13 |
| `SUMMARY` | `--summary` | ISO 2108 说明文字（附加于每条摘要末尾） |
| `EDIT_TAGS` | `--edit-tags` | 编辑时附加的变更标签；多个标签以 `\|` 分隔（如 `Bot\|test`），留空则不附加任何标签 |

如需适配其他 wiki，修改后提交即可。所有字段均可通过对应命令行参数临时覆盖。

### `.env.pwd`（私密，本地 / 服务器专用）

复制 `.env.pwd.example` 并填写实际值：

```ini
BOT_USERNAME=YourBot@BotPassword
BOT_PASSWORD=your_bot_password_here
```

### GitHub Actions

Secrets 中仅需配置 `BOT_USERNAME` 与 `BOT_PASSWORD`。公共配置由 `actions/checkout` 随代码自动带入工作目录，无需额外操作。

### 优先级

```
命令行参数 > 系统环境变量（含 GHA env: 注入）> .env.pwd > .env > 内置默认值
```

## 规范化规则

- 始终规范化模板第 1 参数（当有效时）
- 默认保持第 2 参数不变
- 仅在显式启用且语义相同时：将模板改为 `{{ISBNT|$1}}`，并保持第 1 参数为连字符格式
- 编辑摘要由机器人根据实际改动类型逐页自动拼接，各部分以全角分号（`；`）连接，ISO 2108 说明文字始终附于末尾：

  | 触发条件 | 摘要片段 |
  |----------|----------|
  | 替换了 `[[Special:BookSources/…]]` 链接 | `替换[[Special:BookSources/]]为{{[[T:ISBN\|ISBN]]}}` |
  | 发生了 ISBN-10 → ISBN-13 转换 | `将 ISBN-10 转换为 ISBN-13` |
  | 合并了语义相同的参数为 `{{ISBNT}}` | `自动使用{{[[T:ISBNT\|ISBNT]]}}` |
  | 任意改动（始终附加） | `根据 ISO 2108:2017（…）自动调整ISBN（…）` |

  ISO 2108 说明文字可通过 `SUMMARY` 环境变量或 `--summary` 参数自定义。

## 故障排查

- 报错 `ModuleNotFoundError`：
  - 先执行 `pip install requests brotli mwparserfromhell`

- 报错找不到 `RangeMessage.xml`：
  - 确认当前目录存在该文件，或通过 `--xml` 指定正确路径

- 报错找不到 `BOT_USERNAME` / `BOT_PASSWORD`：
  - 确认 `.env.pwd` 已创建并填写，或通过 `--bot-username` / `--bot-password` 传入

- 机器人未执行编辑：
  - 先用 `--dry-run` 查看是否检测到可修改页面
  - 检查 `--max-edits` 是否设置为 0
  - 检查机器人账号权限与站点的 Allowbots/编辑限制策略

- GitHub Actions 未产生提交：
  - `update-rangemessage` 和 `update-booksource-aliases` 在文件无变化时会显示 "No changes to commit"，这是正常行为

## 参考资料

- [ISO 2108:2017](https://www.iso.org/standard/65483.html)
- [国际 ISBN 中心](https://www.isbn-international.org/range_file_generation)
