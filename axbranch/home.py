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



BG, INK, MUTED, ACCENT = '#f5f5fa', '#30364b', '#6c7488', '#8c7bc8'


def configure_theme(root):
    root.configure(background=BG)
    root.option_add('*Text.background', 'white')
    root.option_add('*Text.relief', 'flat')
    root.option_add('*Text.borderWidth', 0)
    root.option_add('*Text.highlightThickness', 0)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Malgun Gothic', 10), background=BG, foreground=INK)
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG)
    style.configure('TLabelframe', borderwidth=0, relief='flat', background='white')
    style.configure('TLabelframe.Label', background='white', foreground=INK, font=('Malgun Gothic', 11, 'bold'))
    style.configure('TPanedwindow', background=BG, sashwidth=10, sashpad=4, sashrelief='flat', borderwidth=0)
    for orient in ('Vertical', 'Horizontal'):
        width, height = (8, 16) if orient == 'Vertical' else (16, 8)
        thumb = tk.PhotoImage(master=root, width=width, height=height)
        # Stretch the centre, retaining rounded ends without replacing native scrolling behaviour.
        for y in range(height):
            for x in range(width):
                cx = min(max(x, 3), width-4)
                cy = min(max(y, 3), height-4)
                if (x-cx)**2 + (y-cy)**2 <= 10:
                    thumb.put('#c8bfdd', (x, y))
        root.__dict__.setdefault('_scroll_images', []).append(thumb)
        element = 'Pastel.' + orient + '.thumb'
        style.element_create(element, 'image', thumb, border=3, sticky='nswe')
        style.layout(orient + '.TScrollbar', [(orient + '.Scrollbar.trough', {'sticky': 'nswe', 'children': [
            (element, {'sticky': 'nswe', 'expand': '1'})]})])
        style.configure(orient + '.TScrollbar', background='#d4cde5', troughcolor=BG, borderwidth=0,
                        bordercolor=BG, lightcolor=BG, darkcolor=BG, arrowsize=9, gripcount=0, width=9)
        style.map(orient + '.TScrollbar', background=[('active', '#b3a4d5'), ('pressed', '#9b8ac4')])
    for name, color in [('Card', 'white'), ('Sidebar', '#eae6f5')]:
        style.configure(name + '.TFrame', background=color)
    for name, size, color, bg in [('Card', 10, INK, 'white'), ('CardTitle', 12, INK, 'white'),
                                 ('Muted', 9, MUTED, BG), ('Side', 9, '#646179', '#eae6f5'),
                                 ('Brand', 17, '#403955', '#eae6f5'), ('Page', 10, MUTED, BG)]:
        style.configure(name + '.TLabel', background=bg, foreground=color,
                        font=('Malgun Gothic', size, 'bold' if name in ('Brand', 'CardTitle') else 'normal'))
    style.configure('TButton', padding=(12, 8), background='white', bordercolor='#e5e8f0', relief='flat')
    style.configure('TMenubutton', padding=(14, 9), background='#eee8f8', foreground='#554575',
                    borderwidth=0, relief='flat', bordercolor=BG, lightcolor=BG, darkcolor=BG)
    style.map('TMenubutton', background=[('active', '#ded5ef')])
    style.map('TButton', background=[('active', '#eeebfa')])
    style.configure('Primary.TButton', background=ACCENT, foreground='white', bordercolor=ACCENT)
    style.map('Primary.TButton', background=[('active', '#6450c4')], foreground=[('disabled', '#dad5ee')])
    style.configure('Nav.TButton', anchor='w', background='#eae6f5', foreground='#56516b', borderwidth=0, padding=(16, 12))
    style.map('Nav.TButton', background=[('active', '#ded7ef')], foreground=[('active', '#38324c')])
    style.configure('Selected.Nav.TButton', background='#d7ceeb', foreground='#38324c')
    style.configure('Treeview', background='white', fieldbackground='white', rowheight=34, borderwidth=0)
    style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
    style.configure('Treeview.Heading', background='#f6f7fb', padding=8, relief='flat')
    style.map('Treeview', background=[('selected', '#eeeafa')], foreground=[('selected', INK)])
    style.layout('TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
    style.configure('TNotebook', borderwidth=0, background=BG, bordercolor=BG,
                    lightcolor=BG, darkcolor=BG, tabmargins=(0, 0, 0, 8))
    style.layout('TNotebook.Tab', [('Notebook.padding', {'sticky': 'nswe', 'children': [('Notebook.label', {'sticky': 'nswe'})]})])
    style.configure('TNotebook.Tab', padding=(18, 12), background=BG, foreground=MUTED)
    style.map('TNotebook.Tab', background=[('selected', '#eee8f8')], foreground=[('selected', '#554575')])


def rounded(canvas, x1, y1, x2, y2, radius=16, **kw):
    return canvas.create_polygon(x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,
                                 x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,
                                 x1,y2,x1,y2-radius,x1,y1+radius,x1,y1, smooth=True, **kw)


ORB_LABELS = {'idle': '대기', 'planning': '계획 중', 'delegating': '부서·에이전트에 위임 중', 'verifying': '독립 검증 중',
              'rework': '재작업 중', 'waiting': 'Owner 확인 대기', 'error': '오류·사용량 한도', 'done': '완료'}
ANIMATED = {'planning', 'delegating', 'verifying', 'rework', 'waiting'}


def orb_state(projects):
    """The CEO orb from REAL stored state only: projects = [(state, supervisor status, pause_reason)].
    Running work wins; then errors/limits; then Owner waits; otherwise idle (no motion at all)."""
    running = [st for st, status, _ in projects if status in ('ACTIVE', 'RECOVERING')]
    if running:
        return {'PLANNING': 'planning', 'CREATED': 'planning', 'STAFFING': 'delegating', 'EXECUTING': 'delegating',
                'VERIFYING': 'verifying', 'REWORK': 'rework'}.get(running[0], 'planning')
    if any((status in ('STALLED', 'FAILED') and st != 'CREATED') or status == 'WAITING_FOR_PROVIDER'
           or str(reason or '').startswith('RateLimited')
           for st, status, reason in projects):
        return 'error'
    if any(status == 'WAITING_FOR_OWNER' for _, status, _ in projects):
        return 'waiting'
    if projects and all(st == 'CLOSED' for st, _, _ in projects):
        return 'done'
    return 'idle'


class StatusOrb(tk.Canvas):
    """淸月's sphere. Moves only while real work runs (or a ~2 s blink while the Owner is awaited); idle, error and
    done are completely still: no timer is scheduled. With motion off it shows colour only."""
    def __init__(self, parent):
        super().__init__(parent, width=76, height=76, bg='white', highlightthickness=0)
        self.state, self.motion, self._job, self._phase = None, True, None, 0
        self.set_state('idle')

    def set_state(self, state, motion=True):
        if (state, motion) == (self.state, self.motion):
            return
        self.state, self.motion = state, motion
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self._phase = 0
        self._draw()
        if motion and state in ANIMATED:
            self._job = self.after(1000 if state == 'waiting' else 60, self._tick)

    def destroy(self):
        if self._job is not None:                  # no animation callback firing into a destroyed window
            self.after_cancel(self._job)
            self._job = None
        super().destroy()

    def _tick(self):
        self._phase += 1
        self._draw()
        self._job = self.after(1000 if self.state == 'waiting' else 60, self._tick)

    def _draw(self):
        self.delete('all')
        orange = self.state == 'error'
        for radius in range(32, 2, -1):
            t = (32 - radius) / 30
            color = ('#%02x%02x%02x' % (int(222 + 25 * t), int(132 + 60 * t), int(58 + 60 * t)) if orange else
                     '#%02x%02x%02x' % (int(81 + 64 * t), int(108 + 46 * t), int(204 + 30 * t)))
            self.create_oval(38 - radius, 38 - radius, 38 + radius, 38 + radius, fill=color, outline='')
        self.create_oval(29, 23, 35, 29, fill='#e5f6ff', outline='')
        p, s = self._phase, self.state
        if not self.motion or s not in ANIMATED:
            return
        if s in ('planning', 'rework'):
            step = 3 if s == 'planning' else -4
            self.create_arc(5, 5, 71, 71, start=(p * step) % 360, extent=110, style='arc',
                            outline='#a9f0f2' if s == 'planning' else '#f2c46b', width=3)
        elif s == 'verifying':
            self.create_arc(5, 5, 71, 71, start=(p * 4) % 360, extent=90, style='arc', outline='#a9f0f2', width=3)
            self.create_arc(11, 11, 65, 65, start=(-p * 4) % 360, extent=90, style='arc', outline='#d7ceeb', width=3)
        elif s == 'delegating':
            x = 38 + (p * 2) % 34                        # light travels from the sphere toward the departments
            self.create_oval(x - 4, 34, x + 4, 42, fill='#ffffff', outline='')
        elif s == 'waiting' and p % 2 == 0:              # one soft beat per ~2 s
            self.create_oval(4, 4, 72, 72, outline='#c9bdf0', width=2)


class RoundedPanel(tk.Canvas):
    """Native widgets remain focusable inside a rounded canvas surface."""
    def __init__(self, parent, padding=18):
        super().__init__(parent, background=BG, highlightthickness=0, height=100)
        self.content = ttk.Frame(self, style='Card.TFrame')
        self.surface = rounded(self, 0, 0, 100, 100, radius=22, fill='white', outline='')
        self.window = self.create_window(padding, padding, window=self.content, anchor='nw')
        def resize(_event=None):
            width = max(self.winfo_width(), 2*padding+1)
            height = self.content.winfo_reqheight()+2*padding
            self.itemconfigure(self.window, width=max(1, width-2*padding))
            self.configure(height=height)
            self.delete(self.surface)
            self.surface = rounded(self, 0, 0, width, height, radius=22, fill='white', outline='')
            self.tag_lower(self.surface)
        self.bind('<Configure>', resize)
        self.content.bind('<Configure>', resize)


def state_groups(projects):
    counts = Counter(p['state'] for p in projects)
    active = sum(counts[s] for s in ('CREATED', 'PLANNING', 'STAFFING', 'EXECUTING', 'VERIFYING', 'REWORK'))
    review = sum(counts[s] for s in ('OWNER_REVIEW', 'PENDING_CLOSE', 'ARCHIVE_PENDING_APPROVAL'))
    groups = [('진행 단계', active, '#4978e8'), ('검토 대기', review, ACCENT),
              ('일시 중지', counts['PAUSED'], '#e9ad49'), ('종료', counts['CLOSED'], '#52bdb1')]
    other = len(projects) - sum(n for _, n, _ in groups)
    if other:
        groups.append(('기타 상태', other, '#a7b0c1'))
    return groups


class Home(ttk.Frame):
    def __init__(self, parent, workspace):
        super().__init__(parent)
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
        self.projects = []
        viewport = tk.Canvas(self, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=viewport.yview)
        scrollbar.pack(side='right', fill='y')
        viewport.pack(side='left', fill='both', expand=True)
        viewport.configure(yscrollcommand=scrollbar.set)
        content = ttk.Frame(viewport)
        window = viewport.create_window(0, 0, window=content, anchor='nw')
        content.bind('<Configure>', lambda e: viewport.configure(scrollregion=viewport.bbox('all')))
        viewport.bind('<Configure>', lambda e: viewport.itemconfigure(window, width=e.width))
        self.viewport = viewport
        ttk.Label(content, text='좋은 하루예요. 청월입니다.', font=('Malgun Gothic', 22, 'bold')).pack(anchor='w', pady=(0, 6))
        self.summary = ttk.Label(content, text='목표를 맡기고, 진행 과정과 결과를 한곳에서 확인하세요.', style='Muted.TLabel')
        self.summary.pack(anchor='w', pady=(0, 14))
        self.chart = tk.Canvas(content, height=300, bg=BG, highlightthickness=0)
        self.chart.pack(fill='x')
        self.chart.bind('<Configure>', lambda e: self.draw_chart())
        row = ttk.Frame(content); row.pack(fill='x', pady=(16, 10))
        ttk.Label(row, text='둘러보기', font=('Malgun Gothic', 14, 'bold')).pack(side='left')
        self.refresh_button = ttk.Button(row, text='공개 정보 새로 수집', command=self.collect)
        self.refresh_button.pack(side='right')
        self.notice = ttk.Label(content, text='공개 출처의 실제 자료만 표시합니다. 수집 시 AI 호출 없음.', style='Muted.TLabel')
        self.notice.pack(anchor='w', pady=(0, 10))
        self.cards = ttk.Frame(content); self.cards.pack(fill='both', expand=True)
        self.render()

    def draw_chart(self):
        c = self.chart
        c.delete('all')
        width = max(c.winfo_width(), 500)
        groups = state_groups(self.projects)
        cardw = (width - 36) / 4
        for i, (label, count, color) in enumerate(groups[:4]):
            x = i * (cardw + 12)
            rounded(c, x, 0, x+cardw, 94, radius=22,
                    fill=('#e7eefb', '#eee8f8', '#fff0db', '#e2f2eb')[i], outline='')
            c.create_text(x+18, 22, text=label, anchor='w', fill=MUTED, font=('Malgun Gothic', 10))
            c.create_text(x+18, 60, text=str(count), anchor='w', fill=INK, font=('Segoe UI', 27, 'bold'))
            c.create_oval(x+cardw-30, 17, x+cardw-20, 27, fill=color, outline='')
        split = int(width * .59)
        rounded(c, 0, 108, split-6, 298, fill='white', outline='')
        rounded(c, split+6, 108, width, 298, fill='white', outline='')
        c.create_text(18, 132, text='업무 현황', anchor='w', fill=INK, font=('Malgun Gothic', 12, 'bold'))
        c.create_text(18, 155, text='저장된 프로젝트 상태 · 실제 활동은 프로젝트에서 확인', anchor='w', fill=MUTED, font=('Malgun Gothic', 9))
        maximum = max([n for _, n, _ in groups] + [1])
        for i, (label, n, color) in enumerate(groups):
            y = 180 + i*23
            c.create_text(18, y, text=label, anchor='w', fill=MUTED, font=('Malgun Gothic', 9))
            end = split-48
            c.create_line(105, y, end, y, fill='#f0f2f7', width=8)
            if n:
                c.create_line(105, y, 105+(end-105)*n/maximum, y, fill=color, width=8)
            c.create_text(split-24, y, text=str(n), fill=INK, font=('Segoe UI', 10))
        cx, cy, r = split+91, 211, 57
        total = len(self.projects)
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline='#eef0f5', width=16)
        angle = 90
        for label, n, color in groups:
            if n and total:
                extent = -360*n/total
                if n == total:
                    c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=color, width=16)
                else:
                    c.create_arc(cx-r, cy-r, cx+r, cy+r, start=angle, extent=extent, style='arc', outline=color, width=16)
                angle += extent
        c.create_text(cx, cy-7, text=str(total), fill=INK, font=('Segoe UI', 25, 'bold'))
        c.create_text(cx, cy+23, text='전체 업무', fill=MUTED, font=('Malgun Gothic', 9))
        c.create_text(split+170, 139, text='상태 분포', anchor='w', fill=INK, font=('Malgun Gothic', 12, 'bold'))
        for i, (label, n, color) in enumerate(groups):
            y = 173+i*23
            c.create_oval(split+169, y-3, split+175, y+3, fill=color, outline='')
            c.create_text(split+184, y, text=f'{label}  {n}', anchor='w', fill=MUTED, font=('Malgun Gothic', 9))

    def collect(self):
        if self.busy:
            return
        self.busy = True
        self.refresh_button.state(['disabled'])
        self.notice.config(text='공개 피드 수집 중…')
        messages = self.messages
        threading.Thread(target=lambda: messages.put(fetch_feeds()), daemon=True).start()

    def update_state(self, projects):
        self.projects = list(projects)
        signature = tuple(sorted(Counter(p['state'] for p in projects).items()))
        if signature != self._signature:
            self._signature = signature
            self.draw_chart()
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
        names = [category] if category else list(FEEDS)
        for col in range(2):
            self.cards.columnconfigure(col, weight=1 if col < len(names) else 0, uniform='feeds')
        for col, name in enumerate(names):
            data = self.data.get(name, {})
            panel = RoundedPanel(self.cards)
            panel.grid(row=0, column=col, sticky='new', padx=(0, 12 if col == 0 and len(names)>1 else 0), pady=(0, 12))
            box = panel.content
            ttk.Label(box, text=name, style='CardTitle.TLabel').pack(anchor='w', pady=(0, 8))
            labels = []
            def label(text, color=MUTED):
                widget = tk.Label(box, text=text, bg='white', fg=color, anchor='w', justify='left', font=('Malgun Gothic', 9), wraplength=300)
                widget.pack(fill='x', pady=3)
                labels.append(widget)
                return widget
            label(freshness(data.get('fetched')))
            if data.get('error'):
                label('수집 실패 · 기존 자료 유지: ' + data['error'], '#a25b20')
            items = data.get('items', [])[:3]
            if not items:
                label('아직 수집된 자료가 없습니다.\n위의 공개 정보 새로 수집을 눌러주세요.')
            for item in items:
                ttk.Separator(box).pack(fill='x', pady=10)
                url = item.get('url', '')
                title = label(item['title'], INK)
                title.config(font=('Malgun Gothic', 11, 'bold'), cursor='hand2', takefocus=True)
                def open_link(_event, u=url):
                    if urlsplit(u).scheme == 'https':
                        webbrowser.open(u)
                title.bind('<Button-1>', open_link)
                title.bind('<Return>', open_link)
                label(item.get('summary', '')[:140])
                published = time.strftime('%Y-%m-%d', time.localtime(item['published'])) if item.get('published') else '게시일 미상'
                label(f'{urlsplit(url).netloc} · {published}')
            box.bind('<Configure>', lambda e, widgets=labels: [w.configure(wraplength=max(140, e.width-40)) for w in widgets])
        self.viewport.yview_moveto(0)


def draw_pipeline(canvas, rows, on_select):
    """Current engine is sequential. Never invent concurrency or completion percentages."""
    canvas.delete('all')
    colors = {'✓': '#daf0e8', '●': '#dbe9ff', '✗': '#ffe2df', '✕': '#ffe2df', '!': '#fff0d5'}
    x = 15
    for row in rows:
        tag = 'node_' + row['key']
        current = row['mark'] == '●'                    # the node working or waiting now, from the engine record
        if x > 15:   # the hand-off into the current node is the only emphasised arrow; no moving decoration
            canvas.create_line(x - 24, 48, x - 4, 48, arrow='last', fill='#7964db' if current else '#60728b',
                               width=3 if current else 1)
        rounded(canvas, x, 10, x + 205, 94, fill=colors.get(row['mark'], '#f3f4f8'),
                outline='#7964db' if current else '', width=2 if current else 1, tags=tag)
        canvas.create_text(x + 10, 28, text=f'{row["mark"]} {row["title"]}', anchor='w', width=190, font=('Malgun Gothic', 10, 'bold'), tags=tag)
        canvas.create_text(x + 10, 69, text=f'{row["engine"]} · {row["detail"][:42]}', anchor='w', width=190, tags=tag)
        canvas.tag_bind(tag, '<Button-1>', lambda _e, key=row['key']: on_select(key))
        x += 235
    canvas.configure(scrollregion=(0, 0, max(x, 400), 105))
