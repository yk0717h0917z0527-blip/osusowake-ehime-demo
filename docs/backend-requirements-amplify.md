# おすそわけ収穫 バックエンド要件定義書（Amplify Hosting 版）

| 項目 | 内容 |
|---|---|
| 版 | 1.0 |
| 作成日 | 2026-11-05（2026-11-06 更新） |
| 対象 | 収穫お手伝いマッチングアプリ「おすそわけ収穫」愛媛版のバックエンド（API、DB、外部連携、AWS 基盤） |
| 基盤 | AWS Amplify Hosting（Next.js の SSR）＋ DynamoDB 1 テーブル。東京リージョン |
| 構成図 | `demo-amplify-architecture.svg` / `demo-amplify-architecture.png`（同じフォルダ） |
| 画面 | `osusowake-demo-ehime.html`（PC 表示）、`osusowake-ehime-smartphone.html`（スマホ表示）、`osusowake-admin-ehime.html`（運営管理画面） |
| 体制 | 3 人（A: 基盤・DB、B: 外部 API・計算、C: QR・応募・連携） |

本書の 1〜8 章が要件、9 章がデモ画面（HTML）で実装済みの内容との対応です。

## 1. 条件と結論

| 条件 | 対応 |
|---|---|
| Amplify Hosting を基盤にする | Next.js を Amplify Hosting（SSR）に置き、`/api/*` の Route Handlers をバックエンドにする |
| 無料のトークンだけで運営する | 有料 API を使わない。地図、天気、野菜価格のすべてで API キーも不要（8 章で調査） |
| DB は 1 つ | DynamoDB のテーブル 1 つ（シングルテーブル設計） |
| QR 読み取り | 端末のカメラで読み、照合は `/api/checkin` で DynamoDB に条件付き書き込み。外部 API なし |
| 難易度が低く 1 日で終わる | AWS リソースは Amplify アプリ、IAM ロール 1 つ、DynamoDB テーブル 1 つの 3 点だけ。VPC、Lambda の自作、API Gateway、Cognito は使わない |
| 地図、野菜価格、天気の API | 地図は地理院タイル（キー不要）、野菜価格は e-Stat の統計表ファイル（キー不要）、天気は気象庁の予報 JSON（キー不要） |

## 2. チームでの検討

3 人で論点ごとに案を出し、1 日で終わるか、無料で済むか、提供 AWS 環境の制約（命名接頭辞 `EhimeAI2026-`、`Project` タグ必須、IAM ユーザー不可、アクセスキーを書かない）に触れないかで決めた。

| 論点 | 出た案 | 決定 | 理由 |
|---|---|---|---|
| API をどこで動かすか | (1) Amplify Gen 2 の `defineFunction` + AppSync (2) API Gateway + Lambda を自作 (3) Next.js の Route Handlers を Amplify Hosting の SSR で動かす | **(3)** | Gen 2 は CDK のブートストラップで `cdk-...` などの名前のロールを自動作成し、接頭辞の制約で AccessDenied になる恐れがある。(2) は Lambda ごとのタグとロール設定が増える。(3) はリポジトリ 1 つで画面と API がそろい、作る AWS リソースが最少 |
| DB | DynamoDB / RDS / Amplify Gen 2 の Data | **DynamoDB 1 テーブル** | VPC が不要で SSR から直接つなげる。プロビジョンド 5 RCU / 5 WCU なら常時無料枠に収まる |
| AWS への認証 | アクセスキーを環境変数に置く / SSR Compute ロール | **SSR Compute ロール** | アクセスキーを書かずに済む。ロール名は `EhimeAI2026-osusowake-demo-ssr` |
| ログイン | Cognito / なし | **なし（デモ用の固定ユーザーを選ぶ）** | 1 日では SMS や連携ログインの設定が間に合わない。公開運用では Cognito を追加する |
| 地図 | Amazon Location Service / Google Maps / 地理院タイル | **地理院タイル + Leaflet** | キー不要、無料。出典表示だけで使える。表示のたびに読み込むので常に最新 |
| 野菜価格 | 農水省 青果物市況 CSV / WAGRI / e-Stat API / e-Stat の統計表ファイル / 農水省 旬別 CSV | **e-Stat の統計表ファイル（小売物価統計調査「主要品目の都市別小売価格」、松山市）** | キー不要で松山市の円 / kg が取れる。市況 CSV は画面遷移の再現が必要で 1 日では重い。WAGRI は申請と会員費、e-Stat API は appId が要る。値は小売価格の月次なので、画面に「目安」と書く（比較は 8 章） |
| 天気 | 気象庁防災情報 XML / 気象庁の予報 JSON / OpenWeatherMap | **気象庁の予報 JSON（愛媛県 `380000`）** | キー不要、JSON で扱いやすい。仕様の保証はないので、取得できないときはキャッシュか「取得できませんでした」を表示 |
| QR | 外部の QR API / 端末内ライブラリ | **端末内ライブラリ** | 生成は `qrcode`、読み取りは `html5-qrcode`。カメラは HTTPS が必要で、Amplify の既定ドメインで満たせる |
| 定期処理 | EventBridge + Lambda / 要求時に取得してキャッシュ | **要求時に取得し DynamoDB に TTL 付きで保存** | スケジューラを作らずに済む。天気 30 分〜3 時間、価格 24 時間 |

## 3. 構成

```
スマホ（参加者・農家） ──HTTPS──▶ Amplify Hosting（Next.js 16 SSR）
   │                                 ├─ 画面（地図、募集、予定、メッセージ、QR 表示・読取、お礼の換算）
   │                                 └─ /api/*（Route Handlers）
   │                                        │  SSR Compute ロール
   │                                        ├──▶ DynamoDB  EhimeAI2026-osusowake-demo
   │                                        ├──▶ 気象庁 予報 JSON（キー不要）
   │                                        └──▶ e-Stat 統計表ファイル（キー不要）
   └──直接──▶ 地理院タイル（キー不要）
GitHub（main へ push）──▶ Amplify が自動ビルド・デプロイ
Amplify の SSR ログ ──▶ CloudWatch Logs
```

### 3.1 AWS リソース（すべて東京リージョン）

| リソース | 名前 | 設定 | タグ |
|---|---|---|---|
| Amplify アプリ | `EhimeAI2026-osusowake-demo` | GitHub の `main` ブランチと接続。フレームワークは Next.js（SSR） | `Project=EhimeAI2026` |
| IAM ロール（SSR Compute） | `EhimeAI2026-osusowake-demo-ssr` | 信頼先 `amplify.amazonaws.com`。許可はこのテーブルへの `GetItem` `PutItem` `UpdateItem` `DeleteItem` `Query` `Scan` `TransactWriteItems` だけ | `Project=EhimeAI2026` |
| DynamoDB テーブル | `EhimeAI2026-osusowake-demo` | キー `PK`（文字列）+ `SK`（文字列）。プロビジョンド 5/5、TTL 属性 `ttl`。GSI なし | `Project=EhimeAI2026`（作成時に必須） |
| CloudWatch Logs | Amplify が自動作成 | 保持期間 7 日に変更 | - |

Amplify のサービスロールが必要になった場合も `EhimeAI2026-` で始まる名前で作る。

### 3.2 API（Route Handlers）

**1 日目に作る範囲**

| メソッドとパス | 内容 | 担当 |
|---|---|---|
| `GET /api/farms` | 農場の一覧と地図用の座標（地区のおおよその位置。番地は参加確定まで返さない） | A |
| `GET /api/events?date=` | 募集の一覧。各募集に `deadlineAt`、残り枠、受付状態を付ける | A |
| `GET /api/weather` | 気象庁の愛媛県予報（中予・松山）。DynamoDB に 30 分〜3 時間キャッシュ | B |
| `GET /api/prices?item=` | e-Stat の統計表ファイル（Excel）から松山市の品目単価（円 / kg）を読む。24 時間キャッシュ。取れないときは直近の値 | B |
| `POST /api/prices/calc` | `{ items: [{ item, qty, unit }] }` → 品目ごとの金額、合計、1 人あたり。「目安」と出典を返す | B |
| `POST /api/qr/issue` | 農家が募集の QR を発行。ランダムなトークンを 15 分の TTL で保存し、QR の文字列を返す | C |
| `POST /api/checkin` | 読み取ったトークンと参加者 ID で照合。条件付き書き込みで二重チェックインを防ぐ | C |

**デモ画面にある機能（2 日目以降に追加する範囲）**

| メソッドとパス | 内容 |
|---|---|
| `POST /api/applications` | 応募（1 人またはグループ）。締切後は `409 CLOSED`、同じ日に確定・承認待ちの予定があれば `409 SAME_DAY`（3.4） |
| `POST /api/applications/{id}/cancel` | 応募の取り消し・キャンセル |
| `GET /api/party-requests` / `POST /api/party-requests/{id}/answer` | グループ応募で追加されたメンバーへの参加リクエストと回答（参加する / 参加しない）。参加するには安全上の注意への同意が必須 |
| `POST /api/links` | メンバー連携のリクエストを送る（本人確認ずみの相手だけ） |
| `POST /api/links/{id}/approve` | 受け取った側が承認し、4 桁の確認コードを発行（10 分で無効） |
| `POST /api/links/{id}/confirm` | 送った側が確認コードを入力して連携を完了。3 回まちがえるとリクエストは無効 |
| `POST /api/links/{id}/decline` / `POST /api/links/{id}/report` | 拒否・通報（通報は拒否と同時に運営へ送る） |
| `GET /api/threads` / `GET・POST /api/threads/{id}/messages` | メッセージ。農家との 1 対 1、参加者のグループ、運営の 3 種類 |
| `GET /api/notifications` | お知らせ（承認、リマインド、参加リクエスト、連携リクエストなど） |

API キーは使わない。e-Stat のファイル ID（`statInfId`）は毎月変わるので、Amplify の環境変数 `ESTAT_STATINF_ID` に置くか、一覧ページから最新月を自動で探す（8.3）。

### 3.3 DynamoDB（1 テーブル）

| PK | SK | 主な属性 | TTL |
|---|---|---|---|
| `FARM#<farmId>` | `META` | 農場名、市町、地区の緯度経度 | - |
| `FARM#<farmId>` | `EVENT#<eventId>` | 日付、受付時刻、作物、定員、残り枠、お礼の品目と量、`deadlineAt` | - |
| `EVENT#<eventId>` | `APP#<userId>` | 応募の状態（pending / confirmed / cancelled）、グループ ID、参加時間 | - |
| `USER#<userId>` | `DAY#<yyyy-mm-dd>` | その日の予定（応募 ID）。1 日 1 件の判定に使う | - |
| `EVENT#<eventId>` | `QR#<token>` | 発行者、発行時刻 | 15 分 |
| `EVENT#<eventId>` | `CHECKIN#<userId>` | チェックイン時刻 | - |
| `USER#<userId>` | `PREQ#<appId>` | 参加リクエスト（申込者、状態 wait / ok / no、同意の有無） | 応募締切 |
| `USER#<userId>` | `LINK#<otherId>` | 連携の状態（requested / approved / linked / declined）、関係、確認コードのハッシュ、失敗回数 | 承認後 10 分 |
| `THREAD#<threadId>` | `MSG#<時刻>` | 送信者、本文 | - |
| `USER#<userId>` | `NOTI#<時刻>` | お知らせの種類、本文、既読 | 90 日 |
| `PRICE#<品目>` | `<yyyymm>` | 単価（円 / kg）、調査月、出典 | 24 時間 |
| `WEATHER#380000` | `LATEST` | 予報 JSON、取得時刻 | 30 分〜3 時間 |
| `USER#<userId>` | `META` | 表示名、役割（参加者 / 農家）、本人確認、ランク | - |

件数が少ないので一覧は `Query`（農場・利用者単位）と小さな `Scan` で足りる。

### 3.4 業務ルール

| ルール | 内容 | 判定の場所 |
|---|---|---|
| 応募締切 | 締切は募集ごとに「前日 18:00」などで決める。サーバーの現在時刻（日本時間）が `deadlineAt` を過ぎたら応募できない。「受付終了」の募集も応募できない | `POST /api/applications` と回答 API。画面はボタンをグレーにし押せなくする |
| 1 日 1 件 | 確定または承認待ちの予定がある日は、ほかの募集に応募できない | 応募と `USER#…/DAY#…` の作成を `TransactWriteItems` で同時に行い、`attribute_not_exists` で重複を防ぐ |
| 参加リクエスト | グループ応募に追加されたメンバーは、応募締切までに回答する。参加しないと答えても申込者の応募は続く。同じ日に予定があるメンバーは参加できない | 回答 API |
| メンバー連携 | 本人確認ずみ同士だけ。受け取った側が承認すると 4 桁のコードが出て、会うか電話で伝える。送った側がコードを入力すると連携完了。コードは 10 分で無効、3 回まちがえるとリクエストは無効 | 連携 API |
| お礼の換算 | 単価 × お礼の量。個数・本数の品目は 1 個あたりの重さで kg に直す（キウイ 0.1kg、柿 0.25kg、大根 1kg など）。小売価格なので「目安」と表示 | 価格 API |
| 位置 | 番地は参加確定まで出さない。地図は地区のおおよその位置 | 農場 API |

### 3.5 QR の流れ

1. 農家が `POST /api/qr/issue` を呼び、返った文字列を `qrcode` で画面に表示する。
2. 参加者が `html5-qrcode` でカメラから読み取り、`POST /api/checkin` に送る。
3. API は `QR#<token>` があり期限内かを確かめ、`CHECKIN#<userId>` を `attribute_not_exists` 付きで書く。すでにあれば「チェックイン済み」を返す。

ランダムなトークンで照合する。署名付きトークンや位置（農園から 500m 以内）による判定は、公開運用の段階で追加する。

## 4. 3 人の分担と 1 日の進め方

| 担当 | 範囲 | 成果物 |
|---|---|---|
| A: 基盤・DB | Amplify アプリ、GitHub 接続、IAM ロール、DynamoDB、`amplify.yml`、初期データ投入、農場と募集の API | デプロイされた URL、`scripts/seed.ts` |
| B: 外部 API・計算 | 天気、野菜価格、換算計算、地図の表示 | `/api/weather` `/api/prices` `/api/prices/calc`、地図コンポーネント |
| C: QR・チェックイン | QR の発行・表示・読み取り、チェックイン API、画面のつなぎ込み | `/api/qr/issue` `/api/checkin`、QR 画面 |

| 時間 | 全員 | A | B | C |
|---|---|---|---|---|
| 9:00〜9:45 | API の入出力と DynamoDB のキーをこの文書で確定 | | | |
| 9:45〜12:00 | | Amplify 作成、ロール、テーブル、初回デプロイ | e-Stat の統計表と品目を確定し、取得と計算を実装 | QR 発行と読み取りをローカルで実装 |
| 13:00〜15:00 | | 農場・募集 API、初期データ | 天気 API、地図（地理院タイル） | チェックイン API、二重防止 |
| 15:00〜16:30 | Amplify にデプロイし、スマホ 2 台で通し確認（QR はカメラが必要） | | | |
| 16:30〜17:30 | デモの予行、出典表示の確認、不要リソースの確認 | | | |

3.2 の「2 日目以降に追加する範囲」は、応募（締切・1 日 1 件）→ 参加リクエスト → メンバー連携 → メッセージ の順に追加する。画面と業務ルールはデモ画面（9 章）で確定しているので、API とテーブルを足すだけでよい。

ローカル開発で DynamoDB を使うときは、各自の一時的な認証（SSO や CloudShell など事務局の方法）を使い、アクセスキーをファイルや GitHub に置かない。

## 5. 無料で収まるか

| 項目 | 無料の範囲 | デモでの想定 |
|---|---|---|
| Amplify Hosting | 無料枠（ビルド 1,000 分 / 月、配信 15GB / 月、SSR 50 万リクエスト / 月 など）。2025-07-15 以降に作成したアカウントは無料プランのクレジットで扱われる | 数十回のビルドと数百リクエスト |
| DynamoDB | 常時無料（25GB、プロビジョンド 25 RCU / 25 WCU） | 5 / 5 で作成。オンデマンドにしない |
| CloudWatch Logs | 5GB / 月 | 保持 7 日 |
| 地理院タイル | 無料、キー不要。出典「地理院タイル」の表示が必要 | 地図に出典を表示 |
| 気象庁 予報 JSON | 無料、キー不要。出典「気象庁」 | キャッシュで呼び出しを抑える |
| e-Stat 統計表ファイル | 無料、キー不要。出典「政府統計の総合窓口（e-Stat）」と加工した旨を表示 | 24 時間キャッシュ |

提供 AWS 環境の請求条件と無料枠の適用は事務局に確認する（6 章）。

## 6. 事前に確認すること

1. 提供 AWS 環境で Amplify Hosting の作成と、SSR Compute ロールの設定が許可されているか。
2. Amplify が裏で作るリソースが命名・タグの制約に当たらないか。当たる場合は事務局に相談する。
3. 提供環境に無料枠が適用されるか、費用の上限はいくらか。
4. 価格は「小売価格・月次の目安」でよいか（最新は前月分）。
5. デモ後に Amplify アプリと DynamoDB テーブルを削除する日。

## 7. 片付け

デモ後は Amplify アプリ、DynamoDB テーブル、IAM ロールの順に削除する。CloudWatch のロググループも消す。

## 8. キー不要で農作物価格が取れるか（2026-11-05 調査）

### 8.1 結論

キー不要の **JSON の API は見つからなかった**。代わりに、キー不要で決まった URL から取れる**公的統計のファイル**が 2 つあり、デモに使える。

| 候補 | 取得方法 | キー | 松山 | 単位と頻度 | 最新（調査日） | 判定 |
|---|---|---|---|---|---|---|
| **e-Stat 統計表ファイル**（小売物価統計調査「主要品目の都市別小売価格」） | `https://www.e-stat.go.jp/stat-search/file-download?statInfId=<ID>&fileKind=0`（Excel） | 不要 | **あり**（列「松山市 38201」） | 小売価格、円 / kg、月次 | 2026 年 9 月分（2026-10-23 公開） | **採用** |
| 農水省 青果物卸売市場調査（旬別）都市別 CSV | `https://www.maff.go.jp/j/tokei/syohi/shunbetu/<yyyy>/csv/<yy><mm><旬>h_tosi.csv`（Shift_JIS） | 不要 | なし（14 都市。四国は高松市） | 卸売価格、円 / kg、旬（10 日） | 2026 年 10 月中旬（2026-10-26 更新） | 予備 |
| 農水省 青果物市況情報 CSV | 画面操作の POST を再現 | 不要 | あり（日次） | 卸売価格、日次 | - | 不採用（1 日では重い） |
| e-Stat API | REST / JSON | appId が必要 | あり | - | - | 不採用（キー） |
| WAGRI 青果物市況 API | REST / JSON | 申請が必要 | あり | 日次 | - | 不採用（キー、会員費） |
| 統計ダッシュボード API | REST / JSON | 登録不要とされる | 未確認 | - | - | 未確認（調査環境からは接続できず） |
| 札幌市中央卸売市場の CSV | ダウンロード | 不要 | なし | 札幌のみ | - | 不採用 |

### 8.2 実際に取れた値（e-Stat、2026 年 9 月、松山市、円 / kg）

| 品目 | 価格 | 品目 | 価格 |
|---|---|---|---|
| キャベツ | 229 | きゅうり | 810 |
| だいこん | 294 | なす | 767 |
| たまねぎ | 348 | トマト | 997 |
| にんじん | 428 | ほうれんそう | 1,806 |
| じゃがいも | 532 | さつまいも | 709 |
| みかん | 781 | キウイフルーツ | 1,310 |

柿は 9 月に調査がないため、直近の 2025 年 12 月の値（683）を使う。

ファイルはシート `B001-1`。11 行目が見出しで、`銘柄符号`（例 1401 キャベツ）と `品目` と `単位` の列のあと、都市ごとの列が並ぶ。松山市は見出しが「松山市」の列を名前で探して読む（列番号に依存しない）。

### 8.3 取り込み方

1. e-Stat のファイル一覧（小売物価統計調査・動向編・月次）から最新月のページを開き、「主要品目の都市別小売価格」（1001〜2183）の Excel の ID を探す。
2. Excel を読み、松山市の品目単価を取り出す。その月に調査のない品目は、さかのぼって直近の月の値を使う。
3. Amplify 版では `/api/prices` がこれを行い、DynamoDB に 24 時間キャッシュする（Excel は `exceljs` で読む）。
4. デモ画面では `tools/update_prices.py` が同じ手順で取り込み、HTML に値を書き込む（e-Stat はブラウザからの直接取得を許可していないため）。
5. 画面に「出典：政府統計の総合窓口（e-Stat）小売物価統計調査をもとに作成。小売価格による目安」と表示する。

### 8.4 予備（農水省 旬別 CSV）を使う場合

URL の規則が決まっているので、ファイル ID の更新が要らない。ただし松山がないため、高松市の卸売価格を「四国の目安」として使うことになる。e-Stat に障害があったときの予備にする。

### 8.5 出典
- e-Stat 小売物価統計調査（動向編）ファイル一覧：https://www.e-stat.go.jp/stat-search/files?toukei=00200571&tstat=000000680001
- 総務省統計局 小売物価統計調査 調査結果：https://www.stat.go.jp/data/kouri/doukou/3.htm
- 農林水産省 青果物卸売市場調査（旬別結果）：https://www.maff.go.jp/j/tokei/syohi/shunbetu/2026/hinmoku.html
- WAGRI 青果物市況情報取得 API：https://wagri.naro.go.jp/wagri_api/freshmarketinformation-get-freshmarketinformationid/
- 札幌市中央卸売市場 青果部取引情報：https://www.sapporo-market.gr.jp/statistics-fv/
- 地理院タイル一覧：https://maps.gsi.go.jp/development/ichiran.html
- 気象庁 天気予報：https://www.jma.go.jp/bosai/forecast/

## 9. デモ画面（HTML）との対応

デモ画面はサーバーなしで動く HTML で、データはブラウザの中に持っている。Amplify 版では、同じ画面の裏側を 3 章の API と DynamoDB に置き換える。

| 機能 | デモ画面での実装 | Amplify 版での実装 |
|---|---|---|
| 日付 | 開いた日を「今日」として、募集の日付・締切・予定を自動でずらして表示 | DynamoDB の実データ。日付は日本時間で扱う |
| 募集の自動生成 | 募集の少ない日に、農家の募集をもとに自動でつくる（開いた日で組み合わせが変わる） | 農家が募集画面で登録。デモ用には `scripts/seed.ts` で投入 |
| 地図 | Leaflet + 地理院タイル（ブラウザから直接） | 同じ |
| 天気 | 気象庁の予報 JSON をブラウザから直接取得し、30 分保存 | `/api/weather` でキャッシュして返す |
| 野菜価格・お礼の換算 | `tools/update_prices.py` で e-Stat から取り込んだ値を HTML に保存し、画面で計算 | `/api/prices`・`/api/prices/calc` |
| 応募締切 | 現在時刻で判定し、締切後はカードと地図のピンをグレー、応募ボタンを押せなくする。1 分ごとに再判定 | `deadlineAt` をサーバー時刻で判定（3.4） |
| 1 日 1 件 | 同じ日に予定がある募集は「応募できません」画面を出し、ほかの日をすすめる | `TransactWriteItems` で判定（3.4） |
| 参加リクエスト | あおいさんからのリクエストに、同意して「参加する」/「参加しない」で回答 | `/api/party-requests` |
| メンバー連携（送る側） | ID で検索 → リクエスト → 相手の画面（デモ）で承認 → 確認コード 4821 を入力 | `/api/links`・`/confirm` |
| メンバー連携（受け取る側） | なつさんからのリクエストを、お知らせ・参加メンバー画面から開き、承認 → コード 3907 を表示 → 連携完了 | `/api/links/{id}/approve` |
| メッセージ | 農家・グループ・運営の 3 種類（農家モードは参加者・グループ・個別の質問） | `/api/threads` |
| QR チェックイン | 画面の流れのみ（デモ） | `/api/qr/issue`・`/api/checkin` |
| ログイン | なし（みどり @midori_mtym として表示。農家モードに切り替え可） | 1 日目はなし。公開運用で Cognito を追加 |
