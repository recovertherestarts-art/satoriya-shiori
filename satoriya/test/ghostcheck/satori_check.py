#!/usr/bin/env python3
"""里々の辞書を libsatori.so で実際に動かして確かめる、Linux 用の小さなチェッカー。

使い方:
    python3 satori_check.py <libsatori.so> <ゴーストの master フォルダ> [オプション]

オプション:
    --runs N         1 イベントあたりの発火回数（既定 30。里々は候補をランダムに選ぶので複数回踏む）
    --expect FILE    期待ファイル（下記）
    --all            On で始まらない ＊名前 も全部発火する（内部ラベルを含むので 204 の警告が増える）
    --strict         警告（全角括弧の残り・204）も失敗扱いにする
    --engine-log     里々が標準出力/標準エラーに出したデバッグ出力を表示する
    --events FILE    SHIORI イベント一覧の JSON（events/shiori_events.json）。On で始まる標準イベントを
                     全部、仕様どおりの個数の Reference を付けて発火し、辞書が反応するかを数える
    --ref-value V    --events で Reference に入れるダミー値（既定 0）
    --coverage       --events のとき、反応した/しなかったイベント名の一覧も表示する

やること:
  1. フォルダ内の *.txt（dic*.txt、satori_conf.txt、replace.txt など）を一時フォルダにコピーして load する。
     元のフォルダにセーブデータなどを書かないため。
  2. dic*.txt から ＊イベント名 を拾い、既定では On で始まるものだけを N 回発火する。
     （＊検索１ のような内部ラベルは ＞ からのジャンプ先で、単体で呼ぶ前提ではないため。）
  3. 次のどれかに当たれば失敗として報告し、終了コード 1 で終わる。
       - ErrorLevel / ErrorDescription ヘッダが付く（辞書の構文エラー。以降の定義は読み込まれない）
       - SHIORI/3.0 200 OK / 204 以外が返る / request が NULL を返す
       - 期待ファイルに書いたゴールを満たさない
  3b. --events を付けると、標準イベント（JSON の On*）を 1 つずつ発火して、構文エラー・異常応答がないことと、
     辞書が反応した（200）か無反応（204）かを数える。標準イベントの 204 は「その辞書がそのイベントを
     持っていない」だけなので、警告にも失敗にもしない。ダミー値の Reference では出力の正しさまでは
     判定できないので、中身を確かめたいイベントは期待ファイルに書く。
  4. 次は警告（--strict で失敗）。
       - Value に全角の （ ） が残っている（未定義の関数・変数はエラーにならず、括弧ごと出力されるため）
       - 発火した全部が 204 No Content（条件付きのイベントなら正常。期待ファイルに書いた場合は失敗）

期待ファイル（任意。複雑な辞書でゴールを書いておく用）:
    # コメント
    イベント名<TAB>応答に含まれるべき文字列
    イベント名<TAB>!応答に含まれてはいけない文字列
    イベント名[R0=値|R1=値]<TAB>...      Reference0, Reference1 ... を付けて発火する（入力ボックスやクリックの再現）
    @runs 1                              以降の発火回数（既定は --runs）。@runs default で戻す
  - 「含まれるべき」は発火のうちどれか 1 回に出れば OK（ランダム候補を考慮）。
    「含まれてはいけない」は 1 回でも出たら失敗。
  - 期待ファイルに書いたものは、書いた順に、自動の発火より先に実行する。
    同じイベント＋Reference が続く行は 1 回にまとめて発火し、離れていれば別々に発火する。
    セーブデータ（＄の変数）は同じ実行の中で引き継がれるので、順番を使って状態の変化を確かめられる。
  - Reference の値に | と改行は使えない。
  - Value は SHIORI の応答そのまま（さくらスクリプト込み）なので、文字列は
    \\0 \\n などを含まない部分（セリフの文面）で書くのが楽。

注意:
  - 辞書は UTF-8 で書く（unicode ブランチ向け）。
  - 第 1 引数は libsatori.so（makefile.linux の出力）。
"""
import argparse
import ctypes
import glob
import os
import re
import shutil
import sys
import tempfile

TAB_MARK = "【タブ】"
EVENT_RE = re.compile(r"^[＊*]\s*(\S+)")
HEAD_RE = re.compile(r"^([^\[]+)(?:\[(.*)\])?$")
REF_RE = re.compile(r"^R(\d+)=(.*)$")
RUNS_RE = re.compile(r"^@runs\s+(\d+|default)\s*$")


def load_library(path):
    libc = ctypes.CDLL(None)
    libc.malloc.restype = ctypes.c_void_p
    libc.malloc.argtypes = [ctypes.c_size_t]
    libc.free.argtypes = [ctypes.c_void_p]

    lib = ctypes.CDLL(os.path.abspath(path))
    lib.load.argtypes = [ctypes.c_void_p, ctypes.c_long]
    lib.load.restype = ctypes.c_int
    lib.request.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_long)]
    lib.request.restype = ctypes.c_void_p
    lib.unload.restype = ctypes.c_int
    return lib, libc


class Shiori:
    """load / request / unload は渡したバッファを free するので、malloc したものを渡す。"""

    def __init__(self, lib_path, ghost_dir):
        self.lib, self.libc = load_library(lib_path)
        path = (ghost_dir.rstrip("/") + "/").encode()
        if not self.lib.load(self._heap(path), len(path)):
            raise RuntimeError("load に失敗しました: " + ghost_dir)

    def _heap(self, data):
        p = self.libc.malloc(len(data) + 1)
        ctypes.memmove(p, data + b"\0", len(data) + 1)
        return p

    def get(self, event_id, refs=(), bare=False):
        if bare:
            ref_lines = ""
        elif refs:
            ref_lines = "".join("Reference%d: %s\r\n" % (n, v) for n, v in refs)
        else:
            ref_lines = "Reference0: master\r\n"
        req = (
            "GET SHIORI/3.0\r\nCharset: UTF-8\r\nSender: SSP\r\n"
            "SecurityLevel: local\r\nID: %s\r\n%s\r\n" % (event_id, ref_lines)
        ).encode("utf-8")
        n = ctypes.c_long(len(req))
        p = self.lib.request(self._heap(req), ctypes.byref(n))
        if not p:
            return None
        text = ctypes.string_at(p, n.value).decode("utf-8", "replace")
        self.libc.free(p)
        return text

    def close(self):
        self.lib.unload()


def parse_response(text):
    lines = text.replace("\r\n", "\n").split("\n")
    parts = lines[0].split() if lines else []
    code = parts[1] if len(parts) > 1 else ""
    headers = {}
    for line in lines[1:]:
        if ": " in line:
            k, v = line.split(": ", 1)
            headers[k] = v
    return code, headers


def find_events(dic_files):
    events = []
    for f in dic_files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = EVENT_RE.match(line)
                if not m:
                    continue
                # replace.txt で 【タブ】 がタブに置き換わる辞書があるので、その手前までを名前とする
                name = m.group(1).split(TAB_MARK)[0]
                if name and name not in events:
                    events.append(name)
    return events


def label_of(event, refs):
    if not refs:
        return event
    return "%s[%s]" % (event, "|".join("R%d=%s" % (n, v) for n, v in refs))


def parse_head(head, path, lineno):
    m = HEAD_RE.match(head.strip())
    if not m:
        sys.exit("%s:%d: イベント名の書式が違います: %s" % (path, lineno, head))
    event, refs = m.group(1).strip(), []
    if m.group(2):
        for item in m.group(2).split("|"):
            rm = REF_RE.match(item)
            if not rm:
                sys.exit("%s:%d: Reference は R0=値 の形で書きます: %s" % (path, lineno, item))
            refs.append((int(rm.group(1)), rm.group(2)))
    return event, tuple(sorted(refs))


def read_expect(path):
    """[{event, refs, runs, wants}] を書いた順に返す。同じイベント＋Reference が続く行は 1 つにまとめる。"""
    scenarios, runs = [], None
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            rm = RUNS_RE.match(line)
            if rm:
                runs = None if rm.group(1) == "default" else int(rm.group(1))
                continue
            if "\t" not in line:
                sys.exit("%s:%d: 期待ファイルの書式が違います（タブ区切り）: %s" % (path, lineno, line))
            head, want = line.split("\t", 1)
            event, refs = parse_head(head, path, lineno)
            last = scenarios[-1] if scenarios else None
            if last and last["event"] == event and last["refs"] == refs and last["runs"] == runs:
                last["wants"].append(want)
            else:
                scenarios.append({"event": event, "refs": refs, "runs": runs, "wants": [want]})
    return scenarios


def read_events_json(path, ref_value):
    """SHIORI イベント一覧の JSON から On で始まる標準イベントを読む。[(名前, 説明, refs)] を返す。

    平らな形（名前 → {Compatibility, Description, References}）も、カテゴリ → 平らな形 の入れ子も読める。
    On で始まらない項目は、イベントではなく仕様書の項目名（installedballoonname など）なので無視する。
    Reference は ReferenceN（N は数字）だけを数え、Reference* や Reference3～ のような書き方は無視する。
    """
    import json

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    flat = {}
    for k, v in data.items():
        if isinstance(v, dict) and "References" in v:
            flat[k] = v
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, dict) and "References" in v2:
                    flat.setdefault(k2, v2)
    events = []
    for name, info in flat.items():
        if not name.startswith("On"):
            continue
        nums = sorted(
            int(m.group(1)) for m in (re.fullmatch(r"Reference(\d+)", r) for r in info.get("References", {})) if m
        )
        # 0 から最大の番号まで連続して付ける（途中が抜けていると里々側で番号がずれるため）
        refs = tuple((n, ref_value) for n in range(nums[-1] + 1)) if nums else ()
        events.append((name, info.get("Description", ""), refs))
    return events


def fire(sh, event, refs, runs, engine_errors, bare=False):
    values, n204, bad = [], 0, None
    for _ in range(runs):
        text = sh.get(event, refs, bare)
        if text is None:
            bad = "request が NULL を返した"
            break
        code, headers = parse_response(text)
        if "ErrorLevel" in headers or "ErrorDescription" in headers:
            engine_errors.add(
                "[%s] %s" % (headers.get("ErrorLevel", "?"), headers.get("ErrorDescription", "").strip())
            )
        if code == "204":
            n204 += 1
            continue
        if code != "200":
            bad = "応答が %s でした" % (code or "不明")
            break
        values.append(headers.get("Value", ""))
    return values, n204, bad


def main():
    ap = argparse.ArgumentParser(description="里々の辞書を実際に発火させて確かめる")
    ap.add_argument("library", help="libsatori.so のパス")
    ap.add_argument("dicdir", help="dic*.txt が入ったフォルダ（ghost/master）")
    ap.add_argument("--runs", type=int, default=30, help="1イベントあたりの発火回数")
    ap.add_argument("--expect", help="期待ファイル")
    ap.add_argument("--all", action="store_true", help="On で始まらない ＊名前 も発火する")
    ap.add_argument("--strict", action="store_true", help="警告（全角括弧・204）も失敗扱いにする")
    ap.add_argument("--engine-log", action="store_true", help="里々のデバッグ出力を表示する")
    ap.add_argument("--events", help="SHIORI イベント一覧の JSON")
    ap.add_argument("--ref-value", default="0", help="--events で Reference に入れるダミー値")
    ap.add_argument("--coverage", action="store_true", help="--events の反応した/しなかった一覧を表示する")
    args = ap.parse_args()

    dic_files = sorted(glob.glob(os.path.join(args.dicdir, "dic*.txt")))
    if not dic_files:
        sys.exit("dic*.txt が見つかりません: " + args.dicdir)
    events = find_events(dic_files)
    scenarios = read_expect(args.expect) if args.expect else []
    std_all = read_events_json(args.events, args.ref_value) if args.events else []
    if not events and not scenarios and not std_all:
        sys.exit("＊イベントが 1 つも見つかりません")

    # 期待ファイルに書いたイベントは、書いたとおりに発火するので自動・標準の対象から外す。
    # 標準イベントは仕様どおりの Reference を付けて発火するので、辞書から拾った自動の対象からも外す。
    in_expect = {s["event"] for s in scenarios}
    std = [e for e in std_all if e[0] not in in_expect]
    std_names = {e[0] for e in std_all}
    if args.all:
        auto = [e for e in events if e not in in_expect and e not in std_names]
    else:
        auto = [e for e in events if e.startswith("On") and e not in in_expect and e not in std_names]

    # セーブデータ等で元のフォルダを汚さないよう、一時フォルダにコピーして動かす
    work = tempfile.mkdtemp(prefix="satori_check_")
    expect_abs = os.path.abspath(args.expect) if args.expect else None
    for f in glob.glob(os.path.join(args.dicdir, "*.txt")):
        if os.path.abspath(f) != expect_abs:
            shutil.copy(f, work)

    # 里々は標準出力にデバッグ出力を出すことがあるので、実行中はファイルに逃がして結果と混ざらないようにする
    log_fd, log_path = tempfile.mkstemp(prefix="satori_engine_log_")
    sys.stdout.flush()
    sys.stderr.flush()
    saved = (os.dup(1), os.dup(2))
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)

    lines, failures, warnings = [], [], []
    engine_errors = set()
    try:
        sh = Shiori(args.library, work)

        # 何も発火しなくても構文エラーを拾えるよう、存在しない ID で 1 回だけ呼ぶ
        # （構文エラーがあると、どのリクエストの応答にも ErrorLevel が付く）
        fire(sh, "ghostcheck_probe", (), 1, engine_errors)

        def check(event, refs, runs, wants, standard=False):
            """"handled"（反応した）/ "silent"（全部 204）/ "failed" を返す。"""
            label = event if standard else label_of(event, refs)
            values, n204, bad = fire(sh, event, refs, runs, engine_errors, bare=standard and not refs)
            if bad:
                failures.append("%s: %s" % (label, bad))
                return "failed"
            has_positive = any(not w.startswith("!") for w in wants)
            if not values:
                if not standard:
                    msg = "%s: %d 回とも 204 No Content（応答が空。条件付きのイベントなら正常）" % (label, n204)
                    (failures if args.strict or has_positive else warnings).append(msg)
                return "silent"
            note = "" if not n204 else "（%d/%d 回は 204）" % (n204, runs)
            lines.append("OK  %-24s 異なる応答 %d 通り%s" % (label, len(set(values)), note))
            for v in sorted(set(values)):
                if "（" in v or "）" in v:
                    msg = "%s: 全角括弧が残っている（未定義の関数・変数の疑い）: %s" % (label, v)
                    (failures if args.strict else warnings).append(msg)
                    break
            for want in wants:
                if want.startswith("!"):
                    if any(want[1:] in v for v in values):
                        failures.append("%s: 含まれてはいけない文字列が出た: %s" % (label, want[1:]))
                elif not any(want in v for v in values):
                    failures.append("%s: %d 回発火しても期待する文字列が出なかった: %s" % (label, len(values), want))
            return "handled"

        for s in scenarios:
            check(s["event"], s["refs"], s["runs"] if s["runs"] is not None else args.runs, s["wants"])
        for ev in auto:
            check(ev, (), args.runs, [])
        std_result = {"handled": [], "silent": [], "failed": []}
        for name, _desc, refs in std:
            std_result[check(name, refs, args.runs, [], standard=True)].append(name)
        sh.close()
    finally:
        ctypes.CDLL(None).fflush(None)
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])
        os.close(log_fd)
        try:
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                engine_log = fh.read()
        finally:
            os.remove(log_path)
            shutil.rmtree(work, ignore_errors=True)

    for e in sorted(engine_errors):
        # エラー文に出る一時フォルダのパスを、元の辞書フォルダに戻して読みやすくする
        failures.append("里々のエラー: " + e.replace(work, args.dicdir.rstrip("/")))

    for l in lines:
        print(l)
    for w in warnings:
        print("WARN " + w)
    for f in failures:
        print("NG   " + f)
    if engine_log.strip():
        if args.engine_log:
            print("--- 里々のデバッグ出力 ---")
            print(engine_log.rstrip())
            print("--- ここまで ---")
        else:
            print("INFO 里々のデバッグ出力が %d 行ありました（--engine-log で表示）" % len(engine_log.splitlines()))
    if args.events:
        print("--- 標準イベント %d 個: 反応あり %d / 無反応（204）%d / 失敗 %d" % (
            len(std), len(std_result["handled"]), len(std_result["silent"]), len(std_result["failed"])))
        if args.coverage:
            print("反応あり: " + ", ".join(std_result["handled"]))
            print("無反応: " + ", ".join(std_result["silent"]))
    print("--- 発火 %d 個（期待ファイル %d / 自動 %d / 標準 %d） / 失敗 %d / 警告 %d" % (
        len(scenarios) + len(auto) + len(std), len(scenarios), len(auto), len(std), len(failures), len(warnings)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
