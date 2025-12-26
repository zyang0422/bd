# -*- coding: utf-8 -*-
import json
import re
import sys
import hashlib
from base64 import b64decode, b64encode
import requests
from pyquery import PyQuery as pq
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import time
sys.path.append('..')
from base.spider import Spider as BaseSpider

# 图片缓存，避免重复解密
img_cache = {}

class Spider(BaseSpider):
    
    def init(self, extend=""):
        """初始化"""
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else extend or {}
            self.proxies = cfg.get('proxies', {})
            self.host = (cfg.get('host', '') or '').strip()
            if not self.host:
                self.host = 'https://madou.net'
        except:
            self.proxies = {}
            self.host = 'https://madou.net'
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; M2102J2SC Build/TKQ1.221114.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.32 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # 解析host用于Referer
        from urllib.parse import urlparse
        parsed = urlparse(self.host)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.headers.update({'Origin': base_url, 'Referer': f"{base_url}/"})
        print(f"[Spider] 使用站点: {self.host}")
    
    def getName(self):
        return "麻豆传媒"
    
    def isVideoFormat(self, url):
        return any(ext in (url or '').lower() for ext in ['.m3u8', '.mp4', '.ts', '.flv', '.mkv'])
    
    def manualVideoCheck(self):
        return False
    
    def destroy(self):
        global img_cache
        img_cache.clear()
    
    def homeContent(self, filter):
        """首页：固定分类"""
        classes = [
            {'type_name': '首页', 'type_id': '/'},
            {'type_name': '每日更新', 'type_id': '/category/17202/'},
            {'type_name': '麻豆AV', 'type_id': '/category/17210101/'},
            {'type_name': '热门吃瓜', 'type_id': '/category/165810103/'},
            {'type_name': '顶流网黄', 'type_id': '/category/58110101/'},
            {'type_name': '热门女优', 'type_id': '/category/52310101/'},
            {'type_name': '国产精品', 'type_id': '/category/117710101/'},
            {'type_name': '片商传媒', 'type_id': '/category/71310101/'},
            {'type_name': '网红明星', 'type_id': '/category/167310101/'},
            {'type_name': '日本AV', 'type_id': '/category/64110101/'},
        ]
        
        # 尝试获取首页视频列表
        try:
            response = requests.get(self.host, headers=self.headers, timeout=10)
            if response.status_code == 200:
                html = response.text
                videos = []
                
                # 从HTML中提取文章块
                articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
                
                for article in articles[:12]:  # 首页只显示12个
                    # 提取链接
                    href_match = re.search(r'href="([^"]+)"', article)
                    if not href_match:
                        continue
                        
                    href = href_match.group(1)
                    if not href or '/archives/' not in href:
                        continue
                    
                    # 构建完整URL
                    if not href.startswith('http'):
                        href = self.host + href if href.startswith('/') else f'{self.host}/{href}'
                    
                    # 提取标题
                    title_match = re.search(r'headline">([^<]+)</h2>', article)
                    if not title_match:
                        continue
                        
                    title = title_match.group(1).strip()
                    
                    # 提取图片（加密图片需要解密）
                    cover = ''
                    img_match = re.search(r'data-src="([^"]+)"', article)
                    if img_match:
                        data_src = img_match.group(1).strip()
                        if data_src:
                            cover = self._process_img_url(data_src)
                    
                    videos.append({
                        'vod_id': href,
                        'vod_name': title[:100],
                        'vod_pic': cover,
                        'vod_remarks': '',
                        'style': {"type": "rect", "ratio": 1.5}
                    })
                
                return {'class': classes, 'list': videos}
        except Exception as e:
            print(f"首页获取失败: {e}")
        
        return {'class': classes, 'list': []}
    
    def homeVideoContent(self):
        """首页视频内容 - 与homeContent保持一致"""
        return self.homeContent(None)
    
    def categoryContent(self, tid, pg, filter, extend):
        """分类页内容"""
        try:
            pg = int(pg) if pg else 1
            
            # 构建URL
            if tid == '/':
                base_url = self.host
            else:
                base_url = f"{self.host}{tid}"
            
            # 处理分页
            if pg == 1:
                url = base_url.rstrip('/') + '/'
            else:
                url = f"{base_url.rstrip('/')}/{pg}/"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return {'list': [], 'page': pg, 'pagecount': 0, 'limit': 20, 'total': 0}
            
            html = response.text
            videos = []
            
            # 提取文章块
            articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
            
            for article in articles[:20]:  # 每页20个
                # 提取链接
                href_match = re.search(r'href="([^"]+)"', article)
                if not href_match:
                    continue
                    
                href = href_match.group(1)
                if not href or '/archives/' not in href:
                    continue
                
                # 构建完整URL
                if not href.startswith('http'):
                    href = self.host + href if href.startswith('/') else f'{self.host}/{href}'
                
                # 提取标题
                title_match = re.search(r'headline">([^<]+)</h2>', article)
                if not title_match:
                    continue
                    
                title = title_match.group(1).strip()
                
                # 提取图片（加密图片需要解密）
                cover = ''
                img_match = re.search(r'data-src="([^"]+)"', article)
                if img_match:
                    data_src = img_match.group(1).strip()
                    if data_src:
                        cover = self._process_img_url(data_src)
                
                videos.append({
                    'vod_id': href,
                    'vod_name': title[:100],
                    'vod_pic': cover,
                    'vod_remarks': '',
                    'style': {"type": "rect", "ratio": 1.5}
                })
            
            return {
                'list': videos,
                'page': pg,
                'pagecount': 9999,
                'limit': 20,
                'total': 999999
            }
            
        except Exception as e:
            print(f"分类页获取失败: {e}")
            return {'list': [], 'page': pg, 'pagecount': 0, 'limit': 20, 'total': 0}
    
    def detailContent(self, ids):
        """详情页内容 - 修复播放地址和标签功能"""
        try:
            url = ids[0] if ids[0].startswith('http') else self.host + ids[0]
            
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return {'list': []}
            
            html = response.text
            
            # 1. 提取标题
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
            title = title_match.group(1).strip() if title_match else '未知标题'
            # 清理标题
            if '|' in title:
                title = title.split('|')[0].strip()
            
            # 2. 提取简介/描述
            desc_match = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', html)
            description = desc_match.group(1).strip() if desc_match else ''
            
            # 3. 提取封面（加密图片）
            cover = ''
            img_match = re.search(r'data-src="([^"]+)"', html)
            if img_match:
                data_src = img_match.group(1).strip()
                if data_src:
                    cover = self._process_img_url(data_src)
            
            # 4. 提取标签（关键修复：恢复标签功能）
            keywords_html = ''
            try:
                # 从keywords meta标签提取
                keywords_match = re.search(r'<meta[^>]*name="keywords"[^>]*content="([^"]+)"', html)
                if keywords_match:
                    keywords = keywords_match.group(1).strip()
                    # 将关键词转换为标签链接格式
                    if keywords:
                        keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
                        # 限制标签数量
                        keyword_list = keyword_list[:10]
                        # 构建标签HTML（保留原代码的标签格式）
                        tags = []
                        for kw in keyword_list:
                            # 模拟原代码的标签格式 [a=cr:{target}/]{name}[/a]
                            target = json.dumps({'id': f'/search/{kw}/', 'name': kw})
                            tags.append(f'[a=cr:{target}/]{kw}[/a]')
                        
                        if tags:
                            keywords_html = ' '.join(tags)
            except Exception as e:
                print(f"标签提取失败: {e}")
            
            # 5. 提取播放地址（关键修复：正确提取DPlayer播放地址）
            play_urls = []
            
            # 方法1：从DPlayer的data-config属性提取
            dplayer_pattern = r'<div[^>]*class="dplayer"[^>]*data-config="([^"]+)"'
            dplayer_matches = re.findall(dplayer_pattern, html, re.IGNORECASE)
            
            for dplayer_config in dplayer_matches:
                try:
                    # 处理HTML实体
                    config_str = dplayer_config.replace('&quot;', '"').replace('&amp;', '&')
                    config = json.loads(config_str)
                    
                    # 提取视频地址
                    if 'video' in config and 'url' in config['video']:
                        video_url = config['video']['url']
                        if video_url and 'http' in video_url:
                            play_urls.append(video_url)
                except Exception as e:
                    print(f"DPlayer配置解析失败: {e}")
            
            # 方法2：从script标签中查找
            if not play_urls:
                script_pattern = r'<script[^>]*>(.*?)</script>'
                script_matches = re.findall(script_pattern, html, re.DOTALL | re.IGNORECASE)
                
                for script_content in script_matches:
                    # 查找m3u8地址
                    m3u8_patterns = [
                        r'"(https?://[^\s"\']+\.m3u8[^\s"\']*)"',
                        r'\'(https?://[^\s"\']+\.m3u8[^\s"\']*)\'',
                        r'(https?://[^\s"\']+\.m3u8[^\s"\']*)'
                    ]
                    
                    for pattern in m3u8_patterns:
                        matches = re.findall(pattern, script_content, re.IGNORECASE)
                        for match in matches:
                            if isinstance(match, str):
                                video_url = match
                            else:
                                video_url = match[0] if isinstance(match, tuple) else match
                            
                            if video_url and 'http' in video_url and video_url not in play_urls:
                                play_urls.append(video_url)
            
            # 方法3：从iframe提取
            if not play_urls:
                iframe_match = re.search(r'<iframe[^>]*src="([^"]+)"', html)
                if iframe_match:
                    iframe_src = iframe_match.group(1).strip()
                    if iframe_src and iframe_src.startswith('http'):
                        play_urls.append(iframe_src)
            
            # 构建播放列表
            play_list = []
            if play_urls:
                for i, play_url in enumerate(play_urls[:3]):  # 最多3个播放源
                    play_list.append(f"线路{i+1}${play_url}")
            else:
                # 如果没有找到播放地址，使用原始URL
                play_list.append(f"线路1${url}")
            
            play_line = '#'.join(play_list)
            
            # 6. 构建vod对象
            vod = {
                'vod_name': title,
                'vod_pic': cover or f'{self.host}/static/images/logo.png',
                'vod_content': description,  # 简介
                'vod_play_from': '麻豆传媒',
                'vod_play_url': play_line,
            }
            
            # 如果有标签，添加到vod_content后面
            if keywords_html:
                vod['vod_content'] = f"{description}\n\n标签: {keywords_html}"
            
            return {'list': [vod]}
            
        except Exception as e:
            print(f"详情页获取失败: {e}")
            return {'list': []}
    
    def searchContent(self, key, quick, pg="1"):
        """搜索内容"""
        try:
            pg = int(pg) if pg else 1
            
            # URL编码关键词
            import urllib.parse
            encoded_key = urllib.parse.quote(key)
            
            if pg == 1:
                url = f"{self.host}/search/{encoded_key}/"
            else:
                url = f"{self.host}/search/{encoded_key}/{pg}/"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return {'list': [], 'page': pg, 'pagecount': 0}
            
            html = response.text
            videos = []
            
            # 提取文章块
            articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
            
            for article in articles:
                # 提取链接
                href_match = re.search(r'href="([^"]+)"', article)
                if not href_match:
                    continue
                    
                href = href_match.group(1)
                if not href or '/archives/' not in href:
                    continue
                
                # 构建完整URL
                if not href.startswith('http'):
                    href = self.host + href if href.startswith('/') else f'{self.host}/{href}'
                
                # 提取标题
                title_match = re.search(r'headline">([^<]+)</h2>', article)
                if not title_match:
                    continue
                    
                title = title_match.group(1).strip()
                
                # 提取图片（加密图片需要解密）
                cover = ''
                img_match = re.search(r'data-src="([^"]+)"', article)
                if img_match:
                    data_src = img_match.group(1).strip()
                    if data_src:
                        cover = self._process_img_url(data_src)
                
                videos.append({
                    'vod_id': href,
                    'vod_name': title[:100],
                    'vod_pic': cover,
                    'vod_remarks': '',
                    'style': {"type": "rect", "ratio": 1.5}
                })
            
            return {'list': videos, 'page': pg, 'pagecount': 9999}
            
        except Exception as e:
            print(f"搜索失败: {e}")
            return {'list': [], 'page': pg, 'pagecount': 0}
    
    def playerContent(self, flag, id, vipFlags):
        """播放器内容"""
        # 检查是否是视频格式
        parse = 0 if self.isVideoFormat(id) else 1
        
        return {
            'parse': parse,  # 0: 直接播放, 1: 需要解析
            'url': id,
            'header': self.headers
        }
    
    def localProxy(self, param):
        """本地代理 - 处理图片解密和视频代理"""
        try:
            type_ = param.get('type', '')
            url = param.get('url', '')
            key = param.get('key', '')
            
            if type_ == 'cache':
                # 从缓存获取图片
                if key in img_cache:
                    return [200, 'image/jpeg', img_cache[key]]
                return [404, 'text/plain', b'Expired']
            
            elif type_ == 'img':
                # 解密图片
                real_url = self._d64(url) if not url.startswith('http') else url
                
                # 设置Referer
                headers = self.headers.copy()
                from urllib.parse import urlparse
                parsed = urlparse(real_url)
                if parsed.netloc:
                    headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"
                
                res = requests.get(real_url, headers=headers, timeout=10)
                if res.status_code == 200:
                    # 尝试解密图片
                    content = self._aesimg(res.content)
                    
                    # 缓存图片
                    cache_key = hashlib.md5(content).hexdigest()
                    img_cache[cache_key] = content
                    
                    return [200, 'image/jpeg', content]
                return [404, 'text/plain', b'Not Found']
            
            elif type_ == 'm3u8':
                # 代理m3u8文件
                return self._proxy_m3u8(url)
            
            elif type_ == 'ts':
                # 代理ts文件
                return self._proxy_ts(url)
            
            return [404, 'text/plain', b'Invalid request']
            
        except Exception as e:
            print(f"本地代理错误: {e}")
            return [404, 'text/plain', b'Error']
    
    def _process_img_url(self, url):
        """处理图片URL - 转换为代理URL"""
        if not url:
            return ''
        
        url = url.strip('\'" ')
        
        # 如果是data:image格式，直接返回
        if url.startswith('data:image'):
            return url
        
        # 如果已经是完整URL
        if url.startswith('http'):
            # 使用代理URL进行解密
            return f"{self.getProxyUrl()}&url={self._e64(url)}&type=img"
        
        # 如果是相对路径，添加主机前缀
        if url.startswith('/'):
            full_url = f"{self.host}{url}"
        else:
            full_url = f"{self.host}/{url}"
        
        # 使用代理URL进行解密
        return f"{self.getProxyUrl()}&url={self._e64(full_url)}&type=img"
    
    def _e64(self, text):
        """Base64编码"""
        return b64encode(str(text).encode()).decode()
    
    def _d64(self, text):
        """Base64解码"""
        return b64decode(str(text).encode()).decode()
    
    def _aesimg(self, data):
        """AES解密图片 - 麻豆传媒图片解密"""
        if len(data) < 16:
            return data
        
        # 尝试多种AES解密方式
        keys_try = [
            # 第一种密钥对
            (b'f5d965df75336270', b'97b60394abc2fbe1'),
            # 第二种密钥对
            (b'75336270f5d965df', b'abc2fbe197b60394'),
            # 第三种可能的密钥对
            (b'f5d965df75336270', b'0000000000000000'),
            (b'75336270f5d965df', b'0000000000000000'),
        ]
        
        for key, iv in keys_try:
            try:
                # 尝试CBC模式解密
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted = cipher.decrypt(data)
                decrypted = unpad(decrypted, 16)
                
                # 检查是否是有效的图片
                if (decrypted.startswith(b'\xff\xd8') or  # JPEG
                    decrypted.startswith(b'\x89PNG') or   # PNG
                    decrypted.startswith(b'GIF8') or      # GIF
                    decrypted.startswith(b'BM')):         # BMP
                    return decrypted
            except Exception as e:
                continue
            
            try:
                # 尝试ECB模式解密
                cipher = AES.new(key, AES.MODE_ECB)
                decrypted = cipher.decrypt(data)
                decrypted = unpad(decrypted, 16)
                
                # 检查是否是有效的图片
                if decrypted.startswith(b'\xff\xd8'):
                    return decrypted
            except Exception as e:
                continue
        
        # 如果解密失败，返回原始数据
        return data
    
    def _proxy_m3u8(self, url):
        """代理m3u8文件"""
        try:
            real_url = self._d64(url)
            
            # 设置Referer
            headers = self.headers.copy()
            from urllib.parse import urlparse
            parsed = urlparse(real_url)
            if parsed.netloc:
                headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"
            
            res = requests.get(real_url, headers=headers, timeout=10)
            if res.status_code != 200:
                return [404, 'text/plain', b'Not Found']
            
            content = res.text
            base_url = res.url.rsplit('/', 1)[0] + '/'
            
            # 处理m3u8内容，将相对路径转换为绝对路径
            lines = []
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('http'):
                    if not line.startswith('/'):
                        line = base_url + line
                    lines.append(self._get_proxy_url(line, 'ts'))
                else:
                    lines.append(line)
            
            return [200, 'application/vnd.apple.mpegurl', '\n'.join(lines)]
        except Exception as e:
            print(f"m3u8代理错误: {e}")
            return [404, 'text/plain', b'Error']
    
    def _proxy_ts(self, url):
        """代理ts文件"""
        try:
            real_url = self._d64(url)
            
            # 设置Referer
            headers = self.headers.copy()
            from urllib.parse import urlparse
            parsed = urlparse(real_url)
            if parsed.netloc:
                headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"
            
            res = requests.get(real_url, headers=headers, timeout=10)
            if res.status_code == 200:
                return [200, 'video/mp2t', res.content]
            return [404, 'text/plain', b'Not Found']
        except Exception as e:
            print(f"ts代理错误: {e}")
            return [404, 'text/plain', b'Error']
    
    def _get_proxy_url(self, url, type_=''):
        """获取代理URL"""
        return f"{self.getProxyUrl()}&url={self._e64(url)}&type={type_}"