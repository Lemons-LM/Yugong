[![Update Range File](https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP/actions/workflows/update-rangemessage.yml/badge.svg)](https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP/actions/workflows/update-rangemessage.yml)

[中文](README.md) | [English](README.en.md)

# ISBN 规范化工具

这是一个用于处理萌娘百科 wikitext 中 {{[ISBN](https://mzh.moegirl.org.cn/Template:ISBN)}} 模板的 ISBN 规范化工具，同时提供 MediaWiki 机器人。ISBN 规范化脚本可以单独使用。

## 核心功能

- **isbn_normalise.py** — ISBN 规范化核心库
  - 按国际标准书号规则对 ISBN-10/13 进行连字符规范化
  - 可选：将 ISBN-10 转换为 ISBN-13

- **isbn_template_normalise.py** — wikitext 模板处理工具
  - 批量处理 `{{ISBN}}` 模板参数
  - 可选：将 ISBN-10 转换为 ISBN-13
  - 可选：当参数 1 和参数 2 的语义相同时，将模板替换为 `{{ISBNT|$1}}`，其中 `$1` 为带连字符的 ISBN

- **mw_bot_core.py** — 通用 MediaWiki 工具层
  - 读取环境变量，封装 HTTP 请求，处理登录和 CSRF 认证，以及页面读写
  - 不包含 ISBN 相关逻辑，可以供其他 MediaWiki 机器人复用

- **mw_isbn_bot.py** — MediaWiki 机器人程序
  - 支持多种页面查询策略（通过 `--query` / `-q` 选择）
  - `transcludedin`：使用 `generator=transcludedin` 获取嵌入 Template:ISBN 的页面及其修订版本
  - `booksource-search`：通过 `insource:` 进行全文检索，查找包含 `Special:BookSources/` 链接的页面
  - 自动处理 API 分页（continue）和修订版本的后续获取（rvcontinue）
  - 当 API 返回的结果达到大小限制时，输出警告并继续获取后续数据
  - 检查 Allowbots 规则，确认允许后再编辑页面
  - 可以限制每次运行的编辑数量
  - 根据每个页面的实际改动类型自动生成编辑摘要
  - 可选：将运行状态（busy/holiday）写入 `User:<机器人名>/Status` 子页面（**默认关闭**，见 `UPDATE_STATUS_PAGE`）

## 依赖资源

- `RangeMessage.xml` — 国际 ISBN 中心提供的范围消息文件

## 环境与依赖

- Python 3.10+（推荐 3.11，与 GitHub Actions 一致）
- 第三方依赖（仅处理单个 ISBN 而不处理 wikitext 时不需要）：
  - `requests`
  - `brotli`
  - `mwparserfromhell`

快速安装：

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 快速开始

```bash
git clone https://github.com/Kelly-Hsueh/ISBN-normaliser-forMGP.git
cd ISBN-normaliser-forMGP
python -m pip install --upgrade pip
pip install -r requirements.txt
```

然后准备 `RangeMessage.xml`（仓库已包含），即可按下文命令运行。

## 使用方法

### 命令行工具

**单个 ISBN 规范化：**
```bash
python isbn_normalise.py \
  --xml RangeMessage.xml \
  9787302511625
```

**处理单个文件中的模板：**
```bash
python isbn_template_normalise.py \
  --xml RangeMessage.xml \
  --text-file your_wikitext.txt \
  -format \
  --in-place
```

**规范化并转换为 ISBN-13：**
```bash
python isbn_template_normalise.py \
  --xml RangeMessage.xml \
  --text-file your_wikitext.txt \
  -format -to13 \
  --in-place
```

**规范化模板，并将语义相同的参数合并为 ISBNT：**
```bash
python isbn_template_normalise.py \
  --xml RangeMessage.xml \
  --text-file your_wikitext.txt \
  -format \
  --rehyphenate-equal-label \
  --in-place
```

### MediaWiki 机器人

完成 `.env.pwd` 配置（见下文）后，可以运行：

```bash
# 试运行（仅测试，不保存编辑）
python mw_isbn_bot.py --dry-run

# 正式运行，并限制编辑数量
python mw_isbn_bot.py --max-edits 10

# 指定查询策略
python mw_isbn_bot.py -q ti --dry-run          # transcludedin，使用缩写
python mw_isbn_bot.py -q bs --dry-run          # booksource-search，使用缩写
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
| `transcludedin` | `ti` | 获取所有嵌入 Template:ISBN 的页面（默认） |
| `booksource-search` | `booksource`、`bs` | 通过全文检索查找包含 `Special:BookSources/` 链接的页面 |

默认查询策略由 `.env` 中的 `DEFAULT_QUERY` 决定；未配置时使用 `transcludedin`。

## GitHub Actions 自动运行

### 1) ISBN 机器人工作流

文件：`.github/workflows/isbn-normaliser-bot.yml`

1. **手动触发（workflow_dispatch）**
  - `query` — 查询策略（留空则使用 `.env` 中的 `DEFAULT_QUERY`）
  - `dry_run` — 是否仅运行测试，不保存编辑
  - `max_edits` — 本次最多编辑的页面数（留空则不限制）
  - 访问 Actions 标签页点击"运行工作流"

2. **定时执行**
  - 每两个月的 1 日 UTC `20:15` 自动运行（cron: `15 20 1 */2 *`）

3. **多策略并行（可选）**
  - 如需同时运行多种查询策略，可以在 GHA 中使用矩阵策略：
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

2. **运行方式**
  - 下载最新的 `RangeMessage.xml`
  - 文件发生变化时，自动提交并推送到当前分支

3. **权限要求**
  - 工作流已声明 `contents: write`，用于提交更新

### 3) BookSource 别名更新工作流

文件：`.github/workflows/update-booksource-aliases.yml`

1. **触发方式**
  - 支持手动触发（`workflow_dispatch`）
  - 每年 1 月 1 日和 7 月 1 日 UTC `03:05` 自动执行（cron: `05 3 1 1,7 *`）

2. **运行方式**
  - 从萌娘百科 API 获取 `Booksources` 特殊页面的全部本地化别名
  - 对别名进行规范化（casefold、去除空格和下划线）后，直接更新 `isbn_template_normalise.py` 中的 `BOOKSOURCE_PAGE_ALIASES` 常量
  - 常量值没有变化时，不提交文件

3. **权限要求**
  - 工作流已声明 `contents: write`，用于提交更新

## 文件说明

- `isbn_normalise.py`：
  - ISBN 规范化核心逻辑
  - 仅处理单个 ISBN 输入输出

- `isbn_template_normalise.py`：
  - wikitext 中 `{{ISBN}}` 模板的批量处理逻辑
  - `ChangeReport` 数据类记录四类改动：BookSources 链接替换、连字符规范化、ISBN-10 转换和 ISBNT 合并
  - 供 `mw_isbn_bot.py` 和命令行模板处理功能复用

- `mw_bot_core.py`：
  - 通用 MediaWiki 工具（读取环境变量、处理 HTTP 请求、认证和页面读写）
  - 不依赖任何 ISBN 相关逻辑，可以供其他机器人脚本直接复用

- `mw_isbn_bot.py`：
  - MediaWiki 机器人的启动入口
  - 负责登录、分页获取页面、检查 Allowbots、按页面生成编辑摘要和提交编辑

- `RangeMessage.xml`：
  - ISBN 号段规则文件
  - 由国际 ISBN 中心发布，供规范化算法使用

- `.env`：
  - 公共配置（Wiki 地址、UA、模板名称和默认查询策略），纳入版本控制

- `.env.pwd`：
  - 私密凭据（机器人用户名和密码），已在 `.gitignore` 中，**不提交**

- `.env.pwd.example`：
  - `.env.pwd` 的填写模板，纳入版本控制

- `.github/workflows/isbn-normaliser-bot.yml`：
  - 机器人运行流程（手动触发 + 每两个月定时）

- `.github/workflows/update-rangemessage.yml`：
  - 自动更新 `RangeMessage.xml` 的流程（每周三）

- `.github/workflows/update-booksource-aliases.yml`：
  - 自动更新 `BOOKSOURCE_PAGE_ALIASES` 的流程（每半年）

## 环境变量配置

项目使用两个配置文件，分别保存公共设置和私密凭据：

| 文件 | 是否纳入版本控制 | 用途 |
|------|----------------|------|
| `.env` | ✅ 提交到仓库 | Wiki 地址、UA、模板名称和默认查询策略 |
| `.env.pwd` | ❌ 已在 `.gitignore` 中 | 机器人账号凭据 |

### `.env`（公共配置，随仓库提供）

仓库已内置适用于萌娘百科的默认值：

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
UPDATE_STATUS_PAGE=false
```

| 变量 | 对应 CLI 参数 | 说明 |
|------|-------------|------|
| `WIKI_API` | `--wiki-api` | MediaWiki API 地址 |
| `USER_AGENT` | `--user-agent` | HTTP User-Agent |
| `TEMPLATE_TITLE` | `--template-title` | 模板名称（可以填写多个，以 `\|` 分隔） |
| `DEFAULT_QUERY` | `--query` / `-q` | 默认查询策略 |
| `XML_PATH` | `--xml` | RangeMessage.xml 路径 |
| `REHYPHENATE_EQUAL_LABEL` | `--rehyphenate-equal-label` | 语义相同时合并为 ISBNT |
| `TO13` | `-to13` | 将 ISBN-10 转换为 ISBN-13 |
| `SUMMARY` | `--summary` | ISO 2108 说明文字（附加到每条摘要末尾） |
| `EDIT_TAGS` | `--edit-tags` | 编辑时附加的变更标签；多个标签以 `\|` 分隔（如 `Bot\|test`），留空则不添加标签 |
| `UPDATE_STATUS_PAGE` | `--update-status-page` | 是否启用机器人状态子页面（向 `User:<机器人名>/Status` 写入 busy/holiday）；**默认关闭**，需显式设置为 `true` |

> [!NOTE]
> `UPDATE_STATUS_PAGE` 的默认值为 `false`。启用后，机器人会向自己的用户子页面写入状态；派生项目可能不需要这个状态页。
> 本仓库自带的 `.env` 已将其显式设置为 `true`，这是源机器人使用的配置。使用派生项目时，请根据部署需求保留或改为 `false`。

如需适配其他 Wiki，修改此文件后提交即可。所有字段都可以通过对应的命令行参数临时覆盖。

### `.env.pwd`（私密配置，仅供本地或服务器使用）

复制 `.env.pwd.example` 并填写实际值：

```ini
BOT_USERNAME=YourBot@BotPassword
BOT_PASSWORD=your_bot_password_here
```

### GitHub Actions

只需在 GitHub Secrets 中配置 `BOT_USERNAME` 和 `BOT_PASSWORD`。公共配置会由 `actions/checkout` 随代码带入工作目录，无需额外设置。

### 优先级

```
命令行参数 > 系统环境变量（包括 GitHub Actions 注入的环境变量）> .env.pwd > .env > 内置默认值
```

## 规范化规则

- 始终规范化模板的第 1 个参数（当参数有效时）。
- 默认保留第 2 个参数，不进行修改。
- 只有在明确启用相关选项且两个参数语义相同时，才会将模板改为 `{{ISBNT|$1}}`，并保留带连字符的第 1 个参数。
- 机器人会根据每个页面的实际改动类型自动生成编辑摘要，各部分以全角分号（`；`）连接：

  | 触发条件 | 摘要片段 |
  |----------|----------|
  | 替换了 `[[Special:BookSources/…]]` 链接 | `替换[[Special:BookSources/]]为{{[[T:ISBN\|ISBN]]}}` |
  | 发生了 ISBN-10 → ISBN-13 转换 | `将 ISBN-10 转换为 ISBN-13` |
  | 合并了语义相同的参数为 `{{ISBNT}}` | `自动使用{{[[T:ISBNT\|ISBNT]]}}` |
  | ISBN **数值本身**的格式发生了实际变化 | `根据 ISO 2108:2017（…）自动调整ISBN（…）` |

  需要注意的是，`ISBN-10 → ISBN-13 转换` 和普通连字符规范化都会改变 ISBN 的数值格式，因此一定会附加最后这条说明。BookSources 链接替换或 ISBNT 合并有时只涉及结构变化（例如将链接替换为模板，或更换模板名称），底层 ISBN 数值可能已经正确；这种情况下不会附加这条说明，避免编辑摘要与实际改动不符。

  ISO 2108 说明文字可以通过 `SUMMARY` 环境变量或 `--summary` 参数自定义。

## 故障排查

- 出现 `ModuleNotFoundError`：
  - 执行 `pip install -r requirements.txt`

- 找不到 `RangeMessage.xml`：
  - 确认当前目录存在该文件，或通过 `--xml` 指定正确路径

- 找不到 `BOT_USERNAME` / `BOT_PASSWORD`：
  - 确认 `.env.pwd` 已创建并填写，或通过 `--bot-username` / `--bot-password` 传入

- 机器人没有编辑页面：
  - 先使用 `--dry-run`，确认是否检测到可以修改的页面
  - 检查 `--max-edits` 是否设置为 0
  - 检查机器人账号权限与站点的 Allowbots/编辑限制策略

- GitHub Actions 没有产生提交：
  - `update-rangemessage` 和 `update-booksource-aliases` 在文件没有变化时会显示 "No changes to commit"，这是正常情况

## 参考资料

- [ISO 2108:2017](https://www.iso.org/standard/65483.html)
- [国际 ISBN 中心](https://www.isbn-international.org/range_file_generation)
