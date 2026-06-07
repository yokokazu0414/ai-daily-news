#!/usr/bin/env python3
"""
AI Daily News - Morning Delivery
PC起動時に自動実行: git pull → Notion保存 → メール送信

認証情報は同フォルダの .env（gitignore済み）から読み込む。
.env のキー: GITHUB_TOKEN / NOTION_TOKEN / NOTION_PARENT / NOTION_DB /
            GMAIL_USER / GMAIL_PASSWORD / EMAIL_TO
"""

import os
import re
import csv
import subprocess
import json
import smtplib
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

# スクリプト自身の置き場所を基準にする（ローカルMac・GitHub Actions 両対応）
REPO_DIR = Path(__file__).resolve().parent


def load_env():
    """同フォルダの .env を読み環境変数へ。直書きを避け秘密情報を分離する。"""
    env_path = REPO_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


load_env()

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GIT_REMOTE      = f"https://{GITHUB_TOKEN}@github.com/yokokazu0414/ai-daily-news.git"
NOTION_TOKEN    = os.getenv("NOTION_TOKEN", "")
NOTION_PARENT   = os.getenv("NOTION_PARENT", "")
NOTION_DB       = os.getenv("NOTION_DB", "")
GMAIL_USER      = os.getenv("GMAIL_USER", "")
GMAIL_PASSWORD  = os.getenv("GMAIL_PASSWORD", "")
EMAIL_TO        = os.getenv("EMAIL_TO", "")


def git_pull():
    subprocess.run(
        ["git", "remote", "set-url", "origin", GIT_REMOTE],
        cwd=REPO_DIR, capture_output=True
    )
    r = subprocess.run(["git", "pull"], cwd=REPO_DIR, capture_output=True, text=True)
    msg = r.stdout.strip() or r.stderr.strip()
    print(f"  git pull: {msg}")


def get_today_md():
    today = datetime.now().strftime("%Y-%m-%d")
    path = REPO_DIR / f"{today}_ai-news.md"
    if path.exists():
        return today, path.read_text(encoding="utf-8")
    return today, None


def load_today_links(today):
    """index.csv の当日分から {タイトル: リンク} を返す（公開日取得用）。"""
    path = REPO_DIR / "index.csv"
    out = {}
    if not path.exists():
        return out
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("日付") == today:
                    t = (row.get("タイトル") or "").strip()
                    link = (row.get("リンク") or "").strip()
                    if t and link.startswith("http"):
                        out[t] = link
    except Exception as e:
        print(f"  公開日: index.csv 読込エラー {e}")
    return out


def fetch_pubdate(url):
    """記事ページから公開日(YYYY-MM-DD)を抽出。取れなければ空文字。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read(300000).decode("utf-8", "ignore")
    except Exception:
        return ""
    patterns = [
        r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})',
        r'property=["\']article:published_time["\']\s+content=["\'](\d{4}-\d{2}-\d{2})',
        r'content=["\'](\d{4}-\d{2}-\d{2})[^"\']*["\']\s+property=["\']article:published_time',
        r'itemprop=["\']datePublished["\']\s+content=["\'](\d{4}-\d{2}-\d{2})',
        r'<time[^>]+datetime=["\'](\d{4}-\d{2}-\d{2})',
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return m.group(1)
    return ""


def resolve_pubdates(today):
    """当日記事のリンク先から公開日を取得。{タイトル: 公開日}。"""
    links = load_today_links(today)
    out = {}
    for title, link in links.items():
        d = fetch_pubdate(link)
        if d:
            out[title] = d
    print(f"  公開日: {len(out)}/{len(links)} 件取得")
    return out


def _match_pubdate(card_title, pubdates):
    """md のカードタイトルと csv タイトルを照合して公開日を返す。"""
    if not pubdates:
        return ""
    if card_title in pubdates:
        return pubdates[card_title]
    # 部分一致フォールバック（記号差・末尾差を吸収）
    for t, d in pubdates.items():
        if card_title and (card_title in t or t in card_title):
            return d
    return ""


def parse_inline(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color:#0066cc;text-decoration:none">\1</a>', text)
    return text


def md_to_html(content, today, pubdates=None):
    # カバーストーリーを抽出
    cover_title = ''
    cover_body = ''
    in_cover = False
    cover_lines = []

    # Top5カードを抽出
    cards = []
    current = None

    for line in content.split('\n'):
        s = line.strip()
        if not s:
            continue

        if 'カバーストーリー' in s and s.startswith('## '):
            in_cover = True
            continue
        if in_cover and s.startswith('## '):
            in_cover = False
        if in_cover:
            cover_lines.append(s)
            continue

        if s.startswith('### '):
            if current:
                cards.append(current)
            current = {'title': s[4:], 'player': '', 'source': '', 'summary': '', 'impact': ''}
        elif current:
            if '**Player**:' in s:
                current['player'] = re.sub(r'.*\*\*Player\*\*:\s*', '', s)
            elif '**出典**:' in s:
                current['source'] = re.sub(r'.*\*\*出典\*\*:\s*', '', s)
            elif '**要約**:' in s:
                current['summary'] = re.sub(r'.*\*\*要約\*\*:\s*', '', s)
            elif 'ビジネスインパクト' in s:
                current['impact'] = re.sub(r'.*\*\*[^*]+\*\*:\s*', '', s)

    if current:
        cards.append(current)

    # カバーストーリーHTMLを生成
    for line in cover_lines:
        if line.startswith('**') and line.endswith('**') and not cover_title:
            cover_title = line.strip('*')
        elif line and not line.startswith('*'):
            cover_body += line + ' '

    cover_html = ''
    if cover_title or cover_body:
        cover_html = f"""
    <div style="background-color:#f5f3ff;border-left:4px solid #4f46e5;padding:20px 24px;margin:0">
      <p style="margin:0 0 8px;font-size:10px;color:#4f46e5;text-transform:uppercase;letter-spacing:2px;font-weight:700">🗞️ Cover Story</p>
      <h2 style="margin:0 0 12px;font-size:16px;font-weight:700;line-height:1.5;color:#1e1b4b">{cover_title}</h2>
      <p style="margin:0;font-size:13px;color:#374151;line-height:1.8">{cover_body.strip()}</p>
    </div>"""

    # Top5カードHTMLを生成
    cards_html = ''
    for card in cards:
        source_html = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            r'<a href="\2" style="color:#0066cc;text-decoration:none">\1</a>',
            card['source']
        )
        pubdate = _match_pubdate(card['title'], pubdates)
        pubdate_html = f' &nbsp;｜&nbsp; 📅 {pubdate}' if pubdate else ''
        cards_html += f"""
      <div style="border:1px solid #e8eaed;border-radius:10px;padding:18px;margin-bottom:16px">
        <h3 style="margin:0 0 10px;font-size:15px;color:#1a1a2e;line-height:1.5">{card['title']}</h3>
        <p style="margin:0 0 10px;font-size:12px;color:#888">🏷️ {card['player']} &nbsp;｜&nbsp; 📰 {source_html}{pubdate_html}</p>
        <p style="margin:0 0 12px;font-size:14px;color:#333;line-height:1.7">{card['summary']}</p>
        <div style="background:#f0f7ff;border-left:3px solid #0066cc;padding:10px 14px;border-radius:0 6px 6px 0">
          <p style="margin:0;font-size:13px;color:#0055aa;line-height:1.5">💼 {card['impact']}</p>
        </div>
      </div>"""

    return f"""<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;margin:0;padding:24px">
  <div style="max-width:600px;margin:auto;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.12)">
    <div style="background-color:#ffffff;border-top:4px solid #6366f1;border-bottom:1px solid #e5e7eb;padding:28px 24px;text-align:center">
      <p style="margin:0 0 6px;font-size:11px;color:#6366f1;text-transform:uppercase;letter-spacing:2px">Daily Briefing</p>
      <h1 style="margin:0 0 6px;font-size:22px;font-weight:700;color:#1e1b4b">📰 AI Daily News</h1>
      <p style="margin:0;font-size:13px;color:#64748b">{today}</p>
    </div>
    {cover_html}
    <div style="background:white;padding:20px 20px 8px">
      <p style="margin:0 0 16px;font-size:13px;color:#666;font-weight:600">🏆 今日の Top 5</p>
      {cards_html}
    </div>
    <div style="background:#f8f9fa;padding:14px;text-align:center;border-top:1px solid #eee">
      <p style="margin:0;font-size:12px;color:#aaa">🕕 Generated: {today} 06:00 JST &nbsp;｜&nbsp; AI Daily News Bot</p>
    </div>
  </div>
</body></html>"""


def md_to_notion_blocks(content):
    blocks = []
    for line in content.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": s[4:]}}]}})
        elif s.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": s[3:]}}]}})
        elif s.startswith("# "):
            pass
        elif s.startswith("- "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": re.sub(r'\*\*(.+?)\*\*', r'\1', s[2:])}}]}})
        elif s == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        else:
            blocks.append({"object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": s.strip('*')}}]}})
    return blocks[:100]


def post_to_notion(today, content):
    payload = {
        "parent": {"page_id": NOTION_PARENT},
        "properties": {
            "title": {"title": [{"text": {"content": f"📰 AI Daily News - {today}"}}]}
        },
        "children": md_to_notion_blocks(content)
    }
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"  Notion: ✅ {result.get('url', '作成完了')}")
    except urllib.error.HTTPError as e:
        print(f"  Notion: ❌ {e.code} - {e.read().decode()}")
    except Exception as e:
        print(f"  Notion: ❌ {e}")


def insert_to_notion_db(today, pubdates=None):
    csv_path = REPO_DIR / "index.csv"
    if not csv_path.exists():
        print("  Notion DB: ⚠️ index.csv が見つかりません")
        return
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["日付"] == today:
                rows.append(row)
    if not rows:
        print(f"  Notion DB: ⚠️ {today} のデータなし")
        return
    inserted = 0
    for row in rows:
        players = [{"name": p.strip()} for p in re.split(r'[/・]', row["プレーヤー"]) if p.strip()]
        # 公開日: 記事から取得できればそれを、無ければ配信日にフォールバック
        kokai_date = _match_pubdate(row.get("タイトル", ""), pubdates) or row["日付"].split(" ")[0]
        payload = {
            "parent": {"database_id": NOTION_DB},
            "properties": {
                "タイトル": {"title": [{"text": {"content": row["タイトル"]}}]},
                "日付": {"date": {"start": row["日付"]}},
                "公開日": {"date": {"start": kokai_date}},
                "プレーヤー": {"multi_select": players},
                "分類": {"select": {"name": row["分類"]}},
                "出典": {"rich_text": [{"text": {"content": row["出典"]}}]},
                "要約": {"rich_text": [{"text": {"content": row["要約"][:2000]}}]},
                "本文": {"rich_text": [{"text": {"content": row["本文"][:2000]}}]},
                "リンク": {"url": row["リンク"]}
            }
        }
        req = urllib.request.Request(
            "https://api.notion.com/v1/pages",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                json.loads(resp.read())
                inserted += 1
        except urllib.error.HTTPError as e:
            print(f"  Notion DB: ❌ {e.code} - {e.read().decode()}")
        except Exception as e:
            print(f"  Notion DB: ❌ {e}")
    print(f"  Notion DB: ✅ {inserted}件追加")


def send_email(today, content, pubdates=None):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📰 AI Daily News | {today} Top 5"
    msg["From"] = GMAIL_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(content, "plain", "utf-8"))
    msg.attach(MIMEText(md_to_html(content, today, pubdates), "html", "utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.send_message(msg)
            print(f"  Email: ✅ 送信完了")
    except Exception as e:
        print(f"  Email: ❌ {e}")


def main():
    print(f"=== AI Daily News [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===")

    print("\n[1/5] git pull...")
    if os.getenv("GITHUB_ACTIONS"):
        print("  git pull: skip (GitHub Actions — checkout済み)")
    else:
        git_pull()

    print("\n[2/5] 今日のファイル確認...")
    today, content = get_today_md()
    if not content:
        print(f"  ⚠️  {today}_ai-news.md が見つかりません（CCR未実行または6時前）")
        return
    print(f"  ✅ {today}_ai-news.md 取得")

    print("\n[3/5] 記事の公開日を取得...")
    pubdates = resolve_pubdates(today)

    print("\n[4/5] Notionに保存...")
    post_to_notion(today, content)
    insert_to_notion_db(today, pubdates)

    print("\n[5/5] メール送信...")
    send_email(today, content, pubdates)

    print("\n=== 完了 ===")


if __name__ == "__main__":
    main()
