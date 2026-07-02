# AI Daily News — システム概要（後のAIへの引き継ぎ書）

> このリポジトリは「毎朝AIニュースを自動でメール＋Notion配信する」システム。
> **作りがトリッキー**なので、触る前に必ずこの章を読むこと。特に **2段構え** と **CCRのGitHub書き込み方式（2026-07に刷新）** を理解してから手を入れる。

最終更新: 2026-07-03

---

## 0. 一言で

毎朝5:30(JST)に、クラウド上のAIが当日のAIニュースを調査・執筆し、その結果がメール（Gmail）とNotionに自動で届く。**横山さんのMacが起動していなくても届く**ことが最重要要件。

---

## 1. なぜこの構成にしたか（設計理由）★重要

- **「MacBookがスリープ／電源オフでも毎朝メールが届く」ことが目的。** これが全ての出発点。
- 当初はMacのlaunchdで配信していたが、スリープ・電源オフだと落ちるため、**完全にPC非依存（クラウド実行）に移管**した（2026-06-07）。
- 役割で道具が違う：
  - **生成（ニュース調査・執筆）にはAIが必要** → クラウドのClaude（CCR routine）が担当。
  - **配信（Notion保存・メール送信）は定型処理**でAI不要、かつNotion/Gmailに繋がる必要 → GitHub Actions が担当。
- **なぜGitHubを間に挟むか**：CCR（クラウドのClaude実行環境）は**ネットワーク制限でNotion/Gmailに直接書き込めない**。一方GitHubへは（正しい方式なら）pushできる。そこで **GitHubをリレー** にして「CCRがpush → Actionsが検知して配信」という流れにした。

---

## 2. 2段構えアーキテクチャ

```
[第1段：生成]  毎朝5:30 JST
  CCR routine（クラウドのClaude / claude.ai/code の定期ジョブ）
   ├ 接続済みリポ ai-daily-news を自動マウント（git pull）
   ├ Webでニュース調査（WebSearch / WebFetch）
   ├ news_md/{YYYY-MM-DD}_ai-news.md と index.csv を作成
   └ git push（プロキシ認証）で GitHub(main) へ push
        │
        ▼ （index.csv の変更を検知）
[第2段：配信]
  GitHub Actions（.github/workflows/deliver.yml）
   └ morning_delivery.py を実行
        ├ 当日の news_md/*.md を読む
        ├ Notion にページ＋DB行を作成
        └ Gmail で HTMLメール送信
        │
        ▼
  横山さんのメール受信箱 ＋ Notion
```

- **第1段＝生成＝CCR routine**（AIが要る・クラウド）
- **第2段＝配信＝GitHub Actions**（定型処理・GitHub上）
- 両者は **GitHubのmainブランチ** を介して疎結合。CCRが落ちても配信は安全側に倒れる。

---

## 3. CCRのGitHub書き込み方式 ★★★（2026-07刷新・一番大事）

**現在の唯一動く方式：「接続済みリポを紐付け → 素の `git push`（プロキシ認証）」**

- CCR routine には ai-daily-news リポを **GitHub連携で紐付けてある**（`job_config.ccr.session_context.sources[].git_repository`）。これによりリポが自動マウントされ、**`git push` はコンテナ内ローカルプロキシ（`http://127.0.0.1:PORT/git/...`）経由でGitHub認証される**。PATをURLに書く必要はない。
- routineプロンプトは Step1 `git pull` → 生成 → Step6 `git add/commit/push origin main` の素直なgit操作だけ。

### ⚠️ やってはいけない旧方式（2026-07-01に全滅）
CCRコンテナのegressが厳格化し、以下は**PATの有効性と無関係に全て403**になった。**絶対に使わない：**
- `git clone https://<PAT>@github.com/...`（PATをURLに埋める）
- `api.github.com`（Git Data API）への直接commit
- 未紐付けリポへの `git push`

> 2026-06以前の版には「Step6でGitHub Data APIを叩くインラインPython」「/web-setup同期トークンが本体」等の記述があったが、**いずれも旧方式で今は無効**。現行は上記の「紐付け＋git push」一本。

---

## 4. Python はどこにあるか

| Python | 場所 | 役割 | 実行者 |
|---|---|---|---|
| **`morning_delivery.py`**（repo root・追跡済み） | repo root | **配信**専用。`news_md/`の当日mdを読み→HTMLメール変換、Notionページ作成(`post_to_notion`)、NotionDB行追加(`insert_to_notion_db`)、Gmail送信(`send_email`) | GitHub Actions（`deliver.yml`が `python3 morning_delivery.py`） |
| **CCR routineの生成ロジック** | `/schedule` のトリガープロンプト内（リポには無い） | **生成側**。リサーチ・md/CSV作成・`git push`。コードではなく自然言語の指示＋素のgitコマンド | CCR routine（クラウドのClaude） |

- `morning_delivery.py` は **生成しない**。既にpushされたmdを読んで配信するだけ。

---

## 5. ファイル・ID 早見表

| 項目 | 値 |
|---|---|
| GitHubリポ（Public） | `https://github.com/yokokazu0414/ai-daily-news` |
| ローカルclone | `~/VibeMaker/VibeCoding/apps/17_ai-daily-news` |
| **生成: CCR routine ID（現行）** | **`trig_01GUeBYowswxbRbf4BbodqqR`**（紐付け＋git push方式・model sonnet-5・毎日5:30 JST） |
| 生成: CCR routine ID（旧・**無効化済み**・PAT方式） | `trig_01134PBtYchnny8uT6X3AyLC`（再有効化しないこと） |
| 生成: 環境ID | `env_01V9WFyvK8jhxfZe1tUhm8AM` |
| 生成: スケジュール | `30 20 * * *`(UTC) = 毎日 05:30 JST |
| 配信: ワークフロー | `.github/workflows/deliver.yml`（main push時＋手動）。`paths` は **`index.csv` のみ**で発火（mdやドキュメントの移動では発火しない。routineは毎日index.csvを更新するので確実に発火） |
| 配信スクリプト | `morning_delivery.py`（repo root・Mac/Actions共用） |
| 配信の秘密情報 | **GitHub Secrets**：`NOTION_TOKEN` `NOTION_PARENT` `NOTION_DB` `GMAIL_USER` `GMAIL_PASSWORD` `EMAIL_TO` |
| 日次mdの置き場 | **`news_md/`**（`news_md/{YYYY-MM-DD}_ai-news.md`。2026-07-02にルート直下から移設） |
| Notion親ページID | `35ea4133-d6eb-8001-8246-c2156d4b5df4` |
| Notion DB | `https://www.notion.so/35ea4133d6eb8167bbe2cbcaed513cea`（タイトル「AI Daily News Index」） |
| launchd（無効化・保持） | `~/Library/LaunchAgents/com.kazunari.ai-daily-news.plist`。**再有効化しないこと**（重複メール防止） |

---

## 6. データ形式 ★列契約に注意

- **MD**（`news_md/{日付}_ai-news.md`）: `# 📰 AI Daily News - {日付}` ／ `## 🗞️ カバーストーリー`（Top1の詳しい解説）／ `## 🏆 Top 5 ニュース`（各カード: Player / 公開日 / 出典 / 要約 / 💼ビジネスインパクト）。
  - 要約は **3〜4文・固有名詞/数値/関係者名を含む350〜450字**（薄くしない）。
- **index.csv**（repo root）: **必ず8列固定** = `日付,プレーヤー,分類,タイトル,出典,要約,本文,リンク`。
  - ⚠️ **列を増やさない（特に`公開日`）。** `morning_delivery.py` の `insert_to_notion_db` は `csv.DictReader`（1行目ヘッダー基準）で読む。行が9列になるとヘッダーとズレて **Notion DBの全列が1つずつ誤登録される**（タイトル欄に分類が入る等）。2026-06-27〜07-02に実際に発生し修正済み。公開日はCSVに持たず deliver.py が記事URLから取得する。

---

## 7. 障害対応（よくある詰まり）

| 症状 | 原因 | 対処 |
|---|---|---|
| 毎朝のメールが来ない／CCRのpushが403 | **CCRリポ紐付けが外れている**（egressプロキシがブロック） | routineに ai-daily-news が紐付いているか確認（`sources.git_repository`）。紐付けし直せば `git push` が通る（§3）。**PATやapi.github.comで回避しようとしない** |
| Notion DBが特定日で止まって見える／中身がおかしい | ①ビューが日付降順でない ②index.csvの列ドリフト（9列化）でDB行がズレ | ①ビューのソートを日付降順に ②index.csvを8列に是正（§6）。過去の壊れ行はアーカイブ→CSVから正しく入れ直し |
| 記事のリンク/公開日が空・おかしい | 上記の列ドリフトで`リンク`列が本文になっている | index.csvを8列に是正 |
| Notion/メールが重複 | mainへの余計なpushでdeliver.ymlが再発火 | `deliver.yml`の`paths`は`index.csv`のみ。index.csvを変えないインフラ変更なら発火しない |
| その日のニュースが抜けた | CCRの生成失敗 | 下記「手動復旧」 |

### 手動復旧（その日の分が落ちたとき）
**方法A（推奨・claude.ai/code）**: 新規セッションで ai-daily-news を紐付け → 「当日分のAI Daily Newsを作って news_md/ に置き、index.csv(8列)に5件追記して git push」と指示。routineと同じ方式で復旧できる。
**方法B（ローカルMac）**: MacはGitHubへ普通にpushできる。`git pull` → `news_md/{日付}_ai-news.md` 作成＋`index.csv`に8列で5行追記 → `git add news_md/... index.csv && git commit && git push`。push→Actionsが配信。

---

## 8. 触るときの心得

- **生成＝CCR routine（プロンプト）／配信＝Actions（morning_delivery.py）** の役割分担を崩さない。
- **CCRのGitHub書き込みは「紐付け＋git push」一本**（§3）。PAT/api.github.com方式は死んでいる。
- **日次mdは `news_md/`／index.csvは8列固定**（§6）。
- mainへのpushは配信を誘発しうる（`deliver.yml`の`paths`は`index.csv`のみに限定済み）。
- 関連メモ（ローカルClaude用）: `project_ai_daily_news_architecture`, `feedback_ccr_git_issues`, `project_ai_daily_news_csv_contract`。
