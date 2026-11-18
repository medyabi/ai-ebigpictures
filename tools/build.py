#!/usr/bin/env python3
"""Builds ai.ebigpictures.com from the two Copilot lab repositories.

Usage: python3 build.py <copilot-studio-lab-repo> <copilot-cowork-lab-repo> <output-dir>
"""
import html
import os
import posixpath
import re
import shutil
import subprocess
import sys

import markdown

STU, COW, OUT = (os.path.abspath(p) for p in sys.argv[1:4])
REPO_URL = {"stu": "https://github.com/medyabi/Copilot-Studio-lab",
            "cow": "https://github.com/medyabi/Copilot-Cowork-lab"}
GH = {k: v + "/blob/main/" for k, v in REPO_URL.items()}
ROOTS = {"stu": STU, "cow": COW}
TRACK = {"stu": "studio", "cow": "cowork"}

# --------------------------------------------------------------------------
# 1. Which source files become which pages
# --------------------------------------------------------------------------
pages = {}   # (repo, src_rel) -> out_rel
kinds = {}   # (repo, src_rel) -> "Lab" | "Teaching edition" | ...


def add(repo, src, out, kind="Article"):
    pages[(repo, src)] = out
    kinds[(repo, src)] = kind


def slug(f):
    return re.sub(r"[^a-z0-9]+", "-", f[:-3].lower()).strip("-")


add("stu", "README.md", "copilot-studio/index.html", "Overview")
for f in sorted(os.listdir(os.path.join(STU, "Instructions/Labs"))):
    if f.endswith(".md"):
        add("stu", f"Instructions/Labs/{f}", f"copilot-studio/{slug(f)}.html", "Lab")
for f in sorted(os.listdir(os.path.join(STU, "Instructions/Trainer"))):
    if f.endswith(".md"):
        add("stu", f"Instructions/Trainer/{f}", "copilot-studio/trainer-notes.html", "Trainer guide")

add("cow", "README.md", "cowork/index.html", "Overview")
for f in sorted(os.listdir(os.path.join(COW, "Instructions/Labs"))):
    if f.endswith(".md"):
        add("cow", f"Instructions/Labs/{f}", f"cowork/{slug(f)}.html", "Lab")
for f in sorted(os.listdir(os.path.join(COW, "Instructions/Teaching"))):
    if f.endswith(".md"):
        add("cow", f"Instructions/Teaching/{f}", f"cowork/teaching/{slug(f)}.html", "Teaching edition")
for f in sorted(os.listdir(os.path.join(COW, "Instructions/Trainer"))):
    if f.endswith(".md"):
        add("cow", f"Instructions/Trainer/{f}", "cowork/trainer-guide.html", "Trainer guide")


def first_h1(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("# "):
                return line[2:].strip()
    return os.path.basename(path)


titles = {k: first_h1(os.path.join(ROOTS[k[0]], k[1])) for k in pages}
TRACK_NAME = {"studio": "From simple agents to autonomous agents",
              "cowork": "AI automation with Copilot Cowork"}
TRACK_SHORT = {"studio": "Copilot Studio track", "cowork": "Cowork track"}


def short(t):
    t = re.sub(r"\s*\(Teaching edition\)$", "", t)
    return re.sub(r"^Lab (\d+)\s*[-:]\s*", r"\1 · ", t)


def nav_for(repo):
    items = [("Overview", pages[(repo, "README.md")])]
    labs = sorted((o, s) for (r, s), o in pages.items() if r == repo and kinds[(r, s)] == "Lab")
    items += [(short(titles[(repo, s)]), o) for o, s in labs]
    teach = sorted((o, s) for (r, s), o in pages.items() if r == repo and kinds[(r, s)] == "Teaching edition")
    trainer = [(o, s) for (r, s), o in pages.items() if r == repo and kinds[(r, s)] == "Trainer guide"]
    return items, [(short(titles[(repo, s)]), o) for o, s in teach], [("Trainer guide", o) for o, s in trainer]


NAV = {"studio": nav_for("stu"), "cowork": nav_for("cow")}

# --------------------------------------------------------------------------
# 3. Rendering helpers
# --------------------------------------------------------------------------
def rel(from_out, to_out):
    r = posixpath.relpath(to_out, posixpath.dirname(from_out) or ".")
    return r


def copy_asset(repo, src_rel):
    """Copy an image from a repo into the site; return its site path."""
    name = f"assets/{repo}/{src_rel.replace('/', '-')}"
    dst = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(os.path.join(ROOTS[repo], src_rel), dst)
    return name


def rewrite_url(url, repo, src_rel, out_rel, is_img=False):
    if re.match(r"^[a-z]+:", url) or url.startswith("#") or url.startswith("//"):
        return url
    path, _, frag = url.partition("#")
    path = html.unescape(path)
    if posixpath.normpath(posixpath.join(posixpath.dirname(src_rel), path)) in ("index.html", "index.md"):
        return REPO_URL[repo]
    if path.endswith(".html") and not is_img:
        cand = posixpath.normpath(posixpath.join(posixpath.dirname(src_rel), path[:-5] + ".md"))
        if (repo, cand) in pages:
            path = path[:-5] + ".md"
    target = posixpath.normpath(posixpath.join(posixpath.dirname(src_rel), path))
    if is_img:
        if os.path.isfile(os.path.join(ROOTS[repo], target)):
            return rel(out_rel, copy_asset(repo, target))
        return url
    key = (repo, target)
    if key in pages:
        new = rel(out_rel, pages[key])
    else:
        new = GH[repo] + target
    return new + ("#" + frag if frag else "")


md = markdown.Markdown(extensions=["tables", "pymdownx.superfences", "pymdownx.highlight", "sane_lists", "toc"],
                       extension_configs={"toc": {"permalink": False},
                                          "pymdownx.highlight": {"use_pygments": False}})


def render_md(repo, src_rel, out_rel):
    with open(os.path.join(ROOTS[repo], src_rel), encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    text = text.replace("{{ site.github.repository_nwo }}", REPO_URL[repo].split("github.com/")[1])
    # a closing code fence directly followed by text breaks lists: add a blank line
    out_lines, in_fence = [], False
    lines = text.split("\n")
    for i, line in enumerate(lines):
        out_lines.append(line)
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            if not in_fence and i + 1 < len(lines) and lines[i + 1].strip():
                out_lines.append("")
    text = "\n".join(out_lines)
    md.reset()
    body = md.convert(text)
    body = re.sub(r'<pre class="highlight">', '<pre>', body)

    # links and images
    body = re.sub(r'href="([^"]+)"', lambda m: 'href="%s"' % rewrite_url(m.group(1), repo, src_rel, out_rel), body)
    body = re.sub(r'src="([^"]+)"', lambda m: 'src="%s"' % rewrite_url(m.group(1), repo, src_rel, out_rel, True), body)
    # external links open normally; mark them
    body = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" rel="noopener"', body)
    # mermaid
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  r'<pre class="mermaid">\1</pre>', body, flags=re.S)
    # blockquotes -> callouts
    def callout(m):
        inner = m.group(1)
        lead = re.sub(r"<[^>]+>", "", inner[:300]).lower()
        kind, label = "note", "Note"
        if "⚠" in lead or re.search(r"\b(warning|never|do not|don't)\b", lead):
            kind, label = "important", "Important"
        elif "🔍" in lead:
            kind, label = "tip", "Spot it"
        elif "💡" in lead or lead.startswith("tip"):
            kind, label = "tip", "Tip"
        elif re.search(r"question:", lead):
            kind, label = "note", "Check yourself"
        elif re.search(r"\bcost|credit", lead):
            kind, label = "warning", "Cost"
        # the title already carries the icon: drop the same emoji at the start of the text
        inner = re.sub(r"^(\s*<p>(?:<strong>)?)\s*(?:💡|⚠️|⚠|🔍)\ufe0f?\s*", r"\1", inner, count=1)
        return f'<div class="alert {kind}"><p class="alert-title">{label}</p>{inner}</div>'
    body = re.sub(r"<blockquote>\s*(.*?)\s*</blockquote>", callout, body, flags=re.S)
    # task lists
    body = re.sub(r"<li>\[ \]\s*", '<li class="task"><input type="checkbox"> ', body)
    body = re.sub(r"<li>\[[xX]\]\s*", '<li class="task"><input type="checkbox" checked> ', body)
    # drop header rows whose cells are all empty (key/value tables)
    body = re.sub(r"<thead>\s*<tr>(?:\s*<th>\s*</th>)+\s*</tr>\s*</thead>", "", body)
    # wrap tables for horizontal scroll
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    # navigation lines at top/bottom of labs: paragraph made only of links and separators
    body = re.sub(r"<p>((?:<a [^>]+>[^<]+</a>\s*(?:·\s*)?)+)</p>",
                  lambda m: '<nav class="pager">' + re.sub(r'\s*·\s*', ' ', m.group(1)) + '</nav>', body)
    return body



MERMAID = ('<script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs";'
           'const dark = document.documentElement.matches("[data-theme=dark]") || (window.matchMedia("(prefers-color-scheme: dark)").matches && !document.documentElement.matches("[data-theme=light]"));'
           'mermaid.initialize({startOnLoad:true, theme: dark ? "dark" : "neutral", securityLevel:"strict"});</script>')

CHECKLIST_JS = """<script>
(function(){
  var key = 'progress:' + location.pathname;
  var boxes = Array.prototype.slice.call(document.querySelectorAll('li.task input'));
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(key) || '{}'); } catch (e) {}
  boxes.forEach(function(b, i){
    b.id = 'task-' + i;
    if (saved[i]) b.checked = true;
    b.addEventListener('change', function(){
      saved[i] = b.checked;
      try { localStorage.setItem(key, JSON.stringify(saved)); } catch (e) {}
    });
  });
})();
</script>"""

SITE_JS = """<script>
(function(){
  // Table of contents: open on wide screens, collapsible on small ones
  var toc = document.querySelector('details.toc');
  if (toc) {
    var mq = window.matchMedia('(min-width: 1024px)');
    var sync = function(){ if (mq.matches) toc.open = true; };
    sync(); if (mq.addEventListener) mq.addEventListener('change', sync);
    var cur = toc.querySelector('[aria-current="page"]');
    if (cur && cur.scrollIntoView && mq.matches) cur.scrollIntoView({block: 'center'});
  }
  // Filter by title
  var f = document.getElementById('toc-filter');
  if (f) f.addEventListener('input', function(){
    var q = f.value.trim().toLowerCase();
    document.querySelectorAll('.toc-list li').forEach(function(li){
      var hit = !q || li.textContent.toLowerCase().indexOf(q) !== -1;
      li.hidden = !hit;
    });
  });
  // Copy buttons on code blocks
  document.querySelectorAll('.codeblock').forEach(function(cb){
    var btn = cb.querySelector('.copy'), code = cb.querySelector('code');
    if (!btn || !code) return;
    btn.addEventListener('click', function(){
      navigator.clipboard.writeText(code.innerText).then(function(){
        btn.textContent = 'Copied'; setTimeout(function(){ btn.textContent = 'Copy'; }, 1500);
      }, function(){ btn.textContent = 'Select and copy'; });
    });
  });
  // Highlight the current section in "In this article"
  var links = document.querySelectorAll('.aside-toc a');
  if (links.length && 'IntersectionObserver' in window) {
    var map = {}; links.forEach(function(a){ map[a.getAttribute('href').slice(1)] = a; });
    var obs = new IntersectionObserver(function(es){
      es.forEach(function(e){ if (e.isIntersecting) {
        links.forEach(function(a){ a.classList.remove('on'); });
        var a = map[e.target.id]; if (a) a.classList.add('on');
      }});
    }, {rootMargin: '0px 0px -75% 0px'});
    Object.keys(map).forEach(function(id){ var h = document.getElementById(id); if (h) obs.observe(h); });
  }
})();
</script>"""


LANG_LABEL = {"powershell": "PowerShell", "bash": "Bash", "json": "JSON", "yaml": "YAML", "text": "Text", "markdown": "Markdown"}

def enhance(body):
    """Code-block headers with Copy, and the 'In this article' list."""
    def code(m):
        lang = m.group(1) or ""
        label = LANG_LABEL.get(lang, lang.capitalize() if lang else "")
        if not lang:
            nxt = body_ref[0][m.end():m.end() + 400]
            if re.search(r"\b(Get|Set|New|Remove|Add|Install|Invoke|Enable|Disable|Start|Stop|Restart|Test|Import|Export|Update|Register|Grant|Copy)-[A-Z]", nxt):
                label = "PowerShell"
        return (f'<div class="codeblock"><div class="code-head"><span>{label}</span>'
                f'<button type="button" class="copy">Copy</button></div><pre><code{m.group(2)}>')
    body_ref = [body]
    body = re.sub(r'<pre><code(?: class="language-([a-z0-9]+)")?()>', code, body)
    body = re.sub(r'(<div class="codeblock">.*?</code></pre>)', r'\1</div>', body, flags=re.S)
    heads = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body)
    if len(heads) < 2:
        heads = re.findall(r'<h3 id="([^"]+)">(.*?)</h3>', body)
    aside = ""
    if len(heads) >= 2:
        lis = "".join(f'<li><a href="#{i}">{re.sub(r"<[^>]+>", "", t)}</a></li>' for i, t in heads)
        aside = f'<aside class="aside-toc" aria-label="In this article"><p>In this article</p><ol>{lis}</ol></aside>'
    return body, aside


def meta_line(body, kind):
    words = len(re.sub(r"<[^>]+>", " ", body).split())
    mins = max(1, round(words / 200))
    return f'<p class="meta"><span>{kind}</span><span>{mins} min read</span></p>'



ICONS = {
    "studio": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8l-5 4v-4H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Zm8 2.5c-.4 2.3-1.2 3.1-3.5 3.5 2.3.4 3.1 1.2 3.5 3.5.4-2.3 1.2-3.1 3.5-3.5-2.3-.4-3.1-1.2-3.5-3.5Z" fill="currentColor"/></svg>',
    "cowork": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h7v7H4zm9 0h7v7h-7zM4 14h7v5H4zm9 0h7v5h-7z" fill="currentColor"/></svg>',
    "trainer": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 1 8l11 5 9-4.1V15h2V8Zm-6 9.2V16c0 1.7 2.7 3 6 3s6-1.3 6-3v-3.8l-6 2.7Z" fill="currentColor"/></svg>',
}


def sidebar(track, out_rel):
    def link(label, target):
        cur = ' aria-current="page"' if target == out_rel else ""
        return f'<a href="{rel(out_rel, target)}"{cur}>{html.escape(label)}</a>'

    labs, teach, trainer = NAV[track]
    parts = [f"<li>{link(l, t)}</li>" for l, t in labs]
    if teach:
        sub = "".join(f"<li>{link(l, t)}</li>" for l, t in teach)
        open_ = " open" if any(t == out_rel for _, t in teach) else ""
        parts.append(f'<li class="group"><details{open_}><summary>Teaching editions</summary><ol>{sub}</ol></details></li>')
    parts += [f"<li>{link(l, t)}</li>" for l, t in trainer]
    name = TRACK_NAME[track]
    return (f'<details class="toc"><summary>Table of contents</summary>'
            f'<nav aria-label="{name}"><p class="toc-title">{name}</p>'
            f'<input id="toc-filter" class="toc-filter" type="search" placeholder="Filter by title" aria-label="Filter by title">'
            f'<ol class="toc-list">{"".join(parts)}</ol></nav></details>')


def crumbs(out_rel, track):
    trail = [("AI Labs", "index.html"), (TRACK_SHORT[track], NAV[track][0][0][1])]
    trail = [(l, t) for l, t in trail if t != out_rel]
    items = "".join(f'<li><a href="{rel(out_rel, t)}">{html.escape(l)}</a></li>' for l, t in trail)
    return f'<nav class="crumbs" aria-label="Breadcrumb"><ol>{items}</ol></nav>'


def pager(track, out_rel):
    seq = [t for _, t in NAV[track][0]]
    if out_rel not in seq:
        return ""
    i = seq.index(out_rel)
    labels = dict((t, l) for l, t in NAV[track][0])
    prev = f'<a href="{rel(out_rel, seq[i-1])}">‹ {html.escape(labels[seq[i-1]])}</a>' if i > 0 else "<span></span>"
    nxt = f'<a href="{rel(out_rel, seq[i+1])}">{html.escape(labels[seq[i+1]])} ›</a>' if i + 1 < len(seq) else "<span></span>"
    return f'<nav class="pager bottom">{prev}{nxt}</nav>'


def shell(out_rel, title, body, track=None, extra="", kind="Article", repo=None):
    css = rel(out_rel, "assets/site.css")
    home = rel(out_rel, "index.html")
    nav = [("Copilot Studio", "copilot-studio/index.html", "studio"), ("Copilot Cowork", "cowork/index.html", "cowork"),
           ("Windows Server Labs", "https://learn.ebigpictures.com/", "ws")]
    cur = ' aria-current="true"'
    nav_html = "".join(f'<a href="{t if t.startswith("http") else rel(out_rel, t)}"{cur if track == k else ""}>{l}</a>' for l, t, k in nav)
    full_title = f"{title} · AI Labs" if title != "AI Labs" else "AI Labs · Copilot Studio and Copilot Cowork"
    if track:
        body, aside = enhance(body)
        side = sidebar(track, out_rel)
        meta = meta_line(body, kind)
        dur = re.search(r"(?:Estimated (?:timing|duration)|Time)[:\s]*(?:</strong>)?\s*(?:about\s*)?(\d+\s*min(?:utes)?)", body, re.I)
        if dur:
            meta = meta.replace("</p>", f"<span>Lab time: {dur.group(1).replace('minutes', 'min')}</span></p>")
        body = re.sub(r"(</h1>)", lambda m: m.group(1) + meta, body, count=1)
        # the lab time is now in the metadata line: drop the "Estimated timing" heading and its TOC entry
        body = re.sub(r'<h2 id="[^"]*">Estimated timing:[^<]*</h2>\s*', '', body)
        body = re.sub(r'<p><strong>Estimated duration:</strong>[^<]*</p>\s*', '', body)
        aside = re.sub(r'<li><a href="#[^"]*">Estimated timing:[^<]*</a></li>', '', aside)
        layout = f"""<div class="doc has-toc">
{side}
<main id="content" class="article">
{crumbs(out_rel, track)}
<article class="prose">
{body}
</article>
{pager(track, out_rel)}
<p class="source"><a href="{REPO_URL[repo]}" rel="noopener">View the source on GitHub</a></p>
</main>
{aside}
</div>"""
        extra = SITE_JS + extra
    else:
        layout = f'<main id="content" class="home">\n{body}\n</main>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="Hands-on labs for Microsoft Copilot Studio, Agent Builder and Microsoft 365 Copilot Cowork: from a simple agent to autonomous agents.">
<link rel="stylesheet" href="{css}">
<link rel="icon" href="{rel(out_rel, 'assets/favicon.svg')}" type="image/svg+xml">
<link rel="icon" href="{rel(out_rel, 'assets/favicon-32.png')}" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="{rel(out_rel, 'assets/apple-touch-icon.png')}">
</head>
<body class="t-{track or 'home'}">
<a class="skip" href="#content">Skip to main content</a>
<header class="masthead">
  <a class="brand" href="{home}"><img src="{rel(out_rel, 'assets/favicon.svg')}" alt="" width="24" height="24"><span>AI Labs</span></a>
  <span class="divider" aria-hidden="true"></span>
  <nav class="mainnav" aria-label="Main">{nav_html}</nav>
  <a class="gh" href="https://github.com/medyabi" rel="noopener">GitHub</a>
</header>
{layout}
<footer class="sitefoot">
  <div class="foot-in">
    <div><strong>AI Labs</strong><p>Hands-on Copilot labs by Mohamed Dyabi, Microsoft Certified Trainer.</p></div>
    <ul>
      <li><a href="{rel(out_rel, 'copilot-studio/index.html')}">Copilot Studio track</a></li>
      <li><a href="{rel(out_rel, 'cowork/index.html')}">Copilot Cowork track</a></li>
      <li><a href="https://learn.ebigpictures.com/">Windows Server Labs</a></li>
      <li><a href="{REPO_URL['stu']}" rel="noopener">Copilot Studio labs on GitHub</a></li>
      <li><a href="{REPO_URL['cow']}" rel="noopener">Cowork labs on GitHub</a></li>
    </ul>
  </div>
  <p class="fine">Use a test or demo tenant: these labs create agents, workflows and SharePoint items, and consume Copilot Credits. Preview features and labels change often. An independent site, not affiliated with Microsoft. © 2026 Mohamed Dyabi</p>
</footer>
{extra}
</body>
</html>
"""


# --------------------------------------------------------------------------
# Home page
# --------------------------------------------------------------------------
def home_page():
    def lab_list(track):
        return "".join(f'<li><a href="{t}">{html.escape(re.sub(r"^\d+ · ", "", l))}</a></li>' for l, t in NAV[track][0][1:])
    n_stu, n_cow = len(NAV["studio"][0]) - 1, len(NAV["cowork"][0]) - 1
    first_stu = NAV["studio"][0][1][1]
    first_cow = NAV["cowork"][0][1][1]
    body = f"""
<section class="hero">
  <div class="wrap">
    <p class="kicker">Microsoft 365 Copilot · Copilot Studio · Copilot Cowork</p>
    <h1>Build AI agents by doing it, one lab at a time</h1>
    <p class="lede">Two hands-on tracks. In the first, you grow one agent from a few lines of instructions into a team of agents that act, ask for approval and start on their own. In the second, you hand real multi-step work to Copilot Cowork and package it as your own skills and plugins.</p>
    <p class="cta"><a class="btn primary" href="{first_stu}">Start the Copilot Studio track</a><a class="btn" href="{first_cow}">Start the Cowork track</a></p>
  </div>
</section>

<div class="wrap">
<h2 class="section-title">Browse the tracks</h2>
<div class="cards">
  <article class="card">
    <div class="card-head"><span class="ico c-purple">{ICONS['studio']}</span><div><p class="card-kicker">Learning path · {n_stu} labs · about 8 hours</p>
    <h3><a href="copilot-studio/index.html">From simple agents to autonomous agents</a></h3></div></div>
    <p>One storyline, the Contoso IT Service Desk. Start in Agent Builder with instructions and company knowledge, move to Copilot Studio, then add connectors, MCP tools, workflows with human approval, skills, memory, connected agents and triggers. Finish by evaluating, publishing and governing what you built.</p>
    <ol class="mini">{lab_list('studio')}</ol>
    <p class="card-foot"><a href="copilot-studio/index.html">Start the Copilot Studio track ›</a></p>
  </article>
  <article class="card">
    <div class="card-head"><span class="ico c-blue">{ICONS['cowork']}</span><div><p class="card-kicker">Workshop · {n_cow} labs · about 3.5 hours</p>
    <h3><a href="cowork/index.html">AI automation with Copilot Cowork</a></h3></div></div>
    <p>Cowork plans and carries out multi-step work across your mail, calendar and files, then hands you a finished result. Run your first tasks, organize files and meetings, then build custom skills, a personal dashboard and a plugin you can publish. Each lab has a teaching edition for trainers.</p>
    <ol class="mini">{lab_list('cowork')}</ol>
    <p class="card-foot"><a href="cowork/index.html">Start the Cowork track ›</a></p>
  </article>
</div>

<h2 class="section-title">How every lab works</h2>
<ol class="steps5">
  <li><strong>The scenario</strong><span>A Contoso request: why this lab matters.</span></li>
  <li><strong>The concepts</strong><span>Just enough theory, in plain words, with an analogy.</span></li>
  <li><strong>Step by step</strong><span>Real screenshots of the current UI, field by field.</span></li>
  <li><strong>Test it</strong><span>Prompts to try, and the trace that proves what the agent did.</span></li>
  <li><strong>Takeaways</strong><span>What to remember, and what to tell a customer.</span></li>
</ol>

<h2 class="section-title">What you need</h2>
<div class="cards two">
  <div class="card plain"><h3>Copilot Studio track</h3><p>A test Microsoft 365 tenant, a Microsoft 365 Copilot license, Copilot Studio access with Copilot Credits, and a Power Platform environment with Dataverse.</p></div>
  <div class="card plain"><h3>Cowork track</h3><p>A Microsoft 365 account with Copilot and access to Copilot Cowork. Sample files are provided in the repository.</p></div>
</div>

<section class="band">
  <span class="ico c-blue">{ICONS['trainer']}</span>
  <div>
    <p class="card-kicker">For trainers</p>
    <h2>Run these labs as a workshop</h2>
    <p>Each track has a trainer guide: agendas, what to check before you deliver, common problems and their fixes, and discussion questions.</p>
  </div>
  <div class="band-actions"><a class="btn" href="{NAV['studio'][2][0][1]}">Copilot Studio trainer notes</a><a class="btn" href="{NAV['cowork'][2][0][1]}">Cowork trainer guide</a></div>
</section>
</div>
"""
    return shell("index.html", "AI Labs", body)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
if os.path.isdir(OUT):
    for name in os.listdir(OUT):
        if name in (".git", "CNAME", "tools", "README.md"):
            continue
        p = os.path.join(OUT, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
os.makedirs(OUT, exist_ok=True)

for (repo, src), out in pages.items():
    body = render_md(repo, src, out)
    extra = MERMAID if 'class="mermaid"' in body else ""
    if 'class="task"' in body:
        extra += CHECKLIST_JS
    dst = os.path.join(OUT, out)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(shell(out, short(titles[(repo, src)]).replace(" · ", ": ", 1) if kinds[(repo, src)] != "Overview" else titles[(repo, src)],
                       body, TRACK[repo], extra, kind=kinds[(repo, src)], repo=repo))

with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as fh:
    fh.write(home_page())

TOOLS = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
shutil.copyfile(os.path.join(TOOLS, "site.css"), os.path.join(OUT, "assets", "site.css"))
shutil.copyfile(os.path.join(TOOLS, "favicon.svg"), os.path.join(OUT, "assets", "favicon.svg"))
from PIL import Image
for size, name in ((32, "favicon-32.png"), (180, "apple-touch-icon.png"), (48, "_ico48.png")):
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size),
                    os.path.join(TOOLS, "favicon.svg"), "-o", os.path.join(OUT, "assets", name)], check=True)
Image.open(os.path.join(OUT, "assets", "_ico48.png")).save(os.path.join(OUT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
os.remove(os.path.join(OUT, "assets", "_ico48.png"))
with open(os.path.join(OUT, "CNAME"), "w") as fh:
    fh.write("ai.ebigpictures.com\n")
open(os.path.join(OUT, ".nojekyll"), "w").close()
nf = shell("404.html", "Page not found",
           '<div class="wrap"><h1>Page not found</h1><p>That page doesn\'t exist. Go back to the <a href="index.html">home page</a>.</p></div>')
nf = re.sub(r'(href|src)="(?!https?:|/|#)', r'\1="/', nf)
with open(os.path.join(OUT, "404.html"), "w", encoding="utf-8") as fh:
    fh.write(nf)
print(f"{len(pages) + 2} pages written to {OUT}")
