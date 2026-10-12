# YaoTubng

Windows 11 向け、個人利用の YouTube / YouTube Music 音声ダウンローダーの試作です。
Python + PySide6 の画面から yt-dlp を独立したプロセスで呼び出します。サーバー、広告、テレメトリーはありません。

## 今できること

- 曲・動画 URL １件の音声専用形式を確認する。URL にプレイリスト指定があっても１件だけ扱います。
- 自動選択、または取得可能な形式 ID を指定して、元の形式（M4A / WebM など）で保存する。
- 進捗・残り時間を表示し、処理をキャンセルする。終了時も取得処理を止めます。
- ログインなし、Edge / Chrome / Firefox の既定プロファイル、ローカル Cookie ファイルを選ぶ。
- 完成ファイルを NTFS 上で原子的に確定し、同名ファイル・シンボリックリンクを上書きしない。

MP3 変換、タグ編集、プレイリストの一括取得、キューの永続化、途中終了後の再開は次の段階です。
取得中の `.part` は作業フォルダーに置かれ、通常終了・キャンセル時に片付けます。OS やアプリ自体の強制終了時には残る場合があります。
音声の再エンコードはしませんが、yt-dlp がコンテナーの修復に FFmpeg を使う場合があります。

## Windows 11 で準備する

Python 3.12（64 bit）、FFmpeg、Node.js 22 以上が必要です。例として Windows Terminal / PowerShell から：

```powershell
winget install --exact --id Python.Python.3.12
winget install --exact --id Gyan.FFmpeg
winget install --exact --id OpenJS.NodeJS.LTS
```

インストール後は Terminal を開き直してください。リポジトリを手元に取得して、そのフォルダーから実行します。

```powershell
.\scripts\setup.ps1
.\scripts\run.ps1
```

スクリプト実行が端末のポリシーで制限される場合は、同じ処理を直接実行できます。ポリシーを変更する必要はありません。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e ".[dev]"
.\.venv\Scripts\python.exe -m yaotubng.cli doctor
.\.venv\Scripts\python.exe -m yaotubng.app
```

保存先はローカルの NTFS ドライブを選んでください。FAT / exFAT などハードリンク非対応の保存先には、完成ファイルを保存せずエラーにします。
音声形式の WebM（Opus）と M4A（AAC）はコーデックが異なるため、ビットレートの数字だけで音質を比較しないでください。

## Premium の動作確認

Premium の公式オフライン保存と、音声ファイルとしての取得は別機能です。Premium 契約だけでは取得可否を保証できません。
まずログインなしで形式を確認し、次に同じ URL を認証ありで確認して、提供される形式の違いを比較します。
アプリは yt-dlp が返した実際の形式を表示し、存在しない高品質形式を約束しません。DRM の解除機能はありません。

1. 手元のブラウザーで YouTube にログインする。
2. アプリで同じブラウザーを選び「形式を確認」を押す。
3. 必要ならブラウザーを閉じて再確認する。Windows の暗号化方式によっては読み取りに対応できません。
4. 対応しない場合は、本人が安全に用意した Netscape 形式の Cookie ファイルをローカルで選択する。

Cookie はログイン情報です。**チャット・クラウド環境・Git には送らないでください。**
Cookie ファイルを使う場合は一時コピーを作り、元ファイルは更新しません。処理終了時に一時コピーを削除します。
ブラウザー認証は既定プロファイルのみを対象にしています。アプリは Cookie や認証設定を保存しません。
通常のファイル削除は暗号学的な消去を保証しないため、PC のアクセス権やディスク暗号化も本人の管理に依存します。

## アクセスを集中させない設計

並列ジョブなし、フラグメント並列数１、情報取得リクエスト間２秒、取得開始前３秒待機。
失敗時の自動再試行は無効です。制限や認証確認が発生したら停止し、利用者が状況を確認します。
これらはアクセス集中を抑えるための設定で、YouTube の検知・遮断やアカウントへの影響を防ぐ保証ではありません。
プロキシの切り替えやアクセス制限を迂回する機能はありません。

## CLI と開発

GUI と同じエンジンを使って、手元で形式を比較できます。

```powershell
.\.venv\Scripts\python.exe -m yaotubng.cli inspect "https://music.youtube.com/watch?v=VIDEO_ID"
.\.venv\Scripts\python.exe -m yaotubng.cli inspect "https://music.youtube.com/watch?v=VIDEO_ID" --browser edge
.\.venv\Scripts\python.exe -m yaotubng.cli download "https://music.youtube.com/watch?v=VIDEO_ID" --output "C:\Users\YOUR_NAME\Music\YaoTubng" --format best
.\.venv\Scripts\python.exe -m pytest
```

`VIDEO_ID` は実際の11文字の動画 ID に置き換えます。CLI の出力は JSON Lines です。Cookie やストリーム URL は出力しません。
CLI のキャンセルは Ctrl+C。Windows のプロセスツリー終了を含むキャンセルは GUI 側で実装しています。

Linux のクラウドでは既存チェックアウトを使用します。新しい Git worktree は不要です。

```bash
bash scripts/setup.sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

自動テストはローカル HTTP サーバーと生成した音声を使い、実際の yt-dlp で取得・保存を検証します。
Premium、Windows のブラウザー Cookie 復号、Windows 実画面での操作は手元での確認が必要です。

### 更新

`requirements.lock` は検証時の依存バージョンを固定しています。YouTube 側の変更で取得できなくなった場合は、
yt-dlp と `yt-dlp-ejs` を一緒に更新し、形式確認・公開音声の取得・テストを再確認してからロックを更新します。
TLS 検証は常に有効です。JavaScript 補助コンポーネントは Python パッケージから使い、実行時のリモート配布物取得は有効にしていません。

### ファイル構成

- `core.py`: URL・認証指定の検証、Windows ファイル名、上書きしない保存
- `engine.py`: yt-dlp、音声形式、進捗、認証情報の一時利用
- `worker.py` / `controller.py`: 子プロセス通信、キャンセル、後片付け
- `app.py`: デスクトップ画面
- `cli.py`: ツール診断・形式確認・保存
- `tests/`: 保存・認証保護・実取得・画面・キャンセルの検証
