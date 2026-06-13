import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
DATABASE_ID = "293e629dade74f1cb222eb2f26a8b8c4"

TODAY = datetime.today().strftime("%Y-%m-%d")

SYSTEM_PROMPT = f"""あなたは医師の症例録音をNotion APIに直接投稿できるJSONに変換するアシスタントです。
医療用語を補正し、略語を展開してください（DM→糖尿病、HTN→高血圧など）。
以下の形式のJSONのみ出力し、説明文やコードブロック記号は絶対に含めないでください。
出力は必ず有効なJSONとし、末尾のカンマ、コメント、Markdownを含めない。
日付は今日の日付 {TODAY} を使用してください（録音内に日付の言及がない場合）。

{
  "parent": {"database_id": "293e629dade74f1cb222eb2f26a8b8c4"},
  "properties": {
    "症例名": {"title": [{"text": {"content": "年代・性別・主病態を一言で"}}]},
    "日付": {"date": {"start": "YYYY-MM-DD"}},
    "診療科": {"select": {"name": "内科 or 外科 or 救急 or 小児科 or 産婦人科 or 精神科 or 腎臓内科 or その他"}},
    "場面": {"select": {"name": "初診 or 入院 or 回診 or 退院 or 当直"}},
    "主訴": {"rich_text": [{"text": {"content": "主訴"}}]},
    "問題リスト": {"multi_select": [{"name": "#1 問題"}, {"name": "#2 問題"}]},
    "タグ": {"multi_select": [{"name": "キーワード1"}, {"name": "キーワード2"}]},
    "学び": {"rich_text": [{"text": {"content": "学び・気づき"}}]},
    "疑問点": {"rich_text": [{"text": {"content": "疑問点"}}]}
  },
  "children": [
    {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "現病歴"}}]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "現病歴内容"}}]}},
    {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "既往歴・内服"}}]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "既往歴と内服薬"}}]}},
    {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "身体所見"}}]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "身体所見"}}]}},
    {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "検査・画像所見"}}]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "検査・画像所見"}}]}},
    {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "アセスメント・方針"}}]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "アセスメントと方針"}}]}},
    {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "ToDo"}}]}},
    {"object": "block", "type": "to_do", "to_do": {"rich_text": [{"type": "text", "text": {"content": "タスク"}}], "checked": false}},
    {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "申し送り（SBAR）"}}]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "S: \\nB: \\nA: \\nR: "}}]}},
    {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "原文"}}]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "原文テキスト"}}]}}
  ]
}"""


def call_gpt(transcript: str) -> dict:
    res = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-4o",
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript}
            ]
        }
    )
    res.raise_for_status()
    content = res.json()["choices"][0]["message"]["content"]
    payload = json.loads(content)
    payload["properties"]["日付"] = {"date": {"start": datetime.today().strftime("%Y-%m-%d")}}
    return payload


def post_to_notion(payload: dict) -> dict:
    res = requests.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        },
        json=payload
    )
    res.raise_for_status()
    return res.json()


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "today": TODAY, "version": "2026-06-13-1"})


@app.route("/case", methods=["POST"])
def create_case():
    data = request.get_json()
    if not data or "transcript" not in data:
        return jsonify({"error": "transcript field required"}), 400

    transcript = data["transcript"]

    try:
        notion_payload = call_gpt(transcript)
    except Exception as e:
        return jsonify({"error": f"GPT error: {str(e)}"}), 500

    try:
        result = post_to_notion(notion_payload)
    except Exception as e:
        return jsonify({"error": f"Notion error: {str(e)}"}), 500

    return jsonify({
        "status": "ok",
        "url": result.get("url", "")
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
