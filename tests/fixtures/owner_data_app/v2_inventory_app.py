#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""작은 매장용 재고 확인 웹앱 (Python 표준 라이브러리만 사용).

실행:
    python inventory_app.py                 # 서버 시작 + 브라우저 열기 (기본 포트 8050)
    python inventory_app.py --port 9000     # 포트 지정
    python inventory_app.py --no-browser    # 브라우저를 열지 않음
    python inventory_app.py --csv data.csv  # CSV 경로 지정
    python inventory_app.py --self-test     # 내장 테스트 실행

서버는 127.0.0.1에서만 열리며, 요청마다 CSV를 다시 읽습니다.
"""

import argparse
import csv
import html
import io
import json
import os
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOST = '127.0.0.1'
DEFAULT_PORT = 8050
LOW_STOCK_THRESHOLD = 5
CSV_RELATIVE_PATH = os.path.join('inputs', 'inventory.csv')
SUMMARY_TEMPLATE = '전체 품목 {total}개 · 재고 부족 품목 {low}개'
MISSING_CSV_MESSAGE = 'CSV 파일을 찾을 수 없습니다'

PAGE_CSS = """
body { font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
       margin: 0; padding: 24px; background: #f6f7f9; color: #222; }
main { max-width: 720px; margin: 0 auto; background: #fff; padding: 24px 28px;
       border-radius: 10px; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08); }
h1 { font-size: 1.5rem; margin: 0 0 12px; }
#summary { font-size: 1.1rem; font-weight: bold; margin: 8px 0 16px; }
table { width: 100%; border-collapse: collapse; font-size: 1rem; }
th, td { padding: 10px 12px; border-bottom: 1px solid #e3e5e8; text-align: left; }
th { background: #eef1f5; }
td.qty { text-align: right; font-variant-numeric: tabular-nums; }
th.qty { text-align: right; }
tr.low-stock { background: #ffe8e8; }
tr.low-stock td.status { color: #c62828; font-weight: bold; }
tr.normal td.status { color: #2e7d32; }
td.empty { color: #666; text-align: center; }
.warnings { margin: 16px 0; padding: 12px 16px; background: #fff8e1;
            border: 1px solid #f0c36d; border-radius: 6px; }
.warnings ul { margin: 6px 0 0; padding-left: 20px; }
.notice { margin: 16px 0; padding: 16px; background: #fff3f3;
          border: 1px solid #e0a0a0; border-radius: 6px; }
.meta { color: #666; font-size: 0.85rem; margin-top: 16px; word-break: break-all; }
"""


# ---------------------------------------------------------------- data

def resolve_csv_path(override=None):
    """Return the CSV path: --csv, else ./inputs/inventory.csv, else next to this script."""
    if override:
        return os.path.abspath(override)
    cwd_path = os.path.abspath(CSV_RELATIVE_PATH)
    if os.path.isfile(cwd_path):
        return cwd_path
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CSV_RELATIVE_PATH)
    if os.path.isfile(script_path):
        return script_path
    return cwd_path


def is_low_stock(qty):
    return qty <= LOW_STOCK_THRESHOLD


def parse_qty(text):
    """Return the integer in text (optional + or - sign, ASCII digits), else None."""
    digits = text[1:] if text and text[0] in '+-' else text
    if not (digits.isascii() and digits.isdigit()):
        return None
    return int(text)


def parse_inventory_text(text):
    """Parse CSV text with header item,qty. Returns (items, warnings)."""
    if text.startswith('﻿'):
        text = text[1:]
    reader = csv.reader(io.StringIO(text, newline=''))
    items = []
    warnings = []
    item_col = None
    qty_col = None
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        line = reader.line_num
        if item_col is None:
            header = [cell.strip().lower() for cell in row]
            if 'item' not in header or 'qty' not in header:
                warnings.append('{}번째 줄: 첫 줄(머리글)에 item, qty 열이 있어야 합니다.'.format(line))
                return items, warnings
            item_col = header.index('item')
            qty_col = header.index('qty')
            continue
        name = row[item_col].strip() if item_col < len(row) else ''
        qty_text = row[qty_col].strip() if qty_col < len(row) else ''
        if not name:
            warnings.append('{}번째 줄: 품목 이름이 비어 있어 건너뛰었습니다.'.format(line))
            continue
        qty = parse_qty(qty_text)
        if qty is None:
            warnings.append('{}번째 줄 ({}): 수량 "{}"이(가) 정수가 아니어서 건너뛰었습니다.'
                            .format(line, name, qty_text))
            continue
        items.append({'item': name, 'qty': qty, 'low_stock': is_low_stock(qty)})
    if item_col is None:
        warnings.append('CSV 파일에 머리글(item,qty)이 없습니다.')
    return items, warnings


def load_inventory(path):
    """Read the CSV file. Never raises; problems are reported in the 'error' field."""
    result = {'path': path, 'items': [], 'warnings': [], 'error': None}
    try:
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            text = f.read()
    except FileNotFoundError:
        result['error'] = '{}: {}'.format(MISSING_CSV_MESSAGE, path)
        return result
    except (OSError, UnicodeDecodeError):
        result['error'] = '{}(또는 읽을 수 없습니다): {}'.format(MISSING_CSV_MESSAGE, path)
        return result
    try:
        result['items'], result['warnings'] = parse_inventory_text(text)
    except csv.Error:
        result['error'] = '{}(또는 읽을 수 없습니다): {}'.format(MISSING_CSV_MESSAGE, path)
    return result


# ---- developer fixture addition (NOT model-generated): Owner data in ./data/inventory.json -------------------------
DATA_PATH = os.path.join('data', 'inventory.json')


def load_saved_items():
    """Items the Owner changed, if any (./data/inventory.json); None when there is no saved data."""
    try:
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            rows = json.load(f)
    except FileNotFoundError:
        return None
    return [{'item': r['item'], 'qty': int(r['qty']), 'low_stock': is_low_stock(int(r['qty']))} for r in rows]


def save_items(items):
    os.makedirs('data', exist_ok=True)
    tmp = DATA_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump([{'item': e['item'], 'qty': e['qty']} for e in items], f, ensure_ascii=False)
    os.replace(tmp, DATA_PATH)


def current_data(override):
    data = load_inventory(resolve_csv_path(override))
    saved = load_saved_items()
    if saved is not None:
        data = {'path': DATA_PATH, 'items': saved, 'warnings': [], 'error': None}
    return data


def summarize(items):
    return len(items), sum(1 for entry in items if entry['low_stock'])


def build_api_payload(data):
    total, low = summarize(data['items'])
    payload = {
        'items': [{'item': e['item'], 'qty': e['qty'], 'low_stock': e['low_stock']}
                  for e in data['items']],
        'total_count': total,
        'low_stock_count': low,
    }
    if data['error']:
        payload['error'] = data['error']
    return payload


# ---------------------------------------------------------------- HTML

def _page(title, body):
    return ('<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>' + html.escape(title) + '</title>\n<style>' + PAGE_CSS + '</style>\n'
            '</head>\n<body>\n<main>\n' + body + '\n</main>\n</body>\n</html>\n')


def render_page(data):
    parts = ['<h1>매장 재고 현황 (수정 버전 v2)</h1>', '<form method="post" action="/update" id="update-form"><label>품목 <input name="item" required></label> <label>수량 <input name="qty" type="number" required></label> <button type="submit">저장</button></form>']
    if data['error']:
        parts.append('<div id="load-error" class="notice" role="alert">'
                     '<p><strong>' + html.escape(data['error']) + '</strong></p>'
                     '<p>inputs 폴더에 inventory.csv 파일이 있는지 확인한 뒤 이 페이지를 새로고침하세요.</p>'
                     '</div>')
    else:
        total, low = summarize(data['items'])
        parts.append('<p id="summary">' + SUMMARY_TEMPLATE.format(total=total, low=low) + '</p>')
        rows = []
        for entry in data['items']:
            if entry['low_stock']:
                tr, status = '<tr class="low-stock">', '재고 부족'
            else:
                tr, status = '<tr class="normal">', '정상'
            rows.append(tr + '<td class="item">' + html.escape(entry['item']) + '</td>'
                        '<td class="qty">' + str(entry['qty']) + '</td>'
                        '<td class="status">' + status + '</td></tr>')
        if not rows:
            rows.append('<tr><td colspan="3" class="empty">표시할 품목이 없습니다.</td></tr>')
        parts.append('<table id="inventory-table">\n<thead><tr><th>품목</th>'
                     '<th class="qty">수량</th><th>상태</th></tr></thead>\n<tbody>\n'
                     + '\n'.join(rows) + '\n</tbody>\n</table>')
        if data['warnings']:
            parts.append('<div id="warnings" class="warnings" role="status">'
                         '<p>다음 행은 형식이 맞지 않아 건너뛰었습니다.</p><ul>'
                         + ''.join('<li>' + html.escape(w) + '</li>' for w in data['warnings'])
                         + '</ul></div>')
    parts.append('<p class="meta">수량 {}개 이하 품목은 재고 부족으로 표시됩니다. '
                 '새로고침하면 CSV 파일을 다시 읽습니다.<br>데이터 파일: {}</p>'
                 .format(LOW_STOCK_THRESHOLD, html.escape(data['path'])))
    return _page('매장 재고 현황', '\n'.join(parts))


def render_not_found():
    return _page('페이지를 찾을 수 없습니다',
                 '<h1>페이지를 찾을 수 없습니다</h1><p><a href="/">재고 현황으로 돌아가기</a></p>')


def render_internal_problem():
    return _page('잠시 후 다시 시도해 주세요',
                 '<h1>페이지를 표시하는 중 문제가 발생했습니다</h1>'
                 '<p>잠시 후 새로고침해 주세요.</p>')


# ---------------------------------------------------------------- server

class InventoryServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second socket steal a busy port, which would
    # hide "port in use" and break the fallback, so only enable it elsewhere.
    allow_reuse_address = os.name != 'nt'
    csv_override = None
    quiet = False


class InventoryHandler(BaseHTTPRequestHandler):
    server_version = 'InventoryApp/1.0'

    def do_GET(self):
        self._handle(send_body=True)

    def do_POST(self):
        # developer fixture addition: change one item's quantity and keep it in ./data/inventory.json
        from urllib.parse import parse_qs
        if urlsplit(self.path).path != '/update':
            self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
        form = parse_qs(self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode('utf-8'))
        name, qty = form.get('item', [''])[0].strip(), parse_qty(form.get('qty', [''])[0])
        data = current_data(self.server.csv_override)
        items = [e for e in data['items'] if e['item'] != name]
        if name and qty is not None:
            items.append({'item': name, 'qty': qty, 'low_stock': is_low_stock(qty)})
            save_items(items)
        self.send_response(303); self.send_header('Location', '/'); self.send_header('Content-Length', '0'); self.end_headers()

    def do_HEAD(self):
        self._handle(send_body=False)

    def _handle(self, send_body):
        path = urlsplit(self.path).path
        try:
            if path == '/':
                data = current_data(self.server.csv_override)
                status = 200
                ctype = 'text/html; charset=utf-8'
                body = render_page(data).encode('utf-8')
            elif path == '/api/inventory':
                data = current_data(self.server.csv_override)
                status = 503 if data['error'] else 200
                ctype = 'application/json; charset=utf-8'
                body = json.dumps(build_api_payload(data), ensure_ascii=False).encode('utf-8')
            else:
                status = 404
                ctype = 'text/html; charset=utf-8'
                body = render_not_found().encode('utf-8')
        except Exception:
            status = 500
            ctype = 'text/html; charset=utf-8'
            body = render_internal_problem().encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def log_message(self, format, *args):
        if getattr(self.server, 'quiet', False) or sys.stderr is None:
            return
        super().log_message(format, *args)


def make_server(port, explicit, csv_override=None, quiet=False):
    """Bind on 127.0.0.1. If the default port is busy (not given explicitly), use a free port."""
    try:
        server = InventoryServer((HOST, port), InventoryHandler)
    except OSError:
        if explicit:
            raise
        server = InventoryServer((HOST, 0), InventoryHandler)
    server.csv_override = csv_override
    server.quiet = quiet
    return server


def server_url(server):
    return 'http://{}:{}/'.format(HOST, server.server_address[1])


def _open_browser(url):
    try:
        webbrowser.open(url)
    except Exception:
        pass


def run_server(args):
    explicit = args.port is not None
    port = args.port if explicit else DEFAULT_PORT
    try:
        server = make_server(port, explicit, args.csv)
    except OSError as exc:
        print('포트 {}을(를) 사용할 수 없습니다: {}'.format(port, exc))
        return 1
    url = server_url(server)
    print('재고 확인 앱이 실행 중입니다: {}'.format(url))
    print('데이터 파일: {}'.format(resolve_csv_path(args.csv)))
    print('종료하려면 Ctrl+C를 누르거나 이 창을 닫으세요.')
    if sys.stdout is not None:
        sys.stdout.flush()
    if not args.no_browser:
        timer = threading.Timer(0.8, _open_browser, args=(url,))
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('종료합니다.')
    finally:
        server.server_close()
    return 0


# ---------------------------------------------------------------- CLI

def _port_number(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('포트는 0~65535 사이의 정수여야 합니다.')
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError('포트는 0~65535 사이의 정수여야 합니다.')
    return port


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='매장 재고 확인 웹앱 (127.0.0.1 전용)')
    parser.add_argument('--port', type=_port_number, default=None,
                        help='서버 포트 (기본 {}; 사용 중이면 빈 포트 사용)'.format(DEFAULT_PORT))
    parser.add_argument('--no-browser', action='store_true', help='브라우저를 자동으로 열지 않음')
    parser.add_argument('--csv', default=None, help='재고 CSV 파일 경로')
    parser.add_argument('--self-test', action='store_true', help='내장 테스트 실행')
    return parser.parse_args(argv)


def _make_console_safe():
    # Windows consoles/pipes may not use UTF-8; never crash on printing Korean.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(errors='backslashreplace')
            except Exception:
                pass


# ---------------------------------------------------------------- self-test

def _check(condition, message):
    # Explicit raise so the checks still run under python -O.
    if not condition:
        raise AssertionError(message)


def _fetch(opener, url):
    import urllib.error
    try:
        with opener.open(url, timeout=10) as resp:
            return resp.status, resp.headers.get('Content-Type', ''), resp.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode('utf-8', 'replace')
        finally:
            exc.close()
        return exc.code, exc.headers.get('Content-Type', '') if exc.headers else '', body


def _self_test_checks():
    import re
    import urllib.request

    # 1. Parsing: BOM, CRLF, invalid rows, blank line.
    text = '﻿item,qty\r\n종이컵,120\r\n빨대,4\r\n,7\r\n냅킨,abc\r\n컵홀더,2\r\n\r\n'
    items, warnings = parse_inventory_text(text)
    _check([e['item'] for e in items] == ['종이컵', '빨대', '컵홀더'], 'parsed item names/order wrong')
    _check([e['qty'] for e in items] == [120, 4, 2], 'parsed quantities wrong')
    _check(len(warnings) == 2, 'expected 2 warnings, got %d' % len(warnings))
    _check(warnings[0].startswith('4번째 줄') and warnings[1].startswith('5번째 줄'),
           'warning line numbers wrong')
    items, warnings = parse_inventory_text('item,qty\n뚜껑,60\n')
    _check(items == [{'item': '뚜껑', 'qty': 60, 'low_stock': False}] and not warnings,
           'LF parsing failed')

    # 2. Threshold: 5 is low, 6 is normal.
    _check(LOW_STOCK_THRESHOLD == 5, 'threshold must be 5')
    _check(is_low_stock(5) and not is_low_stock(6), 'is_low_stock boundary wrong')
    items, _ = parse_inventory_text('item,qty\r\nA,5\r\nB,6\r\n')
    _check([e['low_stock'] for e in items] == [True, False], 'parsed low_stock flags wrong')
    items, warnings = parse_inventory_text('item,qty\r\nC,-1\r\nD,+5\r\nE,1.5\r\nF,-\r\n')
    _check([(e['item'], e['qty'], e['low_stock']) for e in items] == [('C', -1, True), ('D', 5, True)],
           'signed integer quantities not parsed as low stock')
    _check(len(warnings) == 2, 'expected 2 warnings for 1.5 and -, got %d' % len(warnings))

    # 3. Escaping and warning block.
    page = render_page({'path': 'x.csv', 'items': [{'item': '<b>', 'qty': 1, 'low_stock': True}],
                        'warnings': [], 'error': None})
    _check('&lt;b&gt;' in page and '<b>' not in page, 'item name not HTML-escaped')
    _check('id="warnings"' not in page, 'warning block shown without warnings')
    _check('오류' not in page, 'normal page contains the forbidden word')
    items, warnings = parse_inventory_text('item,qty\r\n<i>,x\r\n')
    page = render_page({'path': 'x.csv', 'items': items, 'warnings': warnings, 'error': None})
    _check('id="warnings"' in page and '&lt;i&gt;' in page and '<i>' not in page,
           'warning block missing or not escaped')

    with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
        # 4. Missing CSV gives a friendly message.
        missing = load_inventory(os.path.join(tmp, 'nope.csv'))
        _check(missing['error'] and MISSING_CSV_MESSAGE in missing['error'], 'missing CSV not reported')
        page = render_page(missing)
        _check(MISSING_CSV_MESSAGE in page and 'Traceback' not in page, 'missing CSV page wrong')

        # 5. Real server on an ephemeral 127.0.0.1 port.
        csv_path = os.path.join(tmp, 'inventory.csv')
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            f.write('﻿item,qty\r\n종이컵,120\r\n빨대,4\r\n냅킨,35\r\n컵홀더,2\r\n뚜껑,60\r\n')
        server = make_server(0, True, csv_path, quiet=True)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1},
                                  daemon=True)
        thread.start()
        try:
            _check(server.server_address[0] == HOST, 'server not bound to 127.0.0.1')
            base = 'http://{}:{}'.format(HOST, server.server_address[1])
            # Empty ProxyHandler: never route the local request through a proxy.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            status, ctype, page = _fetch(opener, base + '/')
            _check(status == 200, 'GET / status %s' % status)
            _check(ctype == 'text/html; charset=utf-8', 'GET / content type %r' % ctype)
            _check('id="inventory-table"' in page and 'lang="ko"' in page, 'table or lang missing')
            _check('<p id="summary">전체 품목 5개 · 재고 부족 품목 2개</p>' in page,
                   'summary text wrong')
            names = ['종이컵', '빨대', '냅킨', '컵홀더', '뚜껑']
            positions = [page.find('<td class="item">%s</td>' % n) for n in names]
            _check(all(p >= 0 for p in positions) and positions == sorted(positions),
                   'rows missing or out of file order')
            low_rows = re.findall(r'<tr class="low-stock">(.*?)</tr>', page, re.S)
            _check(len(low_rows) == 2, 'expected 2 low-stock rows, got %d' % len(low_rows))
            _check('빨대' in low_rows[0] and '재고 부족' in low_rows[0], 'row 빨대 not low stock')
            _check('컵홀더' in low_rows[1] and '재고 부족' in low_rows[1], 'row 컵홀더 not low stock')
            _check(page.count('<td class="status">정상</td>') == 3, 'expected 3 normal rows')
            _check('id="warnings"' not in page and '오류' not in page,
                   'normal page shows warnings or forbidden word')

            status, ctype, api = _fetch(opener, base + '/api/inventory')
            _check(status == 200, 'GET /api/inventory status %s' % status)
            _check(ctype == 'application/json; charset=utf-8', 'API content type %r' % ctype)
            _check('"low_stock_count": 2' in api and '"total_count": 5' in api, 'API counts wrong')
            expected = {
                'items': [{'item': n, 'qty': q, 'low_stock': q <= 5}
                          for n, q in zip(names, [120, 4, 35, 2, 60])],
                'total_count': 5,
                'low_stock_count': 2,
            }
            _check(api == json.dumps(expected, ensure_ascii=False), 'API body differs from expected')

            status, _, body = _fetch(opener, base + '/no-such-page')
            _check(status == 404, 'unknown path returned %s, expected 404' % status)
            _check('Traceback' not in body, '404 page contains a traceback')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


def run_self_test():
    try:
        _self_test_checks()
    except Exception as exc:
        print('SELF-TEST FAILED: {}: {}'.format(type(exc).__name__, exc))
        sys.exit(1)
    print('SELF-TEST PASSED')
    sys.exit(0)


if __name__ == '__main__':
    _make_console_safe()
    cli_args = parse_args()
    if cli_args.self_test:
        run_self_test()
    sys.exit(run_server(cli_args))
