/* ------------------------------------------------------------------ your texts: every text reminder that is scheduled */
function textRows() {
  var pl = (H.state && H.state.play) || {};
  var groups = {},
    order = [];
  (pl.reminders || []).forEach(function (r) {
    var g = r.group || r.id;
    if (!groups[g]) {
      groups[g] = { id: r.id, text: r.text, at: [] };
      order.push(g);
    }
    groups[g].at.push(new Date(r.at));
  });
  var once = order
    .map(function (g) {
      var x = groups[g];
      x.at.sort(function (a, b) {
        return a - b;
      });
      return x;
    })
    .sort(function (a, b) {
      return a.at[0] - b.at[0];
    });
  var rep = (pl.habits || []).slice();
  return { once: once, rep: rep, n: once.length + rep.length };
}
function shortTime(d) {
  return d.getMinutes() ? hm(d) : hm(d).replace(":00", "");
}
function refreshTexts() {
  var b = $("txt");
  if (!b) return;
  var r = textRows();
  $("txtN").textContent = r.n ? String(r.n) : "";
  b.title = r.n ? r.n + " scheduled text" + (r.n === 1 ? "" : "s") + " (click to see them)" : "No texts scheduled";
  var p = $("textsP");
  if (p && !p.hidden) renderTexts();
}
function renderTexts() {
  var p = $("textsP"),
    body = p.querySelector(".hb"),
    r = textRows();
  clear(body);
  function remove(label, action, id) {
    return el("button", {
      type: "button",
      class: "rm",
      text: "\u00d7",
      title: "Remove",
      "aria-label": "Remove " + label,
      onclick: function (e) {
        e.stopPropagation();
        this.disabled = true;
        post("/api/play", { action: action, id: id })
          .then(update)
          .catch(function (er) {
            say(er.message, true);
          });
      },
    });
  }
  if (!r.n) {
    ap(body, el("section", { class: "hr" }, el("p", { text: "No texts scheduled. Say \"remind me tomorrow to ...\" in the box." })));
    return;
  }
  if (r.once.length) {
    var byText = {},
      names = [];
    r.once.forEach(function (x) {
      if (!byText[x.text]) {
        byText[x.text] = [];
        names.push(x.text);
      }
      byText[x.text].push(x);
    });
    names.forEach(function (name) {
      var card = el("div", { class: "tcard" }, el("b", { class: "tn", text: name }));
      byText[name].forEach(function (x) {
        ap(
          card,
          el(
            "div",
            { class: "tday" },
            el("span", { text: day(x.at[0]).replace(/,/, "") + "  " + x.at.map(shortTime).join(" · ") }),
            remove(name + " on " + day(x.at[0]), "dropreminder", x.id),
          ),
        );
      });
      ap(body, card);
    });
  }
  if (r.rep.length) {
    ap(body, el("p", { class: "tsec", text: "REPEATING" }));
    r.rep.forEach(function (h) {
      var when = (h.cadence || "daily") + " from " + clock12(h.nudgeAt || "09:00") + (h.until ? ", until " + day(new Date(h.until + "T12:00")).replace(/,/, "") : "");
      ap(
        body,
        el(
          "div",
          { class: "tcard" },
          el("b", { class: "tn", text: h.base || h.title }),
          el("div", { class: "tday" }, el("span", { text: when }), remove(h.title, "drophabit", h.id)),
        ),
      );
    });
  }
}
function openTexts(on) {
  var p = $("textsP"),
    b = $("txt");
  if (!p) {
    p = el("div", { class: "helpp textsp", id: "textsP", role: "dialog", "aria-label": "Your texts", hidden: "" });
    ap(
      p,
      el(
        "div",
        { class: "hh" },
        el("span", { text: "YOUR TEXTS" }),
      ),
    );
    ap(p, el("div", { class: "hb" }));
    ap($("app"), p);
  }
  if (on) renderTexts();
  p.hidden = !on;
  b.setAttribute("aria-expanded", String(!!on));
}
