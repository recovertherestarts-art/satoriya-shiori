# POSIX環境向けテスト（Linux / macOS）

里々（SATORI）の POSIX 共有ライブラリ（`libsatori.so` / `libsatori.bundle`）を `dlopen` して動作確認するための CLI テスト環境です。

## テストプログラム一覧

- `posix_smoke.c`: SHIORI 応答の smoke テスト (`load`, `request`, `unload`)
- `posix_savedata.c`: 里々のセーブデータ動作（ファイル書き出し、読み戻し、バックアップ作成、一時ファイル管理、保存失敗時の保護、テスト間独立性）の自動テスト

## ビルドと実行方法

### 1. 本体のビルド

```bash
cd satoriya/satori
make -f makefile.linux
```

### 2. コンパイルとテスト実行

```bash
# Smoke テスト
cc -o posix_smoke satoriya/test/posix/posix_smoke.c -ldl
mkdir -p ghost
cp satoriya/test/posix/ghost/*.txt ghost/
./posix_smoke "$PWD/satoriya/satori/libsatori.so" "$PWD/ghost"

# セーブデータ テスト
cc -o posix_savedata satoriya/test/posix/posix_savedata.c -ldl
./posix_savedata "$PWD/satoriya/satori/libsatori.so" "$PWD/satoriya/test/posix/ghost_savedata"
```

## 注意事項

- Windows 固有の `DeleteFile` や `MoveFile` に依存する挙動（Windows OS におけるファイルロック競合や置換の非アトミック性など）は、本 POSIX テストの保証対象外です。
- リポジトリ内のフィクスチャ (`satoriya/test/posix/ghost_savedata/`) は実行中に変更されず、テストごとに `/tmp` 配下へコピーされた一時ディレクトリ内で検証されます。
