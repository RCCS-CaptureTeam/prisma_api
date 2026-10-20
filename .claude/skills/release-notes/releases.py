#!/usr/bin/env python3
"""Helpers for the release-notes skill.

  releases.py plan v0.4.x     # patches missing from docs/release_notes/v0.4.x.md, plus any
                              # tag newer than the newest one documented in any notes doc
  releases.py plan v0.4.7    # the same, and, if v0.4.7 is not tagged yet, the upcoming
                              # release: commits since the latest tag + uncommitted changes
  releases.py check v0.4.x    # reorder H1 sections newest-first, add missing release
                              # edit links under each H1, and validate the doc
  releases.py check v0.4.7   # the same for v0.4.7's doc, accepting the upcoming tag

Only genuine releases count: tags with a published GitHub release, plus every tag newer
than the latest release (assumed to become releases). Older tags without a release are
historical and skipped; their commits fold into the next release's compare range.

Each listed patch comes with its date, edit URL, compare URL and commits. Each commit
is tagged with the areas it touched (v1 client, v2 client, config, docs, ...) and the
public client methods it added or removed, as a hint for choosing themes.
"""
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[3]
NOTES_DIR = REPO / "docs" / "release_notes"
COMPARE = "https://github.com/RCCS-CaptureTeam/prisma_api/compare/{prev}...{tag}"
EDIT = "https://github.com/RCCS-CaptureTeam/prisma_api/releases/edit/{tag}"
RELEASES_API = "https://api.github.com/repos/RCCS-CaptureTeam/prisma_api/releases?per_page=100&page={page}"
CLIENTS = {"prisma_api/prisma_api.py": "api.", "prisma_api/prisma_api_v2.py": "api.v2."}
# (path prefix, area label) - first match wins; unmatched paths are reported as "other".
AREAS = [
    ("prisma_api/prisma_api_v2.py", "v2"),
    ("prisma_api/prisma_api.py", "v1"),
    ("prisma_api/config.py", "config"),
    ("prisma_api/__init__.py", "package"),
    ("API_REFERENCE_V1.md", "docs"),
    ("API_REFERENCE_V2.md", "docs"),
    ("README.md", "docs"),
    ("user_guide.md", "docs"),
    ("User Guide.md", "docs"),
    ("examples/", "examples"),
    ("integration/", "integration"),
    ("tests/", "tests"),
    (".github/", "ci"),
    ("pyproject.toml", "packaging"),
    (".claude/", "agent"),
]
DEF_RE = re.compile(r"^([+-])    def ([a-z]\w*)\(", re.M)
TAG_RE = re.compile(r"^v(\d+(?:\.\d+)+)$")
H1_RE = re.compile(r"^# (v\d+(?:\.\d+)+)\s*$", re.M)


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, check=True,
                          capture_output=True, text=True).stdout


def vkey(tag):
    return tuple(int(p) for p in TAG_RE.match(tag).group(1).split("."))


def parse_arg(arg):
    """'v0.4.x' / 'v0.4' / '0.4' -> (0, 4, None);  'v0.4.7' / '0.4.7' -> (0, 4, 'v0.4.7')."""
    m = re.match(r"^v?(\d+)\.(\d+)(?:\.(x|\d+))?$", arg.strip())
    if not m:
        sys.exit(f"Expected a minor release like 'v0.4.x' or a tag like 'v0.4.7', got {arg!r}")
    tag = f"v{m.group(1)}.{m.group(2)}.{m.group(3)}" if m.group(3) not in (None, "x") else None
    return int(m.group(1)), int(m.group(2)), tag


def all_tags():
    tags = [t for t in git("tag").split() if TAG_RE.match(t)]
    return sorted(tags, key=vkey)


def github_releases():
    """{tag: 'YYYY-MM-DD'} for every published (non-draft) GitHub release."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "release-notes-skill"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    found, page = {}, 1
    while True:
        try:
            with urlopen(Request(RELEASES_API.format(page=page), headers=headers), timeout=30) as r:
                batch = json.load(r)
        except (URLError, OSError, ValueError) as e:
            sys.exit(f"Could not list GitHub releases ({e}). Check network access, or set "
                     "GITHUB_TOKEN if rate-limited.")
        found.update({r["tag_name"]: r["published_at"][:10] for r in batch
                      if not r["draft"] and r.get("published_at")})
        if len(batch) < 100:
            return found
        page += 1


def release_tags(tags, releases):
    """Tags treated as releases: published GitHub releases, plus every tag newer than the
    latest release (assumed to become releases). Older tags without a release are historical."""
    latest = max((t for t in tags if t in releases), key=vkey, default=None)
    return [t for t in tags if t in releases or latest is None or vkey(t) > vkey(latest)]


def doc_path(major, minor):
    return NOTES_DIR / f"v{major}.{minor}.x.md"


def rel(path):
    try:
        return path.relative_to(REPO)
    except ValueError:
        return path


def series_doc(tag):
    major, minor = vkey(tag)[:2]
    return doc_path(major, minor)


def documented_tags():
    """Every '# vX.Y.Z' heading across all release-notes docs."""
    found = set()
    for path in NOTES_DIR.glob("v*.x.md"):
        found |= set(H1_RE.findall(path.read_text()))
    return found


def upcoming_tag(tag, tags):
    """`tag` if it is the next release (not tagged yet, newer than the latest tag), else None."""
    if tag is None or tag in tags:
        return None
    if tags and vkey(tag) <= vkey(tags[-1]):
        sys.exit(f"{tag} is not tagged and is not newer than the latest tag {tags[-1]}")
    return tag


def area(path):
    return next((label for prefix, label in AREAS if path.startswith(prefix)), "other")


def method_changes(diff_args):
    """Public client methods added / removed by a diff, e.g. (['api.v2.foo'], ['api.bar'])."""
    added, removed = [], []
    for path, prefix in CLIENTS.items():
        diff = git("diff", *diff_args, "--", path)
        plus = {m.group(2) for m in DEF_RE.finditer(diff) if m.group(1) == "+"}
        minus = {m.group(2) for m in DEF_RE.finditer(diff) if m.group(1) == "-"}
        added += [prefix + n for n in sorted(plus - minus)]
        removed += [prefix + n for n in sorted(minus - plus)]
    return added, removed


def describe(paths, diff_args):
    areas = sorted({area(p) for p in paths})
    added, removed = method_changes(diff_args)
    out = f"[{', '.join(areas) or '-'}]"
    if added:
        out += f"\n                new: {', '.join(added)}"
    if removed:
        out += f"\n                removed: {', '.join(removed)}"
    return out


def print_commits(rev_range):
    lines = git("log", "--reverse", "--no-merges", "--format=%H\t%s", rev_range).splitlines()
    for line in lines:
        sha, subject = line.split("\t", 1)
        paths = git("show", "--no-renames", "--format=", "--name-only", sha).split("\n")
        print(f"    {sha[:8]}  {subject}")
        print(f"              {describe([p for p in paths if p], [f'{sha}^!'])}")
    if not lines:
        print("    (no commits)")


def print_uncommitted():
    status = git("status", "--porcelain", "--untracked-files=all").splitlines()
    print(f"    uncommitted changes ({len(status)} paths; read them with `git diff HEAD -- <path>`"
          " or open untracked files):")
    for line in status:
        print(f"      {line}")
    if status:
        print(f"      {describe([line[3:] for line in status], ['HEAD'])}")
    else:
        print("      (none)")


def plan(major, minor, tag):
    tags = all_tags()
    upcoming = upcoming_tag(tag, tags)
    releases = github_releases()
    tags_all, tags = tags, release_tags(tags, releases)
    historical = [t for t in tags_all if t not in tags]
    in_minor = [t for t in tags if vkey(t)[:2] == (major, minor)]
    if tag:
        in_minor = [t for t in in_minor if vkey(t) <= vkey(tag)]
    documented = documented_tags()
    newest_doc = max(documented, key=vkey) if documented else None

    # Missing in the named series, plus any release after the newest documented one
    # (any series) - i.e. releases missed since the notes were last updated.
    missing = {t for t in in_minor if t not in documented}
    if newest_doc:
        missing |= {t for t in tags if vkey(t) > vkey(newest_doc) and t not in documented}
    missing = sorted(missing, key=vkey)

    print(f"newest documented tag: {newest_doc or '-'}")
    print(f"latest tag: {tags_all[-1] if tags_all else '-'}")
    print(f"latest GitHub release: {max(releases, key=vkey) if releases else '-'}")
    print(f"releases in v{major}.{minor}.x: {', '.join(in_minor) or '-'}")
    print(f"historical tags without a release (skipped): {', '.join(historical) or 'none'}")
    print(f"missing: {', '.join(missing) or 'none'}")
    print(f"upcoming (not tagged yet): {upcoming or '-'}\n")

    for t in missing:
        i = tags.index(t)
        prev = tags[i - 1] if i else None
        # The tag date is the release date: some GitHub releases were published long after.
        released = git("log", "-1", "--format=%ad", "--date=short", t).strip()
        if t not in releases:
            released += "; no GitHub release yet, assumed to become one"
        elif releases[t] != released:
            released += f"; GitHub release published {releases[t]}"
        print(f"=== {t}  ({released})  -> {rel(series_doc(t))}")
        print(f"    edit:    {EDIT.format(tag=t)}")
        if prev is None:
            print("    (first release - no compare range)\n")
            continue
        print(f"    compare: {COMPARE.format(prev=prev, tag=t)}")
        folded = [h for h in historical if vkey(prev) < vkey(h) < vkey(t)]
        if folded:
            print(f"    includes historical tag(s) without a release: {', '.join(folded)}")
        print_commits(f"{prev}..{t}")
        print()

    if upcoming:
        prev = tags[-1] if tags else None
        print(f"=== {upcoming}  (upcoming: write it as released {date.today().isoformat()})"
              f"  -> {rel(series_doc(upcoming))}")
        print(f"    edit:    {EDIT.format(tag=upcoming)}")
        if prev:
            print(f"    compare: {COMPARE.format(prev=prev, tag=upcoming)}  (live once the tag is pushed)")
        print_commits(f"{prev}..HEAD" if prev else "HEAD")
        print_uncommitted()
        print()

    # The upcoming tag's doc must be checked with the tag itself, so it is accepted.
    docs = {series_doc(t): t for t in missing}
    if upcoming:
        docs[series_doc(upcoming)] = upcoming
    if docs:
        print("then run:", "; ".join(
            f"releases.py check {t if t == upcoming else d.stem}" for d, t in sorted(docs.items())))


def check(major, minor, tag):
    tags = all_tags()
    upcoming = upcoming_tag(tag, tags)
    known = release_tags(tags, github_releases()) + ([upcoming] if upcoming else [])
    path = doc_path(major, minor)
    if not path.exists():
        sys.exit(f"{path} does not exist")
    text = path.read_text()
    starts = [m.start() for m in H1_RE.finditer(text)]
    if not starts:
        sys.exit("No '# vX.Y.Z' sections found")
    preamble = text[:starts[0]].rstrip()
    sections = [text[s:e].strip() for s, e in zip(starts, starts[1:] + [len(text)])]
    sections.sort(key=lambda s: vkey(H1_RE.match(s).group(1)), reverse=True)

    problems = []
    added = 0
    for idx, sec in enumerate(sections):
        t = H1_RE.match(sec).group(1)
        # The release edit link sits on its own line directly under the H1.
        heading, _, body = sec.partition("\n")
        body = body.lstrip("\n")
        first = body.split("\n", 1)[0].strip()
        if first.startswith(EDIT.format(tag="")):
            if first != EDIT.format(tag=t):
                problems.append(f"{t}: edit link must be {EDIT.format(tag=t)}")
        else:
            sections[idx] = sec = f"{heading}\n\n{EDIT.format(tag=t)}\n\n{body}"
            added += 1
        if t in tags and t not in known:
            problems.append(f"{t}: historical tag with no GitHub release - remove this section "
                            "and describe its changes under the next release")
            continue
        if t not in known:
            problems.append(f"{t}: no such git tag" + ("" if tag else
                            " (pass the tag, e.g. 'check v0.4.7', if it is the upcoming release)"))
            continue
        i = known.index(t)
        if i:
            url = COMPARE.format(prev=known[i - 1], tag=t)
            if not sec.rstrip().endswith(f"## Changelog\n\n- {url}"):
                problems.append(f"{t}: must end with '## Changelog' and '- {url}'")
        for theme in re.split(r"^### ", sec, flags=re.M)[1:]:
            bullets = len(re.findall(r"^- ", theme.split("\n## ")[0], re.M))
            if bullets > 5:
                problems.append(f"{t}: theme '{theme.splitlines()[0]}' has {bullets} bullets (max 5)")

    out = (preamble + "\n\n" if preamble else "") + "\n\n".join(sections) + "\n"
    path.write_text(out)
    print(f"sorted {len(sections)} sections in {rel(path)}")
    if added:
        print(f"added the release edit link under {added} heading(s)")
    if upcoming:
        print(f"{upcoming} accepted as the upcoming release (not tagged yet)")
    for p in problems:
        print("PROBLEM:", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("plan", "check"):
        sys.exit(__doc__)
    {"plan": plan, "check": check}[sys.argv[1]](*parse_arg(sys.argv[2]))
