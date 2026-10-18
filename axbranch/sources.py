"""Source verification for documents: read the PUBLIC originals a report cites and keep what was read as evidence.

Read-only and bounded: GET only, no cookies or credentials, http(s) to public addresses only (private, loopback,
link-local and reserved addresses are refused, re-checked on every redirect), size and time limits. A source that
cannot be read is recorded as such and can never support a claim. A claim counts as supported only when the
verifier's quote is found verbatim (whitespace-normalised) in the text actually fetched from that source."""
import hashlib
import html.parser
import http.client
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

MAX_SOURCES, MAX_BYTES, TIMEOUT, MAX_REDIRECTS = 40, 2 * 2**20, 20, 3
MIN_QUOTE = 20                       # characters: a shorter "quote" proves nothing about a source
_URL = re.compile(r'https?://[^\s<>()\[\]"\'`]+', re.I)
USER_AGENT = 'AX-Branch-source-check/1 (read-only verification of cited sources)'


def cited_urls(text, limit=MAX_SOURCES):
    """URLs a document cites, in order of first appearance (trailing punctuation removed)."""
    seen = []
    for m in _URL.finditer(text or ''):
        url = m.group(0).rstrip('.,;:!?*_')
        if url not in seen:
            seen.append(url)
    return seen[:limit]


def _public_address(value):
    ip = ipaddress.ip_address(value.split('%')[0])
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _public(host):
    try:
        infos = socket.getaddrinfo(host, None)
        if not infos or any(not _public_address(info[4][0]) for info in infos):
            return False, f'{host} resolves to a non-public address'
    except (OSError, ValueError) as e:
        return False, f'cannot resolve {host}: {e}'
    return True, ''


def _connect_public(address, timeout=TIMEOUT, source_address=None):
    """Validate the resolution used for this connection and connect the exact numeric sockaddr.
    Never let a second name lookup change a checked public destination into a private one.
    HTTPSConnection still validates the original hostname and uses it for SNI.
    """
    host, port = address
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not infos or any(not _public_address(info[4][0]) for info in infos):
        raise OSError(f'{host} resolves to a non-public address')
    last = None
    for family, kind, proto, _, sockaddr in infos:
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as e:
            last = e
            sock.close()
    raise last or OSError('no usable public address')


class _HTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_HTTPConnection, req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_HTTPSConnection, req, context=self._context)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None                   # redirects are followed by hand, each target re-checked


class _Text(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'template'):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'template') and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def normalise(text):
    return ' '.join(str(text).split()).lower()


def _fetch(url, opener=None):
    """One source: {url, final_url, status, content_type, bytes, sha256, accessible, error, text}."""
    rec = {'url': url, 'final_url': None, 'status': None, 'content_type': None, 'bytes': 0, 'sha256': None,
           'accessible': False, 'error': None, 'text': ''}
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect, _HTTPHandler, _HTTPSHandler)
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        parts = urllib.parse.urlsplit(current)
        if (parts.scheme not in ('http', 'https') or not parts.hostname
                or parts.username is not None or parts.password is not None):
            rec['error'] = f'not an http(s) URL: {current}'
            return rec
        ok, why = _public(parts.hostname)
        if not ok:
            rec['error'] = why
            return rec
        request = urllib.request.Request(current, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,text/plain,*/*'})
        try:
            resp = opener.open(request, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get('Location'):
                current = urllib.parse.urljoin(current, e.headers['Location'])
                e.close()
                continue
            rec.update(status=e.code, final_url=current, error=f'HTTP {e.code}')
            e.close()
            return rec
        except (urllib.error.URLError, OSError, ValueError) as e:
            rec.update(final_url=current, error=f'{type(e).__name__}: {e}'[:300])
            return rec
        with resp:
            data = resp.read(MAX_BYTES + 1)
            rec.update(status=resp.status, final_url=current, content_type=resp.headers.get('Content-Type', ''))
        if len(data) > MAX_BYTES:
            data = data[:MAX_BYTES]
            rec['error'] = f'truncated at {MAX_BYTES} bytes'
        if not (rec['content_type'].lower().startswith(('text/', 'application/xhtml+xml', 'application/json'))):
            rec['error'] = 'unsupported content type (text sources only)'
            return rec
        charset = re.search(r'charset=([\w-]+)', rec['content_type'] or '', re.I)
        body = data.decode(charset.group(1) if charset else 'utf-8', errors='replace')
        if 'html' in (rec['content_type'] or '').lower() or body.lstrip()[:15].lower().startswith(('<!doctype', '<html')):
            parser = _Text()
            parser.feed(body)
            body = ' '.join(' '.join(parser.parts).split())
        rec.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), text=body,
                   accessible=200 <= rec['status'] < 300 and bool(body.strip()))
        return rec
    rec['error'] = f'more than {MAX_REDIRECTS} redirects'
    return rec


def fetch(url, opener=None):
    """A failed URL/read/decode is evidence of unavailability, never an engine crash.
    TIMEOUT bounds individual socket operations, not a total wall-clock deadline for DNS/slow streaming.
    """
    try:
        return _fetch(url, opener)
    except (OSError, ValueError, LookupError, http.client.HTTPException) as e:
        return {'url': url, 'final_url': None, 'status': None, 'content_type': None, 'bytes': 0,
                'sha256': None, 'accessible': False, 'error': f'{type(e).__name__}: {e}'[:300], 'text': ''}


def check_claims(claims, fetched):
    """Deterministic check of the verifier's claim judgments against what was actually fetched.
    claims: [{claim, source_url, quote, verdict}]. Returns the claims with 'checked_verdict' and 'check' notes."""
    by_url = {}
    for rec in fetched:
        for key in (rec['url'], rec.get('final_url')):
            if key:
                by_url[key.rstrip('/')] = rec
    out = []
    for c in claims:
        rec = by_url.get(str(c.get('source_url', '')).rstrip('/'))
        quote = normalise(c.get('quote', ''))
        verdict = c.get('verdict')
        if verdict not in ('supported', 'contradicted', 'unverifiable'):
            checked, note = 'unverifiable', 'invalid claim verdict'
        elif not str(c.get('claim', '')).strip():
            checked, note = 'unverifiable', 'empty claim'
        elif rec is None:
            checked, note = 'unverifiable', 'cited source was not fetched (not cited in the document or over the limit)'
        elif not rec['accessible']:
            checked, note = 'unverifiable', f"source not accessible: {rec['error'] or rec['status']}"
        elif verdict in ('supported', 'contradicted') and (len(quote) < MIN_QUOTE or quote not in normalise(rec['text'])):
            checked, note = 'unverifiable', 'quote not found verbatim in the fetched source text'
        else:
            checked, note = verdict, 'quote found in the fetched source text' if verdict in ('supported', 'contradicted') else ''
        out.append({**c, 'checked_verdict': checked, 'check': note})
    return out
