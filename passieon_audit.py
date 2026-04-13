import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
import csv
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ============================================================
# CONFIGURATION
# ============================================================

WORKERS = 20
REQUEST_TIMEOUT = 10

TITLE_MIN = 30
TITLE_MAX = 60
META_MIN = 70
META_MAX = 160
H1_MAX = 70
THIN_CONTENT_THRESHOLD = 300
SLOW_PAGE_THRESHOLD = 2.0
MAX_URL_LENGTH = 115
MAX_LINKS_PER_PAGE = 100
MAX_HTML_SIZE_KB = 100
MAX_CRAWL_DEPTH = 3

# ============================================================
# SHEET NAME MAPPING (Excel max 31 chars)
# ============================================================

SHEET_NAMES = {
    # Response Codes
    "4xx Client Error": "4xx Errors",
    "5xx Server Error": "5xx Errors",
    "3xx Redirect": "Redirects",
    "Connection Error": "Connection Errors",
    # Security
    "HTTP URL (Not Secure)": "HTTP URLs",
    "Mixed Content Links": "Mixed Content",
    # URL
    "URL Contains Uppercase": "Uppercase URLs",
    "URL Contains Underscores": "Underscore URLs",
    "URL Over 115 Characters": "Long URLs",
    "URL Contains Parameters": "Parameterized URLs",
    # Titles
    "Missing Title Tag": "Missing Titles",
    "Title Too Short": "Titles Too Short",
    "Title Too Long": "Titles Too Long",
    "Duplicate Title Tag": "Duplicate Titles",
    "Title Same As H1": "Title Same As H1",
    # Meta Description
    "Missing Meta Description": "Missing Meta Desc",
    "Meta Description Too Short": "Meta Desc Too Short",
    "Meta Description Too Long": "Meta Desc Too Long",
    "Duplicate Meta Description": "Duplicate Meta Desc",
    # H1
    "Missing H1 Tag": "Missing H1",
    "Multiple H1 Tags": "Multiple H1s",
    "H1 Too Long": "H1 Too Long",
    "Duplicate H1 Tag": "Duplicate H1s",
    # H2
    "No H2 Subheadings": "No H2 Subheadings",
    # Content
    "Thin Content": "Thin Content",
    "Large HTML Size": "Large Pages",
    # Images
    "Images Missing Alt Text": "Images Missing Alt",
    "Images With Long Alt Text": "Long Alt Text",
    # Canonicals
    "Missing Canonical Tag": "Missing Canonical",
    "Canonical Points Elsewhere": "Canonical Mismatch",
    # Links
    "No Internal Links On Page": "No Internal Links",
    "Links With No Anchor Text": "Empty Anchor Links",
    "Excessive Links On Page": "Excessive Links",
    "Broken Internal Links": "Broken Internal Links",
    "Orphan Page": "Orphan Pages",
    # Mobile / Accessibility
    "Missing HTML Lang Attribute": "Missing Lang Attr",
    # Social
    "Missing Open Graph Tags": "Missing OG Tags",
    # Structured Data
    "Missing Structured Data": "Missing Schema",
    # Architecture
    "Deep Page (Crawl Depth)": "Deep Pages",
    # Performance
    "Slow Page Response": "Slow Pages",
    # Site-Level
    "Missing robots.txt": "Missing robots.txt",
    "Missing sitemap.xml": "Missing sitemap.xml",
}

ISSUE_COLUMNS = {
    "4xx Errors":            ["Address", "Status Code", "Title 1", "Crawl Depth"],
    "5xx Errors":            ["Address", "Status Code", "Title 1"],
    "Redirects":             ["Address", "Status Code", "Title 1"],
    "Connection Errors":     ["Address", "Status Code"],
    "HTTP URLs":             ["Address", "Status Code", "Title 1"],
    "Mixed Content":         ["Address", "Status Code", "Title 1"],
    "Uppercase URLs":        ["Address", "Status Code"],
    "Underscore URLs":       ["Address", "Status Code"],
    "Long URLs":             ["Address", "Status Code"],
    "Parameterized URLs":    ["Address", "Status Code", "Indexability"],
    "Missing Titles":        ["Address", "Status Code", "Title 1", "H1-1", "Word Count"],
    "Titles Too Short":      ["Address", "Status Code", "Title 1", "Title 1 Length"],
    "Titles Too Long":       ["Address", "Status Code", "Title 1", "Title 1 Length"],
    "Duplicate Titles":      ["Address", "Status Code", "Title 1"],
    "Title Same As H1":      ["Address", "Status Code", "Title 1", "H1-1"],
    "Missing Meta Desc":     ["Address", "Status Code", "Meta Description 1", "Title 1"],
    "Meta Desc Too Short":   ["Address", "Status Code", "Meta Description 1", "Meta Description 1 Length"],
    "Meta Desc Too Long":    ["Address", "Status Code", "Meta Description 1", "Meta Description 1 Length"],
    "Duplicate Meta Desc":   ["Address", "Status Code", "Meta Description 1"],
    "Missing H1":            ["Address", "Status Code", "H1-1", "Title 1"],
    "Multiple H1s":          ["Address", "Status Code", "H1-1", "H1 Count"],
    "H1 Too Long":           ["Address", "Status Code", "H1-1", "H1-1 Length"],
    "Duplicate H1s":         ["Address", "Status Code", "H1-1"],
    "No H2 Subheadings":     ["Address", "Status Code", "H2 Count", "Word Count"],
    "Thin Content":          ["Address", "Status Code", "Word Count", "Title 1", "Indexability"],
    "Large Pages":           ["Address", "Status Code", "HTML Size (KB)", "Word Count"],
    "Images Missing Alt":    ["Address", "Status Code", "Images Total", "Images Missing Alt"],
    "Long Alt Text":         ["Address", "Status Code", "Images Total"],
    "Missing Canonical":     ["Address", "Status Code", "Canonical URL", "Indexability"],
    "Canonical Mismatch":    ["Address", "Status Code", "Canonical URL"],
    "No Internal Links":     ["Address", "Status Code", "Internal Links", "External Links"],
    "Empty Anchor Links":    ["Address", "Status Code", "Empty Anchor Links"],
    "Excessive Links":       ["Address", "Status Code", "Internal Links", "External Links", "Total Links"],
    "Broken Internal Links": ["Address", "Status Code"],
    "Orphan Pages":          ["Address", "Status Code", "Word Count", "Indexability"],
    "Missing Lang Attr":     ["Address", "Status Code"],
    "Missing OG Tags":       ["Address", "Status Code", "Title 1", "Indexability"],
    "Missing Schema":        ["Address", "Status Code", "Title 1", "Indexability"],
    "Deep Pages":            ["Address", "Status Code", "Crawl Depth", "Title 1"],
    "Slow Pages":            ["Address", "Status Code", "Response Time (s)", "Word Count"],
    "Missing robots.txt":    ["Address"],
    "Missing sitemap.xml":   ["Address"],
}

DEFAULT_COLUMNS = ["Address", "Status Code", "Title 1", "Word Count", "Indexability"]

# URLs matching these patterns are system/utility pages, not real content
SYSTEM_URL_PATTERNS = [
    "/cdn-cgi/", "/wp-admin/", "/wp-includes/", "/wp-json/",
    "/feed/", "/xmlrpc", "/wp-login", "/cart/", "/checkout/",
    "/my-account/", "/?s=", "/search?", "/tag/", "/author/",
]

def is_page_url(url):
    for pattern in SYSTEM_URL_PATTERNS:
        if pattern in url:
            return False
    return True

def normalize_domain(netloc):
    """Strip www. so www.example.com and example.com match as same site"""
    if netloc.startswith("www."):
        return netloc[4:]
    return netloc

def normalize_url_for_comparison(url):
    """Normalize URL for canonical/duplicate comparison"""
    parsed = urlparse(url)
    netloc = normalize_domain(parsed.netloc)
    path = parsed.path.rstrip("/") + "/"
    return f"{parsed.scheme}://{netloc}{path}"

# ============================================================
# PAGE PROCESSOR
# ============================================================

def process_page(url, domain, depth):
    page_data = {
        "Address": url, "Status Code": "Error",
        "Title 1": "", "Title 1 Length": 0,
        "Meta Description 1": "", "Meta Description 1 Length": 0,
        "H1-1": "", "H1-1 Length": 0, "H1 Count": 0,
        "H2 Count": 0, "Word Count": 0,
        "Indexability": "Non-Indexable", "Canonical URL": "",
        "Internal Links": 0, "External Links": 0, "Total Links": 0,
        "Images Total": 0, "Images Missing Alt": 0,
        "Response Time (s)": 0, "Crawl Depth": depth,
        "HTML Size (KB)": 0,
        "HTML Lang": "", "Has OG Tags": False,
        "Has Structured Data": False, "Empty Anchor Links": 0,
    }

    try:
        response = requests.get(
            url, timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},
            allow_redirects=True,
        )
    except requests.exceptions.RequestException as e:
        return {
            "data": page_data,
            "new_urls": [],
            "issues": [{"url": url, "issue": "Connection Error", "priority": "High", "details": str(e)[:200]}],
            "internal_link_targets": [],
        }

    status_code = response.status_code
    response_time = round(response.elapsed.total_seconds(), 2)
    content_type = response.headers.get("Content-Type", "")
    html_size_kb = round(len(response.content) / 1024, 1)

    # Detect redirects (allow_redirects=True means status_code is the FINAL code)
    was_redirected = len(response.history) > 0
    redirect_status = response.history[0].status_code if was_redirected else None
    final_url = response.url if was_redirected else url

    # Use original redirect status for reporting, final status for on-page analysis
    reported_status = redirect_status if was_redirected else status_code

    page_data["Status Code"] = reported_status
    page_data["Response Time (s)"] = response_time
    page_data["HTML Size (KB)"] = html_size_kb

    if "text/html" not in content_type:
        return {"data": page_data, "new_urls": [], "issues": [], "internal_link_targets": []}

    soup = BeautifulSoup(response.text, "html.parser")
    issues = []

    # ---- EXTRACT DATA ----

    # Title
    title_tag = soup.find("title")
    title = title_tag.get_text().strip() if title_tag else ""
    title_len = len(title)

    # Meta Description
    meta_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta_tag.get("content", "").strip() if meta_tag else ""
    meta_len = len(meta_desc)

    # H1
    h1_tags = soup.find_all("h1")
    h1_count = len(h1_tags)
    h1 = h1_tags[0].get_text().strip() if h1_tags else ""

    # H2
    h2_count = len(soup.find_all("h2"))

    # Canonical (resolve relative URLs to absolute)
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical_raw = canonical_tag.get("href", "").strip() if canonical_tag else ""
    canonical = urljoin(url, canonical_raw) if canonical_raw else ""

    # Meta Robots
    robots_tag = soup.find("meta", attrs={"name": "robots"})
    robots_content = robots_tag.get("content", "").lower() if robots_tag else ""
    indexability = "Non-Indexable" if "noindex" in robots_content else "Indexable"

    # HTML lang attribute
    html_tag = soup.find("html")
    html_lang = html_tag.get("lang", "").strip() if html_tag else ""

    # Open Graph
    og_title = soup.find("meta", attrs={"property": "og:title"})
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    has_og = og_title is not None and og_desc is not None

    # Structured Data (JSON-LD)
    json_ld_tags = soup.find_all("script", attrs={"type": "application/ld+json"})
    has_structured_data = len(json_ld_tags) > 0

    # Links
    internal_links = 0
    external_links = 0
    empty_anchor_count = 0
    new_urls = []
    internal_link_targets = []
    http_links_on_https = 0
    page_is_https = url.startswith("https://")

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        full_url = urljoin(url, href)
        parsed_link = urlparse(full_url)

        if parsed_link.scheme not in ("http", "https"):
            continue

        anchor_text = a_tag.get_text().strip()
        if not anchor_text:
            empty_anchor_count += 1

        if parsed_link.netloc == domain or normalize_domain(parsed_link.netloc) == normalize_domain(domain):
            internal_links += 1
            clean_url = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}"
            if not clean_url.endswith("/"):
                clean_url += "/"
            # Only add non-parameterized URLs to crawl queue (avoid infinite crawl on e-commerce sites)
            if not parsed_link.query:
                new_urls.append((clean_url, depth + 1))
            internal_link_targets.append({"url": clean_url, "anchor": anchor_text or "(no anchor text)"})

            if page_is_https and parsed_link.scheme == "http":
                http_links_on_https += 1
        else:
            external_links += 1

    total_links = internal_links + external_links

    # Images - collect per-image details for page-level reporting
    images = soup.find_all("img")
    images_total = len(images)
    imgs_missing_alt = []
    imgs_long_alt = []
    for img in images:
        img_src = img.get("src", "")
        if img_src:
            img_src = urljoin(url, img_src)
        else:
            img_src = "(no src)"
        alt_text = img.get("alt", "")
        if not alt_text.strip():
            imgs_missing_alt.append(img_src)
        elif len(alt_text) > 125:
            imgs_long_alt.append({"src": img_src, "alt_len": len(alt_text)})
    missing_alt = len(imgs_missing_alt)

    # Word Count
    soup_copy = BeautifulSoup(response.text, "html.parser")
    for tag in soup_copy(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    visible_text = soup_copy.get_text(separator=" ", strip=True)
    word_count = len(visible_text.split())

    # Update page data
    page_data.update({
        "Title 1": title, "Title 1 Length": title_len,
        "Meta Description 1": meta_desc, "Meta Description 1 Length": meta_len,
        "H1-1": h1, "H1-1 Length": len(h1), "H1 Count": h1_count,
        "H2 Count": h2_count, "Word Count": word_count,
        "Indexability": indexability, "Canonical URL": canonical,
        "Internal Links": internal_links, "External Links": external_links,
        "Total Links": total_links,
        "Images Total": images_total, "Images Missing Alt": missing_alt,
        "HTML Size (KB)": html_size_kb,
        "HTML Lang": html_lang, "Has OG Tags": has_og,
        "Has Structured Data": has_structured_data,
        "Empty Anchor Links": empty_anchor_count,
    })

    # ---- DETECT ISSUES ----

    # === ALWAYS CHECK (regardless of status code) ===

    # Response Codes (use reported_status which is the original status, not the final after redirects)
    if was_redirected:
        issues.append({"url": url, "issue": "3xx Redirect", "priority": "Medium",
            "details": f"HTTP {redirect_status} -> redirects to {final_url}"})
    elif str(status_code).startswith("4"):
        issues.append({"url": url, "issue": "4xx Client Error", "priority": "High", "details": f"HTTP {status_code}"})
    elif str(status_code).startswith("5"):
        issues.append({"url": url, "issue": "5xx Server Error", "priority": "High", "details": f"HTTP {status_code}"})

    # Security
    if not url.startswith("https://"):
        issues.append({"url": url, "issue": "HTTP URL (Not Secure)", "priority": "High", "details": "Page served over HTTP, not HTTPS"})
    if http_links_on_https > 0:
        issues.append({"url": url, "issue": "Mixed Content Links", "priority": "Medium", "details": f"{http_links_on_https} internal links use HTTP on an HTTPS page"})

    # URL Issues (about the URL itself, not page content)
    parsed_url = urlparse(url)
    if parsed_url.path != parsed_url.path.lower():
        issues.append({"url": url, "issue": "URL Contains Uppercase", "priority": "Low", "details": f"Path: {parsed_url.path}"})
    if "_" in parsed_url.path:
        issues.append({"url": url, "issue": "URL Contains Underscores", "priority": "Low", "details": "Use hyphens instead of underscores"})
    if len(url) > MAX_URL_LENGTH:
        issues.append({"url": url, "issue": "URL Over 115 Characters", "priority": "Low", "details": f"URL is {len(url)} characters"})
    if parsed_url.query:
        issues.append({"url": url, "issue": "URL Contains Parameters", "priority": "Low", "details": f"Parameters: {parsed_url.query[:80]}"})

    # Performance (always relevant)
    if response_time > SLOW_PAGE_THRESHOLD and not was_redirected:
        issues.append({"url": url, "issue": "Slow Page Response", "priority": "Medium", "details": f"{response_time}s (threshold {SLOW_PAGE_THRESHOLD}s)"})

    # Architecture (always relevant)
    if depth > MAX_CRAWL_DEPTH:
        issues.append({"url": url, "issue": "Deep Page (Crawl Depth)", "priority": "Medium", "details": f"Depth {depth} (max recommended {MAX_CRAWL_DEPTH} clicks from homepage)"})

    # === ON-PAGE CHECKS ===
    # Only for pages that: returned 200 directly (not via redirect), are real content URLs
    # Redirected pages are skipped because their content belongs to the final URL

    if str(status_code) == "200" and not was_redirected and is_page_url(url):

        # Title Issues
        if not title:
            issues.append({"url": url, "issue": "Missing Title Tag", "priority": "High", "details": "No title tag found"})
        elif title_len < TITLE_MIN:
            issues.append({"url": url, "issue": "Title Too Short", "priority": "Medium", "details": f'"{title}" ({title_len} chars, min {TITLE_MIN})'})
        elif title_len > TITLE_MAX:
            issues.append({"url": url, "issue": "Title Too Long", "priority": "Medium", "details": f'"{title}" ({title_len} chars, max {TITLE_MAX})'})

        if title and h1 and title.lower() == h1.lower():
            issues.append({"url": url, "issue": "Title Same As H1", "priority": "Low", "details": f'Both are: "{title}"'})

        # Meta Description Issues
        if not meta_desc:
            issues.append({"url": url, "issue": "Missing Meta Description", "priority": "Medium", "details": "No meta description found"})
        elif meta_len < META_MIN:
            issues.append({"url": url, "issue": "Meta Description Too Short", "priority": "Medium", "details": f'"{meta_desc}" ({meta_len} chars, min {META_MIN})'})
        elif meta_len > META_MAX:
            issues.append({"url": url, "issue": "Meta Description Too Long", "priority": "Low", "details": f'"{meta_desc[:80]}..." ({meta_len} chars, max {META_MAX})'})

        # H1 Issues
        if h1_count == 0:
            issues.append({"url": url, "issue": "Missing H1 Tag", "priority": "High", "details": "No H1 tag found"})
        elif h1_count > 1:
            issues.append({"url": url, "issue": "Multiple H1 Tags", "priority": "Medium", "details": f"Found {h1_count} H1 tags (should be 1)"})

        if h1 and len(h1) > H1_MAX:
            issues.append({"url": url, "issue": "H1 Too Long", "priority": "Low", "details": f'"{h1[:60]}..." ({len(h1)} chars, max {H1_MAX})'})

        # H2 Issues
        if h2_count == 0 and word_count > THIN_CONTENT_THRESHOLD:
            issues.append({"url": url, "issue": "No H2 Subheadings", "priority": "Low", "details": f"{word_count} words but no H2 tags"})

        # Content Issues
        if word_count < THIN_CONTENT_THRESHOLD and indexability == "Indexable":
            issues.append({"url": url, "issue": "Thin Content", "priority": "High", "details": f"Only {word_count} words (min {THIN_CONTENT_THRESHOLD})"})

        if html_size_kb > MAX_HTML_SIZE_KB:
            issues.append({"url": url, "issue": "Large HTML Size", "priority": "Medium", "details": f"{html_size_kb} KB (max {MAX_HTML_SIZE_KB} KB)"})

        # Image Issues (reported at page level with affected image URLs)
        if missing_alt > 0:
            img_list = imgs_missing_alt[:5]
            img_display = "\n".join(img_list)
            if missing_alt > 5:
                img_display += f"\n...and {missing_alt - 5} more"
            issues.append({"url": url, "issue": "Images Missing Alt Text", "priority": "Medium",
                "details": f"{missing_alt} of {images_total} images have no alt text",
                "extra": {"Affected Image URLs": img_display}})

        if len(imgs_long_alt) > 0:
            img_list = [f"{i['src']} ({i['alt_len']} chars)" for i in imgs_long_alt[:5]]
            img_display = "\n".join(img_list)
            issues.append({"url": url, "issue": "Images With Long Alt Text", "priority": "Low",
                "details": f"{len(imgs_long_alt)} images have alt text over 125 characters (possible keyword stuffing)",
                "extra": {"Affected Image URLs": img_display}})

        # Canonical Issues
        if not canonical and indexability == "Indexable":
            issues.append({"url": url, "issue": "Missing Canonical Tag", "priority": "Low", "details": "No canonical URL specified"})
        elif canonical and normalize_url_for_comparison(canonical) != normalize_url_for_comparison(url):
            issues.append({"url": url, "issue": "Canonical Points Elsewhere", "priority": "Medium", "details": f"Canonical: {canonical}"})

        # Link Issues
        if internal_links == 0 and indexability == "Indexable":
            issues.append({"url": url, "issue": "No Internal Links On Page", "priority": "Medium", "details": "Zero outbound internal links"})

        if empty_anchor_count > 0:
            issues.append({"url": url, "issue": "Links With No Anchor Text", "priority": "Medium", "details": f"{empty_anchor_count} links have empty anchor text"})

        if total_links > MAX_LINKS_PER_PAGE:
            issues.append({"url": url, "issue": "Excessive Links On Page", "priority": "Low", "details": f"{total_links} total links (max {MAX_LINKS_PER_PAGE})"})

        # Accessibility
        if not html_lang:
            issues.append({"url": url, "issue": "Missing HTML Lang Attribute", "priority": "Low", "details": "No lang attribute on <html> tag"})

        # Social
        if not has_og and indexability == "Indexable":
            issues.append({"url": url, "issue": "Missing Open Graph Tags", "priority": "Low", "details": "Missing og:title or og:description meta tags"})

        # Structured Data
        if not has_structured_data and indexability == "Indexable":
            issues.append({"url": url, "issue": "Missing Structured Data", "priority": "Low", "details": "No JSON-LD structured data found"})

    return {
        "data": page_data,
        "new_urls": new_urls,
        "issues": issues,
        "internal_link_targets": internal_link_targets,
    }


# ============================================================
# MULTI-THREADED CRAWLER
# ============================================================

def crawl_site(start_url, workers=WORKERS, on_progress=None):
    parsed_start = urlparse(start_url)
    domain = parsed_start.netloc

    visited = set()
    visited_lock = threading.Lock()

    to_visit = [(start_url, 0)]
    crawled_count = 0
    all_results = []
    all_issues = []
    all_link_targets = {}  # source_url -> [target_urls]
    inlinked_urls = set()  # all URLs that receive at least one internal link

    print(f"\nCrawling: {domain}")
    print(f"Threads: {workers}")
    print(f"Crawling entire site...\n")

    start_time = time.time()

    while to_visit:
        batch_size = min(workers, len(to_visit))
        batch = []
        while to_visit and len(batch) < batch_size:
            url, depth = to_visit.pop(0)
            with visited_lock:
                if url not in visited:
                    visited.add(url)
                    batch.append((url, depth))

        if not batch:
            break

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_info = {
                executor.submit(process_page, url, domain, depth): (url, depth)
                for url, depth in batch
            }

            for future in as_completed(future_to_info):
                url, depth = future_to_info[future]
                crawled_count += 1

                try:
                    result = future.result()
                    all_results.append(result["data"])
                    all_issues.extend(result["issues"])
                    all_link_targets[url] = result["internal_link_targets"]

                    for link_info in result["internal_link_targets"]:
                        inlinked_urls.add(link_info["url"])

                    for new_url, new_depth in result["new_urls"]:
                        with visited_lock:
                            if new_url not in visited:
                                to_visit.append((new_url, new_depth))

                    status = result["data"]["Status Code"]
                    issue_count = len(result["issues"])
                    issue_label = f" -- {issue_count} issues" if issue_count > 0 else ""
                    msg = f"[{crawled_count}] ({status}) {url}{issue_label}"
                    print(f"  {msg}")
                    if on_progress:
                        on_progress(crawled_count, msg)

                except Exception as e:
                    print(f"  [{crawled_count}] FAILED: {url} - {e}")

    elapsed = round(time.time() - start_time, 1)

    # ---- POST-CRAWL ANALYSIS ----
    print("\nRunning post-crawl analysis...")

    # Build status code lookup
    status_lookup = {page["Address"]: page["Status Code"] for page in all_results}

    # Only include real 200 pages in duplicate checks (excludes 404 error pages and system URLs)
    real_pages = [p for p in all_results if str(p["Status Code"]) == "200" and is_page_url(p["Address"])]

    # 1. Duplicate Titles
    titles_seen = {}
    for page in real_pages:
        t = page["Title 1"]
        if t:
            titles_seen.setdefault(t, []).append(page["Address"])
    for title_text, urls in titles_seen.items():
        if len(urls) > 1:
            for u in urls:
                all_issues.append({"url": u, "issue": "Duplicate Title Tag", "priority": "High",
                    "details": f'"{title_text}" -- shared by {len(urls)} pages'})

    # 2. Duplicate Meta Descriptions
    metas_seen = {}
    for page in real_pages:
        m = page["Meta Description 1"]
        if m:
            metas_seen.setdefault(m, []).append(page["Address"])
    for meta_text, urls in metas_seen.items():
        if len(urls) > 1:
            for u in urls:
                all_issues.append({"url": u, "issue": "Duplicate Meta Description", "priority": "Medium",
                    "details": f'"{meta_text[:60]}..." -- shared by {len(urls)} pages'})

    # 3. Duplicate H1 Tags
    h1s_seen = {}
    for page in real_pages:
        h = page["H1-1"]
        if h:
            h1s_seen.setdefault(h, []).append(page["Address"])
    for h1_text, urls in h1s_seen.items():
        if len(urls) > 1:
            for u in urls:
                all_issues.append({"url": u, "issue": "Duplicate H1 Tag", "priority": "Medium",
                    "details": f'"{h1_text}" -- shared by {len(urls)} pages'})

    # 4. Broken Internal Links (deduplicated per source+target, with anchor text)
    error_urls = {url for url, status in status_lookup.items() if str(status).startswith("4") or str(status).startswith("5") or status == "Error"}
    active_urls = {url for url, status in status_lookup.items() if str(status) == "200"}
    broken_seen = set()
    for source_url, link_details in all_link_targets.items():
        for link_info in link_details:
            target_url = link_info["url"]
            anchor = link_info["anchor"]
            if target_url in error_urls:
                dedup_key = f"{source_url} -> {target_url}"
                if dedup_key in broken_seen:
                    continue
                broken_seen.add(dedup_key)

                target_status = status_lookup.get(target_url, "Unknown")
                recommendation = "Remove this link"
                target_path = urlparse(target_url).path.rstrip("/")
                if target_path:
                    path_parts = target_path.split("/")
                    for active in active_urls:
                        active_path = urlparse(active).path.rstrip("/")
                        if len(path_parts) > 1 and path_parts[-2] in active_path and active != target_url:
                            recommendation = f"Consider replacing with: {active}"
                            break
                all_issues.append({"url": source_url, "issue": "Broken Internal Links", "priority": "High",
                    "details": f'Anchor text: "{anchor}" -> links to {target_url} (HTTP {target_status}). {recommendation}',
                    "extra": {"Broken Link URL": target_url, "Broken Link Status": str(target_status), "Anchor Text": anchor}})

    # 5. Orphan Pages (only real content pages, not system URLs)
    for page in real_pages:
        page_url = page["Address"]
        if page_url != start_url and page_url not in inlinked_urls and page["Indexability"] == "Indexable":
            all_issues.append({"url": page_url, "issue": "Orphan Page", "priority": "Medium",
                "details": "No other crawled page links to this URL"})

    # 6. Check robots.txt
    try:
        robots_url = f"https://{domain}/robots.txt"
        r = requests.get(robots_url, timeout=5, headers={"User-Agent": "Passieon-SEO-Crawler/2.0"})
        if r.status_code != 200:
            all_issues.append({"url": robots_url, "issue": "Missing robots.txt", "priority": "Low",
                "details": f"robots.txt returned HTTP {r.status_code}"})
    except Exception:
        all_issues.append({"url": f"https://{domain}/robots.txt", "issue": "Missing robots.txt", "priority": "Low",
            "details": "Could not access robots.txt"})

    # 7. Check sitemap.xml
    try:
        sitemap_url = f"https://{domain}/sitemap.xml"
        r = requests.get(sitemap_url, timeout=5, headers={"User-Agent": "Passieon-SEO-Crawler/2.0"})
        if r.status_code != 200:
            all_issues.append({"url": sitemap_url, "issue": "Missing sitemap.xml", "priority": "Low",
                "details": f"sitemap.xml returned HTTP {r.status_code}"})
    except Exception:
        all_issues.append({"url": f"https://{domain}/sitemap.xml", "issue": "Missing sitemap.xml", "priority": "Low",
            "details": "Could not access sitemap.xml"})

    return all_results, all_issues, elapsed


# ============================================================
# EXCEL REPORT BUILDER
# ============================================================

def build_report(pages, issues, domain, elapsed):
    wb = Workbook()

    header_fill = PatternFill(start_color="1B2A4A", end_color="1B2A4A", fill_type="solid")
    header_font = Font(name="Arial", color="FFFFFF", bold=True, size=11)
    body_font = Font(name="Arial", size=10)
    bold_font = Font(name="Arial", size=10, bold=True)
    title_font = Font(name="Arial", size=18, bold=True, color="1B2A4A")
    subtitle_font = Font(name="Arial", size=11, color="666666")
    high_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    medium_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    low_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    pass_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"), right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"), bottom=Side(style="thin", color="D9D9D9"),
    )
    wrap = Alignment(wrap_text=True, vertical="top")
    center = Alignment(horizontal="center", vertical="top")
    priority_fills = {"High": high_fill, "Medium": medium_fill, "Low": low_fill}

    def style_header_row(ws, headers, row=1):
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=row, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

    def auto_width(ws, col_index, min_w=10, max_w=60):
        col_letter = get_column_letter(col_index)
        max_len = min_w
        for row in ws.iter_rows(min_col=col_index, max_col=col_index):
            for cell in row:
                if cell.value:
                    max_len = max(max_len, min(len(str(cell.value)), max_w))
        ws.column_dimensions[col_letter].width = max_len + 2

    page_lookup = {page["Address"]: page for page in pages}

    # ===================== SUMMARY =====================
    ws = wb.active
    ws.title = "Summary"

    ws.merge_cells("A1:D1")
    ws["A1"].value = f"SEO Audit Report -- {domain}"
    ws["A1"].font = title_font

    ws.merge_cells("A2:D2")
    ws["A2"].value = f"Crawled {len(pages)} pages in {elapsed} seconds | Passieon SEO Auditor v5.0"
    ws["A2"].font = subtitle_font

    pages_with_issues = len(set(i["url"] for i in issues))
    pages_clean = len(pages) - pages_with_issues
    health_score = round((pages_clean / max(len(pages), 1)) * 100)

    ws["A4"].value = "Site Health Score"
    ws["A4"].font = bold_font
    ws["B4"].value = f"{health_score}%"
    ws["B4"].font = Font(name="Arial", size=14, bold=True, color="1B2A4A")

    high_count = sum(1 for i in issues if i["priority"] == "High")
    medium_count = sum(1 for i in issues if i["priority"] == "Medium")
    low_count = sum(1 for i in issues if i["priority"] == "Low")

    style_header_row(ws, ["Metric", "Count"], row=6)
    summary_rows = [
        ("Total Issues", len(issues), None),
        ("High Priority", high_count, high_fill),
        ("Medium Priority", medium_count, medium_fill),
        ("Low Priority", low_count, low_fill),
        ("Clean Pages (No Issues)", pages_clean, pass_fill),
    ]
    for idx, (label, count, fill) in enumerate(summary_rows, 7):
        ws.cell(row=idx, column=1, value=label).font = body_font
        cell_b = ws.cell(row=idx, column=2, value=count)
        cell_b.font = bold_font
        ws.cell(row=idx, column=1).border = thin_border
        cell_b.border = thin_border
        if fill:
            cell_b.fill = fill

    issue_types = {}
    issue_priority_map = {}
    for i in issues:
        issue_types[i["issue"]] = issue_types.get(i["issue"], 0) + 1
        issue_priority_map[i["issue"]] = i["priority"]

    row_start = 14
    style_header_row(ws, ["Issue Type", "Count", "Priority", "Sheet"], row=row_start)
    priority_order = {"High": 0, "Medium": 1, "Low": 2}

    sorted_issue_types = sorted(issue_types.items(), key=lambda x: (priority_order.get(issue_priority_map.get(x[0], "Low"), 3), -x[1]))
    for idx, (issue_type, count) in enumerate(sorted_issue_types, row_start + 1):
        priority = issue_priority_map.get(issue_type, "")
        sheet_name = SHEET_NAMES.get(issue_type, issue_type[:31])
        cell_a = ws.cell(row=idx, column=1, value=issue_type)
        cell_b = ws.cell(row=idx, column=2, value=count)
        cell_c = ws.cell(row=idx, column=3, value=priority)
        cell_d = ws.cell(row=idx, column=4, value=sheet_name)
        cell_a.font = body_font
        cell_b.font = bold_font
        cell_c.font = body_font
        cell_d.font = Font(name="Arial", size=10, color="0563C1", underline="single")
        for c in [cell_a, cell_b, cell_c, cell_d]:
            c.border = thin_border
        if priority in priority_fills:
            cell_c.fill = priority_fills[priority]

    ws.column_dimensions["A"].width = 35
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 25

    # ===================== ALL PAGES =====================
    ws_pages = wb.create_sheet("All Pages")
    page_headers = [
        "URL", "Status", "Title", "Title Len", "Meta Description", "Meta Len",
        "H1", "H1 Count", "H2 Count", "Word Count", "Indexability", "Canonical",
        "Int Links", "Ext Links", "Images", "Missing Alt", "Response (s)",
        "Depth", "HTML KB", "Lang", "OG Tags", "Schema",
    ]
    page_keys = [
        "Address", "Status Code", "Title 1", "Title 1 Length",
        "Meta Description 1", "Meta Description 1 Length",
        "H1-1", "H1 Count", "H2 Count", "Word Count",
        "Indexability", "Canonical URL",
        "Internal Links", "External Links",
        "Images Total", "Images Missing Alt", "Response Time (s)",
        "Crawl Depth", "HTML Size (KB)", "HTML Lang",
        "Has OG Tags", "Has Structured Data",
    ]
    style_header_row(ws_pages, page_headers)
    for row_num, page in enumerate(pages, 2):
        for col, key in enumerate(page_keys, 1):
            val = page.get(key, "")
            if isinstance(val, bool):
                val = "Yes" if val else "No"
            cell = ws_pages.cell(row=row_num, column=col, value=val)
            cell.font = body_font
            cell.border = thin_border
            cell.alignment = wrap
        if str(page["Status Code"]) != "200":
            ws_pages.cell(row=row_num, column=2).fill = high_fill

    col_widths = [50, 7, 35, 7, 45, 7, 25, 7, 7, 8, 10, 35, 7, 7, 7, 7, 8, 6, 7, 6, 7, 7]
    for i, w in enumerate(col_widths):
        if i < len(col_widths):
            ws_pages.column_dimensions[get_column_letter(i + 1)].width = w

    # ===================== ALL ISSUES =====================
    ws_issues = wb.create_sheet("All Issues")
    style_header_row(ws_issues, ["URL", "Issue", "Priority", "Details"])
    sorted_issues = sorted(issues, key=lambda x: (priority_order.get(x["priority"], 3), x["issue"]))
    for row_num, issue in enumerate(sorted_issues, 2):
        for col, key in enumerate(["url", "issue", "priority", "details"], 1):
            cell = ws_issues.cell(row=row_num, column=col, value=issue[key])
            cell.font = bold_font if key == "priority" else body_font
            cell.border = thin_border
            cell.alignment = center if key == "priority" else wrap
        if issue["priority"] in priority_fills:
            ws_issues.cell(row=row_num, column=3).fill = priority_fills[issue["priority"]]
    ws_issues.column_dimensions["A"].width = 55
    ws_issues.column_dimensions["B"].width = 28
    ws_issues.column_dimensions["C"].width = 12
    ws_issues.column_dimensions["D"].width = 65

    # ===================== PER-ISSUE SHEETS =====================
    issues_by_type = {}
    for issue in issues:
        issues_by_type.setdefault(issue["issue"], []).append(issue)

    sorted_types = sorted(issues_by_type.keys(),
        key=lambda t: (priority_order.get(issue_priority_map.get(t, "Low"), 3), -len(issues_by_type[t])))

    for issue_type in sorted_types:
        type_issues = issues_by_type[issue_type]
        sheet_name = SHEET_NAMES.get(issue_type, issue_type[:31])

        if sheet_name in wb.sheetnames:
            sheet_name = sheet_name[:28] + " (2)"

        ws_type = wb.create_sheet(sheet_name)
        page_cols = ISSUE_COLUMNS.get(sheet_name, DEFAULT_COLUMNS)

        # Check if any issues have extra columns
        extra_keys = []
        for ti in type_issues:
            if "extra" in ti:
                for k in ti["extra"]:
                    if k not in extra_keys and k not in page_cols:
                        extra_keys.append(k)

        all_cols = page_cols + extra_keys + ["Details"]
        style_header_row(ws_type, all_cols, row=2)

        priority = issue_priority_map.get(issue_type, "")
        ws_type.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(all_cols))
        title_cell = ws_type.cell(row=1, column=1)
        title_cell.value = f"{issue_type} -- {len(type_issues)} affected -- Priority: {priority}"
        title_cell.font = Font(name="Arial", size=12, bold=True, color="1B2A4A")
        if priority in priority_fills:
            title_cell.fill = priority_fills[priority]

        for row_num, issue in enumerate(type_issues, 3):
            page_data = page_lookup.get(issue["url"], {})
            col = 1
            for key in page_cols:
                val = page_data.get(key, issue["url"] if key == "Address" else "")
                if isinstance(val, bool):
                    val = "Yes" if val else "No"
                cell = ws_type.cell(row=row_num, column=col, value=val)
                cell.font = body_font
                cell.border = thin_border
                cell.alignment = wrap
                col += 1

            for key in extra_keys:
                val = issue.get("extra", {}).get(key, "")
                cell = ws_type.cell(row=row_num, column=col, value=val)
                cell.font = body_font
                cell.border = thin_border
                cell.alignment = wrap
                col += 1

            cell = ws_type.cell(row=row_num, column=col, value=issue["details"])
            cell.font = body_font
            cell.border = thin_border
            cell.alignment = wrap

        for col_idx in range(1, len(all_cols) + 1):
            auto_width(ws_type, col_idx)
        ws_type.column_dimensions["A"].width = 55

        for r in range(3, len(type_issues) + 3):
            ws_type.row_dimensions[r].height = 35

    return wb


# ============================================================
# MAIN (only runs when executed directly, not when imported)
# ============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("  PASSIEON SEO AUDITOR v5.0")
    print("  40+ Technical SEO Checks")
    print("=" * 55)

    url = input("\nEnter the website URL: ").strip()

    if not url.startswith("http"):
        url = "https://" + url
    if not url.endswith("/"):
        url = url + "/"

    domain = urlparse(url).netloc

    pages, issues, elapsed = crawl_site(url, workers=WORKERS)

    if not pages:
        print("\nNo pages were crawled. Check that the URL is correct and the site is accessible.")
        print("Common causes: site is down, URL is wrong, or the site blocks crawlers.")
        exit()

    print("\nBuilding report...")
    wb = build_report(pages, issues, domain, elapsed)

    output_file = f"audit_{domain.replace('.', '_')}.xlsx"
    wb.save(output_file)

    csv_file = "crawl.csv"
    if pages:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=pages[0].keys())
            writer.writeheader()
            writer.writerows(pages)

    high = sum(1 for i in issues if i["priority"] == "High")
    medium = sum(1 for i in issues if i["priority"] == "Medium")
    low = sum(1 for i in issues if i["priority"] == "Low")
    health = round(((len(pages) - len(set(i["url"] for i in issues))) / max(len(pages), 1)) * 100)
    sheet_count = len(set(i["issue"] for i in issues))

    print(f"\n{'=' * 55}")
    print(f"  AUDIT COMPLETE")
    print(f"{'=' * 55}")
    print(f"  Site:           {domain}")
    print(f"  Pages crawled:  {len(pages)}")
    print(f"  Time taken:     {elapsed} seconds")
    print(f"  Health score:   {health}%")
    print(f"  Total issues:   {len(issues)}")
    print(f"    High:         {high}")
    print(f"    Medium:       {medium}")
    print(f"    Low:          {low}")
    print(f"  Issue sheets:   {sheet_count} tabs created")
    print(f"  Report saved:   {output_file}")
    print(f"  Raw CSV saved:  {csv_file}")
    print(f"\n  Open it: start {output_file}")
    print(f"{'=' * 55}")
