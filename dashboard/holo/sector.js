/* Open sector and task card (Phase 19, slice d; views 1 to 6 in mockups/brain/STATES.md).
   A dial glides left, the brain dims, the sector's tasks branch out as small dials, and a glass card opens beside
   the selected one. The dock shrinks to the command bar meanwhile. Same requests as the other skins.
   Bundled after holo.js in the same scope (uses its helpers). Play opens in slice e. */

var BR_MAX = 5; // branches shown; past this, 4 tasks and a "+N more" dial
var TOOL_ICON = {
  pin: "M9 2h6l-1 6 3 3H7l3-3zM12 14v7",
  snooze: "M4 12a8 8 0 1 0 8-8M4 4v5h5M12 8v4l3 2",
  skip: "M5 5l7 7-7 7M13 5l7 7-7 7",
  stuck: "M13 3L5 14h6l-1 7 8-11h-6z",
  earlier: "M3 12a9 9 0 1 0 3-6.7M3 4v5h5M12 7v5l3 3",
};

function secById(id) {
  for (var k in SECT) if (SECT[k].id === id) return { name: k, m: SECT[k] };
  return null;
}
function catRowOf(s, name) {
  return (
    ((s && s.categories) || []).filter(function (c) {
      return c.name === name;
    })[0] || { open: 0 }
  );
}
/* Branches for a sector: the engine's ranked items first (they carry why-lines), then every other open task
   by due date, then repeating items that live in this sector. Security keeps to its one focus project. */
function branchItems(s, id) {
  var sc = secById(id),
    name = sc.name,
    row = catRowOf(s, name),
    seen = {},
    out = [],
    cur = s.current && s.current.taskId;
  function push(t, ranked) {
    if (!t || seen[t.taskId]) return;
    seen[t.taskId] = 1;
    out.push({
      kind: "task",
      id: t.taskId,
      title: t.title,
      list: t.list || "",
      category: name,
      dueDate: t.dueDate || null,
      minutes: ranked ? t.minutes : null,
      minutesEstimated: t.minutesEstimated,
      why: ranked ? t.why || "" : "",
      resources: ranked ? t.resources || "" : "",
      band: t.band || "",
      now: t.taskId === cur,
      pinned: t.band === "pinned",
    });
  }
  if (row.focusId) {
    // Security: the focus project leads, the rest follow behind it and can be opened like any other branch
    var fr = [s.current].concat(s.queue || []).filter(function (t) {
      return t && t.category === name && t.taskId === row.focusId;
    })[0];
    if (fr) push(fr, true);
  }
  [s.current].concat(s.queue || []).forEach(function (t) {
    if (t && t.category === name) push(t, true);
  });
  ((s.command && s.command.tasks) || [])
    .filter(function (t) {
      return t.category === name;
    })
    .sort(function (a, b) {
      if (!a.dueDate !== !b.dueDate) return a.dueDate ? -1 : 1;
      return a.dueDate
        ? new Date(a.dueDate) - new Date(b.dueDate)
        : a.title.localeCompare(b.title);
    })
    .forEach(function (t) {
      push(t, false);
    });
  ((s.play && s.play.habits) || [])
    .filter(function (h) {
      return h.cluster === id;
    })
    .forEach(function (h) {
      out.push({ kind: "habit", id: h.id, title: h.title, habit: h });
    });
  return out;
}
function branchDue(it) {
  if (it.kind === "habit") {
    var h = it.habit;
    return h.doneToday
      ? "done today"
      : h.cadence + (h.dueToday ? " · one for today" : "");
  }
  if (!it.dueDate) return "no deadline";
  var d = new Date(it.dueDate);
  if (it.band === "escalated" || d < now())
    return low() ? "past due" : "slipped past " + day(d);
  return day(d) + " · " + hm(d);
}
function branchFill(it) {
  if (it.kind === "habit") return it.habit.doneToday ? 1 : 0.3;
  if (!it.dueDate) return 0.1;
  var days = (new Date(it.dueDate) - now()) / 86400000;
  return Math.max(0.06, Math.min(1, 1 - days / 14));
}
function branchSoon(it) {
  return (
    it.kind === "task" &&
    !!it.dueDate &&
    new Date(it.dueDate) - now() < 48 * 3600000
  );
}
function miniDial(it, color) {
  var C = 2 * Math.PI * 17,
    k = it.kind,
    dashed =
      k === "more" ||
      k === "idea" ||
      k === "pidea" ||
      k === "add" ||
      k === "offer",
    faint = k === "idea" || k === "pidea" || k === "add",
    fill =
      k === "project" || k === "item"
        ? 1
        : k === "task" || k === "habit"
          ? branchFill(it)
          : 0, // projects: a solid ring
    o = [];
  o.push(
    '<svg width="46" height="46" viewBox="-23 -23 46 46" aria-hidden="true" style="flex:none;filter:drop-shadow(0 0 8px ' +
      color +
      '55)">',
  );
  o.push(
    '<circle r="21" fill="none" stroke="' +
      color +
      '" stroke-opacity=".28" stroke-width="1" stroke-dasharray="' +
      (dashed ? "2 4" : "1 5") +
      '"/>',
  );
  o.push(
    '<circle r="17" fill="' +
      color +
      '" fill-opacity="' +
      (faint ? ".04" : ".12") +
      '" stroke="#fff" stroke-opacity=".1" stroke-width="2.5"/>',
  );
  if (fill > 0)
    o.push(
      '<circle r="17" fill="none" stroke="' +
        color +
        '" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="' +
        (fill * C).toFixed(1) +
        " " +
        C.toFixed(1) +
        '" transform="rotate(-90)"/>',
    );
  if (branchSoon(it)) o.push('<circle cx="0" cy="-21" r="2.4" fill="#fff"/>');
  if (k === "more")
    o.push(
      '<text y="4.5" text-anchor="middle" fill="#fff" font-family="JetBrains Mono, monospace" font-size="12">+' +
        it.n +
        "</text>",
    );
  else if (k === "add")
    o.push(
      '<text y="6" text-anchor="middle" fill="' +
        color +
        '" font-family="Inter, sans-serif" font-size="18">+</text>',
    );
  else if (k === "offer")
    o.push(
      '<text y="5" text-anchor="middle" fill="' +
        color +
        '" font-family="Inter, sans-serif" font-size="13">✦</text>',
    );
  else if (k === "idea" || k === "pidea")
    o.push('<circle r="2.6" fill="' + color + '" fill-opacity=".5"/>');
  else if (k === "habit")
    o.push(
      '<text y="5" text-anchor="middle" fill="' +
        color +
        '" font-family="Inter, sans-serif" font-size="14">↻</text>',
    );
  else
    o.push(
      '<circle r="' + (it.now ? 4 : 2.6) + '" fill="#fff" fill-opacity=".9"/>',
    );
  o.push("</svg>");
  return o.join("");
}
function toolBtn(icon, label, fn, on) {
  var b = el("button", {
    class: "tool" + (on ? " on" : ""),
    type: "button",
    onclick: fn,
  });
  b.innerHTML =
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' +
    TOOL_ICON[icon] +
    '"/></svg>';
  var nm = label.replace(/\s*▾$/, "");
  b.setAttribute("data-t", nm); // shown by the CSS tooltip (native title is slow and hidden by the card's cut corners)
  b.setAttribute("aria-label", nm);
  return b;
}
function cardDial(it, color) {
  var d = el("div", { class: "mdial", "aria-hidden": "true" }),
    ms = it.dueDate ? new Date(it.dueDate) - now() : null,
    frac = ms === null ? 0.08 : Math.max(0.06, Math.min(1, 1 - ms / (7 * 86400000))),
    h = ms === null ? null : ms / 3600000,
    lab = h === null ? "–" : h < 0 ? "!" : h < 48 ? Math.max(1, Math.round(h)) + "h" : Math.round(h / 24) + "d",
    C = 119.4;
  d.innerHTML =
    '<svg viewBox="0 0 46 46"><circle class="tr" cx="23" cy="23" r="19" fill="none" stroke-width="3"/><circle cx="23" cy="23" r="19" fill="none" stroke="' +
    color +
    '" stroke-width="3" stroke-linecap="round" stroke-dasharray="' +
    C +
    '" stroke-dashoffset="' +
    (C * (1 - frac)).toFixed(1) +
    '" style="filter:drop-shadow(0 0 4px ' +
    color +
    ')"/></svg><b>' +
    lab +
    "</b>";
  return d;
}
function blockBusy() {
  var p = H.state && H.state.blocks && H.state.blocks.phase;
  return !!p && p !== "idle";
}

/* ------------------------------------------------------------------ open / close */
function openSector(id) {
  if (H.open === id) {
    closeSector();
    return;
  }
  closeMenu();
  H.open = id;
  H.bsel = id === "play" ? null : "__first"; // a task is open when the sector opens (resolved in renderSector)
  H.moreQ = "";
  HB.setOpen(id);
  $("app").classList.add("insector");
  renderSector(true);
  setTimeout(function () {
    var f = $("sectorL").querySelector(".brn");
    if (f) f.focus();
  }, 650);
}
function closeSector(noFocus) {
  if (!H.open) return;
  var id = H.open;
  closeMenu();
  H.open = null;
  H.bsel = null;
  HB.setOpen(null);
  $("app").classList.remove("insector");
  var layer = $("sectorL");
  clear(layer);
  layer.hidden = true;
  var d = $("dials").querySelector('[data-id="' + id + '"]');
  if (!noFocus && d && d.focus) d.focus();
}
function focusSector(prev) {
  var L = $("sectorL");
  if (H.bsel) {
    var h =
      L.querySelector(".icard .find") ||
      L.querySelector(".icard h3") ||
      L.querySelector(".icard button");
    if (h) {
      if (h.tagName === "H3") h.tabIndex = -1;
      h.focus();
    }
  } else if (prev) {
    var b = L.querySelector('.brn[data-id="' + prev + '"]');
    if (b) b.focus();
  }
}
function selectBranch(id) {
  var prev = H.bsel || id;
  H.bsel = H.bsel === id ? null : id;
  closeMenu();
  renderSector();
  focusSector(prev);
  if (H.bsel === "more") {
    var f = $("sectorL").querySelector(".find");
    if (f) f.focus();
  }
}
function jumpPinned() {
  var s = H.state || {},
    pins = [s.current].concat(s.queue || []).filter(function (x) {
      return x && x.band === "pinned";
    });
  if (!pins.length) return;
  var p = pins[(H.pinI || 0) % pins.length],
    m = SECT[p.category];
  H.pinI = (H.pinI || 0) + 1;
  if (!m || m.id === "play") return;
  if (H.open !== m.id) openSector(m.id);
  setTimeout(
    function () {
      H.bsel = p.taskId;
      renderSector();
    },
    H.open === m.id ? 0 : 650,
  );
}

/* ------------------------------------------------------------------ render */
HB.onResize = function () {
  if (H.open) {
    HB.place();
    renderSector();
  }
};
function renderSector(first) {
  var hadFocus = !!(
    H.root &&
    $("sectorL").contains(H.root.activeElement) &&
    H.root.activeElement.tagName !== "INPUT"
  );
  var layer = $("sectorL");
  if (!H.open || !H.state) {
    layer.hidden = true;
    return;
  }
  if (H.menu && layer.contains(H.menu.btn)) return; // keep an open Snooze menu steady
  var s = H.state,
    sc = secById(H.open),
    color = sc.m.color,
    row = catRowOf(s, sc.name);
  var isPlay = H.open === "play",
    all = isPlay ? playItemsAll(s) : branchItems(s, H.open),
    shown = all,
    max = BR_MAX; // same for every sector: 4 tasks then "+N more"; Play also gets its "Add a side project" row
  if (all.length > max) {
    shown = all.slice(0, max - 1);
    shown.push({
      kind: "more",
      id: "more",
      n: all.length - (max - 1),
      title: all.length - (max - 1) + " more in this sector",
      rest: all.slice(max - 1),
    });
  }
  if (isPlay) shown.push({ kind: "add", id: "add", title: "Add a side project" });
  if (H.bsel === "__first") {
    var f1 = shown.filter(function (x) {
      return (
        x.kind !== "more" &&
        x.kind !== "add" &&
        x.kind !== "idea" &&
        x.kind !== "pidea" &&
        x.kind !== "offer"
      );
    })[0];
    var waitNext = H.wantNext && now() < H.wantNext; // a Done is still being confirmed: the next one may not have arrived yet
    H.bsel = f1 ? f1.id : waitNext ? "__first" : null;
    if (f1) H.wantNext = 0;
  }
  if (
    H.bsel &&
    H.bsel !== "__first" &&
    !shown.some(function (x) {
      return x.id === H.bsel;
    })
  ) {
    var inMore = shown.filter(function (x) {
      return x.kind === "more";
    })[0];
    if (
      inMore &&
      inMore.rest.some(function (x) {
        return x.id === H.bsel;
      })
    )
      H.moreSel = H.bsel;
    else H.bsel = null; // it left the list (done, snoozed, skipped)
  }
  var prevAny = !first && layer.querySelector(".icard"),
    prevId = prevAny ? prevAny.getAttribute("data-id") : null,
    prevAnyTop = prevAny ? prevAny.offsetTop : null;
  var prevCard = !first && !H.afterDone && layer.querySelector(".icard"),
    prevTop = prevCard ? prevCard.offsetTop : null;
  H.afterDone = false; // after a Done the next card just fades in, no glide from the old spot
  layer.hidden = false;
  layer.style.setProperty("--sec", color);
  layer.classList.toggle("reselect", !first);
  clear(layer);
  var w = HB.w,
    h = HB.h,
    at = HB.openAt(),
    ax = at.x,
    ay = at.y;
  ap(
    layer,
    el("button", {
      class: "bd",
      type: "button",
      tabindex: "-1",
      "aria-label": "Close the sector and return to the brain",
      onclick: closeSector,
    }),
  );
  var count = isPlay
    ? playCount(s)
    : sc.name === "Security"
      ? "one project in focus" + (row.later ? " · " + row.later + " more waiting" : "")
      : all.length
        ? (all.filter(function (x) {
            return x.kind === "task";
          }).length
            ? (row.open || 0) + " open · "
            : "") +
          (all.filter(function (x) {
            return x.kind === "habit";
          }).length
            ? all.filter(function (x) {
                return x.kind === "habit";
              }).length + " repeating · "
            : "") +
          "showing " +
          Math.min(all.length, BR_MAX - (all.length > BR_MAX ? 1 : 0))
        : "nothing open";
  ap(
    layer,
    el(
      "div",
      { class: "xh" },
      el(
        "button",
        { class: "xbk", type: "button", onclick: closeSector },
        "← Back ",
        el("span", { text: "esc" }),
      ),
      el("span", {
        class: "xn",
        style: "color:" + color,
        text: "Sector " + sc.m.no + " · " + sc.m.label,
      }),
      el("span", { class: "xc", text: count }),
    ),
  );
  if (!shown.length) {
    ap(
      layer,
      el(
        "div",
        {
          class: "empty-s",
          style: "left:" + (ax + 110) + "px;top:" + (ay - 30) + "px",
        },
        el("b", { text: "Nothing here right now." }),
        el("span", {
          text:
            sc.name === "Personal"
              ? "Errands you add (in QuickToDo or by typing “remind me to email Dr. Lee”) land here."
              : "New tasks for this sector land here as they come in.",
        }),
      ),
    );
    return;
  }
  /* the stage already ends above the chat's quiet line */
  var floor = h - 44;
  var n = shown.length,
    top = 110,
    bot = Math.min(h - 70, floor - 30),
    one = n === 1 && !isPlay,
    pitch = n > 1 ? Math.min(84, (bot - top - 30) / (n - 1)) : 0,
    colX = ax + 250,
    cardW = one ? 420 : 376,
    cardL = Math.min(
      one ? ax + 372 : Math.max(colX + 300, w - cardW - 36),
      w - cardW - 12,
    );
  var pos = shown.map(function (it, i) {
    var y = Math.max(top, Math.min(bot, ay + (i - (n - 1) / 2) * pitch));
    return { it: it, x: one ? ax + 300 : colX, y: one ? ay : y };
  });
  var rowMax = Math.max(280, cardL - colX - 70);
  var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"),
    html = "";
  svg.setAttribute("class", "br");
  svg.setAttribute("aria-hidden", "true");
  pos.forEach(function (p, i) {
    var d =
      "M" +
      (ax + 56) +
      " " +
      ay +
      " C" +
      (ax + 140) +
      " " +
      ay +
      ", " +
      (p.x - 110) +
      " " +
      p.y +
      ", " +
      (p.x - 25) +
      " " +
      p.y;
    html +=
      '<path d="' +
      d +
      '" fill="none" stroke="' +
      color +
      '" stroke-opacity="' +
      (H.bsel === p.it.id ? 0.85 : dimKind(p.it.kind) ? 0.22 : 0.45) +
      '" stroke-width="1.1"' +
      (dimKind(p.it.kind) && p.it.kind !== "more"
        ? ' stroke-dasharray="3 5"'
        : "") +
      (first && !H.still
        ? ' stroke-dasharray="400" stroke-dashoffset="400"><animate attributeName="stroke-dashoffset" from="400" to="0" dur=".7s" begin="' +
          (i * 0.06).toFixed(2) +
          's" fill="freeze"/></path>'
        : "/>");
    if (!H.still && p.it.kind !== "more" && p.it.kind !== "add")
      html +=
        '<circle r="2" fill="#fff"><animateMotion dur="' +
        (2.8 + i * 0.4) +
        's" begin="' +
        (0.7 + i * 0.3).toFixed(1) +
        's" repeatCount="indefinite" path="' +
        d +
        '"/></circle>';
  });
  svg.innerHTML = html;
  ap(layer, svg);
  pos.forEach(function (p, i) {
    var it = p.it,
      sub = it.kind === "task" ? subject(it) : "";
    var b = el("button", {
      class: "brn" + (dimKind(it.kind) ? " dim" : "") + (one ? " solo" : ""),
      type: "button",
      "data-id": it.id,
      "aria-expanded": String(H.bsel === it.id),
      style:
        "left:" +
        (p.x - 24) +
        "px;top:" +
        (p.y - 24) +
        "px;animation-delay:" +
        (first ? 0.2 + i * 0.07 : 0) +
        "s",
      onclick: function () {
        selectBranch(it.id);
      },
    });
    b.innerHTML = miniDial(it, color);
    var t1 = el(
      "span",
      { class: "bt1" },
      it.title,
      it.pinned ? el("span", { class: "tagp", text: "pinned" }) : null,
      it.now
        ? el("span", {
            class: "tagn",
            style: "background:" + color,
            text: "now",
          })
        : null,
    );
    var t2 =
      it.kind === "more"
        ? el("span", { class: "bt2", text: "search and act on any of them" })
        : isPlay
          ? el("span", { class: "bt2", text: playDue(it) })
          : el(
              "span",
              { class: "bt2" },
              sub
                ? el("span", {
                    class: "subj",
                    style: "color:" + color,
                    text: sub + " · ",
                  })
                : null,
              branchDue(it) +
                (it.minutes
                  ? " · " + dur(it.minutes).replace(/ /g, "\u00a0")
                  : ""),
            );
    var btw = el("span", { class: "bt" }, t1, t2);
    if (!one) btw.style.maxWidth = rowMax + "px";
    ap(b, btw);
    ap(layer, b);
  });
  var S = pos.filter(function (p) {
    return p.it.id === H.bsel;
  })[0];
  if (!S && H.bsel && H.moreSel === H.bsel) {
    var mp = pos.filter(function (p) {
      return p.it.kind === "more";
    })[0];
    var hid =
      mp &&
      mp.it.rest.filter(function (x) {
        return x.id === H.bsel;
      })[0];
    if (hid) S = { it: hid, x: mp.x, y: mp.y };
  }
  if (S) {
    var maxX = Math.max.apply(
      null,
      pos.map(function (p) {
        return p.x;
      }),
    );
    var card = itemCard(S.it, sc, color);
    // sit just right of the longest row (so the card is near its list), joined to the chosen row by a fibre
    var rowsR = Array.prototype.map.call(
      layer.querySelectorAll(".brn:not(.later)"),
      function (e) {
        return e.offsetLeft + e.offsetWidth;
      },
    );
    var selEl = layer.querySelector('.brn[data-id="' + S.it.id + '"]');
    var selR = selEl ? selEl.offsetLeft + selEl.offsetWidth : S.x + 40;
    if (!one && rowsR.length)
      cardL = Math.min(
        Math.max(colX + 80, Math.max.apply(null, rowsR) + 64),
        w - cardW - 12,
      );
    card.style.width = cardW + "px";
    card.style.left = cardL + "px";
    card.style.top = Math.max(64, ay - 120) + "px";
    ap(layer, card);
    var ch = card.offsetHeight; // aligned with the chosen row, and kept on screen
    var topY = Math.max(64, Math.min((one ? ay : S.y) - ch / 2, floor - ch));
    card.setAttribute("data-id", S.it.id);
    var same = prevId === S.it.id; // the same task redrawn (a refresh): no fade, no glide
    if (same) {
      card.style.animation = "none";
      card.style.transition = "none";
      if (prevAnyTop !== null) card.style.top = prevAnyTop + "px";
      void card.offsetHeight;
      card.style.top = topY + "px";
    } else if (prevTop !== null) {
      card.style.top = prevTop + "px"; // glide from where the last card was
      void card.offsetHeight;
      card.style.top = topY + "px";
    } else {
      // a new card (first open, or the next task after a Done) appears in place and only fades in
      card.style.transition = "none";
      card.style.top = topY + "px";
      void card.offsetHeight;
      card.style.transition = "";
    }
    var cy = Math.max(topY + 18, Math.min(S.y, topY + ch - 18)),
      lx = Math.min(selR + 10, cardL - 24),
      ld =
        "M" + lx + " " + S.y + " C" + (lx + (cardL - lx) / 2) + " " + S.y + ", " +
        (lx + (cardL - lx) / 2) + " " + cy + ", " + cardL + " " + cy;
    var link = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    link.setAttribute("class", "br lk");
    link.setAttribute("aria-hidden", "true");
    link.innerHTML =
      '<path d="' + ld + '" fill="none" stroke="' + color + '" stroke-width="1.3" stroke-opacity=".8"/>' +
      '<circle cx="' + lx + '" cy="' + S.y + '" r="3" fill="' + color + '"/>' +
      '<circle cx="' + cardL + '" cy="' + cy + '" r="3" fill="' + color + '"/>' +
      (H.still ? "" : '<circle r="2" fill="#fff"><animateMotion dur="1.8s" repeatCount="indefinite" path="' + ld + '"/></circle>');
    if (same) link.style.animation = "none";
    layer.insertBefore(link, card);
    if (one && sc.name === "Security" && row.later) {
      // the hidden projects sit just under the card, on the same left edge
      ap(
        layer,
        el(
          "div",
          {
            class: "brn dim later",
            style:
              "left:" +
              (cardL - 12) +
              "px;top:" +
              (card.offsetTop + ch + 12) +
              "px",
          },
          el("span", { class: "ldot", "aria-hidden": "true" }),
          el(
            "span",
            { class: "bt" },
            el("span", {
              class: "bt1",
              text: row.later + " more later, hidden on purpose",
            }),
          ),
        ),
      );
    }
  }
  if (hadFocus) focusSector(H.bsel);
}

/* ------------------------------------------------------------------ the card */
function itemCard(it, sc, color) {
  var c = el("div", {
    class: "icard",
    role: "dialog",
    "aria-label": it.kind === "more" ? "More in " + sc.m.label : it.title,
  });
  var head = el(
    "div",
    { class: "ih" },
    el("p", {
      class: "eb",
      style: "color:" + color,
      text:
        "Sector " +
        sc.m.no +
        " · " +
        (it.kind === "more"
          ? "everything else"
          : it.kind === "habit"
            ? "repeating"
            : sc.m.label),
    }),
    el("button", {
      class: "ix",
      type: "button",
      "aria-label": "Close card",
      text: "×",
      onclick: function () {
        var p = H.bsel;
        H.bsel = null;
        renderSector();
        focusSector(p);
      },
    }),
  );
  ap(c, head);
  if (it.kind === "more" || it.kind === "habit" || H.open === "play" || it.kind === "add") c.classList.add("nodial"); // no dial column: text starts at the left edge
  if (it.kind === "more") return moreCard(c, it, sc);
  if (it.kind === "habit") return habitCard(c, it);
  if (H.open === "play" || it.kind === "add") return playCard(c, it);
  var s = H.state,
    sub = subject(it),
    canStart = it.category !== "Play",
    canEarlier = canStart && it.category !== "Personal",
    busy = blockBusy();
  ap(
    c,
    el("h3", { text: it.title }),
    el(
      "p",
      { class: "meta" },
      sub
        ? el("span", {
            class: "subj",
            style: "color:" + color,
            text: sub + " · ",
          })
        : null,
      (it.minutes
        ? dur(it.minutes) + (it.minutesEstimated ? "" : " (guess)") + " · "
        : "") + branchDue(it),
    ),
  );
  var why =
    low() && it.band === "escalated"
      ? "Past its deadline. No need to do all of it: one small piece at a time."
      : it.why;
  if (sc.name === "Security" && !why)
    why =
      "Your one project right now. Finish it before starting another; the rest wait out of sight.";
  if (why) ap(c, el("p", { class: "why", text: why }));
  var lo = s.leftOff && s.leftOff[it.id];
  if (lo)
    ap(
      c,
      el("p", {
        class: "left" + (lo.auto ? " auto" : ""),
        text: "Where you left off: " + lo.text,
      }),
    );
  if (it.resources) ap(c, el("pre", { class: "res", text: it.resources }));
  c.classList.add("hasdial");
  c.insertBefore(cardDial(it, color), c.firstChild);
  var two = el("div", { class: "two" });
  var mins = Math.max(
    BLOCK.min,
    Math.min(it.minutes || 30, low() ? BLOCK.lowMax : BLOCK.max),
  );
  if (canStart && !busy)
    ap(
      two,
      btn(
        it.minutes ? "▶  Start " + mins + " min" : "▶  Start",
        "pri",
        function () {
          closeSector();
          blockAct({ action: "start_work", taskId: it.id });
        },
      ),
    );
  var pend = pendingDone(it.id);
  ap(
    two,
    btn(
      pend ? "Marking done…" : "✓  Done",
      "",
      function () {
        doDone(it.id);
        H.bsel = "__first"; // after the strike finishes the screen refreshes and opens the next task
        H.wantNext = now() + 30000; // one-at-a-time sectors (Security) only get their next project once QuickToDo confirms
      },
      { disabled: pend },
    ),
  );
  ap(c, two);
  if (canStart && busy)
    ap(
      c,
      el("p", {
        class: "wait",
        text: "// a block is running, so Start waits until it ends",
      }),
    );
  var tl = el("div", { class: "tl" });
  ap(
    tl,
    toolBtn(
      "pin",
      it.pinned ? "Unpin" : "Pin",
      function () {
        doAction({ action: it.pinned ? "unpin" : "pin", taskId: it.id });
      },
      it.pinned,
    ),
  );
  var sw = el("span", { class: "mw" }),
    sb = toolBtn("snooze", "Snooze ▾", null);
  sb.setAttribute("aria-haspopup", "menu");
  sb.addEventListener("click", function (e) {
    e.stopPropagation();
    openMenu(sb, "Snooze", [
      {
        label: "Snooze 1 hour",
        run: function () {
          doAction({ action: "snooze", taskId: it.id, hours: 1 });
        },
      },
      {
        label: "Snooze 3 hours",
        run: function () {
          doAction({ action: "snooze", taskId: it.id, hours: 3 });
        },
      },
      {
        label: "Snooze until tomorrow",
        run: function () {
          doAction({ action: "snooze", taskId: it.id, until: "tomorrow" });
        },
      },
    ]);
  });
  ap(sw, sb);
  ap(
    tl,
    sw,
    toolBtn("skip", "Not this one", function () {
      doAction({ action: "skip", taskId: it.id });
    }),
  );
  if (canEarlier && !busy) {
    var ew = el("span", { class: "mw" }),
      eb2 = toolBtn("earlier", "Started earlier? ▾", null);
    eb2.setAttribute("aria-haspopup", "menu");
    eb2.addEventListener("click", function (e) {
      e.stopPropagation();
      openMenu(
        eb2,
        "Started earlier?",
        [10, 15, 30, 60].map(function (m) {
          return {
            label: "I started " + m + " min ago",
            run: function () {
              closeSector();
              blockAct({ action: "start_work", taskId: it.id, startedAgo: m });
            },
          };
        }),
      );
    });
    ap(ew, eb2);
    ap(tl, ew);
  }
  ap(two, tl); // Done and the icon tools share one row
  return c;
}
/* Repeating item card (also any study plan). Left-aligned, no dial column. The title already names today's item, so
   there is no "Today" line; items are added one at a time with Enter. */
function habitCard(c, it) {
  var h = it.habit,
    left = h.plan
      ? h.plan.filter(function (x) {
          return !x.done;
        })
      : [],
    rest = left.filter(function (x) {
      return x.t !== h.planToday;
    });
  ap(
    c,
    el("h3", { text: it.title }),
    el("p", {
      class: "hmeta",
      text: (h.notes ? h.notes + " · " : "") + h.cadence + " · text around " + clock12(h.nudgeAt) + (h.minutes ? " · " + dur(h.minutes) : ""),
    }),
  );
  if (h.plan && h.planTotal) {
    ap(
      c,
      el(
        "div",
        { class: "pprog" },
        el("span", { class: "pbar" }, el("i", { style: "width:" + Math.round((100 * h.planDone) / h.planTotal) + "%" })),
        el("span", { class: "pnum", text: h.planDone + " of " + h.planTotal + " done" + (left.length ? "" : " · finished") }),
      ),
    );
    if (rest.length) {
      var ul = el("ul", { class: "plist" });
      rest.slice(0, 5).forEach(function (x) {
        ap(ul, el("li", { text: x.t }));
      });
      if (rest.length > 5) ap(ul, el("li", { class: "more", text: "+" + (rest.length - 5) + " more" }));
      ap(c, el("p", { class: "pk", text: "Still in the cycle" }), ul);
    }
  }
  var inp = el("input", {
    class: "padd",
    type: "text",
    maxlength: "140",
    autocomplete: "off",
    placeholder: h.plan ? "add an item, press enter" : "make this a plan: add an item, press enter",
    "aria-label": "Add an item to the plan",
  });
  inp.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    var v = inp.value.trim();
    if (!v) return;
    inp.value = "";
    H.planFocus = h.id; // the card redraws after the save: keep typing
    playPost({ action: "planadd", id: h.id, items: v });
  });
  ap(c, el("div", { class: "pin" }, el("span", { "aria-hidden": "true", text: "+" }), inp));
  if (H.planFocus === h.id) {
    H.planFocus = null;
    setTimeout(function () {
      inp.focus();
    }, 30);
  }
  ap(
    c,
    el(
      "div",
      { class: "two" },
      h.doneToday
        ? btn("Undo done", "", function () {
            doAction({ action: "habitundo", id: h.id }, "/api/play");
          })
        : btn("Did one today", "pri", function () {
            doAction({ action: "habitdone", id: h.id }, "/api/play");
          }),
      rest.length && !h.doneToday
        ? btn("Pick another", "", function () {
            playPost({ action: "planskip", id: h.id });
          })
        : null,
    ),
    el(
      "div",
      { class: "qrow" },
      el("button", {
        type: "button",
        text: it.front ? "Take off the front" : "Show first",
        onclick: function () {
          playPost({ action: it.front ? "unfront" : "front", id: h.id });
        },
      }),
      el("button", {
        type: "button",
        text: "Stop repeating",
        onclick: function () {
          H.bsel = null;
          doAction({ action: "drophabit", id: h.id }, "/api/play");
        },
      }),
    ),
  );
  return c;
}
function moreCard(c, it, sc) {
  var q = el("input", {
    class: "find",
    type: "text",
    placeholder: "find a task…",
    "aria-label": "Find a task",
    autocomplete: "off",
  });
  var list = el("ul", { class: "morel" }),
    busy = blockBusy();
  q.value = H.moreQ || "";
  function fill() {
    clear(list);
    var f = q.value.trim().toLowerCase();
    H.moreQ = q.value;
    it.rest
      .filter(function (r) {
        return (
          !f ||
          r.title.toLowerCase().indexOf(f) >= 0 ||
          (r.list || "").toLowerCase().indexOf(f) >= 0
        );
      })
      .forEach(function (r) {
        var sub = r.kind === "task" ? subject(r) : "";
        var li = el(
          "li",
          {},
          el(
            "span",
            { class: "mt" },
            r.title,
            el("i", {
              text:
                " · " +
                (sub ? sub + " · " : "") +
                (H.open === "play" ? playDue(r) : branchDue(r)),
            }),
          ),
        );
        if (r.kind === "task") {
          if (r.category !== "Personal" && !busy)
            ap(
              li,
              el("button", {
                class: "mb2 go",
                type: "button",
                text: "Start",
                onclick: function () {
                  closeSector();
                  blockAct({ action: "start_work", taskId: r.id });
                },
              }),
            );
          ap(
            li,
            el("button", {
              class: "mb2 ok",
              type: "button",
              text: pendingDone(r.id) ? "Marking" : "Done",
              disabled: pendingDone(r.id),
              onclick: function () {
                doDone(r.id);
              },
            }),
          );
        } else
          ap(
            li,
            el("button", {
              class: "mb2",
              type: "button",
              text: "Open",
              onclick: function () {
                H.bsel = r.id;
                renderSector();
              },
            }),
          );
        ap(list, li);
      });
    if (!list.childNodes.length)
      ap(list, el("li", {}, el("span", { class: "mt", text: "No match." })));
  }
  q.addEventListener("input", fill);
  ap(c, el("h3", { text: it.n + " more in " + sc.m.label }), q, list);
  fill();
  return c;
}

/* ------------------------------------------------------------------ Play (slice e; views 7 to 12)
   No deadlines and no ranking: an optional offer, projects, repeating items, parked ideas and "Add an idea".
   Same /api/play actions as the other skins. */
function dimKind(k) {
  return k === "more" || k === "idea" || k === "add";
}
function playItemsAll(s) {
  var pl = s.play || {},
    out = [];
  (pl.habits || [])
    .filter(function (h) {
      return h.cluster === "play";
    })
    .forEach(function (h) {
      out.push({ kind: "habit", id: h.id, title: h.title, habit: h });
    });
  if (pl.offer)
    out.push({
      kind: "offer",
      id: "offer:" + pl.offer.taskId,
      title: "Offer: " + pl.offer.title,
      offer: pl.offer,
    });
  (pl.projects || []).forEach(function (p) {
    out.push({
      kind: p.state === "idea" ? "pidea" : "project",
      id: p.id,
      title: p.title,
      state: p.state,
      left: p.leftOffAuto ? "" : p.leftOff || "",
      auto: p.leftOffAuto ? p.leftOff : "",
    });
  });
  (pl.items || []).forEach(function (t) {
    out.push({
      kind: "item",
      id: t.taskId,
      title: t.title,
      left: t.leftOffAuto ? "" : t.leftOff || "",
      auto: t.leftOffAuto ? t.leftOff : "",
    });
  });
  // "Show first": the items she pinned fill the visible nodes before the rest (newest pin first).
  var front = pl.front || [];
  out.forEach(function (x) {
    var i = front.indexOf(x.id);
    x.front = i >= 0;
    x.fi = i >= 0 ? i : 99;
    if (x.front) x.pinned = true;
  });
  out = out
    .map(function (x, i) {
      return [x, i];
    })
    .sort(function (a, b) {
      return a[0].fi - b[0].fi || a[1] - b[1];
    })
    .map(function (x) {
      return x[0];
    });
  return out;
}
function frontBtn(it) {
  var id = it.kind === "idea" && it.idea ? it.idea.id : it.id;
  return it.front
    ? btn("Take off the front", "q", function () {
        playPost({ action: "unfront", id: id });
      })
    : btn("Show first", "q", function () {
        playPost({ action: "front", id: id });
      });
}
function playCount(s) {
  var all = playItemsAll(s),
    n = function (k) {
      return all.filter(function (x) {
        return k.indexOf(x.kind) >= 0;
      }).length;
    };
  var parts = [],
    pr = n(["project", "item", "pidea"]), // an idea is a side project that has not started, so it counts here
    rp = n(["habit"]);
  if (pr) parts.push(pr + (pr === 1 ? " project" : " projects"));
  if (rp) parts.push(rp + " repeating");
  parts.push("no deadlines here");
  return parts.join(" · ");
}
function playDue(it) {
  if (it.kind === "habit") return branchDue(it);
  if (it.kind === "offer")
    return (
      "optional" +
      (it.offer.minutes
        ? " · " + dur(it.offer.minutes).replace(/ /g, "\u00a0")
        : "")
    );
  if (it.kind === "item") return it.left || it.auto || "no deadline"; // a plain task moved into Play, not a started project
  if (it.kind === "project")
    return it.left || it.auto ? "started · " + (it.left || it.auto) : "started";
  if (it.kind === "pidea") return "not started";
  if (it.kind === "add") return "no deadline";
  return "";
}
function playPost(body) {
  return doAction(body, "/api/play");
}
function lineBox(placeholder, label, initial, fn) {
  var inp = el("input", {
    class: "find",
    type: "text",
    maxlength: "140",
    placeholder: placeholder,
    "aria-label": placeholder,
    autocomplete: "off",
  });
  inp.value = initial || "";
  function go() {
    if (inp.value.trim()) fn(inp.value.trim());
  }
  inp.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      go();
    }
  });
  return el("div", { class: "lrow" }, inp, btn(label, "", go));
}
function playCard(c, it) {
  var close = function () {
    H.bsel = null;
  };
  if (it.kind === "offer") {
    var o = it.offer;
    ap(
      c,
      el("h3", { text: it.title }),
      el("p", { class: "why", text: o.text || "" }),
      o.leftOff
        ? el("p", {
            class: "left auto",
            text: "Where you left off: " + o.leftOff,
          })
        : null,
      el("p", { class: "wait", text: "optional. saying no changes nothing." }),
      el(
        "div",
        { class: "two" },
        btn("Sounds good", "pri", function () {
          close();
          playPost({ action: "accept", taskId: o.taskId });
        }),
        btn("Not now", "q", function () {
          close();
          renderSector();
        }),
      ),
    );
  } else if (it.kind === "project" || it.kind === "item") {
    ap(
      c,
      el("h3", { text: it.title }),
      el("p", { class: "lab", text: "Where I left off" }),
    );
    if (it.auto && !it.left)
      ap(
        c,
        el("p", {
          class: "left auto",
          text: it.auto + " (automatic; type a line to replace it)",
        }),
      );
    ap(
      c,
      lineBox("one line, so restarting is easy", "Save", it.left, function (v) {
        playPost({ action: "leftoff", taskId: it.id, text: v });
      }),
      el(
        "div",
        { class: "two" },
        btn("Worked on it today", "", function () {
          playPost({
            action: "leftoff",
            taskId: it.id,
            text:
              "Worked on it " +
              new Date().toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              }),
          });
        }),
        it.kind === "project"
          ? btn("Finished / drop", "q", function () {
              close();
              playPost({ action: "dropproject", id: it.id });
            })
          : btn("✓  Done", "q", function () {
              close();
              doDone(it.id);
            }),
      ),
      el("div", { class: "two" }, frontBtn(it)),
    );
  } else if (it.kind === "pidea") {
    ap(
      c,
      el("h3", { text: it.title }),
      el("p", {
        class: "why",
        text: "An idea you parked. Nothing is due; start it when you feel like it.",
      }),
      el(
        "div",
        { class: "two" },
        btn("Start it", "pri", function () {
          playPost({ action: "startproject", id: it.id });
        }),
        btn("Drop it", "q", function () {
          close();
          playPost({ action: "dropproject", id: it.id });
        }),
      ),
      el("div", { class: "two" }, frontBtn(it)),
    );
  } else if (it.kind === "idea") {
    ap(
      c,
      el("h3", { text: it.title }),
      el("p", {
        class: "why",
        text: "An idea you parked. Nothing is due; start it when you feel like it.",
      }),
      el(
        "div",
        { class: "two" },
        btn("Start it", "pri", function () {
          close();
          playPost({ action: "promote", id: it.idea.id });
        }),
        btn("Remove", "q", function () {
          close();
          playPost({ action: "unpark", id: it.idea.id });
        }),
      ),
    );
  } else if (it.kind === "add") {
    ap(
      c,
      el("h3", { text: "Add a side project" }),
      el("p", {
        class: "why",
        text: "Type it the way it hit you, even half an idea. It lands as a dim, not-started project.",
      }),
      lineBox("a side project, even half an idea", "Add it", "", function (v) {
        playPost({ action: "park", text: v });
      }),
    );
    setTimeout(function () {
      var f = c.querySelector("input");
      if (f) f.focus();
    }, 30);
  }
  return c;
}


/* When the list changes (a task finished, the next one opens) the rows glide to their new places instead of jumping. */
(function () {
  var raw = renderSector;
  renderSector = function (first) {
    var old = {},
      calm = H.still || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    if (!first && H.root)
      H.root.querySelectorAll(".sectorl .brn[data-id]").forEach(function (b) {
        old[b.getAttribute("data-id")] = b.getBoundingClientRect();
      });
    raw(first);
    if (first || calm || !H.root) return;
    H.root.querySelectorAll(".sectorl .brn[data-id]").forEach(function (b) {
      var o = old[b.getAttribute("data-id")];
      if (!o) return;
      var n = b.getBoundingClientRect(),
        dx = o.left - n.left,
        dy = o.top - n.top;
      if (Math.abs(dx) + Math.abs(dy) < 1) return;
      b.animate([{ translate: dx + "px " + dy + "px" }, { translate: "0 0" }], {
        duration: 380,
        easing: "cubic-bezier(.2,.8,.2,1)",
      });
    });
  };
})();
