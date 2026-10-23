"""CEO workspace widgets and bounded public feeds; no model calls or engine mutations."""
import json
import queue
import re
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from collections import Counter
from email.utils import parsedate_to_datetime
from pathlib import Path
from tkinter import ttk
from urllib.parse import urlsplit

FEEDS = {'AI 동향': 'https://openai.com/news/rss.xml',
         'AI 취업': 'https://www.python.org/jobs/feed/rss/'}
JOB_PATTERN = re.compile(r'\b(ai|ml|llm|machine learning|deep learning|artificial intelligence)\b', re.I)


def parse_feed(raw, category):
    items, seen = [], set()
    for item in ET.fromstring(raw).findall('./channel/item'):
        title = item.findtext('title', '').strip()
        description = re.sub(r'<[^>]+>', ' ', item.findtext('description', ''))
        description = ' '.join(description.split())
        url = item.findtext('link', '').strip()
        if not title or urlsplit(url).scheme != 'https' or url in seen:
            continue
        if category == 'AI 취업' and not JOB_PATTERN.search(title + ' ' + description):
            continue
        try:
            published = parsedate_to_datetime(item.findtext('pubDate', '')).timestamp()
        except (ValueError, TypeError, OverflowError):
            published = None
        seen.add(url)
        items.append(dict(title=title, summary=description[:220], url=url, published=published))
    return sorted(items, key=lambda x: x['published'] or 0, reverse=True)[:30]


STALE_AFTER = 24 * 3600     # seconds; older collected feeds are labelled stale, never shown as current


def freshness(fetched, now=None):
    """How old the collected feed is, stated plainly: never collected, current, or stale with its age."""
    if not fetched:
        return '수집 전'
    age = (now or time.time()) - fetched
    stamp = time.strftime('%m/%d %H:%M', time.localtime(fetched))
    if age > STALE_AFTER:
        return f'마지막 수집 {stamp} · 오래된 정보 ({int(age // 86400) or 1}일 전) — 새로 수집하세요'
    return f'마지막 수집 {stamp}'


def fetch_feeds():
    results = {}
    for category, url in FEEDS.items():
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AXBranch/CEO-home'})
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('피드 크기 제한 초과')
            results[category] = dict(items=parse_feed(raw, category), fetched=time.time(), error='')
        except (OSError, ValueError, ET.ParseError) as exc:
            results[category] = dict(items=[], fetched=None, error=str(exc)[:180])
    return results


class Home(ttk.Frame):
    def __init__(self, parent, workspace):
        super().__init__(parent, padding=24)
        self.cache = Path(workspace) / 'home-feeds.json'
        self.messages = queue.Queue()
        self.busy = False
        self.category = None
        self._signature = None
        try:
            self.data = json.loads(self.cache.read_text(encoding='utf-8'))
            if not isinstance(self.data, dict):
                self.data = {}
        except (OSError, ValueError):
            self.data = {}
        ttk.Label(self, text='청월 · 나의 AI CEO', font=('Malgun Gothic', 23, 'bold')).pack(anchor='w')
        self.summary = ttk.Label(self, font=('Malgun Gothic', 12), wraplength=850)
        self.summary.pack(anchor='w', pady=(12, 8))
        self.chart = tk.Canvas(self, height=70, bg='#f2f5f8', highlightthickness=0)
        self.chart.pack(fill='x', pady=8)
        row = ttk.Frame(self); row.pack(fill='x', pady=8)
        self.refresh_button = ttk.Button(row, text='공개 정보 새로 수집', command=self.collect)
        self.refresh_button.pack(side='left')
        self.notice = ttk.Label(row, text='수집은 OpenAI 뉴스·Python.org 채용 공개 피드만 읽습니다. AI 호출 없음.')
        self.notice.pack(side='left', padx=12)
        self.cards = ttk.Frame(self); self.cards.pack(fill='both', expand=True)
        self.render()

    def collect(self):
        if self.busy:
            return
        self.busy = True
        self.refresh_button.state(['disabled'])
        self.notice.config(text='공개 피드 수집 중…')
        messages = self.messages
        threading.Thread(target=lambda: messages.put(fetch_feeds()), daemon=True).start()

    def update_state(self, projects):
        counts = Counter(p['state'] for p in projects)
        active = sum(counts[s] for s in ('CREATED', 'PLANNING', 'STAFFING', 'EXECUTING', 'VERIFYING', 'REWORK'))
        self.summary.config(text=f'전체 {len(projects)}개 업무 · 진행 단계 {active}개 · 검토 대기 {counts["OWNER_REVIEW"]}개 · 일시 중지 {counts["PAUSED"]}개\n'
                            '새 업무는 위 입력창에 맡겨주세요. 진행 단계는 저장된 상태이며 실제 활동은 프로젝트에서 확인합니다.')
        signature = tuple(sorted(counts.items()))
        if signature != self._signature:
            self._signature = signature
            self.chart.delete('all')
            x = 12
            for label, count, color in [('진행', active, '#326ed2'), ('검토', counts['OWNER_REVIEW'], '#208676'),
                                        ('중지', counts['PAUSED'], '#bd7924'), ('종료', counts['CLOSED'], '#798596')]:
                self.chart.create_rectangle(x, 12, x + 150, 58, fill=color, outline='')
                self.chart.create_text(x + 75, 35, text=f'{label}  {count}', fill='white', font=('Malgun Gothic', 12, 'bold'))
                x += 160
        try:
            fresh = self.messages.get_nowait()
        except queue.Empty:
            return
        for category, result in fresh.items():
            if result['error']:
                old = self.data.get(category, {})
                result['items'] = old.get('items', [])
                result['fetched'] = old.get('fetched')
            self.data[category] = result
        self.busy = False
        self.refresh_button.state(['!disabled'])
        self.notice.config(text='수집 결과를 확인하세요. 일부 출처만 포함하며 전체 시장 목록은 아닙니다.')
        try:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.cache)
        except OSError as exc:
            self.notice.config(text=f'수집 결과 저장 실패: {exc}')
        self.render(self.category)

    def render(self, category=None):
        self.category = category
        for child in self.cards.winfo_children():
            child.destroy()
        for name in ([category] if category else list(FEEDS)):
            data = self.data.get(name, {})
            box = ttk.LabelFrame(self.cards, text=name, padding=12)
            box.pack(fill='x', pady=8)
            ttk.Label(box, text=f"{freshness(data.get('fetched'))} · 게시일순 · 날짜 미상은 뒤에 표시").pack(anchor='w')
            if data.get('error'):
                ttk.Label(box, text='수집 실패 · 기존 자료 유지: ' + data['error'], wraplength=850).pack(anchor='w')
            items = data.get('items', [])[:3]
            if not items:
                ttk.Label(box, text='표시할 실제 자료가 없습니다. 공개 정보 수집 후 확인할 수 있습니다.').pack(anchor='w', pady=10)
            for item in items:
                published = time.strftime('%Y-%m-%d', time.localtime(item['published'])) if item.get('published') else '게시일 미상'
                url = item.get('url', '')
                button = ttk.Button(box, text=f'{published}  {item["title"]}',
                                    command=lambda u=url: webbrowser.open(u) if urlsplit(u).scheme == 'https' else None)
                button.pack(anchor='w', pady=(8, 2))
                ttk.Label(box, text=item.get('summary', ''), wraplength=850).pack(anchor='w')
                ttk.Label(box, text=urlsplit(url).netloc + (' · 마감·모집 상태는 원문 확인' if name == 'AI 취업' else '')).pack(anchor='w')


def draw_pipeline(canvas, rows, on_select):
    """Current engine is sequential. Never invent concurrency or completion percentages."""
    canvas.delete('all')
    colors = {'✓': '#daf0e8', '●': '#dbe9ff', '✗': '#ffe2df', '✕': '#ffe2df', '!': '#fff0d5'}
    x = 15
    for row in rows:
        tag = 'node_' + row['key']
        if x > 15:
            canvas.create_line(x - 24, 48, x - 4, 48, arrow='last', fill='#60728b')
        canvas.create_rectangle(x, 10, x + 205, 94, fill=colors.get(row['mark'], '#eef1f5'), outline='#ccd5e0', tags=tag)
        canvas.create_text(x + 10, 28, text=f'{row["mark"]} {row["title"]}', anchor='w', width=190, font=('Malgun Gothic', 10, 'bold'), tags=tag)
        canvas.create_text(x + 10, 69, text=f'{row["engine"]} · {row["detail"][:42]}', anchor='w', width=190, tags=tag)
        canvas.tag_bind(tag, '<Button-1>', lambda _e, key=row['key']: on_select(key))
        x += 235
    canvas.configure(scrollregion=(0, 0, max(x, 400), 105))
