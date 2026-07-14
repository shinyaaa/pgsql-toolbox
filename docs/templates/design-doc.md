# Design Doc: <feature name>

<!--
pgsql-hackers への機能提案の前に書く設計ドキュメントのテンプレート。
著名ハッカーの提案メールの構造を抽出したもの:
  - Robert Haas "block-level incremental backup" (2019)
    https://www.postgresql.org/message-id/CA+TgmoYxQLL=mVyN90HZgH0X_EUrw+aZ0xsXJk7XV3-3LygTvA@mail.gmail.com
  - Thomas Munro "WIP: WAL prefetch (another approach)" (2020)
    https://www.postgresql.org/message-id/CA+hUKGJ4VJN8ttxScUFM8dOKX0BrBiboo5uz1cq=AovOddfHpA@mail.gmail.com
  - Robert Haas "backup manifests" (2019)
    https://www.postgresql.org/message-id/CA+TgmoZV8dw1H2bzZ9xkKwdrk8+XYa+DC9H=F7heO2zna5T6qg@mail.gmail.com

書き方の原則 (4通に共通):
  1. 問題は「誰が困っているか」から書く。技術の説明から始めない。
  2. 先行研究・先行スレッドを必ず引用し、自分の案が何が違うかを明示する。
  3. 設計は番号付きコンポーネントに分割し、各所で代替案とトレードオフを併記する。
  4. 弱点・不利なケースは自分から先に書く (レビュアーに指摘される前に)。
  5. v1 のスコープを明示的に絞り、やらないことを「別の取り組み」として列挙する。
  6. 未決事項には必ず自分の傾き (leaning) を添える。丸投げの質問はしない。
各セクションの <!-- --> コメントは記入ガイド。記入後は削除する。
-->

- **Status**: Draft | Proposed | Under discussion | Committed | Withdrawn
- **Date**: YYYY-MM-DD
- **Branch**: <worktree branch>
- **Thread**: <-hackers スレッドURL (投稿後に記入)>

## 1. Problem

<!--
誰がどう困っているか。Haas は「EnterpriseDB, NTT, Postgres Pro が各社バラバラに
out-of-core 実装を持っている。コアで解決すべきだ」と書いた。
- 現状の挙動と、それがユーザ/運用者に与える実害
- 可能なら実測値 (Andres は「テーブル100万個で stats アクセスが0.4秒、170MB」と書いた)
- なぜ今やるべきか、なぜコアでやるべきか
-->

## 2. Prior art

<!--
先行スレッド・既存ツール・過去に沈んだパッチを列挙し、[1][2] 形式で References に繋ぐ。
Munro は pg_prefaulter と Knizhnik 案を挙げ、それぞれ「自分の案とどう違うか」を
1段落ずつ書いた。過去の努力には敬意を払う (Haas: "I intend no disrespect to
those efforts")。既存案を知らずに再発明すると最初の返信で指摘される。
-->

## 3. Goals / Non-goals

### Goals

<!-- v1 で達成すること。箇条書きで3〜5個まで。 -->

### Non-goals (future work)

<!--
やらないことを明示する。Haas は parallel backup と object store 対応を
"But that sounds like a separate effort" と切った。
「あれば良いが v1 の必須ではない」ものもここに置く
("This doesn't seem like a must-have for v1")。
-->

## 4. Proposal overview

<!--
設計の要約を1〜2段落。ここだけ読めば全体像が掴めるように。
ユーザから見える変化 (新GUC、新ツール、新構文) を先に書く。
Haas は「focus on the user experience rather than the technology」と明言している。
-->

## 5. Design

<!--
番号付きコンポーネントに分割する。Haas は
  1. サーバ側のブロック選択 (複数戦略と各トレードオフ)
  2. ファイルフォーマット
  3. マージ用の新ツール
の3部構成にした。各コンポーネントで:
- 仕組みの説明
- 採らなかった代替案と理由 ("There are several possible ways ... I am at the
  moment not too concerned with the exact strategy" のように、本質でない部分は
  決め打ちせず選択肢を残すのも手)
- 具体的な使用例 (Haas は day1/day2/day9 の運用シナリオを書いた)
-->

### 5.1 <component>

### 5.2 <component>

## 6. Evidence / benchmarks

<!--
実測がある場合。条件を必ず添える。Munro:
"in contrived larger-than-memory pgbench crash recovery experiments ...
as much as 20x faster with full_page_writes=off"
— 「作為的な条件で」「最大で」と正直に書いている。
数値は workload・環境・比較対象 (master のコミットID) をセットで。
コードなし設計先行の提案なら、このセクションは
"This is just a design proposal at this point; there is no code." と書き換える。
-->

## 7. Known weaknesses

<!--
このパッチが不利になるケースを自分から列挙する。Munro の
"Here are some cases where I expect this patch to perform badly:" が模範。
各項目に、可能なら緩和案と「調べていない」の明示
("Perhaps that could be mitigated by ... I haven't looked into this.") を添える。
未実装・未対応の部分 (タイムライン切替未対応など) もここ。
-->

## 8. Open questions

<!--
未決事項。各項目に自分の傾きを必ず書く。
Andres: "My gut feeling here is to try to fix X for 14 and change the
approach in 15." / Haas: "I suppose then we should just write the manifest
into the top level ... but perhaps someone has another idea."
決められない点は ADR (adr.md) に切り出して独立スレッドにする選択肢もある。
-->

## 9. References

<!--
[1] https://www.postgresql.org/message-id/...
形式で。本文中の [n] と対応させる。
-->
