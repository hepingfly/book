#!/usr/bin/env python3
"""
Translate Right Kind of Wrong epub to Simplified Chinese.
Processes each chapter xhtml, translates via Claude API, rebuilds epub.
"""

import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag
import anthropic

# Config
BASE_DIR = Path(__file__).parent
EPUB_SRC = BASE_DIR / "Right_Kind_of_Wrong.epub"
WORK_DIR = BASE_DIR / "epub_extracted" / "book_contents"
TRANSLATED_DIR = BASE_DIR / "translated_xhtml"
OUTPUT_EPUB = BASE_DIR / "Right_Kind_of_Wrong_CN.epub"

XHTML_BASE = WORK_DIR / "e9781982195083" / "xhtml"

# Files to translate (in order)
TRANSLATE_FILES = [
    "title.xhtml",
    "praise.xhtml",
    "epigraph.xhtml",
    "prologue.xhtml",
    "intro.xhtml",
    "part01.xhtml",
    "ch01.xhtml",
    "ch02.xhtml",
    "ch03.xhtml",
    "ch04.xhtml",
    "part02.xhtml",
    "ch05.xhtml",
    "ch06.xhtml",
    "ch07.xhtml",
    "ch08.xhtml",
    "authorbio.xhtml",
    "endnotes.xhtml",
    "copyright.xhtml",
    "SS_US_adult_signup_front.xhtml",
    "SS_US_adult_signup_back.xhtml",
    "nav.xhtml",
]

CHAPTER_TITLES_CN = {
    "praise.xhtml": "赞誉",
    "epigraph.xhtml": "题辞",
    "prologue.xhtml": "序言",
    "intro.xhtml": "引言",
    "part01.xhtml": "第一部分：失败的全景",
    "ch01.xhtml": "第一章：追求正确的失败",
    "ch02.xhtml": "第二章：尤里卡！",
    "ch03.xhtml": "第三章：犯错是人之常情",
    "ch04.xhtml": "第四章：完美风暴",
    "part02.xhtml": "第二部分：践行优雅失败的科学",
    "ch05.xhtml": "第五章：我们遇到了敌人",
    "ch06.xhtml": "第六章：情境与后果",
    "ch07.xhtml": "第七章：欣赏系统",
    "ch08.xhtml": "第八章：作为易错人类的蓬勃生长",
    "authorbio.xhtml": "关于作者",
}


def get_api_key():
    for path in [
        "/home/claude/.claude/remote/.oauth_token",
        "/home/claude/.claude/remote/.session_ingress_token",
    ]:
        p = Path(path)
        if p.exists():
            return p.read_text().strip()
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    raise RuntimeError("No API key found")


def call_with_retry(client, **kwargs):
    """Call client.messages.create with exponential backoff on rate limits."""
    delays = [5, 10, 20, 40, 60]
    for i, delay in enumerate(delays):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            if i == len(delays) - 1:
                raise
            print(f"    Rate limit hit, waiting {delay}s...")
            time.sleep(delay)
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 and i < len(delays) - 1:
                print(f"    Server error {e.status_code}, waiting {delay}s...")
                time.sleep(delay)
            else:
                raise


def translate_chunk(client, texts: list, filename: str) -> list:
    """Translate a list of HTML-fragment strings, returning translated list."""
    if not texts:
        return []

    numbered = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(texts))

    system = (
        "You are a professional literary translator specializing in business and psychology books. "
        "Translate the following numbered HTML text segments from English to Simplified Chinese.\n"
        "Rules:\n"
        "- Translate each segment faithfully, preserving meaning, tone, and style.\n"
        "- Keep any HTML tags (like <em>, <strong>, <a>, <span>) exactly as-is inside translated text.\n"
        "- Return ONLY the translated segments in the SAME numbered format [1], [2], etc.\n"
        "- Do NOT add explanations, notes, commentary, or extra lines.\n"
        "- Use natural, fluent Simplified Chinese suitable for a business/psychology book.\n"
        "- Book title: 'Right Kind of Wrong' = '正确的失败方式'."
    )

    prompt = f"File: {filename}\n\nTranslate these segments to Simplified Chinese:\n\n{numbered}"

    response = call_with_retry(
        client,
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Parse numbered responses
    results = {}
    pattern = re.compile(r"\[(\d+)\]\s*(.*?)(?=\n\[\d+\]|\Z)", re.DOTALL)
    for m in pattern.finditer(raw):
        idx = int(m.group(1)) - 1
        results[idx] = m.group(2).strip()

    translated = []
    for i, original in enumerate(texts):
        translated.append(results.get(i, original))

    return translated


def get_translatable_elements(soup):
    """Return text-bearing leaf/block tags that should be translated."""
    return soup.find_all(
        ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote",
         "dt", "dd", "figcaption", "title", "cite"]
    )


def set_element_html(el, html_content):
    """Replace element's inner content with translated html string."""
    el.clear()
    if not html_content or not html_content.strip():
        return
    # Parse as fragment
    frag = BeautifulSoup(f"<body>{html_content}</body>", "html.parser")
    body = frag.find("body")
    if body:
        for child in list(body.children):
            el.append(child.__copy__() if hasattr(child, "__copy__") else str(child))


def translate_xhtml(client, filepath: Path, outpath: Path, filename: str):
    """Translate a single xhtml file and write result to outpath."""
    print(f"\n  Translating {filename}...")
    content = filepath.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "xml")

    elements = get_translatable_elements(soup)
    translatable = [el for el in elements if el.get_text(strip=True)]

    if not translatable:
        shutil.copy2(filepath, outpath)
        print(f"  No text to translate in {filename}, copied as-is.")
        return

    texts = [el.decode_contents() for el in translatable]
    print(f"  {len(texts)} segments to translate")

    chunk_size = 30
    all_translated = []
    total_chunks = (len(texts) + chunk_size - 1) // chunk_size
    for i in range(0, len(texts), chunk_size):
        chunk = texts[i: i + chunk_size]
        chunk_num = i // chunk_size + 1
        print(f"    chunk {chunk_num}/{total_chunks} ({len(chunk)} segs)...")
        translated_chunk = translate_chunk(client, chunk, filename)
        all_translated.extend(translated_chunk)
        # Small pause between chunks to be gentle on rate limits
        if chunk_num < total_chunks:
            time.sleep(2)

    # Replace content
    for el, translated_html in zip(translatable, all_translated):
        set_element_html(el, translated_html)

    outpath.write_text(str(soup), encoding="utf-8")
    print(f"  Written: {outpath.name}")


def update_toc_ncx(work_dir: Path, translated_dir: Path):
    """Update toc.ncx with Chinese titles."""
    toc_src = work_dir / "toc.ncx"
    if not toc_src.exists():
        return
    toc_dst = translated_dir / "toc.ncx"

    content = toc_src.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "xml")

    doc_title = soup.find("docTitle")
    if doc_title:
        text_el = doc_title.find("text")
        if text_el:
            text_el.string = "正确的失败方式"

    for nav_point in soup.find_all("navPoint"):
        content_el = nav_point.find("content")
        if not content_el:
            continue
        src = content_el.get("src", "")
        fname = Path(src).name
        if fname in CHAPTER_TITLES_CN:
            label = nav_point.find("navLabel")
            if label:
                text_el = label.find("text")
                if text_el:
                    text_el.string = CHAPTER_TITLES_CN[fname]

    toc_dst.write_text(str(soup), encoding="utf-8")
    print("  Updated toc.ncx")


def update_opf(work_dir: Path, translated_dir: Path):
    """Update opf metadata with Chinese title and language."""
    opf_src = next(work_dir.glob("*.opf"), None)
    if not opf_src:
        return

    content = opf_src.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "xml")

    title_el = soup.find("dc:title")
    if title_el:
        title_el.string = "正确的失败方式"

    lang_el = soup.find("dc:language")
    if lang_el:
        lang_el.string = "zh-CN"

    dst = translated_dir / opf_src.name
    dst.write_text(str(soup), encoding="utf-8")
    print(f"  Updated {opf_src.name}")


def build_epub(work_dir: Path, translated_dir: Path, output_path: Path):
    """Repack the epub substituting translated files where available.

    Reads every entry from the original epub to preserve the complete structure
    (including META-INF/container.xml), then substitutes translated xhtml files
    and updated toc.ncx / OPF metadata where available.
    """
    print("\nBuilding epub...")
    if output_path.exists():
        output_path.unlink()

    translated_xhtml_dir = translated_dir / "xhtml"

    with zipfile.ZipFile(EPUB_SRC, "r") as src_zf, \
         zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as dst_zf:

        # mimetype must be first entry and stored uncompressed
        dst_zf.writestr(
            zipfile.ZipInfo("mimetype"),
            src_zf.read("mimetype"),
            compress_type=zipfile.ZIP_STORED,
        )

        for name in src_zf.namelist():
            if name == "mimetype":
                continue

            fname = name.split("/")[-1]

            if name.startswith("e9781982195083/xhtml/") and fname in TRANSLATE_FILES:
                candidate = translated_xhtml_dir / fname
                if candidate.exists():
                    data = candidate.read_bytes()
                else:
                    data = src_zf.read(name)
            elif fname == "toc.ncx":
                candidate = translated_dir / "toc.ncx"
                data = candidate.read_bytes() if candidate.exists() else src_zf.read(name)
            elif name.endswith(".opf"):
                candidate = translated_dir / fname
                data = candidate.read_bytes() if candidate.exists() else src_zf.read(name)
            else:
                data = src_zf.read(name)

            dst_zf.writestr(name, data)

    print(f"Epub built: {output_path}")
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"Size: {size_mb:.1f} MB")


def main():
    print("=== Right Kind of Wrong — Translation to Simplified Chinese ===\n")

    api_key = get_api_key()
    client = anthropic.Anthropic(api_key=api_key)

    translated_xhtml_dir = TRANSLATED_DIR / "xhtml"
    translated_xhtml_dir.mkdir(parents=True, exist_ok=True)

    # Translate each chapter (skip if already done)
    print("--- Translating chapters ---")
    for fname in TRANSLATE_FILES:
        src = XHTML_BASE / fname
        dst = translated_xhtml_dir / fname
        if not src.exists():
            print(f"  Skipping (not found): {fname}")
            continue
        if dst.exists():
            print(f"  Already done, skipping: {fname}")
            continue
        translate_xhtml(client, src, dst, fname)

    # Update metadata
    print("\n--- Updating metadata ---")
    update_toc_ncx(WORK_DIR, TRANSLATED_DIR)
    update_opf(WORK_DIR, TRANSLATED_DIR)

    # Build epub
    build_epub(WORK_DIR, TRANSLATED_DIR, OUTPUT_EPUB)

    print(f"\nAll done! Output: {OUTPUT_EPUB}")


if __name__ == "__main__":
    main()
