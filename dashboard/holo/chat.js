/* The chat drawer (replaces the footer dock). State model: dashboard/STATE_MODEL_CHAT.md.
   The conversation lives on the server (/api/state -> chat, POST /api/chat); this file only draws it.
   The quiet line at the bottom grows into the drawer; the brain layer shrinks just enough to clear it. */

/* the / menu: each entry's starter fills the input. command/tests/test_help_examples.py checks every starter
   (plus `t`, a sample ending used only by the test) reaches the handler in `to`. */
var SLASH = [
  { k: "/now", d: "what to do next", s: "what should i do now", to: "now" },
  { k: "/due", d: "what's due, late or coming up", s: "what's due ", t: "friday", to: "schedule" },
  { k: "/add", d: "add a task or reminder", s: "remind me to ", t: "email dr lee friday", to: "capture" },
  { k: "/done", d: "finish, snooze, skip or pin a task", s: "done", to: "action" },
  { k: "/stuck", d: "a five-minute first step", s: "I'm stuck on ", t: "lab 7", to: "stuck" },
  { k: "/find", d: "open notes, slides, files", s: "find ", t: "teaching notes module 5", to: "lookup" },
  { k: "/where", d: "where I left off on a project", s: "where did I leave off on ", t: "the analyzer", to: "project" },
  { k: "/park", d: "save an idea to Play", s: "idea: ", t: "golf stats tracker", to: "park" },
  { k: "/prep", d: "tailor resume (+ letter) for job links", s: "prep: ", t: "https://example.com/job/1", to: "prep" },
];
var CHAT = {
  open: false,
  sending: null, // the message on its way (shown as her bubble until the server answers)
  sig: "",
  flown: null, // row ids whose fly-in already played (null until the first render: old rows never fly)
  seen: "", // newest reply id she has seen with the drawer open
  pollT: 0,
  tickT: 0,
  pastes: {}, // chip number -> pasted text, for the message being typed
  pasteN: 0,
  sent: {}, // message row id -> its pastes (this page session only, for the chip preview)
  stick: true, // follow new lines (false while she has scrolled up to read)
  slm: { list: [], sel: 0 },
  local: [], // replies made here when the server could not be reached
};
var CHIP_RE = /\[Pasted text #(\d+)(?: · \d+ lines?)?\]/g;
var CHAT_MAX = 220;

function chatRows() {
  var c = H.state && H.state.chat;
  return ((c && c.rows) || []).concat(CHAT.local);
}

/* ------------------------------------------------------------------ open, close, size */
function chatOpen(on, keepFocus) {
  on = !!on;
  if (CHAT.open === on) {
    if (on && !keepFocus) $("cmdin").focus();
    return;
  }
  CHAT.open = on;
  $("app").classList.toggle("chatopen", on);
  $("chatIdle").setAttribute("aria-expanded", String(on));
  $("conv").inert = !on; // closed: the input and links are out of the Tab order
  $("chatIdle").inert = on;
  if (on) {
    CHAT.stick = true;
    chatSeen();
    if (!keepFocus) setTimeout(function () { $("cmdin").focus(); }, 30);
  } else {
    slashHide();
    hideAuto();
    pastePreview(null);
    var a = H.root.activeElement;
    if (a && $("chatw").contains(a)) a.blur();
  }
  chatIdle();
  chatLayout();
}
function chatSeen() {
  var r = chatRows().filter(function (x) { return x.who === "th"; }).pop();
  CHAT.seen = r ? r.id + ":" + (r.final ? 1 : 0) + ":" + r.text.length : "";
}
/* The drawer is as tall as its messages (no empty space on top), up to CHAT_MAX, then it scrolls.
   The stage scales down from just under the top bar so the brain clears it. */
function chatLayout() {
  if (!H.root) return;
  var box = $("chatbox"),
    w = $("chatw"),
    stage = $("stage"),
    appH = $("app").clientHeight,
    h = 38;
  if (CHAT.open) {
    var inH = $("term").offsetHeight,
      n = $("msgsIn").childNodes.length,
      content = n ? $("msgsIn").offsetHeight + 16 : 0,
      max = Math.max(CHAT_MAX, inH + 70);
    h = Math.min(max, inH + content);
    box.classList.toggle("full", inH + content > max);
  }
  box.style.height = h + "px";
  var top = appH - parseFloat(getComputedStyle(w).bottom || "0") - h,
    sBot = stage.offsetTop + stage.offsetHeight,
    over = sBot + 10 - top,
    y0 = 64,
    s = 1;
  if (over > 0) s = Math.max(0.45, (stage.offsetHeight - over - y0) / (stage.offsetHeight - y0));
  stage.style.transformOrigin = "50% " + y0 + "px";
  stage.style.transform = s < 0.999 ? "scale(" + s.toFixed(4) + ")" : "";
  if (CHAT.open && CHAT.stick) {
    var m = $("msgs"); // follow new lines only while she is reading the bottom
    m.scrollTop = m.scrollHeight;
  }
  [$("slm"), $("auto"), $("pprev")].forEach(function (p) {
    p.style.bottom = h + 8 + "px";
  });
}

/* ------------------------------------------------------------------ the quiet line */
function chatIdle() {
  if (!H.root) return;
  var t = $("idleT"),
    k = $("idleK"),
    line = $("chatIdle"),
    s = H.state || {},
    v = s.blocks || {},
    b = v.block,
    ph = v.phase || "idle",
    rows = chatRows(),
    busy = rows.some(function (r) { return r.jobId && !r.final; }),
    last = rows.filter(function (x) { return x.who === "th"; }).pop(),
    unread = last && !CHAT.open && CHAT.seen !== last.id + ":" + (last.final ? 1 : 0) + ":" + last.text.length;
  var txt = "talk to thalamus",
    tail = "",
    kbd = "/ to type",
    tone = "";
  if (H.msg) {
    txt = H.msg;
    tone = H.msgBad ? "bad" : "";
  } else if (ph === "starting" && b) {
    var left = Math.max(0, Math.ceil((new Date(b.startsAt) - now()) / 1000));
    txt = "● Starting “" + b.title + "”";
    tail = "in " + left + " · say begin now";
    tone = "run";
  } else if (ph === "work" && b && v.over) {
    txt = b.overReason === "task-done" ? "● “" + b.title + "” is done" : "● Time's up on “" + b.title + "”";
    tail = b.overReason === "task-done" ? "break or keep going?" : "break, 15 more, or done?";
    tone = "warn";
  } else if (ph === "work" && b) {
    txt = "● " + b.title;
    tail = mmss((now() - new Date(b.startedAt)) / 1000) + " of " + b.minutes + " min";
    tone = "run";
  } else if (ph === "break" && b) {
    txt = "● Break · " + mmss((new Date(b.endsAt) - now()) / 1000) + " left";
    tone = "brk";
  } else if (ph === "checkin") {
    txt = "● Break's over · did you do something just for you?";
    tone = "warn";
  } else if (busy) {
    var j = rows.filter(function (r) { return r.jobId && !r.final; }).pop();
    txt = "● thinking" + (j && j.stage ? " · " + j.stage : "…");
    tone = "run";
  } else if (unread) {
    txt = "● new reply · " + last.text.split("\n")[0];
    tone = "new";
  }
  if (t.textContent !== txt) t.textContent = txt;
  $("idleR").textContent = tail;
  $("idleR").hidden = !tail;
  k.hidden = !!tail;
  k.textContent = kbd;
  line.className = "idle" + (tone ? " t-" + tone : "");
  var ticking = (ph === "work" && b && !v.over) || (ph === "starting" && b) || (ph === "break" && b);
  if (ticking && !CHAT.tickT) CHAT.tickT = setInterval(chatIdle, 1000);
  if (!ticking && CHAT.tickT) {
    clearInterval(CHAT.tickT);
    CHAT.tickT = 0;
  }
}

/* ------------------------------------------------------------------ the conversation */
function chipSpans(text, key) {
  var out = [],
    last = 0,
    m;
  CHIP_RE.lastIndex = 0;
  while ((m = CHIP_RE.exec(text))) {
    if (m.index > last) out.push(document.createTextNode(text.slice(last, m.index)));
    var n = +m[1];
    out.push(
      el("span", {
        class: "pchip",
        role: "button",
        tabindex: "0",
        title: "Show the pasted text",
        text: m[0].slice(1, -1),
        onclick: (function (n) {
          return function (e) {
            e.stopPropagation();
            var p = CHAT.sent[key];
            pastePreview(p && p[n - 1] != null ? { n: n, text: p[n - 1] } : { n: n, text: null });
          };
        })(n),
      }),
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(document.createTextNode(text.slice(last)));
  return out;
}
function rowEl(r) {
  if (r.who === "me") return el("div", { class: "me", "data-id": r.id }, chipSpans(r.text, r.id));
  var d = el("div", { class: "cth" + (r.tone ? " " + r.tone : ""), "data-id": r.id });
  if (r.jobId && !r.final) {
    ap(d, el("span", { class: "think", text: "thinking" + (r.stage ? " · " + r.stage : "…") }));
    return d;
  }
  var text = String(r.text || "");
  if (r.files && r.files.length)
    text = text
      .split("\n")
      .filter(function (ln) {
        return !(/^\s*[-*•]\s/.test(ln) && r.files.some(function (f) { return ln.indexOf(f.name) >= 0; }));
      })
      .join("\n");
  if (r.model || /\n/.test(text)) ap(d, mdBlocks(text));
  else ap(d, el("p", { text: text }));
  if (r.files && r.files.length)
    ap(
      d,
      el(
        "ul",
        { class: "cfiles" },
        r.files.map(function (f) {
          return el(
            "li",
            {},
            el("a", {
              href: "#",
              text: f.name,
              title: "Open " + (f.rel || f.name),
              onclick: function (e) {
                e.preventDefault();
                openFile(f);
              },
            }),
            f.rel ? el("small", { text: " " + f.rel.replace(/\/[^/]*$/, "") }) : null,
          );
        }),
      ),
    );
  return d;
}
function renderChat(s) {
  if (!H.root) return;
  var rows = chatRows(),
    sig = JSON.stringify(
      rows.map(function (r) {
        return [r.id, r.text, r.final, r.stage, r.tone, (r.files || []).length];
      }),
    ) + (CHAT.sending ? "|" + CHAT.sending : "");
  if (CHAT.flown === null) {
    CHAT.flown = {};
    rows.forEach(function (r) {
      if (r.fly) CHAT.flown[r.id] = 1;
    });
  }
  if (sig !== CHAT.sig) {
    CHAT.sig = sig;
    var box = $("msgsIn");
    clear(box);
    rows.forEach(function (r) {
      ap(box, rowEl(r));
    });
    if (CHAT.sending) ap(box, el("div", { class: "me out" }, chipSpans(CHAT.sending, "sending")));
    if (CHAT.open) chatSeen();
    chatLayout();
  }
  rows.forEach(function (r) {
    if (r.fly && !CHAT.flown[r.id]) {
      CHAT.flown[r.id] = 1;
      flyIn(r);
    }
  });
  chatIdle();
  /* look again soon while something is still on its way (a model answer, QuickToDo confirming an add or a Done) */
  var waiting = rows.some(function (r) {
    return (r.jobId && !r.final) || (r.act && !r.act.settled);
  });
  clearTimeout(CHAT.pollT);
  if (waiting) CHAT.pollT = setTimeout(refetch, 1200);
  /* a model is thinking: the stop square sits at the end of the input */
  var job = rows.filter(function (r) {
    return r.jobId && !r.final;
  }).pop();
  var stop = $("chatStop");
  stop.hidden = !job;
  stop.dataset.job = job ? job.jobId : "";
}

function chatStop() {
  var b = $("chatStop"),
    id = b.dataset.job;
  if (!id) return;
  b.disabled = true;
  post("/api/command/cancel", { id: id })
    .catch(function () {})
    .then(function () {
      b.disabled = false;
      refetch();
    });
}

/* ------------------------------------------------------------------ a task added from the chat flies into its dial */
function flyIn(r) {
  var m = sectorOfList(r.fly.list),
    dialN = m && HB.nodes && HB.nodes.querySelector('.dialn[data-id="' + m.id + '"]'),
    rowN = $("msgsIn").querySelector('[data-id="' + r.id + '"]');
  if (!dialN) return;
  var app = $("app").getBoundingClientRect(),
    sv = (dialN.querySelector("svg") || dialN).getBoundingClientRect(),
    to = { x: sv.left + sv.width / 2 - app.left, y: sv.top + sv.height / 2 - app.top };
  function land() {
    var ring = el("span", { class: "flyring" }),
      plus = el("span", { class: "flyplus", text: "+1" });
    ring.style.left = plus.style.left = to.x + "px";
    ring.style.top = plus.style.top = to.y + "px";
    ring.style.borderColor = plus.style.color = m.color;
    $("app").append(ring, plus);
    dialN.classList.add("hot");
    setTimeout(function () {
      ring.remove();
      plus.remove();
      dialN.classList.remove("hot");
    }, 1500);
  }
  if (H.still || !rowN || !CHAT.open || !Element.prototype.animate) {
    land();
    return;
  }
  var fr = rowN.getBoundingClientRect(),
    chip = el("span", { class: "flychip" }, el("i", { "aria-hidden": "true" }), r.fly.title);
  chip.style.setProperty("--c", m.color);
  $("app").append(chip);
  var x0 = fr.left - app.left,
    y0 = fr.top - app.top,
    cw = chip.offsetWidth / 2,
    ch = chip.offsetHeight / 2,
    mx = (x0 + to.x) / 2,
    my = Math.min(y0, to.y) - 70;
  chip
    .animate(
      [
        { transform: "translate(" + x0 + "px," + y0 + "px) scale(.9)", opacity: 0 },
        { transform: "translate(" + x0 + "px," + (y0 - 8) + "px) scale(1)", opacity: 1, offset: 0.15 },
        { transform: "translate(" + (mx - cw) + "px," + (my - ch) + "px) scale(.9)", offset: 0.6 },
        { transform: "translate(" + (to.x - cw) + "px," + (to.y - ch) + "px) scale(.15)", opacity: 0.2 },
      ],
      { duration: 1300, easing: "cubic-bezier(.45,0,.25,1)", fill: "forwards" },
    )
    .finished.then(function () {
      chip.remove();
      land();
    });
}

/* ------------------------------------------------------------------ sending */
function chatSend() {
  var ta = $("cmdin"),
    raw = ta.value.trim();
  if (!raw || CHAT.sending) return;
  /* renumber the chips 1..n in the order they sit, and send their text alongside */
  var pastes = [],
    text = raw.replace(CHIP_RE, function (m, n) {
      var p = CHAT.pastes[n];
      if (p == null) return m;
      pastes.push(p);
      return "[Pasted text #" + pastes.length + " · " + lineCount(p) + " line" + (lineCount(p) === 1 ? "" : "s") + "]";
    });
  var draft = { raw: raw, pastes: CHAT.pastes, n: CHAT.pasteN },
    before = {};
  chatRows().forEach(function (r) {
    before[r.id] = 1;
  });
  CHAT.sent.sending = pastes;
  CHAT.sending = text;
  CHAT.stick = true;
  CHAT.local = [];
  setCmd("");
  CHAT.pastes = {};
  CHAT.pasteN = 0;
  slashHide();
  hideAuto();
  pastePreview(null);
  renderChat(H.state);
  post("/api/chat", { text: text, pastes: pastes, sector: H.open || null })
    .then(function (st) {
      CHAT.sending = null;
      if (pastes.length) {
        var mine = ((st.chat && st.chat.rows) || []).filter(function (r) {
          return r.who === "me" && !before[r.id] && r.text.indexOf("[Pasted text #") >= 0;
        })[0];
        if (mine) CHAT.sent[mine.id] = pastes;
      }
      update(st);
    })
    .catch(function (e) {
      CHAT.sending = null;
      /* it never reached the server: put the draft back (with its pasted text) so she can send it again */
      if (!$("cmdin").value.trim()) {
        setCmd(draft.raw);
        CHAT.pastes = draft.pastes;
        CHAT.pasteN = draft.n;
      }
      CHAT.local.push({ id: "l-" + now(), who: "th", text: "That didn't reach me (" + e.message + "). It's back in the box; press Enter to send it again.", tone: "bad", final: true, at: new Date().toISOString() });
      renderChat(H.state);
      chatLayout();
    });
}
function lineCount(p) {
  return String(p).split("\n").length;
}

/* ------------------------------------------------------------------ pasted text: a chip in the input, whole or not at all */
function chipAt(v, pos) {
  var m;
  CHIP_RE.lastIndex = 0;
  while ((m = CHIP_RE.exec(v))) {
    var a = m.index,
      b = a + m[0].length;
    if (pos >= a && pos <= b) return { a: a, b: b, n: +m[1] };
  }
  return null;
}
function onPaste(e) {
  var p = e.clipboardData && e.clipboardData.getData("text/plain");
  if (!p || (lineCount(p) <= 3 && p.length <= 300)) return;
  e.preventDefault();
  var n = ++CHAT.pasteN,
    lines = lineCount(p),
    chip = "[Pasted text #" + n + " · " + lines + " line" + (lines === 1 ? "" : "s") + "]",
    ta = $("cmdin"),
    a = ta.selectionStart,
    pad = a > 0 && !/\s$/.test(ta.value.slice(0, a)) ? " " : "";
  CHAT.pastes[n] = p;
  ta.setRangeText(pad + chip + " ", a, ta.selectionEnd, "end");
  hideAuto();
  slashHide();
  growCmd();
  chatLayout();
}
function chipKeys(e) {
  var ta = $("cmdin");
  if ((e.key !== "Backspace" && e.key !== "Delete") || ta.selectionStart !== ta.selectionEnd) return false;
  var pos = ta.selectionStart,
    c = chipAt(ta.value, e.key === "Backspace" ? pos : pos);
  if (!c || (e.key === "Backspace" && pos === c.a) || (e.key === "Delete" && pos === c.b)) return false;
  e.preventDefault();
  ta.setRangeText("", c.a, c.b, "start");
  delete CHAT.pastes[c.n];
  hideAuto();
  slashHide();
  growCmd();
  chatLayout();
  pastePreview(null);
  return true;
}
function chipClick() {
  var ta = $("cmdin");
  if (ta.selectionStart !== ta.selectionEnd) return;
  var c = chipAt(ta.value, ta.selectionStart);
  if (c && ta.selectionStart > c.a && ta.selectionStart < c.b) pastePreview({ n: c.n, text: CHAT.pastes[c.n] });
  else pastePreview(null);
}
function pastePreview(p) {
  if (!H.root) return;
  var box = $("pprev");
  if (!p) {
    box.hidden = true;
    return;
  }
  $("pprevH").textContent = "Pasted text #" + p.n;
  $("pprevT").textContent = p.text == null ? "I don't keep pasted text after a reload, so it's not here anymore." : p.text;
  box.hidden = false;
}

/* ------------------------------------------------------------------ the / menu */
function slashUpdate() {
  var v = $("cmdin").value;
  if (!/^\/\S*$/.test(v)) {
    slashHide();
    return;
  }
  var q = v.slice(1).toLowerCase(),
    list = SLASH.filter(function (x) {
      return x.k.slice(1).indexOf(q) === 0;
    });
  if (!list.length) {
    slashHide();
    return;
  }
  CHAT.slm.list = list;
  CHAT.slm.sel = Math.min(CHAT.slm.sel, list.length - 1);
  hideAuto();
  slashDraw();
}
function slashDraw() {
  var ul = $("slmL");
  clear(ul);
  CHAT.slm.list.forEach(function (x, i) {
    ap(
      ul,
      el(
        "li",
        {
          class: "sr0" + (i === CHAT.slm.sel ? " on" : ""),
          role: "option",
          "aria-selected": String(i === CHAT.slm.sel),
          onmousedown: function (e) {
            e.preventDefault();
            slashPick(i);
          },
        },
        el("b", { text: x.k }),
        el("span", { text: x.d }),
      ),
    );
  });
  $("slm").hidden = false;
}
function slashHide() {
  CHAT.slm.list = [];
  CHAT.slm.sel = 0;
  if (H.root) $("slm").hidden = true;
}
function slashPick(i) {
  var x = CHAT.slm.list[i];
  if (!x) return;
  slashHide();
  setCmd(x.s);
  var ta = $("cmdin");
  ta.focus();
  ta.setSelectionRange(x.s.length, x.s.length);
  chatLayout();
}
function slashKeys(e) {
  if (!CHAT.slm.list.length || e.isComposing) return false;
  var n = CHAT.slm.list.length;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    CHAT.slm.sel = (CHAT.slm.sel + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
    slashDraw();
  } else if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) slashPick(CHAT.slm.sel);
  else if (e.key === "Escape") slashHide();
  else return false;
  e.preventDefault();
  e.stopPropagation();
  return true;
}

/* ------------------------------------------------------------------ wiring (called from init) */
function initChat() {
  var ta = $("cmdin");
  $("chatIdle").addEventListener("click", function () {
    chatOpen(true);
  });
  /* her keys in the input: the / menu first, then chips, then the autofill (holo.js), then Enter sends */
  ta.addEventListener(
    "keydown",
    function (e) {
      if (slashKeys(e)) {
        e.stopImmediatePropagation();
        return;
      }
      if (chipKeys(e)) e.stopImmediatePropagation();
    },
    true,
  );
  ta.addEventListener("input", function () {
    slashUpdate();
    pastePreview(null);
    chatLayout();
  });
  ta.addEventListener("paste", onPaste);
  ta.addEventListener("click", chipClick);
  ta.addEventListener("keyup", function (e) {
    if (e.key.indexOf("Arrow") === 0) chipClick();
  });
  $("conv").inert = true;
  $("chatStop").addEventListener("click", chatStop);
  $("msgs").addEventListener("scroll", function () {
    var m = $("msgs");
    CHAT.stick = m.scrollHeight - m.scrollTop - m.clientHeight < 40;
  });
  $("msgs").addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") && e.target.classList && e.target.classList.contains("pchip")) {
      e.preventDefault();
      e.target.click();
    }
  });
  /* "/" anywhere outside a text field opens the drawer; Esc closes the / menu, the autofill, then the drawer */
  document.addEventListener(
    "keydown",
    function (e) {
      if (!H.shown) return;
      var t = e.composedPath ? e.composedPath()[0] : e.target,
        typing = t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        chatOpen(true);
        return;
      }
      if (e.key !== "Escape" || !CHAT.open) return;
      var tp = $("textsP");
      if ((tp && !tp.hidden) || H.menu) return;
      if (AUTO.list.length || CHAT.slm.list.length) return; // the input's own handlers close those
      e.preventDefault();
      e.stopImmediatePropagation();
      if (!$("pprev").hidden) {
        pastePreview(null);
        return;
      }
      chatOpen(false);
      $("chatIdle").focus();
    },
    true,
  );
  document.addEventListener("click", function (e) {
    if (!CHAT.open) return;
    var p = e.composedPath ? e.composedPath() : [];
    if (p.indexOf($("chatw")) < 0) chatOpen(false);
    else if (p.indexOf($("pprev")) < 0 && !p.some(function (x) { return x.classList && x.classList.contains("pchip"); }) && p[0] !== ta)
      pastePreview(null);
  });
  window.addEventListener("resize", chatLayout);
}
