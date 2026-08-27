# Nexus Media 站点配置

Nexus Media 的站点解析配置独立仓库，支持远程热更新：后端启动时自动从本仓库 release 拉取最新站点定义，无需发版后端即可新增/修复站点。

## 目录结构

```
sites/
├── api/          # API 站点定义（JSON-RPC / REST API），如 mteam、rousi、torrentleech
├── html/         # HTML 站点定义（网页抓取），绝大多数 PT 站
└── schema/       # JSON Schema 校验定义（site-api.schema.json / site-html.schema.json）
```

- 一个文件定义且仅定义一个站点；后端以 JSON 内的 `id` 字段为站点标识，**文件名不参与匹配**（如 `pterclub.json` 的 `id` 为 `pterclubnet`）
- 建议文件名与 `id` 保持一致（小写字母/数字/`-`/`_`），便于维护与排查

## 工作原理

1. 本仓库打 tag 后，GitHub Actions 自动运行 `validate.py` 校验并通过 `sites-config.zip` 发布 release
2. Nexus Media 后端启动时自动检查最新 release（也可在系统设置中手动更新）
3. 下载 zip 解压到 `/config/sites/`（`api/`、`html/`、`schema/` 三个子目录）
4. `SiteEngine` 优先加载 `/config/sites/`，回退到后端内置配置

### 更新源配置

后端默认从本仓库拉取更新，可通过配置 `pt.sites_update_url` 覆盖更新源地址：

```yaml
pt:
  # 站点配置更新源（GitHub release API），留空使用默认
  sites_update_url: "https://api.github.com/repos/linyuan0213/nexus-media-sites/releases/latest"
```

也支持环境变量 `PT__SITES_UPDATE_URL`。自定义更新源需返回与 GitHub release API 兼容的结构（`tag_name` + `assets[].browser_download_url`，或 `tag_name` 可拼装下载地址）。

---

## 添加站点

### 1. 判断站点类型

| 类型 | 判定条件 | 目录 |
|------|---------|------|
| **API 站点** | 站点提供搜索 API（如馒头 M-Team、Rousi、TorrentLeech） | `sites/api/{id}.json` |
| **HTML 站点** | 无 API，需要网页抓取解析（大多数 PT 站） | `sites/html/{id}.json` |

### 2. 复制同类型模板

复制一个同类型的现有站点作为起点，参考其结构修改。

### 3. 填写必填字段

所有站点都必须包含：

```json
{
  "id": "site_id",
  "name": "站点显示名称",
  "domain": "example.com"
}
```

- `id`：站点唯一标识，小写字母/数字/`-`/`_`
- `name`：站点显示名称（中文亦可）
- `domain`：主域名，用于 URL 匹配。可带或不带协议（`www.example.com` 或 `https://example.com` 均可），后端统一按主机名匹配。站点有多个可用域名时，请一并填入 `domain_aliases`

**API 站点额外需要**（`sites/api/`）：

```json
{
  "api": {
    "base_url": "https://api.example.com",
    "auth": {"type": "api_key", "header_name": "x-api-key"},
    "endpoints": {
      "search": {"method": "GET", "path": "/torrents"}
    }
  }
}
```

**HTML 站点额外需要**（`sites/html/`）：

```json
{
  "html": {
    "search": {"paths": [{"path": "torrents.php", "method": "get"}]},
    "torrents": {
      "list": {"selector": "table.torrents > tr"},
      "fields": {
        "title": {"selector": "a[href*='details']"},
        "size": {"selector": "td:nth-child(5)"}
      }
    }
  }
}
```

### 4. 本地校验

```bash
uv run python validate.py
```

校验通过后才能提交（详见 [validate.py 使用说明](#validatepy-使用说明)）。

### 5. 提交并打 tag 发布

```bash
git add sites/
git commit -m "feat: 添加 XXX 站点支持"
git tag v$(date +%Y%m%d%H%M)
git push origin master --tags
```

tag 推送后 GitHub Actions 自动校验并打包 `sites-config.zip` 发布 release，后端下次启动（或手动更新）即生效。

---

## 公共字段

所有站点文件支持以下公共字段（`sites/api/schema` 与 `sites/html/schema` 均包含）：

| 字段 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `id` | ✅ | — | 站点唯一标识（建议与文件名一致） |
| `name` | ✅ | — | 站点显示名称 |
| `domain` | ✅ | — | 主域名，用于 URL 匹配（带不带协议均可） |
| `domain_aliases` | | `[]` | 域名别名列表，如主站多个入口 |
| `encoding` | | `"UTF-8"` | 页面编码，乱码时调整 |
| `public` | | `false` | 是否公开站点（BT 站/公开站点为 `true`，无需 Cookie） |
| `language` | | — | 站点语言过滤，如 `"zh"` |
| `favicon` | | — | 站点图标 URL，留空自动抓取 |
| `tid_pattern` | | `"\d+"` | 从 URL 提取种子 ID 的正则表达式 |
| `detail_page_url` | | — | 种子详情页 URL 模板，如 `/details.php?id={tid}` |
| `download` | | — | 下载配置（见下文） |
| `user_info` | | — | 用户信息/做种信息解析配置 |

示例（`sites/api/mteam.json`）：

```json
{
  "id": "mteam",
  "name": "M-Team",
  "domain": "kp.m-team.cc",
  "domain_aliases": ["kp.m-team.cc", "api.m-team.io", "xp.m-team.cc"],
  "tid_pattern": "\\d+",
  "detail_page_url": "/detail/{tid}",
  "encoding": "UTF-8",
  "public": false,
  "language": "zh"
}
```

---

## HTML 站点配置

### html.search（搜索请求）

```json
"search": {
  "paths": [
    {"path": "torrents.php", "method": "get"},
    {"path": "/search/{keyword}", "method": "post"}
  ],
  "params": {"search": "{keyword}"},
  "batch": {"delimiter": " ", "space_replace": "_"}
}
```

- `paths`：搜索路径列表，`{keyword}` 为搜索词占位；可配置多个路径依次尝试
- `method`：`get` 或 `post`
- `params`：请求参数，同样支持 `{keyword}` 占位
- `batch`：批量搜索配置。`delimiter` 为多关键词分隔符，`space_replace` 为空格替换符（有些站点将空格识别为 `_`）

### html.category（分类映射）

```json
"category": {
  "movie": [{"id": 401, "cat": "Movies", "desc": "电影"}],
  "tv": [{"id": 402, "cat": "TV", "desc": "电视剧"}, {"id": 405, "cat": "TV/Anime", "desc": "动漫"}]
}
```

- `movie` / `tv` / `anime`：媒体类型到站点分类 ID 的映射
- `id`：站点内部分类 ID（字符串或数字）
- `cat`：分类显示文本（供前端展示）
- `desc`：分类描述
- 无分类的站点可留空 `"category": {}`（如 Nyaa）

### html.torrents（种子列表解析）

```json
"torrents": {
  "list": {"selector": "table.torrents > tr"},
  "fields": {
    "title": {"selector": "a[href*='details']"},
    "size": {"selector": "td:nth-child(5)"},
    "seeders": {"selector": "td:nth-child(6)"}
  }
}
```

- `list.selector`：匹配每一行种子的 CSS 选择器
- `fields`：字段解析规则，key 为字段名，value 为解析配置

#### 常用字段

`id`、`title`、`details`、`download`、`enclosure`、`poster`、`size`、`seeders`、`leechers`、`grabs`、`date_elapsed`、`date_added`、`date`、`pubdate`、`downloadvolumefactor`、`uploadvolumefactor`、`free_deadline`、`imdbid`、`labels`、`category`、`description`、`csrf`

#### 字段解析语法

```json
"title": {
  "selector": "a[href*='details']",   // CSS 选择器或 XPath
  "attribute": "title",               // 提取的属性（href/src/data-orig...），不填取文本
  "filters": [{"name": "re_search", "args": ["\\d+", 0]}],  // 后处理过滤器
  "case": {"img.pro_free": 0, "*": 1}, // 条件映射（详见下文）
  "optional": true,                   // 该字段缺失是否允许
  "remove": "img,a,b,span",           // 提取前移除的子元素
  "text": "{{ fields['title'] }} 1080P", // Jinja2 模板合成
  "default_value": "now",             // 字段缺失时的默认值
  "default_value_format": "%Y-%m-%d %H:%M:%S"  // 默认值格式（如 now/today 时间格式）
}
```

- `selector`：CSS 选择器或 XPath（`//` 开头）
- `attribute`：要提取的属性名；不填则取元素文本
- `filters`：值后处理过滤器（见 [过滤器列表](#过滤器列表)）
- `case`：条件映射——按 `selector`（未指定则按元素 class 匹配）是否命中映射键，命中返回对应值，`"*"` 为兜底默认值。常用于免费/2x 上传标记解析：

  ```json
  "downloadvolumefactor": {
    "case": {"img.pro_free": 0, "img.pro_free2up": 0, "img.pro_50pctdown": 0.5, "*": 1}
  }
  ```

- `text`：Jinja2 模板，可引用其他字段（`fields['title']`），并与 `filters` 配合做日期解析
- `remove`：提取文本前要移除的子元素，用于清理噪音

#### 日期字段

多数站点提供相对时间（`date_elapsed`，如 "3 hours ago"）和绝对时间（`date_added`，通常在 `title` 属性中）。推荐组合解析：

```json
"date_elapsed": {"selector": "td.rowfollow:nth-child(4) > span", "optional": true},
"date_added": {"selector": "td.rowfollow:nth-child(4) > span", "attribute": "title", "optional": true},
"date": {
  "text": "{% if fields['date_elapsed'] or fields['date_added'] %}{{ fields['date_elapsed'] if fields['date_elapsed'] else fields['date_added'] }}{% else %}now{% endif %}",
  "filters": [{"name": "dateparse", "args": "%Y-%m-%d %H:%M:%S"}]
}
```

> `date` 字段优先取 `date_added`（绝对时间）否则 `date_elapsed`（相对时间），两者都缺失时用 `now`。`dateparse` 过滤器为历史兼容写法，实际日期归一化由后端统一处理。

### html.conf（种子属性抓取规则，详情页）

```json
"conf": {
  "FREE": ["//h1[@id='top']/b/font[@class='free']"],
  "2XFREE": ["//h1[@id='top']/b/font[@class='twoupfree']"],
  "HR": ["//h1[@id='top']/img[@class='hitandrun']"],
  "PEER_COUNT": ["//div[@id='peercount']/b[1]"],
  "PUBDATE": ["//td[@class='rowfollow' and contains(., '发布于')]/span/@title"]
}
```

- `FREE` / `2XFREE` / `HR` / `PEER_COUNT` / `PUBDATE`：详情页 XPath 列表，任一命中即认为具备该属性
- 不支持的属性留空数组即可

### html.browse / parser_type

```json
"html": {
  "browse": {"path": "torrents.php", "params": {"cat": 401}, "start_page": 0},
  "parser_type": "flat"
}
```

- `browse`：浏览模式配置，用于非搜索场景获取种子列表（如按分类浏览）
- `parser_type`：`flat`（单层列表）/ `nested`（嵌套分组）

### download（下载配置，HTML 站点）

```json
"download": {
  "type": "html",
  "selectors": {"download": {"xpath": "//a[contains(@href,'magnet:')]/@href"}}
}
```

- `type`：`html`（从详情页用选择器提取下载链接）或 `template`（URL 模板）
- `selectors.download.xpath`：提取磁力链/下载链接的 XPath

---

## API 站点配置

### api（核心）

```json
"api": {
  "base_url": "https://api.m-team.io",
  "auth": {
    "type": "api_key",          // api_key | bearer | cookie | csrf | passkey | token
    "header_name": "x-api-key"  // api_key/bearer 的 header 名
  },
  "endpoints": {
    "search": {...},
    "detail": {...},
    "test_connection": {...},
    "user_info": {...}
  }
}
```

- `base_url`：API 基础地址
- `auth.type`：认证方式。`api_key`（header 传密钥）、`bearer`（Bearer token）、`cookie`（`token_source` 指定 cookie 键名）、`csrf`（`csrf_url` + `csrf_selector` 获取 token）
- `endpoints`：至少包含 `search`；`detail`/`test_connection`/`user_info` 可选

### endpoint（请求端点）

```json
"search": {
  "method": "POST",
  "path": "/api/torrent/search",
  "params": {"page": "{page_1}"},
  "body": {"keyword": "{keyword}", "pageNumber": "{page_1}"},
  "mode_mapping": {"MOVIE": {"mode": "normal"}, "TV": "tvshow"},
  "response": {
    "total_key": "data.total",
    "items_key": "data.data",
    "item_mapping": {...}
  }
}
```

- `method`：`GET` / `POST`
- `path`：请求路径，支持占位符 `{keyword}`、`{page}`/`{page_1}`（从 1 开始）、`{tid}`
- `params` / `body`：查询参数 / 请求体，同样支持占位符
- `mode_mapping`：按媒体类型覆盖请求参数——`MOVIE`/`TV`/`ANIME` 映射为对象（整体覆盖 body）或字符串/数组
- `response`：
  - `total_key` / `items_key`：总数与列表的 JSON 路径（点号分隔）
  - `item_mapping`：列表项字段映射（见下文）

### item_mapping（字段映射）

```json
"item_mapping": {
  "title": {"source": "name"},
  "size": {"source": "size"},
  "seeders": {"source": "status.seeders"},
  "download": {
    "type": "api",
    "method": "POST",
    "path": "/api/torrent/genDlToken",
    "body": {"id": "{id}"},
    "response_key": "data"
  },
  "uploadvolumefactor": {
    "type": "mapping",
    "source": "status.discount",
    "map": {"FREE": 1.0, "NORMAL": 1.0}
  },
  "imdbid": {
    "source": "imdb",
    "filters": [{"name": "regex", "args": ["tt\\d+", 0]}]
  },
  "page_url": {
    "type": "template",
    "value": "https://{domain}/detail/{tid}",
    "fields": {"tid": "id"}
  }
}
```

每种映射类型：

| `type` | 说明 | 关键字段 |
|--------|------|---------|
| （默认） | 从 JSON 取源值 | `source`（点号路径）、`filters`、`transform` |
| `mapping` | 值映射表 | `source` + `map`（源值 → 目标值） |
| `constant` | 固定值 | `value` |
| `template` | URL/文本模板 | `value` + `fields`（字段名 → 源字段路径） |
| `api` | 需要额外 API 请求 | `method`/`path`/`body`/`response_key` |
| `html` | 从 HTML 提取 | `selector` + `attribute` |
| `int` / `float` | 类型转换 | `source` |

- `source`：JSON 路径，点号分隔（如 `status.seeders`、`data.memberCount.uploaded`）
- `transform`：值转换。`item_mapping` 支持 `utc_to_local`（UTC 时间转本地）、`timestamp_to_date`（时间戳转日期）、`num_filesize_B`（字节数转文件大小）、`split_map`（按分隔符拆分后查 `map` 映射）；`user_info.field_mapping` 额外支持 `map_value`（值映射）
- `filters`：与 HTML 站点相同的过滤器

### download（下载配置，API 站点）

```json
"download": {
  "type": "api",            // api | api_chained | template | html
  "method": "POST",
  "path": "/api/torrent/genDlToken",
  "body": {"id": "{tid}"},
  "response_key": "data",   // 响应中提取下载链接的 JSON 路径
  "download_url": "https://cdn.example.com"  // 下载域名/前缀覆盖（可选）
}
```

- `type: api`：调用 `path` 获取下载地址，`response_key` 指定返回 JSON 中下载链接的路径
- `type: api_chained`：先获取下载 token，再拼接实际下载地址（支持 POST + token 放在 URL 中）
- `type: template`：直接拼 URL 模板
- `type: html`：用 `selectors` 从详情页提取

### torrent_attr / subtitle / user_info

```json
"torrent_attr": {
  "method": "POST",
  "path": "/api/torrent/detail",
  "body": {"id": "{tid}"},
  "response": {
    "free_key": "data.status.discount",
    "free_value": "FREE",
    "2xfree_key": "data.status.discount",
    "2xfree_value": "FREE_2X",
    "peer_count_key": "data.status.seeders",
    "peer_count_type": "int"
  }
}
```

```json
"subtitle": {
  "type": "api",
  "list": {"method": "GET", "path": "/api/subtitle/list", "params": {"torrentId": "{tid}"}, "response_key": "data"},
  "genlink": {"method": "GET", "path": "/api/subtitle/genlink", "params": {"torrentId": "{tid}", "subtitleId": "{subtitle_id}"}},
  "download": {"method": "GET", "path": "/api/subtitle/dlV2", "params": {"torrentId": "{tid}", "subtitleId": "{subtitle_id}"}}
}
```

```json
"user_info": {
  "type": "api",
  "profile": {
    "method": "POST",
    "path": "/api/member/profile",
    "body": {},
    "response": {
      "field_mapping": {
        "username": {"source": "data.username"},
        "upload": {"source": "data.memberCount.uploaded", "type": "int"},
        "bonus": {"source": "data.memberCount.bonus", "type": "float"},
        "user_level": {"source": "data.role", "transform": "map_value", "map": {"1": "Peasant", "2": "User"}}
      }
    }
  },
  "seeding": {
    "method": "POST",
    "path": "/api/member/getUserTorrentList",
    "body": {"userid": "{userid}", "pageNumber": "{page}", "type": "SEEDING"},
    "response": {"items_key": "data.data", "seeders_field": "torrent.status.seeders", "size_field": "torrent.size"}
  }
}
```

`user_info.field_mapping` 常用目标字段：`user_id`、`username`、`upload`、`download`、`ratio`、`bonus`、`user_level`、`join_at`、`leeching`、`seeding`、`message_unread`、`site_favicon`。

---

## 过滤器列表

`filters` 应用于字段提取结果，格式为对象，依次执行：

```json
"filters": [
  {"name": "re_search", "args": ["\\d+", 0]},
  {"name": "replace", "args": ["GB", "G"]}
]
```

| 名称 | 说明 | 示例 |
|------|------|------|
| `regex` / `re_search` | 正则提取，返回第 N 组匹配 | `{"name": "regex", "args": ["tt\\d+", 0]}` |
| `split` | 按分隔符拆分取第 N 段 | `{"name": "split", "args": ["-", 1]}` |
| `replace` | 字符串替换 | `{"name": "replace", "args": ["GB", "G"]}` |
| `strip` | 去除首尾空白 | `{"name": "strip"}` |
| `appendleft` | 前缀拼接 | `{"name": "appendleft", "args": "https://"}` |
| `querystring` | 从 URL 提取查询参数 | `{"name": "querystring", "args": "cat"}` |

> 历史配置中出现的 `trim`、`dateparse` 等名称会被解析器容忍（值原样保留，不报错），但实际生效的过滤器以上表为准。日期字段建议使用 `text` 模板组合 `date_elapsed`/`date_added` 并交由后端统一归一化。

---

## 站点维护

### 修改站点

站点上线后若站点改版导致解析失效、或域名变更，直接修改对应 JSON 文件：

- **搜索/解析规则变更**：修改 `html.search`、`html.torrents.fields` 或 `api.endpoints` 后本地校验、提交打 tag
- **域名变更**：修改 `domain`，并将旧域名保留在 `domain_aliases`（避免历史 Cookie 失效）：

  ```json
  {
    "domain": "new.example.com",
    "domain_aliases": ["old.example.com", "new.example.com"]
  }
  ```

- **新增备用入口**：加入 `domain_aliases`，如 `"ob.m-team.cc"`

### 删除站点

删除 `sites/` 下对应 JSON 文件即可。发布后后端更新会整体替换 `/config/sites/`，被删除的站点随之失效。

### 发布流程

1. 本地校验：`uv run python validate.py`
2. 提交（一个提交只做一件事）：

   ```bash
   git add sites/html/xxx.json
   git commit -m "feat: 添加 XXX 站点支持"
   ```

3. 打 tag 并推送：

   ```bash
   git tag v$(date +%Y%m%d%H%M)
   git push origin master --tags
   ```

4. 发布后后端生效方式（任选其一）：
   - 重启后端自动拉取
   - 系统设置 → 手动更新站点配置

> 站点适配更新无需发版后端，打 tag 即可生效。若改动较大，建议先在本地用浏览器调试抓取规则再发布。

---

## validate.py 使用说明

`validate.py` 是站点配置的校验脚本，提交前必须通过。

### 运行

```bash
# 项目根目录执行
uv run python validate.py

# CI 严格模式：警告也视为失败
uv run python validate.py --strict
```

（首次运行会自动创建虚拟环境并安装依赖。GitHub Actions 发布流程使用常规模式。）

### 输出示例

```
==================================================
站点配置 JSON Schema 校验
==================================================
共校验 110 个文件
全部通过 ✓
```

存在警告时（正常模式仍通过，`--strict` 下失败）：

```
共校验 110 个文件
发现 2 处警告（--strict 时视为失败）
  ⚠ html/chdbits.json: 字段 'hr_days' 未知配置键 'defualt_value'（拼写检查，参见 HTML_FIELD_KEYS）
  ⚠ html/pterclub.json: 文件名与 id 不一致（id='pterclubnet'），建议重命名为 pterclubnet.json
通过（存在警告）
```

出现阻塞错误时：

```
共校验 110 个文件
发现 1 处错误:
  ✗ html/xxx.json: [html.torrents] 'fields' is a required property
```

### 校验内容

**1. JSON Schema 校验（阻塞错误）**
- `sites/api/*.json` → `site-api.schema.json`
- `sites/html/*.json` → `site-html.schema.json`
- 每个文件必须为合法 JSON、满足对应 schema（必填字段、枚举值、字段类型）
- schema 间通过 `$ref` 相互引用（如 HTML 的 `download` 引用 API schema 的 `download_config`），本地 Registry 解析，不访问网络

**2. 语义检查**

| 级别 | 检查项 |
|------|--------|
| 错误 | 跨文件重复的站点 `id` |
| 警告 | `id` 非小写 `[a-z0-9_-]`（id 变更会影响已配置站点，谨慎处理） |
| 警告 | 文件名与 `id` 不一致 |
| 警告 | HTML 字段配置中的未知键（可捕获 `defualt_value` 这类拼写错误） |
| 警告 | 未知/废弃的过滤器名（`trim`、`dateparse` 等为历史兼容写法，当前后端不生效） |
| 警告 | filters 使用字符串形式（后端只支持 `{"name": ..., "args": [...]}` 对象） |

- 警告不阻塞常规校验；CI 或发版前可用 `--strict` 将警告升级为失败
- 废弃过滤器按文件汇总为一条提示，避免刷屏

### 常见错误与排查

| 报错 | 原因 |
|------|------|
| `JSON 解析错误` | 文件不是合法 JSON（多余逗号、引号未转义等） |
| `'id' is a required property` | 缺少必填字段 `id`/`name`/`domain`（`html` 或 `api`） |
| `'paths' is a required property` | `html.search` 缺少 `paths` |
| `'search' is a required property` | `api.endpoints` 缺少 `search` |
| `'base_url' is a required property` | `api` 缺少 `base_url` |
| `X is not valid under any of the given schemas` | 字段值不符合枚举/类型约束（如 `method` 只能为 `get`/`post`） |
| `Unresolvable JSON pointer` | schema 文件缺失或被破坏，先检查 `sites/schema/` |
| `站点 id 重复` | 两个文件使用了相同的 `id`，后加载的会覆盖前者 |
| `未知配置键` | 字段配置键拼写错误，对照 schema 修正 |

### 修改 schema 的注意

`sites/schema/` 的 JSON Schema 是前后端约定，**修改前必须先确认后端解析器兼容**（后端内置 `config/sites/schema/` 需同步）。新增字段时建议使用 `additionalProperties` 默认放行（schema 未开启 `additionalProperties: false` 时，多余字段不会报错）。

---

## JSON Schema 说明

- `sites/schema/site-api.schema.json`：API 站点定义规范（`api`/`download`/`torrent_attr`/`subtitle`/`user_info`）
- `sites/schema/site-html.schema.json`：HTML 站点定义规范（`html.search`/`html.category`/`html.torrents`/`html.conf`，并复用 API schema 的 `download_config`）

schema 中 `$id` 为 `https://nexus-media/schema/*.json`，仅作引用标识，不访问网络。
