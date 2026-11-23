/* Hologram skin (Phases 18/19): top bar, state mapping, Done effects. The conversation is chat.js, the sector panels
   are sector.js, the brain and dials are brain.js. State models: dashboard/STATE_MODEL_HOLO.md and STATE_MODEL_CHAT.md.
   Owns no data: everything shown comes from /api/state and every action calls the same endpoints as the Plain page. */
var HOLO_CSS = /*__HCSS__*/ "";
var HOLO_HTML = /*__HHTML__*/ "";

/* category name in /api/state -> sector */
var SECT = {
  Schoolwork: { id: "school", no: "01", label: "Schoolwork", color: "#2ee6ff" },
  Internships: {
    id: "intern",
    no: "02",
    label: "Internships",
    color: "#ff8a7a",
  },
  Personal: { id: "personal", no: "03", label: "Personal", color: "#4ade80" },
  Security: {
    id: "security",
    no: "04",
    label: "Security Projects",
    color: "#a78bfa",
  },
  Play: { id: "play", no: "05", label: "Play", color: "#fbbf24" },
};
var GREY = "#8a92b4";
/* Block length shown on Start. Mirrors blocks/blocks.py start_work (min 10, max 50, low energy max 20 from engine/config.json). */
var BLOCK = { min: 10, max: 50, lowMax: 20 };

var H = {
  inited: false,
  shown: false,
  root: null,
  host: null,
  state: null,
  msg: "",
  msgBad: false,
  msgT: null,
  menu: null,
  still: false,
  userStill: false,
  busy: false,
  pendT: 0,
  timers: [],
};

function $(id) {
  return H.root.getElementById(id);
}
function el(tag, props) {
  var e = document.createElement(tag),
    k,
    v,
    i;
  props = props || {};
  for (k in props) {
    v = props[k];
    if (v == null || v === false) continue;
    if (k.indexOf("on") === 0) e.addEventListener(k.slice(2), v);
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (i = 2; i < arguments.length; i++) {
    var c = arguments[i];
    if (c == null || c === false) continue;
    (Array.isArray(c) ? c : [c]).forEach(function (x) {
      if (x != null && x !== false) e.append(x);
    });
  }
  return e;
}
/* append that skips null/false children (the native one would print "null") */
function ap(node) {
  for (var i = 1; i < arguments.length; i++) {
    var c = arguments[i];
    (Array.isArray(c) ? c : [c]).forEach(function (x) {
      if (x != null && x !== false) node.append(x);
    });
  }
  return node;
}
function clear(n) {
  while (n.firstChild) n.removeChild(n.firstChild);
}
function hm(d) {
  return d.toLocaleTimeString("en-US", {
    hour12: true,
    hour: "numeric",
    minute: "2-digit",
  });
}
function day(d) {
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}
function dur(m) {
  m = Math.round(m);
  var h = Math.floor(m / 60),
    r = m % 60;
  return h && r ? h + " h " + r + " min" : h ? h + " h" : r + " min";
}
function mmss(s) {
  s = Math.max(0, Math.floor(s));
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}
function sect(cat) {
  return SECT[cat] || { id: null, no: "", label: cat || "Other", color: GREY };
}
function now() {
  return Date.now();
}
function running(j) {
  return !!j && (j.status === "queued" || j.status === "running");
}
function low() {
  return !!(H.state && H.state.mode && H.state.mode.lowEnergy);
}

/* ------------------------------------------------------------------ server calls (same as the other skins) */
function post(path, body) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Brain": "1" },
    body: JSON.stringify(body),
  }).then(function (r) {
    return r.json().then(function (j) {
      if (!r.ok) throw new Error(j.error || r.statusText);
      return j;
    });
  });
}
function refetch() {
  return fetch("/api/state")
    .then(function (r) {
      return r.json();
    })
    .then(update)
    .catch(function (e) {
      say("Lost the thread for a second. Retrying… " + e.message, true);
    });
}
function say(t, bad) {
  H.msg = t || "";
  H.msgBad = !!bad;
  clearTimeout(H.msgT);
  if (t)
    H.msgT = setTimeout(function () {
      H.msg = "";
      chatIdle();
    }, 7000);
  chatIdle();
}
function actionNote(body, after, before) {
  var still = [after.current].concat(after.queue || []).some(function (x) {
    return x && x.taskId === body.taskId;
  });
  if (body.action === "skip")
    return still
      ? (low() ? "It's past due" : "It slipped past its date") +
          ", so it stays in view."
      : before && before.current && before.current.taskId === body.taskId
        ? "Hidden for today. Here's the next best."
        : "Hidden for today.";
  if (body.action === "snooze")
    return still
      ? (low() ? "It's past due" : "It slipped past its date") +
          ", so it stays in view."
      : "Snoozed " +
          (body.until === "tomorrow"
            ? "until tomorrow"
            : "for " + body.hours + " h") +
          ".";
  if (body.action === "pin") return "Pinned to the top for today.";
  if (body.action === "unpin") return "Unpinned.";
  return "";
}
function doAction(body, path) {
  var before = H.state;
  if (H.busy) return Promise.resolve();
  H.busy = true;
  return post(path || "/api/action", body)
    .then(function (st) {
      if (!path) say(actionNote(body, st, before));
      update(st);
    })
    .catch(function (e) {
      say("Hm, that one slipped. Try again? " + e.message, true);
      return refetch();
    })
    .then(function () {
      H.busy = false;
    });
}
function blockAct(body) {
  return doAction(body, "/api/block");
}
function openFile(f) {
  post("/api/open", { path: f.path }).catch(function (e) {
    say("Couldn't open it: " + e.message, true);
  });
}

/* ------------------------------------------------------------------ menus (open upward, arrows move, Esc closes) */
function closeMenu(refocus) {
  if (!H.menu) return;
  var m = H.menu;
  H.menu = null;
  H.menuClosedAt = now();
  if (m.node.parentNode) m.node.parentNode.removeChild(m.node);
  m.btn.setAttribute("aria-expanded", "false");
  if (refocus) m.btn.focus();
}
function openMenu(btn, heading, items, right) {
  if (H.menu && H.menu.btn === btn) {
    closeMenu(true);
    return;
  }
  closeMenu();
  var box = el("div", {
    class: "menu rise" + (right ? " r" : ""),
    role: "menu",
    "aria-label": heading,
  });
  ap(box, el("p", { class: "mh", text: heading }));
  items.forEach(function (it) {
    if (it === "-") {
      ap(box, el("div", { class: "msep", role: "separator" }));
      return;
    }
    var sw = it.checked !== undefined;
    var rad = it.selected !== undefined; // one choice out of a group (a radio), with its description underneath
    var b = el(
      "button",
      {
        class: "mi" + (rad ? " rad" : ""),
        type: "button",
        tabindex: "-1",
        role: rad ? "menuitemradio" : sw ? "menuitemcheckbox" : "menuitem",
        "aria-checked": rad ? String(!!it.selected) : sw ? String(!!it.checked) : null,
      },
      el("span", { class: "b", "aria-hidden": "true" }),
      rad
        ? el(
            "span",
            { class: "l" },
            el("span", { class: "lt", text: it.label }),
            it.hint ? el("span", { class: "hint", text: it.hint }) : null,
          )
        : el("span", { class: "l", text: it.label }),
      !rad && it.hint ? el("span", { class: "hint", text: it.hint }) : null,
      sw ? el("span", { class: "sw", "aria-hidden": "true" }, el("i")) : null,
    );
    b.addEventListener("click", function (e) {
      e.stopPropagation();
      if (rad) {
        closeMenu(true);
        it.run();
        return;
      }
      if (sw) {
        it.checked = !it.checked;
        b.setAttribute("aria-checked", String(it.checked));
        it.run(it.checked);
        return;
      }
      closeMenu();
      it.run();
    });
    ap(box, b);
  });
  box.addEventListener("keydown", function (e) {
    var els = Array.prototype.slice.call(box.querySelectorAll(".mi")),
      i = els.indexOf(H.root.activeElement);
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeMenu(true);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      els[(i + 1) % els.length].focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      els[(i - 1 + els.length) % els.length].focus();
    } else if (e.key === "Tab") {
      var stops = Array.prototype.slice.call(
        box.querySelectorAll(".mi, input"),
      );
      if (stops.length > 1) {
        e.preventDefault();
        var k = stops.indexOf(H.root.activeElement);
        stops[(k + (e.shiftKey ? stops.length - 1 : 1)) % stops.length].focus();
      } else closeMenu();
    }
  });
  btn.parentNode.append(box);
  btn.setAttribute("aria-expanded", "true");
  H.menu = { btn: btn, node: box };
  var first = box.querySelector(".mi");
  if (first) first.focus();
}

/* ------------------------------------------------------------------ update (every fresh state) */
/* A Done takes QuickToDo about 3 to 6 s to finish. Until it does, hide the task and move on to the next one so the screen answers at once. */
function hideDonePending(s) {
  var a = s.actions,
    ids = {},
    any = false;
  ((a && a.pending) || []).forEach(function (p) {
    if (p.action === "complete" && p.taskId) {
      ids[p.taskId] = 1;
      any = true;
    }
  });
  /* After QuickToDo answers, its snapshot can still list the task for a few seconds: keep it hidden unless the Done was undone. */
  ((a && a.recent) || []).forEach(function (r) {
    if (
      r.action === "complete" &&
      r.outcome === "done" &&
      r.undoable &&
      r.taskId &&
      now() - new Date(r.processedAt || 0) < 90000
    ) {
      ids[r.taskId] = 1;
      any = true;
    }
  });
  if (!any) return s;
  function keep(t) {
    return !ids[t.taskId || t.id];
  }
  var o = Object.assign({}, s);
  if (s.queue) o.queue = s.queue.filter(keep);
  if (s.current && ids[s.current.taskId])
    o.current = o.queue && o.queue[0] ? o.queue[0] : null;
  if (s.command && s.command.tasks)
    o.command = Object.assign({}, s.command, {
      tasks: s.command.tasks.filter(keep),
    });
  return o;
}
function update(s) {
  if (!s) return;
  if (H.strikeUntil && now() < H.strikeUntil) {
    H.deferred = s;
    if (!H.defT)
      H.defT = setTimeout(
        function () {
          H.defT = 0;
          var d = H.deferred;
          H.deferred = null;
          if (d) update(d);
        },
        H.strikeUntil - now() + 30,
      );
    return;
  }
  /* When a Done/Undo/Add request settles, QuickToDo rewrites its snapshot a second or two later: look again so the change shows now, not at the next 30 s poll. */
  var np = ((s.actions && s.actions.pending) || []).length;
  if (H.lastPend > 0 && np === 0) {
    [1200, 3000, 6000].forEach(function (ms) {
      setTimeout(refetch, ms);
    });
  }
  H.lastPend = np;
  s = hideDonePending(s);
  if (!H.inited) init();
  H.state = s;
  if (typeof refreshTexts === "function") refreshTexts();
  if (!H.shown) return;
  var c = s.current;
  $("app").style.setProperty("--sec", c ? sect(c.category).color : GREY);
  renderTop(s);
  renderBrain(s);
  renderChat(s);
  if (H.open) renderSector();
  if (H.introWhenData && !H.introDone) setTimeout(playIntro, 120);
}

/* ------------------------------------------------------------------ brain and dials (brain.js draws; this maps the state) */
function mood(s) {
  var esc = 0,
    due = 0;
  (s.categories || []).forEach(function (c) {
    if (SECT[c.name]) {
      esc += c.escalated || 0;
      due += c.dueToday || 0;
    }
  });
  if (esc > 0 && !low()) return "missed";
  if (due >= 3 || (s.dayLoad && s.dayLoad.level === "heavy")) return "busy";
  return "calm";
}
function endOfWeek() {
  var d = new Date();
  d.setHours(23, 59, 59, 999);
  d.setDate(d.getDate() + ((7 - d.getDay()) % 7)); // through Sunday
  return d.getTime();
}
/* Per sector: count (the engine's open count), week (due by Sunday, past due included), soon (due in the next
   48 h), next (the engine's top item in that sector, else the soonest due), and whether it holds "do this now". */
function sectorData(s) {
  var t = now(),
    wk = endOfWeek(),
    tasks = (s.command && s.command.tasks) || [],
    cats = s.categories || [];
  var ranked = [s.current].concat(s.queue || []).filter(Boolean),
    cur = s.current && s.current.category;
  return ["Schoolwork", "Security", "Internships", "Personal", "Play"].map(
    function (name) {
      var m = SECT[name],
        row = cats.filter(function (c) {
          return c.name === name;
        })[0] || { open: 0 };
      var out = {
        id: m.id,
        no: m.no,
        label: m.label,
        color: m.color,
        count: row.open || 0,
        week: 0,
        soon: 0,
        next: null,
        subject: "",
        now: cur === name,
      };
      if (name === "Play") {
        var p = s.play || {},
          first =
            (p.projects || [])[0] ||
            (p.items || [])[0] ||
            (p.habits || []).filter(function (h) {
              return !h.doneToday;
            })[0];
        out.count = p.count != null ? p.count : out.count;
        out.next = first ? first.title : null;
        return out;
      }
      out.repeating = ((s.play && s.play.habits) || []).filter(function (h) {
        return h.cluster === m.id;
      }).length;
      var mine = tasks.filter(function (x) {
        return x.category === name;
      });
      if (row.focusId) {
        out.focus = true;
        out.later = row.later || 0;
        mine = mine.filter(function (x) {
          return x.taskId === row.focusId;
        });
      }
      mine.forEach(function (x) {
        if (!x.dueDate) return;
        var d = new Date(x.dueDate).getTime();
        if (d <= wk) out.week++;
        if (d > t && d - t <= 48 * 3600000) out.soon++;
      });
      out.week = Math.min(out.week, out.count);
      out.soon = Math.min(out.soon, out.count);
      var top = ranked.filter(function (x) {
        return x.category === name;
      })[0];
      if (top) {
        out.next = top.title;
        out.subject = subject(top);
      } else if (out.count) {
        var up = mine
          .filter(function (x) {
            return x.dueDate && new Date(x.dueDate) > t;
          })
          .sort(function (a, b) {
            return new Date(a.dueDate) - new Date(b.dueDate);
          })[0];
        out.next = (up || mine[0] || {}).title || null;
        out.subject = subject(up || mine[0] || {});
      }
      if (!out.count) out.next = null;
      return out;
    },
  );
}
function renderBrain(s) {
  if (!H.brainOn) return;
  HB.set(sectorData(s), mood(s), low(), H.still || document.hidden);
  $("ask").textContent = s.current
    ? "// what should i be doing right now?"
    : "// all quiet up here";
}

function renderTop(s) {
  var snap = s.snapshot,
    box = $("sync"),
    t = $("syncT"),
    warn = "";
  box.className = "sync";
  if (!snap) {
    box.classList.add("none");
    t.textContent = "no data yet";
  } else {
    var gen = new Date(snap.generatedAt),
      mins = Math.max(0, Math.round((new Date(s.serverTime) - gen) / 60000));
    var ago =
      mins >= 2
        ? " · " +
          (mins < 60 ? mins + " min" : Math.round(mins / 60) + " h") +
          " ago"
        : "";
    if (snap.stale) {
      box.classList.add("warn");
      t.textContent =
        "stale · last sync " + hm(gen) + ago + " · is QuickToDo running?";
    } else if (s.error) {
      box.classList.add("warn");
      t.textContent =
        "couldn't read the latest snapshot · showing the last good one";
    } else t.textContent = "synced " + hm(gen) + ago;
  }
  if (s.blocks && s.blocks.error) warn = s.blocks.error;
  else if (s.command && s.command.errors && s.command.errors.length)
    warn = s.command.errors[0];
  else if (s.actions && s.actions.error) warn = s.actions.error;
  $("warn").hidden = !warn;
  $("warn").textContent = warn;
  $("low").setAttribute("aria-pressed", String(low()));
  $("pow").setAttribute("aria-pressed", String(H.userStill));
  var pins = [s.current].concat(s.queue || []).filter(function (x) {
    return (
      x &&
      x.band === "pinned" &&
      SECT[x.category] &&
      SECT[x.category].id !== "play"
    );
  }).length;
  $("pinJump").hidden = !pins;
  $("pinJump").textContent = pins + " pinned ↗";
  var d = s.dayLoad,
    o = s.activeOverrides || {};
  $("footR").textContent = d
    ? "day looks " +
      d.level +
      " · " +
      (o.snoozes || 0) +
      " snoozed · " +
      (o.skips || 0) +
      " skipped"
    : "";
}

/* ------------------------------------------------------------------ left card */
function eb(text, lamp, color) {
  return el(
    "p",
    { class: "eb", style: color ? "color:" + color : null },
    lamp
      ? el("i", {
          class: "lamp",
          style: "background:" + lamp,
          "aria-hidden": "true",
        })
      : null,
    text,
  );
}
function btn(label, cls, fn, extra) {
  return el(
    "button",
    Object.assign(
      { class: "btn " + (cls || ""), type: "button", onclick: fn },
      extra || {},
    ),
    label,
  );
}
/* The subject: the QuickToDo list when it says more than the sector does (e.g. "Network Security" under Schoolwork). */
function subject(c) {
  var l = (c && c.list) || "";
  return l && l !== c.category && l !== sect(c.category).label ? l : "";
}
function pendingDone(id) {
  var a = H.state && H.state.actions;
  return (
    a &&
    (a.pending || []).some(function (p) {
      return p.taskId === id && p.action === "complete";
    })
  );
}
/* Done draws a line through the task's title first; screen updates wait until it has finished. */
var STRIKE_MS = 1000;
function strikeFx(id) {
  if (
    document.hidden ||
    (window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  )
    return 0;
  var els = [],
    cardEl = null;
  if (H.open && H.root) {
    cardEl = H.root.querySelector(".icard");
    var ic = cardEl && cardEl.querySelector("h3");
    if (ic) els.push(ic); // only the expanded card's title, not the node label
  }
  if (!els.length) return 0;
  els.forEach(function (e) {
    // wrap the words in an inline span so the line follows the text itself, line by line
    var sp = document.createElement("span");
    while (e.firstChild) sp.appendChild(e.firstChild);
    e.appendChild(sp);
    sp.classList.add("strike");
  });
  if (cardEl)
    setTimeout(function () {
      cardEl.classList.add("fadeout");
    }, 800);
  H.strikeUntil = now() + STRIKE_MS;
  H.afterDone = true;
  return STRIKE_MS;
}
function doDone(id) {
  var wait = strikeFx(id);
  doneFx();
  post("/api/done", { taskId: id })
    .then(function (st) {
      say("");
      update(st);
    })
    .catch(function (e) {
      say("Couldn't mark it done: " + e.message, true);
      refetch();
    });
  return wait;
}

function doneFx() {
  if (
    H.still ||
    document.hidden ||
    (window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  )
    return;
  var nowDial = H.root && H.root.querySelector(".dialn.now"); // Done flashes the sector's dial
  if (nowDial)
    nowDial.animate(
      [
        { filter: "brightness(1)" },
        { filter: "brightness(2.6)" },
        { filter: "brightness(1)" },
      ],
      { duration: 900, easing: "ease-out" },
    );
}

function mdInline(text) {
  var out = [],
    re = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\s][^*\n]*\*)/g,
    last = 0,
    m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    var t = m[0];
    if (t.slice(0, 2) === "**")
      out.push(el("strong", { text: t.slice(2, -2) }));
    else if (t[0] === "`") out.push(el("code", { text: t.slice(1, -1) }));
    else out.push(el("em", { text: t.slice(1, -1) }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
function mdBlocks(text) {
  var box = document.createDocumentFragment(),
    lines = String(text).replace(/\r/g, "").split("\n"),
    i = 0,
    para = [];
  function flush() {
    if (para.length) ap(box, ap(el("p"), mdInline(para.join("\n"))));
    para = [];
  }
  while (i < lines.length) {
    var ln = lines[i],
      m;
    if (/^\s*```/.test(ln)) {
      // fenced code
      flush();
      var code = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i]))
        code.push(lines[i++]);
      i++;
      ap(box, el("pre", {}, el("code", { text: code.join("\n") })));
    } else if (/^\s*$/.test(ln)) {
      flush();
      i++;
    } else if ((m = /^(#{1,6})\s+(.*)$/.exec(ln))) {
      flush();
      ap(
        box,
        ap(
          el("h" + Math.min(4, m[1].length + 1), { class: "mdh" }),
          mdInline(m[2].replace(/\s*#+\s*$/, "")),
        ),
      );
      i++;
    } else if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(ln)) {
      flush();
      ap(box, el("hr"));
      i++;
    } else if (/^\s*(?:[-*•])\s+/.test(ln) || /^\s*\d+[.)]\s+/.test(ln)) {
      flush();
      var ord = /^\s*\d+[.)]\s+/.test(ln),
        list = el(ord ? "ol" : "ul", { class: "md" });
      while (
        i < lines.length &&
        (ord ? /^\s*\d+[.)]\s+/ : /^\s*(?:[-*•])\s+/).test(lines[i])
      ) {
        ap(
          list,
          ap(
            el("li"),
            mdInline(
              lines[i].replace(ord ? /^\s*\d+[.)]\s+/ : /^\s*(?:[-*•])\s+/, ""),
            ),
          ),
        );
        i++;
      }
      ap(box, list);
    } else if (/^\s*\|/.test(ln)) {
      // a table: keep its columns lined up
      flush();
      var rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      ap(box, el("pre", {}, el("code", { text: rows.join("\n") })));
    } else if (/^\s*>\s?/.test(ln)) {
      flush();
      var q = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i]))
        q.push(lines[i++].replace(/^\s*>\s?/, ""));
      ap(box, ap(el("blockquote"), mdInline(q.join("\n"))));
    } else {
      para.push(ln);
      i++;
    }
  }
  flush();
  return box;
}

function growCmd() {
  var t = $("cmdin");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight, 140) + "px";
}
function setCmd(v) {
  $("cmdin").value = v;
  growCmd();
}

/* ------------------------------------------------------------------ add-a-task card (same requests as the other skins) */
var CLUSTER_OF_LIST = {
  play: "play",
  "side projects": "play",
  games: "play",
  personal: "personal",
  internships: "intern",
  "security projects": "security",
  "network security": "school",
  "cloud computing": "school",
  general: "personal",
};
function clock12(hhmm) {
  var h = parseInt(hhmm.slice(0, 2), 10),
    m = hhmm.slice(3, 5);
  return (
    (h % 12 || 12) + (m === "00" ? "" : ":" + m) + (h < 12 ? " AM" : " PM")
  );
}
/* the sector a list belongs to ("Sector 03 · Personal"), or the list's own name when it has none */
function sectorOfList(l) {
  var cid = CLUSTER_OF_LIST[String(l || "").toLowerCase()];
  for (var k in SECT) if (SECT[k].id === cid) return SECT[k];
  return null;
}

function pickTasks() {
  return (H.state && H.state.command && H.state.command.tasks) || [];
}

var AUTO = { list: [], sel: 0, from: 0 };
function autoTitles() {
  var s = H.state || {},
    seen = {},
    out = [];
  pickTasks()
    .map(function (t) {
      return t.title;
    })
    .concat(
      ((s.play && s.play.projects) || []).map(function (p) {
        return p.title;
      }),
      ((s.play && s.play.parking) || []).map(function (p) {
        return p.text;
      }),
    )
    .forEach(function (t) {
      if (t && !seen[t.toLowerCase()]) {
        seen[t.toLowerCase()] = 1;
        out.push(t);
      }
    });
  return out;
}
function wordsInOrder(frag, low) {
  /* every typed word starts a word in the title, in order: "network an" matches "Network traffic analyzer" */
  var tw = low.split(/[^a-z0-9']+/),
    at = 0;
  return frag.split(/\s+/).every(function (w) {
    while (at < tw.length && tw[at].indexOf(w) !== 0) at++;
    return at++ < tw.length;
  });
}
function autofill() {
  var ta = $("cmdin"),
    cut = ta.selectionStart,
    head = ta.value.slice(0, cut);
  AUTO.list = [];
  var m = head.match(/(\S+(?:\s+\S+){0,3})$/);
  if (m && head.slice(-1) !== " " && ta.selectionEnd === ta.value.length) {
    var words = m[1].split(/\s+/),
      titles = autoTitles();
    for (var n = Math.min(4, words.length); n >= 1 && !AUTO.list.length; n--) {
      var frag = words
        .slice(words.length - n)
        .join(" ")
        .toLowerCase();
      if (frag.length < 3) continue;
      var hits = titles.filter(function (t) {
        return t.toLowerCase() !== frag && wordsInOrder(frag, t.toLowerCase());
      });
      if (hits.length) {
        AUTO.list = hits.slice(0, 4);
        AUTO.from = cut - words.slice(words.length - n).join(" ").length;
        AUTO.frag = frag;
      }
    }
  }
  AUTO.sel = 0;
  drawAuto();
}
function drawAuto() {
  var box = $("auto"),
    ghost = $("ghost"),
    ta = $("cmdin");
  clear(box);
  clear(ghost);
  box.hidden = !AUTO.list.length;
  var titles = pickTasks();
  AUTO.list.forEach(function (t, i) {
    var task = titles.filter(function (x) {
        return x.title === t;
      })[0],
      where = task ? subject(task) || sect(task.category).label : "Play";
    ap(
      box,
      el(
        "li",
        {
          class: "ao" + (i === AUTO.sel ? " act" : ""),
          role: "option",
          "aria-selected": String(i === AUTO.sel),
          onmousedown: function (e) {
            e.preventDefault();
            acceptAuto(i);
          },
        },
        t,
        el("span", { class: "dim", text: " · " + where }),
      ),
    );
  });
  if (AUTO.list.length)
    ap(
      box,
      el("li", {
        class: "ah",
        role: "presentation",
        text: "tab fills it · arrows pick · esc closes",
      }),
    );
  /* grey completion after the cursor, only when the pick simply continues what was typed on a one-line field */
  var pick = AUTO.list[AUTO.sel],
    single =
      ta.value.indexOf("\n") < 0 && ta.scrollHeight <= ta.clientHeight + 2;
  ghost.style.left = ta.offsetLeft + "px";
  ghost.style.top = ta.offsetTop + "px";
  ghost.style.width = ta.clientWidth + "px";
  if (pick && single && pick.toLowerCase().indexOf(AUTO.frag) === 0) {
    ap(
      ghost,
      el("span", { class: "gi", text: ta.value }),
      el("span", { class: "gr", text: pick.slice(AUTO.frag.length) }),
      el("span", { class: "gt", text: "tab" }),
    );
  }
}
function hideAuto() {
  AUTO.list = [];
  drawAuto();
}
function acceptAuto(i) {
  var ta = $("cmdin"),
    t = AUTO.list[i];
  if (!t) return;
  var cut = ta.selectionStart;
  ta.value = ta.value.slice(0, AUTO.from) + t + ta.value.slice(cut);
  var pos = AUTO.from + t.length;
  ta.setSelectionRange(pos, pos);
  hideAuto();
  growCmd();
  chatLayout();
  ta.focus();
}

/* ------------------------------------------------------------------ timers */
function tick() {
  if (!H.shown || !H.state) return;
  /* the 3-2-1 before a block: look again once it reaches zero so the chat's quiet line flips to the timer */
  var v = H.state.blocks || {};
  if (v.phase === "starting" && v.block && new Date(v.block.startsAt) <= now() && now() - (H.startT || 0) > 1500) {
    H.startT = now();
    refetch();
  }
  var a = H.state.actions;
  if (a && a.pending && a.pending.length && now() - H.pendT > 1000) {
    // QuickToDo answers in a few seconds: check once a second
    H.pendT = now();
    refetch();
  }
}
function clockTick() {
  if (document.hidden || !H.shown) return;
  $("clk").textContent = new Date().toLocaleTimeString("en-US", {
    hour12: true,
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}
function playIntro() {
  if (H.introDone || !H.root) return;
  H.introDone = true;
  var app = $("app");
  if (!app.classList.contains("intro")) return;
  Array.prototype.forEach.call($("dials").children, function (d, i) {
    d.style.transitionDelay = 0.35 + i * 0.12 + "s";
  });
  app.classList.add("introing");
  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      app.classList.remove("intro");
    });
  });
  setTimeout(function () {
    Array.prototype.forEach.call($("dials").children, function (d) {
      d.style.transitionDelay = "";
    });
    app.classList.remove("introing");
  }, 2600);
}
function setStill(on) {
  H.still = on;
  $("app").classList.toggle("still", on);
  if (H.brainOn && H.state) renderBrain(H.state);
}

/* ------------------------------------------------------------------ init, show, hide */
function init() {
  H.inited = true;
  if (!document.getElementById("thFonts")) {
    var l = document.createElement("link");
    l.id = "thFonts";
    l.rel = "stylesheet";
    l.href =
      "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@300;400&family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap";
    document.head.appendChild(l);
  }
  var host = document.createElement("div");
  host.id = "holoHost";
  host.style.cssText = "position:fixed;inset:0;z-index:60;display:none";
  document.body.appendChild(host);
  H.host = host;
  H.root = host.attachShadow({ mode: "open" });
  H.root.innerHTML = "<style>" + HOLO_CSS + "</style>" + HOLO_HTML;
  try {
    H.userStill = localStorage.getItem("thalamusLowPower") === "1";
  } catch (e) {}
  var mq = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;
  setStill(H.userStill || !!(mq && mq.matches));
  if (mq && mq.addEventListener)
    mq.addEventListener("change", function () {
      setStill(H.userStill || mq.matches);
    });
  /* in the app, the wordmark clears the window buttons (same hook the old skin uses) */
  var prevPad = window.thalamusPad;
  window.thalamusPad = function (px) {
    $("top").style.paddingLeft = 32 + (px || 0) + "px";
    if (prevPad && prevPad !== window.thalamusPad) prevPad(px);
  };
  if (window.THALAMUS_APP) window.thalamusPad(window.THALAMUS_PAD || 0);
  /* welcome hand-off: the brain fades in, dials light one by one, top bar and dock rise last. In the app the page
     loads hidden behind the welcome screen, so it waits for the app's reveal (window.thalamusReveal). */
  if (!H.still) $("app").classList.add("intro");
  if (window.THALAMUS_APP && !window.THALAMUS_REVEALED) {
    window.thalamusReveal = playIntro;
    setTimeout(playIntro, 15000); // safety: never stay hidden
  } else H.introWhenData = true;
  document.addEventListener("visibilitychange", function () {
    $("app").classList.toggle("still", H.still || document.hidden);
    if (H.brainOn && H.state && H.shown) renderBrain(H.state); // pause when hidden, resume on return
  });

  $("low").addEventListener("click", function () {
    doAction({ action: "lowenergy", state: low() ? "off" : "on" });
  });
  $("pow").addEventListener("click", function () {
    H.userStill = !H.userStill;
    try {
      localStorage.setItem("thalamusLowPower", H.userStill ? "1" : "0");
    } catch (e) {}
    setStill(H.userStill || !!(mq && mq.matches));
    $("pow").setAttribute("aria-pressed", String(H.userStill));
  });

  $("cbar").addEventListener("submit", function (e) {
    e.preventDefault();
    chatSend(); // the chat drawer (chat.js): everything typed goes to POST /api/chat
  });
  /* auto-capitalize: the first letter of the box, and the first letter after a sentence end (". ", "! ", "? ") */
  function autoCap(field) {
    field.addEventListener("input", function () {
      var v = field.value, pos = field.selectionStart, out = "", last = 0, re = /(^|[.!?]\s+)([a-z])/g, m;
      while ((m = re.exec(v))) {
        var at = m.index + m[1].length;
        out += v.slice(last, at) + m[2].toUpperCase();
        last = at + 1;
      }
      out += v.slice(last);
      if (out !== v) {
        field.value = out;
        field.setSelectionRange(pos, pos);
      }
    });
  }
  autoCap($("cmdin"));
  $("cmdin").addEventListener("input", function () {
    growCmd();
    autofill();
  });
  $("cmdin").addEventListener("blur", function () {
    setTimeout(hideAuto, 150);
  });
  $("cmdin").addEventListener("keydown", function (e) {
    if (AUTO.list.length && !e.isComposing) {
      if (e.key === "Tab") {
        e.preventDefault();
        acceptAuto(AUTO.sel);
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        AUTO.sel =
          (AUTO.sel + (e.key === "ArrowDown" ? 1 : AUTO.list.length - 1)) %
          AUTO.list.length;
        drawAuto();
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        hideAuto();
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      hideAuto();
      e.preventDefault();
      $("cbar").requestSubmit();
    }
  });
  $("term").addEventListener("click", function (e) {
    var p = e.composedPath ? e.composedPath() : [];
    if (
      !p.some(function (x) {
        return (
          x && x.tagName && /^(BUTTON|INPUT|SELECT|TEXTAREA|A)$/.test(x.tagName)
        );
      }) &&
      !H.root.getSelection().toString()
    )
      $("cmdin").focus();
  });
  initChat();
  HB.init($("stage"));
  HB.onCoreTap = function () {
    say("// hi. you're doing fine.");
  };
  H.brainOn = true;
  HB.canOpen = function () {
    return true;
  };
  HB.onOpen = openSector;
  $("pinJump").addEventListener("click", jumpPinned);
  $("txt").addEventListener("click", function (e) {
    e.stopPropagation();
    openTexts(!$("textsP") || $("textsP").hidden);
  });
  document.addEventListener("click", function (e) {
    var tp = $("textsP");
    if (tp && !tp.hidden && !tp.contains(e.composedPath()[0]) && e.composedPath()[0] !== $("txt")) openTexts(false);
  });
  document.addEventListener(
    "keydown",
    function (e) {
      var tp = $("textsP");
      if (e.key === "Escape" && tp && !tp.hidden) {
        e.preventDefault();
        e.stopPropagation();
        openTexts(false);
        $("txt").focus();
        return;
      }
    },
    true,
  );
  document.addEventListener("keydown", function (e) {
    if (
      !H.shown ||
      !H.open ||
      e.key !== "Escape" ||
      H.menu ||
      now() - (H.menuClosedAt || 0) < 80
    )
      return;
    e.preventDefault();
    if (H.bsel) {
      var p = H.bsel;
      H.bsel = null;
      renderSector();
      focusSector(p);
    } else closeSector();
  });
  if (document.fonts && document.fonts.ready)
    document.fonts.ready.then(function () {
      HB.key = "";
      if (H.state) renderBrain(H.state);
    }); // label widths change once fonts load

  document.addEventListener("click", function (e) {
    if (!H.menu) return;
    var p = e.composedPath ? e.composedPath() : [];
    if (p.indexOf(H.menu.node) < 0 && p.indexOf(H.menu.btn) < 0) closeMenu();
  });
  document.addEventListener("keydown", function (e) {
    if (H.shown && e.key === "Escape" && H.menu) closeMenu(true);
  });

  H.timers.push(setInterval(tick, 500), setInterval(clockTick, 1000));
  clockTick();
}
function show(state) {
  if (!H.inited) init();
  H.shown = true;
  H.host.style.display = "block";
  document.body.style.overflow = "hidden";
  if (state) H.state = state;
  if (H.state) update(H.state);
  else refetch();
  clockTick();
}
function hide() {
  if (!H.inited) return;
  H.shown = false;
  closeMenu();
  H.host.style.display = "none";
  document.body.style.overflow = "";
}
window.Holo = { show: show, hide: hide, update: update, onSkin: null };
