# AI Daily News — システム概要（後のAIへの引き継ぎ書）

> このリポジトリは「毎朝AIニュースを自動でメール＋Notion配信する」システム。
> **作りがトリッキー**なので、触る前に必ずこの章を読むこと。特に **2段構え** と **トークンの罠** を理解してから手を入れる。

最終更新: 2026-06-26

---

## 0. 一言で

毎朝5:30(JST)に、クラウド上のAIが当日のAIニュースを調査・執筆し、その結果がメール（Gmail）とNotionに自動で届く。**横山さんのMacが起動していなくても届く**ことが最重要要件。

---

## 1. なぜこの構成にしたか（設計理由）★重要

- **「MacBookがスリープ／電源オフでも毎朝メールが届く」ことが目的。** これが全ての出発点。
- 当初はMacのlaunchdで配信していたが、スリープ・電源オフだと配信が落ちるため、**完全にPC非依存（クラウド実行）に移管**した（2026-06-07）。
- ただし役割で道具が違う：
  - **生成（ニュース調査・執筆）にはAIが必要** → クラウドのClaude（CCR routine）が担当。
  - **配信（Notion保存・メール送信）は決まった処理**でAI不要、かつNotion/Gmailに繋がる必要 → GitHub Actions が担当。
- **なぜGitHubを間に挟むか**：CCR（クラウドのClaude実行環境）は**ネットワーク制限でNotion/Gmailに直接書き込めない**。一方GitHubには（接続が生きていれば）push できる。そこで **GitHubをリレー（受け渡し場所）** にして、「CCRがpush → Actionsがそれを検知して配信」という流れにした。

---

## 2. 2段構えアーキテクチャ

```
[第1段：生成]  毎朝5:30 JST
  CCR routine（クラウドのClaude / claude.ai/code の定期ジョブ）
   ├ Webでニュース調査（WebSearch / WebFetch）
   ├ {YYYY-MM-DD}_ai-news.md と index.csv を作成
   └ GitHub(main)へ push   ← ここが詰まりやすい（後述トークンの罠）
        │
        ▼ （mainへのpushを検知）
[第2段：配信]
  GitHub Actions（.github/workflows/deliver.yml）
   └ morning_delivery.py を実行
        ├ 当日の .md を読む
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

## 3. Python はどこにあるか ★よく聞かれる

Pythonは **2か所** にある。混同しないこと。

| Python | 場所 | 役割 | 実行者 |
|---|---|---|---|
| **`morning_delivery.py`**（リポジトリ直下・追跡済み） | repo root | **配信**専用。`.md`→HTMLメール変換、Notionページ作成(`post_to_notion`)、NotionDB行追加(`insert_to_notion_db`)、Gmail送信(`send_email`) | GitHub Actions（`deliver.yml`が `python3 morning_delivery.py`）。ローカルからも実行可だがlaunchdは無効化済み |
| **CCR routineのStep6にインラインで埋まったPython** | `/schedule` のトリガープロンプト内（リポには無い） | **生成側のpush**。git pushが環境プロキシで403になるため、**GitHub Git Data API（blob→tree→commit→ref）でcommit**する小スクリプト | CCR routine（クラウドのClaude）が実行 |

- `morning_delivery.py` は **生成しない**。既にpushされた `.md` を読んで配信するだけ。
- 生成（リサーチ・執筆）は **CCR routineのプロンプト**側にロジックがある（コードではなく自然言語の指示＋Python push）。

---

## 4. トークンの罠 ★★★ 一番ハマる所

**結論：GitHubのPATを無効化／ローテートする前に、必ず `/web-setup` の同期先も考えること。**

### 認証は3層あり、混同しやすい
1. **`apps/17_ai-daily-news/.env` の `GITHUB_TOKEN`** … `morning_delivery.py` がローカル実行時にpushへ使う。**現在はほぼ飾り**（配信はActions、生成はCCR）。
2. **CCR routineのクローンURLに埋めたPAT**（`git clone https://<PAT>@github.com/...`）… **これも飾り**。下記プロキシがURLのトークンを無視して上書きするため、何を入れても効かない。
3. **`/web-setup` で同期した `gh` CLIトークン（＝Claudeアカウントに紐付く）** … **これが本体の鍵**。Claude Code on the web の「GitHubプロキシ」が、全github通信を横取りしてこのトークンを注入する。CCRのpush/cloneが実際に通るかはこれ次第。

### 2026-06の大事故（再発防止）
- 漏洩していた旧クラシックPAT `ghp_…` を無効化したら、**`/web-setup`で同期されていたのがまさにその旧PAT**だったため、クラウドのGitHubプロキシが死亡。git=403／api.github.com=502 "builtin injection failed" に。
- **Routine内のPATをいくら新しくしても直らなかった**（プロキシが同期トークンを使うため）。5日間迷走した。
- **正解＝ターミナルで `/web-setup` を再実行**（今の有効な `gh` トークンを再同期）するだけ。`gh` 認証ベースなので以後勝手に切れない。
- 参考: https://code.claude.com/docs/en/claude-code-on-the-web の「GitHub authentication options」。接続方式は ①GitHub App ②`/web-setup`(gh同期) の2つ。本システムは②。

---

## 5. ファイル・ID 早見表

| 項目 | 値 |
|---|---|
| GitHubリポ（Public） | `https://github.com/yokokazu0414/ai-daily-news` |
| ローカルclone | `~/VibeMaker/VibeCoding/apps/17_ai-daily-news` |
| 生成: CCR routine ID | `trig_01134PBtYchnny8uT6X3AyLC`（`/schedule` RemoteTrigger） |
| 生成: 環境ID | `env_01V9WFyvK8jhxfZe1tUhm8AM` |
| 生成: スケジュール | `30 20 * * *`(UTC) = 毎日 05:30 JST、model: sonnet系 |
| 配信: ワークフロー | `.github/workflows/deliver.yml`（main push時＋手動）。`paths`で `*_ai-news.md` / `index.csv` のみ発火（ドキュメント等のpushでは配信しない） |
| 配信スクリプト | `morning_delivery.py`（repo root・Mac/Actions共用） |
| 配信の秘密情報 | **GitHub Secrets**：`NOTION_TOKEN` `NOTION_PARENT` `NOTION_DB` `GMAIL_USER` `GMAIL_PASSWORD` `EMAIL_TO`（Actionsは`.env`が無いためSecretsで渡す） |
| Notion親ページID | `35ea4133-d6eb-8001-8246-c2156d4b5df4` |
| Notion DB | `https://www.notion.so/35ea4133d6eb8167bbe2cbcaed513cea` |
| launchd（無効化・保持） | `~/Library/LaunchAgents/com.kazunari.ai-daily-news.plist`。**重複メール防止のため再有効化しないこと** |

---

## 6. データ形式

- **MD**: `# 📰 AI Daily News - {日付}` ／ `## 🗞️ カバーストーリー`（Top1の詳しい解説）／ `## 🏆 Top 5 ニュース`（各カード: Player / 公開日 / 出典 / 要約 / 💼ビジネスインパクト）。
  - 要約は **3〜4文・固有名詞/数値/関係者名を含む350〜450字**（薄くしない。過去に「2-3文」指定で内容が薄くなる事故があり強化した）。
- **index.csv**（repo root）: 実ファイルの列は `日付,プレーヤー,分類,タイトル,出典,要約,本文,リンク`。
  - ※CCR routineのプロンプトは `公開日` を含む9列ヘッダーを指示している箇所があり**不一致**。実ファイルは8列で運用中。触るときは実ファイルに合わせる。

---

## 7. 障害対応（よくある詰まり）

| 症状 | 原因 | 対処 |
|---|---|---|
| 毎朝のメールが来ない／pushが403・api502 | **クラウドのGitHubプロキシ認証切れ**（`/web-setup`同期トークンの失効。特にPAT無効化の直後） | **ターミナルで `/web-setup` を再実行**。これが第一手 |
| 要約が薄い（さっぱり） | CCR routineプロンプトの要約字数指定が弱い | プロンプトの要約指定を「350〜450字・具体重視」に強化 |
| Notion/メールが重複 | mainへの余計なpushでdeliver.ymlが再発火 | `deliver.yml`の`paths`で防止済み。手動配信時はmorning_delivery.pyの二重実行に注意 |
| その日のニュースが抜けた | CCRの生成失敗 | 下記「手動復旧」 |

### 手動復旧（その日の分が落ちたとき）
横山さんのMacはGitHubに普通に届く（プロキシを通らないため）。ローカルで：
1. `~/VibeMaker/VibeCoding/apps/17_ai-daily-news` で `git pull`
2. その日の `{YYYY-MM-DD}_ai-news.md` を作成（上記MD形式）＋ `index.csv` に5行追記
3. `git add . && git commit -m "AI Daily News: {日付}" && git push`
4. push→Actionsが配信（メール＋Notion）

---

## 8. 触るときの心得

- **生成＝CCR routine（プロンプト）／配信＝Actions（morning_delivery.py）** の役割分担を崩さない。
- **GitHub認証の本体は `/web-setup` 同期トークン**。PATをいじっても無駄なことが多い。
- mainへのpushは配信を誘発しうる（`paths`フィルタで news/csv のみに限定済み）。
- 関連メモ（ローカルClaude用）: `project_token_dependencies`, `project_ai_daily_news_architecture`。
