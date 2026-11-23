"""One-way push through ntfy. The topic name is the secret; it lives only in push/config.json."""
from __future__ import annotations

import urllib.request


def send(config, title, text, priority="default", timeout=15):
    url = f"{config.get('ntfyServer', 'https://ntfy.sh').rstrip('/')}/{config['ntfyTopic']}"
    req = urllib.request.Request(url, data=text.encode("utf-8"), method="POST",
                                 headers={"Title": title.encode("ascii", "replace").decode(), "Priority": priority})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"ntfy returned {r.status}")
