"""Build one-page resume and letter .docx files, convert to PDF, verify page count (Phase 13)."""
import re, shutil, subprocess, tempfile
from pathlib import Path

SOFFICE = shutil.which("soffice") or "/opt/homebrew/bin/soffice"
PDFINFO = shutil.which("pdfinfo") or "/opt/homebrew/bin/pdfinfo"


def pdf_pages(pdf):
    out = subprocess.run([PDFINFO, str(pdf)], capture_output=True, text=True, timeout=30).stdout
    m = re.search(r"Pages:\s+(\d+)", out)
    return int(m.group(1)) if m else 0


def to_pdf(docx_path, out_dir):
    subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
                   capture_output=True, timeout=120, check=True)
    pdf = Path(out_dir) / (Path(docx_path).stem + ".pdf")
    if not pdf.exists():
        raise RuntimeError("PDF conversion produced no file")
    return pdf


def _docx():
    import docx
    from docx.shared import Pt, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    return docx, Pt, Inches, WD_ALIGN_PARAGRAPH


def _para(doc, text="", size=10, bold=False, align=None, after=2, before=0, italic=False):
    docx, Pt, Inches, AL = _docx()
    p = doc.add_paragraph()
    pf = p.paragraph_format; pf.space_after = Pt(after); pf.space_before = Pt(before); pf.line_spacing = 1.0
    if align == "center": p.alignment = AL.CENTER
    if text:
        r = p.add_run(text); r.font.size = Pt(size); r.bold = bold; r.italic = italic; r.font.name = "Calibri"
    return p


def _two(doc, left, right, size, bold=True):
    """Left text with a right-aligned date, using a right tab stop (never inside a table cell)."""
    docx, Pt, Inches, AL = _docx()
    from docx.enum.text import WD_TAB_ALIGNMENT
    p = doc.add_paragraph(); pf = p.paragraph_format
    pf.space_after = Pt(0); pf.space_before = Pt(3)
    pf.tab_stops.add_tab_stop(Inches(7.5), WD_TAB_ALIGNMENT.RIGHT)
    r = p.add_run(left); r.bold = bold; r.font.size = Pt(size); r.font.name = "Calibri"
    r2 = p.add_run("\t" + right); r2.font.size = Pt(size); r2.font.name = "Calibri"
    return p


def _bullet(doc, text, size):
    docx, Pt, Inches, AL = _docx()
    p = doc.add_paragraph(); pf = p.paragraph_format
    pf.left_indent = Inches(0.2); pf.first_line_indent = Inches(-0.15); pf.space_after = Pt(1); pf.line_spacing = 1.0
    r = p.add_run("• " + text); r.font.size = Pt(size); r.font.name = "Calibri"


def build_resume_docx(facts, draft, path, size=10, drop_projects=0):
    docx, Pt, Inches, AL = _docx()
    exp = {e["id"]: e for e in facts["experience"]}
    proj = {p["id"]: p for p in facts["projects"]}
    doc = docx.Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Inches(8.5), Inches(11)
    s.left_margin = s.right_margin = Inches(0.5); s.top_margin = s.bottom_margin = Inches(0.4)
    def head(t): _para(doc, t, size + 1, bold=True, before=5, after=1)
    _para(doc, facts["contact"]["name"], size + 8, bold=True, align="center", after=0)
    _para(doc, facts["contact"]["line"], size - 1.5, align="center", after=2)
    head("PROFESSIONAL SUMMARY"); _para(doc, draft["summary"].strip(), size, after=2)
    head("SKILLS")
    for g in draft["skills"]:
        p = _para(doc, "", size, after=1)
        r = p.add_run(g["label"] + ": "); r.bold = True; r.font.size = Pt(size); r.font.name = "Calibri"
        r2 = p.add_run(", ".join(g["items"])); r2.font.size = Pt(size); r2.font.name = "Calibri"
    head("CERTIFICATIONS")
    certs = facts["certifications"]; half = (len(certs) + 1) // 2
    for i in range(half):
        t = "• " + certs[i]
        if i + half < len(certs): t += "     • " + certs[i + half]
        _para(doc, t, size, after=0)
    head("PROJECTS")
    pids = draft["projects"][: max(1, len(draft["projects"]) - drop_projects)]
    for pid in pids:
        p = proj[pid]
        _two(doc, f"{p['name']} ({p['stack']})", p.get("tag", ""), size)
        ids = (draft.get("bullets") or {}).get(pid) or [b["id"] for b in p["bullets"]]
        for b in p["bullets"]:
            if b["id"] in ids: _bullet(doc, b["text"], size)
    head("EXPERIENCE")
    eids = draft.get("experience") or [e["id"] for e in facts["experience"]]
    for eid in eids:
        e = exp[eid]
        _two(doc, e["title"], e["date"], size)
        if e.get("org"):
            _para(doc, e["org"], size, after=0, italic=True)
        ids = (draft.get("bullets") or {}).get(eid) or [b["id"] for b in e["bullets"]]
        for b in e["bullets"]:
            if b["id"] in ids: _bullet(doc, b["text"], size)
    head("EDUCATION")
    for ed in facts["education"]:
        _two(doc, ed["school"], ed["date"], size)
        _para(doc, ed["degree"], size, after=0)
        if ed.get("extra") and "Master" in ed["degree"]: _para(doc, ed["extra"], size, after=0)
    doc.save(str(path))


def build_letter_docx(facts, letter, company, path, size=11):
    docx, Pt, Inches, AL = _docx()
    doc = docx.Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Inches(8.5), Inches(11)
    s.left_margin = s.right_margin = Inches(1); s.top_margin = s.bottom_margin = Inches(0.9)
    for block in [b.strip() for b in letter.strip().split("\n\n") if b.strip()]:
        _para(doc, block.replace("\n", " "), size, after=9)
    doc.save(str(path))


def render_pair(facts, draft, company, out_resume_base, out_letter_base, resume_dir, letter_dir, need_letter):
    """Write docx + pdf into the real folders; resume trimmed until exactly 1 page. Returns paths dict."""
    work = Path(tempfile.mkdtemp(prefix="prep-"))
    try:
        stem = Path(out_resume_base).name
        steps = [(10, 0), (9.5, 0), (9, 0), (9, 1), (9, 2), (8.5, 2), (8.5, 3)]
        n = len(draft["projects"])
        last = None
        for size, drop in steps:
            if drop and n - drop < 1: continue
            d = work / (stem + ".docx")
            build_resume_docx(facts, draft, d, size=size, drop_projects=drop)
            pdf = to_pdf(d, work)
            if pdf_pages(pdf) == 1:
                last = (d, pdf); break
        if not last:
            raise RuntimeError("the resume would not fit on one page even after trimming")
        res = {"resume_docx": _place(last[0], resume_dir), "resume_pdf": _place(last[1], resume_dir)}
        if need_letter:
            ld = work / (Path(out_letter_base).name + ".docx")
            build_letter_docx(facts, draft["letter"], company, ld)
            lpdf = to_pdf(ld, work)
            if pdf_pages(lpdf) != 1:
                raise RuntimeError("the cover letter does not fit on one page")
            res["letter_docx"] = _place(ld, letter_dir); res["letter_pdf"] = _place(lpdf, letter_dir)
        return res
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _place(src, dest_dir):
    """Copy into dest_dir, never overwriting an existing file (adds _2, _3...)."""
    dest_dir = Path(dest_dir); dest_dir.mkdir(parents=True, exist_ok=True)
    tgt = dest_dir / Path(src).name; i = 2
    while tgt.exists():
        tgt = dest_dir / f"{Path(src).stem}_{i}{Path(src).suffix}"; i += 1
    shutil.copy2(src, tgt)
    return str(tgt)
