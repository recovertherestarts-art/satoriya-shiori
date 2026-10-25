# ghostcheck

里々の辞書を `libsatori.so` で実際に動かして、壊れていないかを確かめる Linux 用の小さなチェッカーです。
AI に書かせた辞書を定期的に確かめる用途を想定しています（SSP は要りません）。

## 準備

```
git submodule update --init --depth 1 satoriya/uka_regexp
make -C satoriya/satori -f makefile.linux -j"$(nproc)"      # satoriya/satori/libsatori.so ができる
```

必要なもの: gcc / g++ / make / iconv / Python 3。辞書は UTF-8 で書きます（unicode ブランチ向け）。

## 使い方

```
python3 satoriya/test/ghostcheck/satori_check.py satoriya/satori/libsatori.so <ghost/master のフォルダ> [--expect 期待ファイル] [--events events/shiori_events.json] [--coverage] [--runs 30] [--all] [--strict] [--engine-log]
```

フォルダ内の `*.txt`（`dic*.txt` のほか `satori_conf.txt`、`replace.txt` など）を一時フォルダにコピーして読み込みます。元のフォルダにセーブデータは書きません。

`dic*.txt` の `＊イベント名` のうち、**`On` で始まるもの**を `--runs` 回（既定 30 回）発火します。里々は候補をランダムに選ぶので、複数回発火して候補を踏みます。
`＊検索１` のような内部ラベルは、`＞` からのジャンプ先で単体で呼ぶ前提ではないので、既定では発火しません（`--all` で全部発火）。

| 結果 | 内容 |
|------|------|
| 失敗（NG、終了コード 1） | `ErrorLevel` / `ErrorDescription` が付く（辞書の構文エラー。**そのエラー以降の定義は読み込まれません**）／ 200・204 以外の応答／ `request` が NULL／期待ファイルのゴールを満たさない |
| 警告（WARN） | `Value` に全角の `（` `）` が残っている（未定義の関数・変数はエラーにならず、括弧ごと出力されるため）／発火した全部が 204（条件付きのイベントなら正常） |

`--strict` を付けると警告も失敗になります。里々が標準出力に出すデバッグ出力は結果と混ざらないよう別に取っておき、`--engine-log` のときだけ表示します。

## 標準イベントを全部発火する（`--events`）

`events/shiori_events.json` は SHIORI イベントの一覧です（名前・対応環境・説明・Reference の意味。ukadoc の内容を整理したもの）。
`--events` を付けると、このうち **`On` で始まる標準イベント 253 個**を、仕様に書かれた個数の Reference を付けて 1 つずつ発火します。
`installedballoonname` や `First` のような、イベントではなく仕様書の項目名にあたるものは無視します。

```
python3 satoriya/test/ghostcheck/satori_check.py satoriya/satori/libsatori.so <ghost/master> --events satoriya/test/ghostcheck/events/shiori_events.json [--coverage]
```

- 見ているのは「構文エラーや異常応答が出ないこと」と「辞書が反応するか」です。ダミー値の Reference（既定 `0`、`--ref-value` で変更）では出力の正しさまでは判定できないので、中身を確かめたいイベントは期待ファイルに書きます。
- 標準イベントの 204 は「その辞書がそのイベントを持っていない」だけなので、警告にも失敗にもしません。最後に `標準イベント 253 個: 反応あり 37 / 無反応 216 / 失敗 0` のように数えて出します。`--coverage` で名前の一覧も出ます。
- 辞書にある標準イベントは、辞書から拾った自動の発火ではなく、こちらの Reference つきで発火します。`On` で始まるが標準にないイベントは、これまでどおり自動で発火します。
- `events/` には、カテゴリ分けした形の JSON を渡しても読めます（同じ 253 個になります）。

## 期待ファイル（ゴールを書く）

```
# イベント名<TAB>応答に含まれるべき文字列（!で始めると含まれてはいけない文字列）
OnBoot	こんにちは。
OnBoot	!（

# Reference を付けて発火する（入力ボックスやクリックの再現）。値に | と改行は使えない
@runs 1
OnTeach[R0=茴香]	「茴香」を覚えたよ。
OnRecall	さっき教わったのは茴香だね。
```

- 「含まれるべき」は発火のうち 1 回でも出れば OK です。Value はさくらスクリプトのままなので、セリフの文面で書きます。
- 期待ファイルに書いたものは、書いた順に、自動の発火より先に実行します。同じイベント＋Reference が続く行は 1 回にまとめて発火します。
- `@runs N` は以降の発火回数です（`@runs default` で戻す）。セーブデータ（`＄` の変数）は同じ実行の中で引き継がれるので、状態を使うシナリオは `@runs 1` にして順番に書きます。
- 期待ファイルに書いたイベントが 204 だけだと失敗です。

## 例

| フォルダ | 内容 |
|----------|------|
| `examples/good` | 通る |
| `examples/bad` | 構文エラー（括弧の閉じ忘れ）で失敗 |
| `examples/warn` | 警告のみ（未定義の変数） |
| `examples/input` | 入力ボックス＋セーブデータの引き継ぎ（`@runs 1` と Reference） |
| `ghosts/KakkonKarokon` | 実際のゴーストの辞書と、入力ボックスの流れを確かめる `expect.txt` |
| `ghosts/Ariadnes_wool` | 実際のゴーストの辞書（`On*` を自動で発火。警告は条件付きのイベントと未設定の変数） |

## Jules などで定期実行する

```
git submodule update --init --depth 1 satoriya/uka_regexp
make -C satoriya/satori -f makefile.linux -j"$(nproc)"
python3 satoriya/test/ghostcheck/satori_check.py satoriya/satori/libsatori.so satoriya/test/ghostcheck/ghosts/KakkonKarokon/ghost/master --expect satoriya/test/ghostcheck/ghosts/KakkonKarokon/expect.txt --events satoriya/test/ghostcheck/events/shiori_events.json
```

終了コードが 0 なら成功、1 なら失敗です。

## 分かっていること / 分かっていないこと

- 構文エラーの `ErrorDescription` には行番号が出ません（括弧の不整合などの種別とファイル名だけ）。
- 構文エラーがあると、そのエラー以降の定義は読み込まれず 204 になります。204 の警告が並んでいるときは、先に `里々のエラー` が出ていないかを見てください。
- `--events` のダミー値の Reference で、辞書側が値を計算に使うと、里々のエラーや想定外の分岐になることがあります（その場合は失敗として出ます）。
- 時刻や `Reference` に依存する条件付きイベントは、既定の発火では 204 になることがあります。確かめたいときは期待ファイルで Reference を付けて書きます。
- SAORI を呼ぶ辞書、`replace.txt` を使う辞書での動作は確認していません（`*.txt` はコピーしますが、Linux では SAORI の DLL は動きません）。
