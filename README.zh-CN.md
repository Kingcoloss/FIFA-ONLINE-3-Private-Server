# FO3ID Private Server

[English](README.md) | [Bahasa Indonesia](README.id.md) | **简体中文** | [ไทย](README.th.md) | [Tiếng Việt](README.vi.md) | [한국어](README.ko.md)

> 本文译自 [README.md](README.md)。如有出入，以 README.md 为准。

这是 **FIFA Online 3 印尼版**（Garena，客户端版本 654420）的本地私服，用 Python 编写。Garena 已于
2020-06-30 关闭官方服务器；本项目重新实现了客户端所连接的后端，让游戏可以在一台电脑上离线游玩。

> 与 EA、Spearhead 或 Garena 无关。本仓库**不包含任何游戏文件**（没有客户端、数据库、素材或音乐），
> 你需要自己安装 FO3 ID 客户端。本项目**不**包含、修改或绕过客户端的反作弊（XIGNCODE3 / HackShield），
> 这不在项目范围内。仅用于游戏保存与研究。

游戏界面是印尼语。下文中的 Liga、Cup、Market、Tukar、Tim inti、Tim Cadangan、Item saya、Gudang 等
都是游戏里显示的界面名称，保留原文以便对照。

## 已可用的功能

已在真实客户端（印尼语界面）中测试：

- 登录 → 选择 / 创建经理（可从 501 个授权俱乐部中挑选）→ 大厅（FREEROAM）。
- **Single → Liga**（完整赛季：赛程、比赛、积分榜、奖励、升级）和 **Cup**（抽签、小组赛、淘汰赛、
  加时、点球大战）。
- **Market**（买 / 卖；球员卡价格取决于评分和强化等级：fifaaddict 上同评分所有球员卡的价格中位数）、
  **Upgrade**（强化等级 +1…+10）、**Tukar** 和 **Tukar Scout** 球员交易（所有 Market 球员卡，
  不只是本地区授权的）、Tim inti（主力队）/ Tim Cadangan（替补队）、阵容和战术保存。
- **Shop**（商城）所有标签页（球员卡包、消耗品、礼包、MP Shop、月卡礼包和连锁礼包、特别奖励），
  开卡包时随机强化等级，Item saya（我的物品）、Bag（礼物箱）、每日登录奖励。
  **Gudang**（Item saya > Gudang，仓库）：可把卡包和消耗品放进去再取回。
  额外卡包：**All Season +8**（任意赛季，+1…+8），以及 '07 和 fifaaddict 收录的每个赛季各一个卡包。
- 始终拥有 VIP + 官方网吧（IGR）特权，经理删除 / 恢复，'17 赛季球员卡。
- 阵型列表（俱乐部自己的阵型 + 游戏的 33 种常用阵型，读取自客户端的阵型表），以及经理 / 球员等级：
  每场比赛后获得 EXP，球员 LV.1-23（每级所有属性 +1），经理 LV.1-100。
- 游戏音效和 EA Trax 菜单音乐。`tools/eatrax_song.py` 可以把你自己的歌放到第一首，但之后游戏会在
  比赛结束后崩溃（见下文的已知问题）。
- 网页管理后台 http://127.0.0.1:8088/（EP、球员、卡包、礼物、每日奖励、比赛奖励、商城、日志），可切换语言
  （issue #15）：Bahasa Indonesia、English、简体中文、ไทย、Tiếng Việt、한국어；浏览器会记住你的选择。
- 比赛中显示真实的俱乐部球衣（kit id = `teamid << 5 | type`；旧的 `<< 10` 会显示成棋盘格）。
- 开启 **team color**（球队加成）时比赛可以踢完下半场（以前赛季加成会在中场时崩溃），之后显示 EXP 和
  奖励界面。

已添加并通过测试，但尚未在客户端中验证：

- **team color** 加成本身：首发 11 人中来自同一俱乐部的球员获得 OVR 加成（4-5 人 +1，最高 10-11 人
  +4），同一国家或同一赛季（5-6 人 +1，最高 9-11 人 +3）；每名球员只取最高的一项。
- **Opsi > Kontrol**（键盘和手柄按键）可以保存：服务器总是发送游戏自带的默认按键布局，因此该界面可以
  应用并保存修改（以前修改会丢失）。
- 比赛设置界面中的**球衣选择**（每方主场 / 客场）会用于比赛。
- **选择经理**界面显示俱乐部身价最高的球员，穿着俱乐部球衣（以前显示游戏默认的巴塞罗那球员）。
- 修复的崩溃：启动公告弹窗（网页 URL 为空）、Beginner's Guide 联赛教程（缺少脚本）。
- **强化成功率**：按目标等级的基础成功率，乘以 Upgrade 标签页根据材料卡等级显示的
  "Rasio bonus keberhasilan" 标签（Kosong x1、Low x1.1、Normal x1.25、High x1.5）。从 +5 及以上
  强化失败会掉一级。
- **Top 200 卡包**：额外卡包现在给出该赛季最好的 200 张卡（"17 Top 200"、"07 Top 200" 等）；
  **All Season Top 300 +8** 给出任意赛季评分 81 及以上的卡。
- **用 +0 卡强化**（issue #5）：俱乐部自己的 +0 卡可以 100% 保住目标卡的等级（+4 用 +0 仍是 +4），
  +10 卡也可以使用；被保留的卡占用被消耗卡的阵容位置时会离开 Tim Cadangan。
- **Upgrade 2.5**（客户端较新的强化界面，`features...enhancement.v2_5`）：
  - **强化点数**：强化失败会获得点数；"Gunakan poin" 消耗点数换取 +10%；可在 Shop > Paket 免费购买更多
    （Upgrade Point 100 / 500 / 1.000）；
  - **加成道具** Enhancement Boost Gold / Silver / Bronze（+15 / +10 / +5%），在 Shop > Dapat dikonsumsi
    中免费；
  - 永久的**强化活动**（目标 +1…+9 时 +10%，`GET /events`）；
  - "Coba pengembalian lagi" 可以用点数找回因失败而掉的等级。
- **Tukar v2**（`trade2`）：交易按价值（TP）分为 15 级，每级有最高出价等级；标签页显示其他经理"昨天"
  在该等级得到了什么；传奇赛季球员卡按 1.5 倍计算；没有每日或价值上限。Tukar Scout 仍可同时使用。
- **Tukar Scout**：客户端另外两个球探，Scout Khusus（活动；传奇赛季任务）和 VVIP Scout（最佳报价；
  10 亿 EP 任务）。去掉了 Scout Amatir，使列表正好放下 5 行（以前列表可以滚动时，完成的任务会点亮
  别的球探卡，或者都不亮）。
- **强化等级球队加成**（客户端中的 "Upgraded Team"）：强化等级 +2、+5 或 +8 及以上的首发球员；
  5-6 / 7-8 / 9-11 人分别给 +1 / +2 / +3、+2 / +3 / +4 和 +3 / +4 / +5 OVR。单一等级的加成
  （"+3 club" … "+10 Golden summit"）需要 11 名首发全部达到该等级或更高：+4（club +3/+4）、
  +5（silver +5…+7）、+6（Golden passion +8/+9）、+7（Golden summit +10）。球员在最佳俱乐部 / 国家 /
  赛季加成之上，再获得他最好的强化加成。
- **客户端中有名称的所有 team color**（现有 188 个）：
  - 27 个俱乐部（Real Madrid … Jeonbuk）：Single team 的档位，加上游戏提示中该俱乐部自己的加成，
    例如 Barcelona MF agility +3；
  - 30 个国家：Satu Negara 的档位，加上例如 Spanyol MF ball control +2；
  - 使用游戏中名称的赛季加成（World Best 最高 +5、World Legend、2014 WC All-Star 等）；
  - 约 75 个特殊加成：'14 WC 和 EC 各国家、nation BEST、MSN / BBC Trio、Arsenal Invincibles、
    Galácticos、LEGENDS、TOP 100、Power Header、New Star 等。

  原本的加成数值和球员名单是服务器数据，已经丢失。球员名单来自球员数据库（赛季、俱乐部、点名的球员、
  属性限制）；加成数值来自游戏中仍保留的一行提示。未加入：[Test] 加成、"+2~7"、"14 WC Single Nation"
  和四个重复的俱乐部条目。
- **Formasi**（阵型）打开时不再提示 "Tidak cukup pemain"（球员不足）（它会加载服务器从未发送过的预设
  阵容 1）。首发中的空位（issue #7，同一球员的两张首发卡互相强化）会由替补补上，替补席也不会出现同一
  球员的第二张卡。每名首发都会得到 `starting` 数据（积极性和场上位置）：没有它游戏会把他显示在替补席。
- **Tim > Peran** 会保存队长和每个定位球主罚者（issue #8：缺少 `PUT /game/my/team/captain` 和
  `/game/my/team/kickers/<0-4>`）。五个主罚位置（左侧角球、右侧角球、任意球、点球、任意球 2）保持不变；
  空位由一名首发补上。
- **Tim > Locker room**（更衣室）可用（issue #13）：球衣款式和袖子、纹身、护腕、手套（门将：39 种手套
  设计）、球袜、护膝、按品牌分类的 614 双球鞋，以及球衣号码（选用一个号码会与原佩戴者互换）。之前缺少
  物品表 `/static/db/LOCKERROOMITEM`，所以每个列表都是空的，球鞋面板也会出错。球员的外观保存在球员卡上，
  Item saya 中有一张永久更衣室券，游戏需要它才能在比赛中显示这些外观。护腕、手套和护膝只提供客户端
  自带的模型（各一个）。
- **管理后台的商城控制**（issue #10）：商城所有标签页（球员卡包、消耗品、礼包、月卡礼包、推荐、
  MP Shop、特别奖励、连锁礼包）。可以新建卡包（按赛季、前 N 名、OVR、最高强化等级、位置、联赛）、
  随机箱、EP 卡、礼包和月卡礼包，可使用客户端 147 个商城图标中的任意一个。自带商品可以修改、隐藏或
  设置固定价格，整个商城也可以设为免费或收费。修改保存在 `gamedata/shop.json`。
- **Simulasi Liga**（联赛模拟）券（物品 2001，Shop > Dapat dikonsumsi）：Liga 的 Simulasi 按钮不用踢就
  直接给出比赛结果，每场比赛一张券。模拟界面会按结果播放比赛的进球、射门、扑救和红黄牌（之前
  `eventlist` 为空，所以显示 0-0），之后的结果界面显示比分、球员评分和数据、控球率和 MOTM（以前是空白），
  然后是 EP 奖励并回到 Liga 菜单。该按钮会统计 Item saya 中的券数，以前因为没有这个物品而一直不可用。
  可在管理后台新建券（类型"联赛模拟券"）。
- **赛前阵容界面**（Liga 和 Cup，issue #16）：换位、换人和阵型修改现在会保留并保存到俱乐部（之前
  `PUT /match/<id>/side/<side>/squad` 没有处理程序，所以每次修改都会自动撤销）。阵型列表有了内容，
  体力条显示为满（比赛之间不保留疲劳）。
- **球队 FW / MF / DF 能力值与球员一致**（issue #18）：在阵容界面和大厅中，它是球员列表所显示能力值的平均值
  （球员所在位置的能力值，加上强化等级、等级和队伍颜色）。之前用的是球员卡的基础能力值，大约低 12。
- **联赛记录各标签页**（issue #19）：积分榜可以显示了（之前缺少 `league2difficulty` 表，标签页出错；这张表现在也决定赛季
  结束时的升级和降级）。我的记录列出本赛季已踢比赛中每名球员的出场、评分、进球、助攻、传球、抢断和扑救，综合记录显示
  本赛季最佳 11 人和各项数据领先者。只统计自己的球员，模拟比赛不增加球员数据。
- **Formasi 中的 Squad A / B / C**（issue #20）：阵型按钮左边的框用来选择三套保存的阵容之一（之前是空的，因为服务器
  没有发送阵容数量）。每套阵容保存自己的首发、阵型和角色。
- **控制器和视角设置在比赛中保持**（issue #21）：在 Opsi > Konfirmasi 之后，游戏会从服务器回复中读回保存的选项，
  之前回复里没有，所以每场比赛都会回到登录时的选项（键盘、旧视角）。比赛中按 F3-F9 切换视角（F5 = Co-op）。
- **Ganti tim（更换球队）显示俱乐部和你的球员**（issue #23）：这个道具的俱乐部界面现在显示联赛、德比对手、主场、
  建立年份和容纳人数，并显示你的球员穿新俱乐部球衣的样子，以及出生日期、身高和体重。之前服务器的俱乐部信息里没有
  这些内容，没有球衣时 3D 球员也不会显示。
- **视角高度和缩放可以调整**（issue #24）：Opsi > Kamera setting 里的 Customise 刻度（高度和缩放；Pro 视角为缩放、速度和
  摆动）之前没有数值也无法调整，因为服务器发送的视角设置是空的。现在从 10 开始（最大 20）。
- **Tim lain 里有所有国家队**（issue #24）：International 联赛（列表中最后一个国家）有 40 支国家队，包括意大利、
  英格兰、德国、西班牙和法国。国家队阵容取自每名球员的国家队关联；之前只列出球员没有授权俱乐部的国家队。
- **结果画面的球员位置**（issue #26）：比赛结束后，结果画面的球场把所有球员都叠在球门处，因为游戏把每名球员都
  报告为门将。现在服务器按阵容位置给每名球员设置位置。
- **赛后奖励卡**（issue #26）：奖励画面的卡片之前是空的。现在会发三张卡：你选的那张给 EP（1,000 到 10,000）、
  球员包（Semua Pemain 或 '14 Top 200）或 Lucky EP 道具，另外两张显示本可以得到的奖励。
- **选秀卡包和经验胶囊**（issue #27）：Shop > Pak pemain 出售选秀卡包（"06 Draft Pick 3"、"2017 Draft Pick 5"、
  "World Legend Draft Pick 3"）。"Gunakan" 打开挑选球员界面，默认填入该赛季最值钱的卡；挑选该赛季的 N 张卡
  （可按名字、联赛或俱乐部搜索），然后打开其中一张。Shop > Dapat dikonsumsi 出售经验胶囊（1,000、5,000、
  Max = LV.23、一个限 LV.10 及以下、一个限 2017 卡）：选一名球员，他获得这些经验。选秀界面的请求
  （`/item/draftpack/<id>/players/<n>`、`/transfer/price/default/<grade>`）和胶囊道具类型之前都没有。
  管理页面可以再做更多（卡包的 "Draft" 栏位，道具类型 "EXP Capsule"）。
- **随机箱可以打开**（Kotak Platinum 等，issue #12）：箱子界面从 `staticdata.availables` 列出奖品，
  之前缺少这个字段，所以每个箱子在 "Gunakan"（使用）时都会失败。
- **新球员卡进入 Tim Cadangan**：从卡包、交易、Market、Bag 或管理后台得到的卡，在 Skuad 的 Tim 一栏显示
  "-"，可以直接用于 Tukar Scout。点卡上的按钮可把它移到 Tim inti（绿色 RES：18 人大名单之外的 Tim inti），
  Tim inti 可以容纳整个俱乐部（200 人）。管理后台可以一次把 Tim Cadangan 的球员全部移到 Tim inti。
- **Market 搜索**可以找到所有赛季的球员卡：游戏只搜索 `/static/roster` 中的赛季，而其中缺少 29 个有
  Market 球员卡的赛季（World Legend、World Best、'14 TOTS 等），所以例如 WL R. Gullit 从来搜不到。
  Market 筛选的赛季列表可以用了（issue #14：选择赛季时报错 "cannot convert 39 to Array"，因为每个赛季的
  `value` 必须是列表），并显示客户端的赛季名称（World Legend、02 Chinese Legend 等）。
- **所有可交易的球员卡**都出现在 Market、交易和卡包中：只要 fifaaddict 收录或游戏自身标记为可交易
  （`permid.transferable`），就算在内。只用 fifaaddict 会漏掉 6,599 张卡（其中 4,313 张是 '17）；
  Market 现有 44,703 张。新的 **Semua Pemain**（所有球员）卡包可以开出其中任何一张。
- **Tim > Klub > Informasi tim**（issue #9）显示成立日期、主场球场和"建造年份 / 容量"
  （`coach.career`、`coach.stadium`、来自客户端球场表的 `GET /stadium/<id>`），以及球员面板（切换器、
  3D 球员、价格、强化等级），没有球场数据时它一直是空的。客户端数据库中的名称按 UTF-8 读取
  （`tools/re/eadb.py` 以前按 latin-1 读取）。
- **开卡包光效**随卡的价值变化：低于 1000 万 EP 没有光效，从 1000 万、1 亿和 10 亿 EP 起分别为 1-3 级。

已知问题，尚未解决：安装了 `tools/eatrax_song.py` 写入的自定义 EA Trax 歌曲后，每场比赛结束、Cup 界面
或大厅重新加载时，游戏会耗尽 RAssets 内存池（崩溃于 `FifaRNA::Crowd::PlacementData::Seats[]`）；使用
游戏自带的音乐则不会。把歌曲做成原始 PCM（37.7 MB）、作为第 10 首加入的 EALayer3（6.5 MB，
`tools/re/ealayer3.py`）、以及替换 TrackID 1 且音乐库比原版更小的 EALayer3，都会同样崩溃，所以原因不是
音乐大小。请使用游戏自带的音乐：`python -I tools/eatrax_song.py --restore` 可以恢复。

尚未实现：在线模式（排位、友谊赛、King of the Hill）、Road to World、联赛模拟。

## 运行需求

- Windows、Python 3.12、`pip install cryptography`（messenger + 数据库提取需要）。
- 已安装的 FO3 ID 客户端（默认路径 `D:\FO3ID\32795`；装在别处时把 `FO3_GAME` 设为该文件夹；如果在那里
  找不到客户端的图片缓存，服务器启动时会给出警告）。
- 可选：ffmpeg（只有 `tools/eatrax_song.py` 需要）。

## 安装

1. 从你的客户端提取球员数据库：
   `python extract_fifadb.py D:\FO3ID\32795` → `gamedata/fifadb.sqlite`。
2. 可选的市场价格：`python tools/fa_sync.py` → `gamedata/fa_prices.json`（礼貌抓取 fifaaddict.com；
   没有它时价格按评分公式计算）。
3. 为客户端写死的 API 主机 `APSEODESK172` 生成 TLS 证书（接受自签名证书）：

   ```
   openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=APSEODESK172" -addext "subjectAltName=DNS:APSEODESK172" -keyout key.pem -out cert.pem
   python -c "open('certs/server.pem','w').write(open('cert.pem').read()+open('key.pem').read())"
   ```

4. hosts 文件（以管理员身份）：`127.0.0.1 APSEODESK172`。
5. 编译一次启动器（`launcher/fifalauncher.cs`，编译命令写在文件里），然后双击 **`play.bat`**：它会打开
   服务器窗口（`python start_all.py` = `http_config.py 443 --tls` + `messenger.py`；关闭该窗口即停止
   服务器），并在不弹出 UAC 提示的情况下启动游戏。

6. 也可以手动：先运行 `python start_all.py`，再用服务器参数启动客户端（即
   `launcher/fifalauncher.exe` 和 `launch_game.ps1` 传入的参数）：

   ```
   fifazf.exe -QUICKMATCH/SERVER=127.0.0.1:28000 -QUICKMATCH/PROTOCOL=tcp -QUICKMATCH/NOTISERVER=127.0.0.1:28001 -FIFA/LAUNCHER/PID=<pid> -PUBLISHER/GARENA/TOKEN=testtoken -LOCALE/PUBLISHING_REGION=ID -DUMPTRUCK/SERVER=127.0.0.1 region id token testtoken
   ```

## 文件

| 文件 | 作用 |
|---|---|
| `http_config.py` | 客户端调用的 REST 后端（`https://APSEODESK172`）：登录、账号、经理、创建俱乐部、阵容、联赛、杯赛、市场、强化、交易、商城、物品、Bag、每日奖励、静态表，以及 `/cdn/`（从客户端自己的 `_cache` 提供队徽和球员卡）。数据保存在 `gamedata/state.json`。环境变量：`FO3_LANGUAGE`（默认 `ind`）、`FO3_GAME`（客户端文件夹）、`FO3_ASSETS`、`FO3_HALF_LENGTH`、`FO3_ADMIN_PORT`。 |
| `messenger.py` | 通知服务器，端口 `:28002`。帧格式 `<u16 LE len><u16 type=2><Blowfish-CBC(key "kueec", IV 0) of JSON+"\n">`；响应 `auth`、`ping`、`signon`。`python messenger.py --selftest`。 |
| `admin.py` + `admin/index.html` | 管理后台（由 `http_config.py` 启动，仅限本机访问，无密码）。其商城标签页保存到 `gamedata/shop.json`。页面上的所有文字（包括错误信息）都在 `admin.py` 末尾的 `I18N` 表中，每种语言一张表；新增语言只需再加一张表，`python admin.py` 会检查所有表的键是否一致。 |
| `responses/` | 各接口的 JSON 响应体（`/a/b/c` → `responses/a_b_c.json`，每次请求重新读取）。结构来自客户端的 AS3 代码。 |
| `extract_fifadb.py` | 客户端球员数据库（`data_0.big`，RefPack + Blowfish）→ SQLite。 |
| `gen_teams.py` | 根据 `gamedata/fifadb.sqlite` 生成初始阵容和俱乐部概要。 |
| `tools/eatrax_song.py` | 把一首歌以 EALayer3 格式放到 EA Trax 菜单音乐的第一首，替换 TrackID 1（以追加方式修改 `data_0.big` / `data_1.big`；`--restore` 恢复原文件）。会导致比赛后崩溃，见已知问题。 |
| `tools/fa_sync.py` | 同步 fifaaddict.com 价格。 |
| `tools/fa_faces.py` | 补充客户端缓存中缺少的球员小头像（fifaaddict 提供同样的 128x128 PNG）；`--crests` 补充缺少的俱乐部队徽（大多数俱乐部在缓存中没有，游戏会显示默认队徽）。可断点续传，`--remove` 撤销。 |
| `tools/re/` | 逆向工程辅助工具：`bigdir.py`（BIg4 归档表）、`refpack.py`（RefPack 编解码）、`eadb.py`（EA "DB" 数据库表）、`abc*.py`（AS3 字节码解析 / 搜索 / 结构挖掘）、`gfxx.py`（界面 SWF）、`memgrab.py`、`gamectl.ps1`（测试时操控客户端窗口）。 |
| `blaze.py`、`server.py`、`test_client.py`、`analyze_capture.py` | 项目第一阶段的 EA Blaze 帧格式（Fire/TDF）和回环测试服务器；后来发现客户端用的是 REST + messenger。 |
| `analysis/` | 早期的客户端分析脚本（字符串、PE 节、网络接口）。 |
| `FO3ID-private-server.md`、`reports/` | 研究发现和进度报告（`reports/` 为印尼语）。 |

## 测试

```
python run_tests.py
```

运行 Blaze/回环自测和 `test_league.py`；后者用一个新账号走一遍所有后端功能（创建俱乐部、联赛、杯赛、
市场、强化、交易、商城、每日奖励、管理 API、删除经理）。需要 `gamedata/fifadb.sqlite`。

## 贡献者

- **SoloPlayer** — 项目所有者，在真实客户端中测试。
- **Claude**（Anthropic 的 AI 助手，通过 Claude Code）— 逆向工程和大部分服务器代码，与项目所有者共同编写。

## 许可证

本仓库中的代码和文档使用 [GNU GPL v3](LICENSE)。FIFA Online 3 及其客户端、数据、素材和音乐归各自的
所有者所有，不在此许可范围内。
