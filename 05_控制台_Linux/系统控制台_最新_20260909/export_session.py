#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_session.py — AI 对话原文导出工具（铁律：2026-08-22 起）
用法: python3 export_session.py [session_id]
不指定 session_id 时导出最近活跃会话。
输出: 会话记录/AI对话_<标题>_<YYYYMMDD>.md
图片: 会话中的图片附件提取到 会话记录/images/
"""
import sqlite3, json, os, sys, re
from datetime import datetime

DB = os.path.expanduser("~/.local/share/opencode/opencode.db")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "会话记录")
IMG_DIR = os.path.join(OUT_DIR, "images")


def main():
    db = sqlite3.connect(DB)
    sid = sys.argv[1] if len(sys.argv) > 1 else None

    if not sid:
        row = db.execute("SELECT id, title FROM session ORDER BY time_updated DESC LIMIT 1").fetchone()
        sid, title = row
    else:
        row = db.execute("SELECT id, title FROM session WHERE id=?", (sid,)).fetchone()
        title = row[1] if row else sid

    safe_title = re.sub(r'[^\w\u4e00-\u9fff-]', '_', title)[:30]
    date_str = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(OUT_DIR, f"AI对话_{safe_title}_{date_str}.md")

    msgs = db.execute("SELECT id, data FROM message WHERE session_id=? ORDER BY time_created", (sid,)).fetchall()
    roles = {}
    for mid, mdata in msgs:
        try:
            roles[mid] = json.loads(mdata).get('role', '')
        except Exception:
            roles[mid] = ''

    parts = db.execute(
        "SELECT message_id, data, time_created FROM part WHERE session_id=? ORDER BY time_created",
        (sid,)).fetchall()

    md = [f"# AI 对话原文导出 — {title}\n",
          f"- 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
          f"- 会话 ID: {sid}",
          f"- 消息数: {len(msgs)}",
          "- 铁律: AI 对话内容原文保存 md 格式，图片留存\n", "---\n"]

    img_count = 0
    os.makedirs(IMG_DIR, exist_ok=True)

    for mid, pdata, tc in parts:
        try:
            pd = json.loads(pdata)
        except Exception:
            continue
        typ = pd.get('type', '')
        ts = datetime.fromtimestamp(tc / 1000).strftime('%m-%d %H:%M') if tc else ''

        if typ == 'text':
            text = pd.get('text', '').strip()
            if not text:
                continue
            if len(text) > 3000:
                text = text[:1500] + f"\n...[中略 {len(text) - 3000} 字符]...\n" + text[-1500:]
            who = "🧑 用户" if roles.get(mid) == 'user' else "🤖 AI"
            md.append(f"### {who} ({ts})\n")
            md.append(text + "\n")
        elif typ == 'file':
            # 图片/附件留存
            url = pd.get('url', '')
            mime = pd.get('mime', '')
            if url.startswith('data:'):
                import base64
                header, b64 = url.split(',', 1)
                ext = {'image/png': '.png', 'image/jpeg': '.jpg'}.get(mime, '.bin')
                img_count += 1
                img_path = os.path.join(IMG_DIR, f"{date_str}_{img_count}{ext}")
                with open(img_path, 'wb') as f:
                    f.write(base64.b64decode(b64))
                md.append(f"![图片]({os.path.relpath(img_path, OUT_DIR)})\n")
        elif typ == 'tool':
            tool = pd.get('tool', '')
            inp = (pd.get('state') or {}).get('input', {})
            brief = json.dumps(inp, ensure_ascii=False)[:120]
            md.append(f"> 🔧 `{tool}` {brief}\n")

    out = "\n".join(md)
    with open(out_path, 'w') as f:
        f.write(out)
    print(f"✓ 导出 {len(out)} 字符 → {out_path}")
    if img_count:
        print(f"✓ 留存图片 {img_count} 张 → {IMG_DIR}/")


if __name__ == '__main__':
    main()