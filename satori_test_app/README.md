# Satori Test App for Jules

里々（Satori）のスクリプトをテストするためのPython製ツールです。
複雑なループ構造や多段階の条件分岐、変数の代入・参照などが意図通りに動作するかを検証できます。

## 構成
- `runner.py`: テスト実行用メインスクリプト
- `core/parser.py`: 辞書ファイル（dic*.txt）のパース処理
- `core/interpreter.py`: 里々エミュレータ（条件分岐、ループ、関数、ジャンプ等）

## 使い方
以下のコマンドでテストを実行します。

```bash
python3 runner.py <ゴーストのパス> <テスト定義ファイル(.json)>
```

例：
```bash
python3 runner.py ../kampo-ghost kampo_tests.json
```

## テスト定義ファイルの書き方
JSON形式でテストケースを記述します。

```json
[
  {
    "name": "テスト名称",
    "event": "発火させるイベント名（OnBootなど）",
    "references": ["Reference0の値", "Reference1の値"],
    "mocks": {
      "variables": {
        "現在時": "12",
        "ユーザ名": "Jules"
      },
      "saori": {
        "SAORI名": "返り値"
      }
    },
    "expected": "出力に含まれるべき文字列（または /正規表現/）",
    "expected_variables": {
      "期待する変数名": "期待する値"
    }
  }
]
```

## サポートしている機能
- **制御構文**: `if`, `when`, `unless`, `iflist`, `whenlist`, `switch`, `nswitch`
- **ループ**: `loop`, `for`, `times`
- **ジャンプ**: `＞`, `≫` （条件付きジャンプ、多段階ジャンプ対応）
- **変数**: `＄変数名【タブ】値`, `＄変数名＝式`
- **関数**: `calc`, `split`, `replace`, `nop`, `call`, `バイト値`, `乱数` など
- **その他**: 全角・半角の同一視（一部）、SakuraScriptスコープ切替（`：`）

## 注意事項
- 本ツールはエミュレータであり、実際の `satori.dll` とは細部の挙動が異なる場合があります。
- SAORIはWindows用DLLのため直接実行できません。`mocks` を使用して戻り値を定義してください。
