"""Read-only page fetch for job postings (Phase 13). Plain HTTP, no login, no cookies.

Guards: http(s) only, no private/loopback addresses (checked on every redirect hop),
15 s timeout, 1 MB cap. Blocked or thin pages raise NeedsPaste so Morgan can paste the text.
"""
import ipaddress, re, socket, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser

TIMEOUT = 15
MAX_BYTES = 1_000_000
MIN_TEXT = 400
BLOCKED_HOSTS = ("joinhandshake.com", "linkedin.com")
WALL_WORDS = ("sign in to continue", "log in to view", "enable javascript", "access denied", "verify you are human", "captcha")


class NeedsPaste(Exception):
    """The page cannot be read automatically; Morgan pastes the description instead."""


class BadUrl(ValueError):
    pass


def check_url(url):
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise BadUrl("only http and https links are accepted")
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except OSError:
        raise NeedsPaste(f"couldn't look up {p.hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise BadUrl("that address is not a public website")
    return p


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer"}

    def __init__(self):
        super().__init__(); self.out = []; self.skip = 0; self.title = ""; self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title": self._in_title = True
        if tag in self.SKIP and tag != "head": self.skip += 1
        if tag in ("p", "br", "li", "div", "h1", "h2", "h3", "tr"): self.out.append("\n")

    def handle_endtag(self, tag):
        if tag == "title": self._in_title = False
        if tag in self.SKIP and tag != "head" and self.skip: self.skip -= 1

    def handle_data(self, d):
        if self._in_title: self.title += d
        elif not self.skip: self.out.append(d)


def html_to_text(html):
    t = _Text(); t.feed(html)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(t.out))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return t.title.strip(), text


class _Guard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_posting(url, opener=None):
    """Return (title, text). Raises BadUrl, NeedsPaste."""
    p = check_url(url)
    host = p.hostname.lower()
    if any(host == h or host.endswith("." + h) for h in BLOCKED_HOSTS):
        raise NeedsPaste(f"{host} needs a login, so it can't be read automatically")
    op = opener or urllib.request.build_opener(_Guard)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (priority-brain prep; read-only)", "Accept": "text/html"})
    try:
        with op.open(req, timeout=TIMEOUT) as r:
            raw = r.read(MAX_BYTES + 1)[:MAX_BYTES]
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise NeedsPaste(f"the site answered {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise NeedsPaste(f"couldn't load the page ({e})")
    if "html" not in ctype and "text" not in ctype:
        raise NeedsPaste("the link isn't a web page")
    title, text = html_to_text(raw.decode("utf-8", "replace"))
    low = text.lower()
    if len(text) < MIN_TEXT or any(w in low for w in WALL_WORDS) and len(text) < 2500:
        raise NeedsPaste("the page has too little readable text (probably a login wall or a script-built page)")
    return title, text
