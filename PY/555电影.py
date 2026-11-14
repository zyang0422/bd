# -*- coding: utf-8 -*-
"""
555电影 · TVBox / 影视仓 Python 源（Java/python 通用写法：requests + re）

站点特征：苹果CMS v10 + mxtheme 模板，SSR 直出，无加密壳、无 JS 挑战
防御等级：Lv.1「轮海·彼岸」（只有常规 UA/Referer 校验，没有反爬硬拦截）

【成人分区已硬排除】本文件只抓 电影/连续剧/综艺纪录/动漫/短剧 五个分类，
tid=124（福利）与「午夜蓝光」外链不进入任何分类、筛选或搜索结果；
另加关键词兜底，防止成人条目从正常分类漏进来。

可用端点（实测）：
  分类   /vodtype/{tid}.html                  分页 /vodtype/{tid}-{pg}.html
  筛选   /vodshow/{tid}-{area}-{sort}-{class}-{lang}----{page}---{year}.html
         段1=tid 段2=地区 段3=排序 段4=类型 段5=语言 段9=页码 段12=年份
  详情   /voddetail/{id}.html                 播放源 tab 在 module-tab-item
  播放   /vodplay/{id}-{sid}-{nid}.html       页内 player_aaaa 明文 JSON，直接取 url
  搜索   /vodsearch/{关键词}-------------.html
  不可用 /index.php/ajax/data（返回空）、/index.php/ajax/suggest（返回空）、/search/（404）

自检：python 555电影_spider.py
"""

import re
import json
import html as htmllib
import urllib.parse

import gzip
import urllib.error
import io
import urllib.request

try:
    import requests
except Exception:      # 部分壳子的 python 环境没装 requests，退回标准库
    requests = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def init(self, extend=""):
            pass


# ---------------- 配置 ----------------

BASE = "https://555kp23.com"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# 诊断模式：多一个「诊断」分类，直接显示首页请求的状态码/条数/耗时。
# 排查阶段保持 True；确认能用了改成 False，这个分类就消失。
DIAG = False

# 只开放这五个非成人分类
CLASS_LIST = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "连续剧"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "3", "type_name": "综艺纪录"},
    {"type_id": "126", "type_name": "短剧"},
]
if DIAG:
    CLASS_LIST.append({"type_id": "diag", "type_name": "诊断(可删)"})

# 硬排除：成人分类 tid（124=福利，指向镜像域名的韩国伦理分区）
ADULT_TIDS = {"124", "125", "127", "128"}
# 标题/类型兜底黑名单：命中即丢弃，防止成人条目串进正常分类
ADULT_WORDS = ("伦理", "成人", "福利", "三级", "情色", "午夜", "援交",
               "淫", "性爱", "做爱", "裸", "强奸", "迷奸", "偷拍", "无码")

# 筛选兜底（站点取不到时用）
FB_AREA = ["大陆", "香港", "台湾", "美国", "日本", "韩国", "英国", "法国",
           "德国", "印度", "泰国", "俄罗斯", "加拿大", "澳大利亚"]
FB_YEAR = [str(y) for y in range(2026, 2009, -1)]
FB_CLASS = ["剧情", "动作", "喜剧", "爱情", "科幻", "恐怖", "悬疑", "惊悚",
            "犯罪", "战争", "冒险", "奇幻", "武侠", "古装", "历史", "纪录片"]

# 静态筛选表（从站点的 /vodshow/ 筛选条抓下来后写死，首页不再发请求，秒出）
FILTERS_DATA = {
    "1": {
        "area": ["大陆", "香港", "台湾", "美国", "日本", "韩国", "英国", "法国", "德国", "印度", "泰国", "丹麦", "瑞典", "巴西", "加拿大", "俄罗斯", "意大利", "比利时", "爱尔兰", "西班牙"],
        "genre": ["Netflix", "仙侠", "剧情", "科幻", "动作", "喜剧", "爱情", "冒险", "儿童", "歌舞", "音乐", "奇幻", "动画", "恐怖", "惊悚", "丧尸", "战争", "传记", "纪录", "犯罪", "悬疑", "西部", "灾难", "古装", "武侠", "家庭", "短片", "校园", "文艺", "运动", "青春", "同性", "励志", "人性", "美食", "女性", "治愈", "历史", "真人秀", "脱口秀"],
        "year": ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016", "2015", "2014", "2013", "2012", "2011", "2010", "2009", "2008", "2007", "2006", "2005", "2004", "2003", "2002", "2001", "2000", "90年代", "80年代", "70年代"],
    },
    "2": {
        "area": ["大陆", "香港", "韩国", "美国", "日本", "法国", "英国", "德国", "台湾", "泰国", "印度", "其他"],
        "genre": ["Netflix", "短剧", "剧情", "丧尸", "仙侠", "穿越", "惊悚", "恐怖", "言情", "科幻", "动作", "喜剧", "爱情", "偶像", "都市", "军旅", "谍战", "罪案", "宫廷", "冒险", "儿童", "歌舞", "音乐", "奇幻", "动画", "战争", "传记", "记录", "犯罪", "悬疑", "西部", "灾难", "古装", "武侠", "家庭", "短片", "校园", "文艺", "运动", "青春"],
        "year": ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016", "2015", "2014", "2013", "2012", "2011", "2010", "2009", "2008", "2007", "2006", "2005", "2004", "2003", "2002", "2001", "2000", "90年代", "80年代", "70年代"],
    },
    "4": {
        "area": ["大陆", "日本", "欧美", "其他"],
        "genre": ["Netflix", "热血", "科幻", "美少女", "魔幻", "经典", "励志", "少儿", "冒险", "搞笑", "推理", "恋爱", "治愈", "幻想", "校园", "动物", "机战", "亲子", "儿歌", "运动", "悬疑", "怪物", "战争", "益智", "青春", "童话", "竞技", "动作", "社会", "友情", "真人版", "电影版", "OVA版", "TV版", "新番动画", "完结动画"],
        "year": ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016", "2015", "2014", "2013", "2012", "2011", "2010", "2009", "2008", "2007", "2006", "2005", "2004", "2003", "2002", "2001", "2000", "90年代", "80年代", "70年代"],
    },
    "3": {
        "area": ["大陆", "韩国", "香港", "台湾", "美国", "其它"],
        "genre": ["Netflix", "脱口秀", "真人秀", "选秀", "八卦", "访谈", "情感", "生活", "晚会", "搞笑", "音乐", "时尚", "游戏", "少儿", "体育", "纪实", "科教", "曲艺", "歌舞", "财经", "汽车", "播报", "其他"],
        "year": ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016", "2015", "2014", "2013", "2012", "2011", "2010", "2009", "2008", "2007", "2006", "2005", "2004", "2003", "2002", "2001", "2000", "90年代", "80年代", "70年代"],
    },
    "126": {
        "area": ["大陆", "香港", "韩国", "美国", "日本", "法国", "英国", "德国", "台湾", "泰国", "印度", "其他"],
        "genre": ["古代", "现代", "穿越", "玄幻", "霸总", "英雄救美", "未婚妻", "师姐", "绝美", "逆袭", "幻想", "美女", "爱情", "甜宠", "虐恋", "爽剧", "搞笑", "情感", "动漫", "萌宝", "抖音", "快手", "都市", "言情", "重生", "乡村", "神医"],
        "year": ["2026", "2025", "2023", "2022", "2021", "2020", "10年代", "00年代", "90年代", "80年代", "更早"],
    },
}


class Spider(BaseSpider):
    realm_name = "555电影"
    defense_level = 1

    def __init__(self):
        self.siteUrl = BASE
        self.timeout = 10
        self.session = None
        if requests is not None:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
        self._filter_cache = {}

    def getName(self):
        return "555电影"

    def init(self, extend=""):
        return self

    def isVideoFormat(self, url):
        return ".m3u8" in str(url) or ".mp4" in str(url)

    def manualVideoCheck(self):
        return False

    # ---------------- 基础 ----------------

    def _raw(self, url, headers=None, timeout=None):
        """返回 (status, content_type, bytes)。有 requests 就用，没有走 urllib。"""
        h = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip",
        }
        h.update(headers or {})
        to = timeout or self.timeout
        if self.session is not None:
            r = self.session.get(url, headers=h, timeout=to)
            ctype = r.headers.get("Content-Type", "")
            body = r.content or b""
            if body[:2] == b"\x1f\x8b":
                body = gzip.GzipFile(fileobj=io.BytesIO(body)).read()
            return r.status_code, ctype, body
        req = urllib.request.Request(url, headers=h)
        try:
            resp = urllib.request.urlopen(req, timeout=to)
            body = resp.read()
            if body[:2] == b"\x1f\x8b":
                body = gzip.GzipFile(fileobj=io.BytesIO(body)).read()
            return resp.status, resp.headers.get("Content-Type", ""), body
        except urllib.error.HTTPError as e:
            return e.code, "", b""
        except Exception as e:
            raise e

    def _get(self, url, ref=None, retry=2):
        h = {"Referer": ref or (self.siteUrl + "/")}
        last = None
        for i in range(retry):
            try:
                st, ctype, body = self._raw(url, h)
                txt = body.decode("utf-8", "ignore")
                if st == 200 and txt.strip():
                    return txt
                last = "HTTP %s len=%s" % (st, len(txt))
            except Exception as e:
                last = repr(e)
        print("[warn] %s -> %s" % (url, last))
        return ""

    # ---------------- 通用解析 ----------------

    def _pic(self, url):
        """海报归一化：站内图是 /upload/... 相对路径，壳子拼不出域名就只能显示片名首字"""
        u = htmllib.unescape((url or "").strip())
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.siteUrl + u
        return u

    def _bad(self, text):
        t = (text or "")
        return any(w in t for w in ADULT_WORDS)

    def _parse_cards(self, page_html, limit=0):
        """列表页卡片
        A 型（分类/筛选页）：<a href="/voddetail/{id}.html" title="{名称}" class="module-poster-item ...">
        B 型（搜索页）：<a href="/voddetail/{id}.html" class="module-card-item-poster"> 名称在 img alt 或 title 块里
        """
        out, seen = [], set()

        # 只取列表主体：侧边栏/推荐位在多页之间是重复的，会把翻页结果污染成"半页旧内容"
        body = page_html
        st = page_html.find('class="module-items')
        if st > 0:
            ed = page_html.find('class="page', st)
            body = page_html[st:ed] if ed > st else page_html[st:st + 60000]

        def _push(vid, name, block):
            name = htmllib.unescape(re.sub(r"<[^>]+>", "", name or "")).strip()
            if vid in seen or not name or self._bad(name):
                return
            note = re.search(r'class="module-item-note">([^<]*)<', block)
            pic = re.search(r'data-original="([^"]+)"', block) or re.search(r'<img[^>]+src="([^"]+)"', block)
            seen.add(vid)
            out.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self._pic(pic.group(1)) if pic else "",
                "vod_remarks": note.group(1).strip() if note else "",
                "vod_play_from": "",
                "vod_play_url": "",
            })

        # A 型
        for m in re.finditer(r'<a\s+href="/voddetail/(\d+)\.html"[^>]*?title="([^"]*)"', body):
            _push(m.group(1), m.group(2), body[m.start():m.start() + 900])
            if limit and len(out) >= limit:
                return out

        # B 型（搜索卡片）
        for m in re.finditer(r'<a\s+href="/voddetail/(\d+)\.html"', body):
            if m.group(1) in seen:
                continue
            block = body[m.start():m.start() + 1200]
            name = ""
            alt = re.search(r'<img[^>]+alt="([^"]*)"', block)
            if alt:
                name = alt.group(1)
            if not name:
                t = re.search(r'class="module-card-item-title[^"]*"[^>]*>(.*?)</a>', block, re.S)
                if t:
                    name = t.group(1)
            _push(m.group(1), name, block)
            if limit and len(out) >= limit:
                break
        return out

    # ---------------- TVBox 接口 ----------------

    def homeContent(self, filter=False):
        cls = CLASS_LIST
        filters = {}
        if filter:
            for c in CLASS_LIST:
                if c["type_id"] == "diag":
                    continue
                filters[c["type_id"]] = self._filters(c["type_id"])
        return {"class": cls, "filters": filters}

    def _diag(self):
        """诊断分类：把首页请求的真实结果摆出来，一眼看出是网络问题还是解析问题"""
        import time
        url = "%s/vodshow/1-----------.html" % self.siteUrl
        t0 = time.time()
        try:
            st, ctype, body = self._raw(url, {"Referer": self.siteUrl + "/"}, 20)
            txt = body.decode("utf-8", "ignore")
            n = len(set(re.findall(r"/voddetail/(\d+)\.html", txt)))
            ms = int((time.time() - t0) * 1000)
            ok = (st == 200 and n > 0)
            name = "%s HTTP %s · %d条 · %dms" % (
                "正常" if ok else "异常", st, n, ms)
            content = ("请求 %s\n状态码 %s\n列表条数 %d\n耗时 %dms\n引擎 %s\n\n"
                       "正常说明：网络和解析都通，空白问题在壳子那侧。\n"
                       "异常说明：这个站从你的网络访问不到，或返回被拦。") % (
                url, st, n, ms, "requests" if self.session else "urllib(无requests)")
        except Exception as e:
            name = "失败 · %s" % type(e).__name__
            content = "请求 %s 失败\n%r\n\n多半是网络/DNS/证书问题。" % (url, e)
        return [{
            "vod_id": "diag",
            "vod_name": name,
            "vod_pic": "",
            "vod_remarks": "点进来看详情",
            "vod_content": content,
        }]

    def _filters(self, tid):
        """纯静态，不发请求：首页/筛选面板秒开，避免壳子卡在加载中"""
        key = str(tid)
        data = FILTERS_DATA.get(key) or {}
        area = data.get("area") or FB_AREA
        genre = data.get("genre") or FB_CLASS
        year = data.get("year") or FB_YEAR
        return [
            {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}] +
             [{"n": x, "v": x} for x in area]},
            {"key": "class", "name": "类型", "value": [{"n": "全部", "v": ""}] +
             [{"n": x, "v": x} for x in genre]},
            {"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}] +
             [{"n": x, "v": x} for x in year]},
        ]

    def homeVideoContent(self):
        """首页推荐：只发一次请求，失败也不让壳子白屏"""
        lst = []
        try:
            lst = self._parse_cards(self._get("%s/vodtype/1.html" % self.siteUrl, retry=1))
        except Exception as e:
            print("[homeVideoContent] %r" % e)
        if not lst:
            lst = [{
                "vod_id": "diag",
                "vod_name": "首页没拿到数据，点我看原因",
                "vod_pic": "",
                "vod_remarks": "网络或站点问题",
                "vod_play_from": "",
                "vod_play_url": "",
            }]
        return {"list": lst}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            tid = str(tid)
            if tid == "diag":
                return {"list": self._diag(), "page": 1, "pagecount": 1, "limit": 1, "total": 1}
            if tid not in {c["type_id"] for c in CLASS_LIST}:
                return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
            pg = int(pg or 1)
            ext = extend or {}
            area, cls, year = ext.get("area", ""), ext.get("class", ""), ext.get("year", "")
            if area or cls or year or pg > 1:
                url = self._build_show(tid, area, cls, pg, year)
            else:
                url = self._build_show(tid, "", "", 1, "")
            lst = self._parse_cards(self._get(url, ref="%s/vodtype/%s.html" % (self.siteUrl, tid)))
            pc = pg + 1 if len(lst) >= 20 else pg
            return {"list": lst, "page": pg, "pagecount": pc, "limit": len(lst), "total": 0}
        except Exception as e:
            print("[categoryContent] %r" % e)
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def _build_show(self, tid, area, cls, pg, year):
        """12 段：tid - 地区 - 排序 - 类型 - 语言 - 空 - 空 - 空 - 页码 - 空 - 空 - 年份"""
        seg = [tid, area, "", cls, "", "", "", "", str(pg) if pg else "", "", "", year]
        return "%s/vodshow/%s.html" % (self.siteUrl, "-".join(seg))

    def detailContent(self, ids):
        try:
            vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
            vid = re.sub(r"[^\d]", "", vid)
            if vid == "" and "diag" in str(ids):
                return {"list": [{
                    "vod_id": "diag",
                    "vod_name": "诊断",
                    "vod_remarks": "",
                    "vod_content": "这是诊断条目，删掉不会影响使用。",
                    "vod_play_from": "",
                    "vod_play_url": "",
                }]}
            if not vid:
                return {"list": []}
            h = self._get("%s/voddetail/%s.html" % (self.siteUrl, vid))
            if not h:
                return {"list": []}

            name = (re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S) or [None, ""])[1]
            name = htmllib.unescape(re.sub(r"<[^>]+>", "", name)).strip()
            if self._bad(name):
                return {"list": []}

            pic = re.search(r'class="module-info-poster".*?data-original="([^"]+)"', h, re.S) \
                or re.search(r'data-original="([^"]+)"', h)
            content = re.search(
                r'class="module-info-introduction-content[^"]*"[^>]*>(.*?)</div>', h, re.S)
            intro = re.sub(r"<[^>]+>", "", content.group(1)).strip() if content else ""
            intro = htmllib.unescape(intro)

            # 标签区：第1组=年份(有 title)，第2组=地区，第3组=类型（多个 a，无 title）
            year = area = genre = ""
            i = h.find('class="module-info-tag"')
            if i > 0:
                zone = h[i:i + 2200]
                groups = re.split(r'<div class="module-info-tag-link">', zone)[1:]
                vals = []
                for g in groups:
                    vals.append([htmllib.unescape(re.sub(r"<[^>]+>", "", t)).strip()
                                 for t in re.findall(r"<a[^>]*>(.*?)</a>", g, re.S)])
                if len(vals) > 0 and vals[0]:
                    cand = vals[0][0]
                    year = cand if cand.isdigit() else ""
                if len(vals) > 1 and vals[1]:
                    area = vals[1][0]
                if len(vals) > 2:
                    genre = " / ".join([x for x in vals[2] if x][:6])
                if self._bad(" / ".join([area, genre])):
                    return {"list": []}

            actor = ""
            m = re.search(r'主演[^<]*<[^>]*>(.*?)</', h, re.S)
            if m:
                actor = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip(" ,")
            m2 = re.search(r'导演[^<]*<[^>]*>(.*?)</', h, re.S)
            director = htmllib.unescape(re.sub(r"<[^>]+>", "", m2.group(1))).strip(" ,") if m2 else ""

            # 播放源：tab 顺序即 sid 顺序，面板顺序一致
            tabs = re.findall(r'class="module-tab-item tab-item"[^>]*data-dropdown-value="([^"]*)"', h)
            if not tabs:
                tabs = re.findall(r'class="module-tab-item tab-item"[^>]*>\s*<span>([^<]*)</span>', h)
            tabs = [htmllib.unescape(t).strip() for t in tabs]

            groups = []
            pos = [m.start() for m in re.finditer(r'class="module-play-list-content', h)]
            for i, p0 in enumerate(pos):
                # 每块切到下一个播放列表块为止：固定 3000 字符会把 40 集以上的长剧截断
                chunk = h[p0:(pos[i + 1] if i + 1 < len(pos) else p0 + 30000)]
                eps = re.findall(
                    r'<a class="module-play-list-link" href="(/vodplay/[^"]+)"[^>]*>\s*<span>([^<]*)</span>',
                    chunk)
                if not eps:
                    eps = [(u, u.rstrip("/").split("/")[-1].split("-")[-1].replace(".html", ""))
                           for u in re.findall(r'href="(/vodplay/[^"]+)"', chunk)]
                groups.append(eps)

            from_list, url_list = [], []
            for si, eps in enumerate(groups):
                if not eps:
                    continue
                label = tabs[si] if si < len(tabs) and tabs[si] else "线路%d" % (si + 1)
                from_list.append(label)
                parts = []
                for u, ep in eps[:500]:
                    parts.append("%s$%s%s" % (ep or "正片", self.siteUrl, u))
                url_list.append("#".join(parts))

            vod = {
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self._pic(pic.group(1)) if pic else "",
                "vod_remarks": "",
                "vod_year": year,
                "vod_area": area,
                "type_name": genre,
                "vod_actor": actor,
                "vod_director": director,
                "vod_content": intro,
                "vod_play_from": "$$$".join(from_list) if from_list else "",
                "vod_play_url": "$$$".join(url_list) if url_list else "",
            }
            return {"list": [vod]}
        except Exception as e:
            print("[detailContent] %r" % e)
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            kw = urllib.parse.quote(str(key).strip())
            url = "%s/vodsearch/%s-------------.html" % (self.siteUrl, kw)
            return {"list": self._parse_cards(self._get(url)),
                    "page": 1, "pagecount": 1, "limit": 0, "total": 0}
        except Exception as e:
            print("[searchContent] %r" % e)
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = str(id)
            if url.startswith("/"):
                url = self.siteUrl + url
            h = self._get(url)
            m = re.search(r"var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>", h, re.S)
            if not m:
                m = re.search(r"player_aaaa\s*=\s*(\{.*?\})", h, re.S)
            if not m:
                return {"parse": 0, "url": "", "header": {}}
            data = json.loads(m.group(1))
            purl = (data.get("url") or "").strip()
            if not purl:
                purl = (data.get("url_next") or "").strip()
            purl = purl.replace("\\/", "/")
            return {
                "parse": 0 if purl.endswith((".m3u8", ".mp4")) else 1,
                "url": purl,
                "header": {"User-Agent": UA, "Referer": url},
            }
        except Exception as e:
            print("[playerContent] %r" % e)
            return {"parse": 0, "url": "", "header": {}}

    # 海报：站点图有防盗链时补 UA/Referer；失败回 1x1 透明 PNG
    def localProxy(self, param):
        try:
            pic = (param or {}).get("url") or ""
            if pic.startswith("//"):
                pic = "https:" + pic
            st, ctype, body = self._raw(pic, {"Referer": self.siteUrl + "/"}, 10)
            if st == 200 and body:
                return [200, ctype or "image/jpeg", body]
        except Exception:
            pass
        return [200, "image/png", BLANK_PNG]


BLANK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a4944415478da6300010000050001" "0d0a2db40000000049454e44ae426082")


# ---------------- 自检 ----------------

def _self_test():
    sp = Spider()
    print("== 555电影 自检（成人分区已排除）==")
    print("站点:", sp.siteUrl, "| 防御等级 Lv.%d" % sp.defense_level)

    hc = sp.homeContent(True)
    print("1. homeContent 分类:", [c["type_name"] for c in hc["class"]])
    for k in hc["filters"]:
        f = hc["filters"][k]
        print("   tid=%s 筛选: %s" % (k, ", ".join("%s(%d项)" % (g["name"], len(g["value"])) for g in f)))

    print("2. 成人 tid 拦截:", sp.categoryContent("124", 1)["list"], "(应为空)")

    hv = sp.homeVideoContent()
    print("3. homeVideo %d 条: %s" % (len(hv["list"]), [v["vod_name"] for v in hv["list"][:3]]))
    bad_home = [v["vod_name"] for v in hv["list"] if sp._bad(v["vod_name"])]
    print("   黑名单命中:", bad_home or "无")

    for tid in ("1", "2", "4", "3", "126"):
        c = sp.categoryContent(tid, 1)
        print("4. tid=%-4s p1 %2d 条: %s" % (tid, len(c["list"]), [v["vod_name"] for v in c["list"][:2]]))
    c2 = sp.categoryContent("1", 2)
    print("   tid=1 p2 %d 条: %s" % (len(c2["list"]), [v["vod_name"] for v in c2["list"][:2]]))
    same = {v["vod_id"] for v in sp.categoryContent("1", 1)["list"]} & {v["vod_id"] for v in c2["list"]}
    print("   p1/p2 重复 %d 个（0 表示翻页有效）" % len(same))

    f = sp.categoryContent("1", 1, True, {"area": "韩国", "year": "2025"})
    print("5. 筛选 韩国+2025: %d 条 %s" % (len(f["list"]), [v["vod_name"] for v in f["list"][:2]]))

    # 详情
    vid = (sp.homeVideoContent()["list"] or [{}])[0].get("vod_id")
    d = sp.detailContent([vid])
    if d["list"]:
        v = d["list"][0]
        print("6. detail %s | %s | %s | %s" % (v["vod_id"], v["vod_name"], v["vod_year"], v["type_name"]))
        print("   播放源: %s" % v["vod_play_from"])
        print("   第一集: %s" % (v["vod_play_url"].split("$$$")[0].split("#")[0][:80]))
        first = v["vod_play_url"].split("$$$")[0].split("#")[0].split("$")[-1]
        p = sp.playerContent("", first)
        print("7. player parse=%s url=%s" % (p["parse"], p["url"][:70]))

    s = sp.searchContent("庆余年", True, "1")
    print("8. search %d 条: %s" % (len(s["list"]), [x["vod_name"] for x in s["list"][:3]]))
    print("   黑名单命中:", [x["vod_name"] for x in s["list"] if sp._bad(x["vod_name"])] or "无")


if __name__ == "__main__":
    _self_test()
