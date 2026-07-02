# AI Daily News

毎朝5:30(JST)に、クラウド上のAIが当日のAIニュースTop5を調査・執筆し、**Gmail＋Notionに自動配信**するシステム。**Macが起動していなくても届く**（完全クラウド実行）。

## 仕組み（2段構え）

```
[生成] CCR routine（クラウドのClaude, 毎朝5:30 JST）
  Web調査 → news_md/{日付}_ai-news.md + index.csv を作成 → git push
        │  （GitHub main / index.csv の変更を検知）
[配信] GitHub Actions（deliver.yml → morning_delivery.py）
  当日mdを読む → Notionページ＋DB行を作成 → Gmail送信
```

- **生成**はAIが必要なのでCCR（Claude Code on the web の定期ジョブ）、**配信**は定型処理なのでGitHub Actionsが担当。両者はGitHub(main)を介して疎結合。
- CCRはNotion/Gmailに直接繋げないため、GitHubをリレーにしている。

## リポジトリ構成

| パス | 役割 |
|---|---|
| `news_md/{YYYY-MM-DD}_ai-news.md` | 日次ニュース本文（アーカイブ） |
| `index.csv` | 全記事の構造化データ（**8列固定**: 日付,プレーヤー,分類,タイトル,出典,要約,本文,リンク） |
| `morning_delivery.py` | 配信スクリプト（md→HTMLメール変換 / Notion保存 / Gmail送信） |
| `.github/workflows/deliver.yml` | 配信ワークフロー（`index.csv`のpushで発火＋手動） |
| `SYSTEM_OVERVIEW.md` | **引き継ぎ書。触る前に必読** |

## 触る前に

⚠️ 作りがトリッキーです。**必ず [`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md) を読んでから**手を入れてください。特に：
- **CCRのGitHub書き込みは「接続済みリポ紐付け＋素の`git push`（プロキシ認証）」一本**。PATをURLに埋める／api.github.com直叩きは egress で403になり**動きません**（2026-07に旧方式が全滅）。
- **index.csvは8列固定**。`公開日`など列を足すとNotion DB登録が総崩れになります。
- 日次mdは `news_md/` に置く（ルート直下には作らない）。

## 手動復旧・障害対応

`SYSTEM_OVERVIEW.md` の §7（障害対応）参照。その日の分が落ちたら、claude.ai/code で ai-daily-news を紐付けた新規セッション、またはローカルMacから `news_md/` にmd追加＋`index.csv`に8列で追記して `git push` すれば配信されます。
