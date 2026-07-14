# ADR: <decision title>

<!--
設計上の「決定」を1つ (または密接に関連する少数) 記録・議論するためのテンプレート。
模範は Andres Freund "shared memory stats: high level design decisions:
consistency, dropping" (2021):
https://www.postgresql.org/message-id/20210319235115.y3wz7hpnnrshdyv6@alap3.anarazel.de

Andres のやり方の要点:
  1. 長大な実装スレッドから、広い聴衆に問うべき高レベル決定だけを切り出して
     独立スレッドにした ("warrant a wider audience")。低レベルの議論は元スレッドに残す。
  2. 決定ごとに番号を振り、独立に答えられる粒度のサブ質問 (1.1, 1.2, 1.3) に分解した。
  3. 現状 (status quo) の挙動とそのコストを実測値で示した
     ("1 million empty tables → any stats access takes ~0.4s, 170MB")。
  4. 各選択肢に、実装の容易さと帰結 (ユーザから見える挙動の変化) を併記した。
  5. 自分の意見を必ず書いた ("I personally think it's fine to ...",
     "My gut feeling here is ...")。段階的な移行案 (14ではX、15でY) も選択肢に入れる。
使い方: 1決定 = 1 ADR が基本。design doc の Open questions から昇格させる。
各セクションの <!-- --> コメントは記入ガイド。記入後は削除する。
-->

- **Status**: Open | Decided | Superseded by <ADR>
- **Date**: YYYY-MM-DD
- **Related**: <design doc / 実装スレッドURL / commit>
- **Decision owner**: <自分か、コミッタの判断待ちか>

## Context

<!--
この決定がなぜ今必要か。前提知識のない読者向けに、対象システム/パッチが
何をするものかを2〜3段落で。Andres は「共有メモリ stats パッチとは何か」の
説明から始めた ("In case it is not obvious, the goal of ... is to replace ...")。
決定を今しないと何が起きるか (手戻り、リリース逃し) も書く。
-->

## Question(s)

<!--
決めるべきことを疑問文で。複数の独立した論点があるなら番号で分割し、
1つの論点の中でも独立に答えられる粒度までサブ質問に割る。
例 (Andres):
  1) What kind of consistency do we want from the pg_stats_* views?
     1.1) トランザクション内で初回アクセス時点への固定は必要か?
     1.2) 同一 stat への再アクセスは同じ値を返すべきか?
     1.3) 同一ビューのカラム間の一貫性はどこまで必要か?
  2) How to remove stats of dropped objects?
-->

## Status quo

<!--
現在の挙動と、その根拠 (歴史的経緯)。コストは実測値で。
「現状維持」も常に選択肢の1つなので、公平に書く。
旧設計の制約に由来する挙動なら、それを指摘する (Andres: 旧モデルの効率化ハックを
新設計に持ち込むのは "cargo-culting")。
-->

## Options

<!--
選択肢ごとに: 概要 / 実装コスト / 帰結 (ユーザ可視の挙動変化、性能、保守性)。
先行実装者が試した案が既にあるなら、それも選択肢として敬意をもって記載し、
問題点を具体例で示す (Andres は Horiguchi さんの1エントリキャッシュ案を
「同じテーブルに連続アクセス→更新が見えない、indexと切り替える→見える」という
具体的な混乱例で退けた)。
-->

### Option A: <name>

### Option B: <name>

## My take

<!--
自分の意見と、その確度を正直に。確信がなければ gut feeling と明示して良い。
段階案 (今リリースは安全な A、次リリースで B) や、
「中途半端にやるなら最初から B に振り切る方が良いかもしれない」という
逡巡もそのまま書く (Andres: "But I'm also not sure - it might be smarter to
go full in, to avoid introducing a system that we'll just rip out again.")。
-->

## Decision

<!--
議論の結果決まった内容と決定日、決め手になった論点、スレッド内の該当メッセージURL。
決まるまでは空欄で Status: Open のまま。
-->

## References

<!--
[1] https://www.postgresql.org/message-id/...
-->
