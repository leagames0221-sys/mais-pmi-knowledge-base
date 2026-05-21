"""MAIS PMI Knowledge Base demo 動画 全自動制作 pipeline (action-then-narration timing model)。

4 段 orchestrator:
  1. AivisSpeech HTTP API (Style-Bert-VITS2、 まお おちついた speaker_id=888753763) で 16 scene raw narration WAV 生成
  2. Playwright (Chromium、 1920x1080) で uvicorn live demo flow を navigate + WebM 録画 + 各 scene action_elapsed 計測
  3. action_elapsed + settle buffer を lead-in silence にして per-scene padded WAV build (narration が settled page 上で 流れる timing 保証)
  4. ffmpeg で WebM + narration WAV → MP4 最終合成 (SRT 字幕 burn-in + 末尾 credit overlay + tpad で video 末尾 frame clone)

narration writing rule (英字 brand 名 letter spelling 防御):
  - 「MAIS」 → 「マイス」、 「PMI」 → 「ピーエムアイ」 (3-letter acronym letter spell OK)
  - jargon 漢字化 (PMI → 経営統合、 GraphRAG → 関係性検索、 ADR → 意思決定記録)

precondition (起動済 / install 済 verify):
  - uvicorn http://127.0.0.1:8001/health = 200
  - AivisSpeech engine http://127.0.0.1:10101/version = 200
    起動: `.vendor/aivis-engine/Windows-x64/run.exe --host 127.0.0.1 --port 10101`
  - ffmpeg (PATH 上、 `winget install Gyan.FFmpeg`)
  - playwright + chromium (`pip install -r requirements-video.txt && playwright install chromium`)

run:
  PYTHONIOENCODING=utf-8 python -m scripts.produce_video
  → out_video/mais_pmi_knowledge_base_demo.mp4 (約 2 分、 1080p、 約 5-6 MB)

env var (override 可):
  SPEAKER_ID=<int>     default 888753763 (まお おちついた)
  PITCH_SCALE=<float>  default 0.0、 ±0.03 が natural 域 (Style-Bert-VITS2 model 制限、 SSoT § 3)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

# Windows cp932 console で ✅/❌/日本語 print fail 防御 (T1-T4 同 pattern、 cross-PJ universal)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ─── config ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "out_video"
TEMP_DIR = OUTPUT_DIR / "_temp"
UVICORN_URL = "http://127.0.0.1:8001"
ENGINE_URL = "http://127.0.0.1:10101"  # AivisSpeech-Engine standalone
SPEAKER_ID = int(os.environ.get("SPEAKER_ID", "888753763"))  # まお おちついた (cross-PJ 統一、 SSoT § 1)

LEAD_IN_SEC = 0.4    # legacy (--narration-only mode の fallback)
TRAIL_OUT_SEC = 0.4  # narration 終了から次 scene までの最低 silence
SETTLE_BUFFER_SEC = 0.3  # action 完了 (networkidle) 後 narration 開始 までの buffer

# pitchScale: AivisSpeech (Style-Bert-VITS2) は ±0.03 が natural 域、 超過で音割れ artifact (SSoT § 3)
PITCH_SCALE = float(os.environ.get("PITCH_SCALE", "0.0"))

VIEWPORT = {"width": 1920, "height": 1080}


# ─── scene definitions (id, duration_sec, action, narration_text) ────

@dataclass
class Scene:
    id: str
    duration: float
    action: Callable
    narration: str


def _scenes_factory() -> list[Scene]:
    """Playwright page を受け取り navigation を行う lambda 群を構築 (T5 PMI knowledge base + Lilli 型対話 demo)。

    pre-condition (script invocation 前):
      - uvicorn (port 8000) 起動済 (T5 src/api/app.py = FastAPI、 黒金 brand)
      - AivisSpeech (port 10101) 起動済

    T5 UI structure (src/api/app.py 順守):
      - landing (/) = h1「クレスマントル ティーファイブ + PMI Knowledge Base」 + 4 機能 + tech stack badges + verify badges
      - search (/search GET) = form (query textarea + industry + size + culture + financial + integration_type filter)
      - search results (/search POST) = 5 dim weighted similar case list + 推奨
      - lilli (/assistant GET) = form (query textarea + user_role select)
      - lilli response (/assistant POST) = citation array + similar cases + Lilli recommendation

    narration writing rules (video-pipeline SSoT § 3 順守、 Mode 8 trap 防御):
      - 「、」 を 1 文 1-2 個 max、 単語間空白除去
      - jargon literal 漢字化 (PMI → 経営統合、 GraphRAG → 関係性検索、 ADR → 意思決定記録)
      - 英字 brand 名 カタカナ化必須 (クレスマントル ティーファイブ + リリ)
    """

    def s1(p):
        """landing top show (クレスマントル ティーファイブ brand 提示)。"""
        p.goto(f"{UVICORN_URL}/")
        p.wait_for_load_state("networkidle")
        p.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")

    def s2(p):
        """tagline + 機能 4 件 (scope + Similar Case + リリ対話 + API Health) を expose。"""
        p.evaluate("window.scrollTo({top: 100, behavior: 'smooth'})")

    def s3(p):
        """tech stack badges show (GraphRAG / louvain / fugashi / 5 dim weighted / LangGraph 9 node DAG)。"""
        p.evaluate(
            "[...document.querySelectorAll('h2')].find(h => h.textContent.includes('tech stack'))"
            "?.scrollIntoView({behavior: 'smooth', block: 'center'})"
        )

    def s4(p):
        """verify evidence badges (8 gate + 248 test + 0 CVE + Ollama e2e smoke)。"""
        p.evaluate(
            "[...document.querySelectorAll('h2')].find(h => h.textContent.includes('verify evidence'))"
            "?.scrollIntoView({behavior: 'smooth', block: 'center'})"
        )

    def s5(p):
        """navigate to /search (Similar Case Search panel show)。"""
        p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        p.wait_for_timeout(500)
        p.locator("a.nav-link", has_text="Similar Case Search").click(timeout=10000)
        p.wait_for_url("**/search", timeout=10000)
        p.wait_for_load_state("networkidle")

    def s6(p):
        """search form 全体 show (query textarea + 5 dim filter literal 提示)。"""
        p.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")

    def s7(p):
        """search 実行 (textarea 既存 placeholder query で submit、 結果遷移を 90s timeout 待機)。"""
        # placeholder query で submit (textarea が空でも form は submit 可、 default 値が page 側で active)
        p.locator("textarea[name='query']").fill(
            "Day-1 で組合存続を決定。 同族経営 + 関西本社 + 製造業、 retention rate 向上の path を検索したい。"
        )
        p.wait_for_timeout(400)
        p.locator("button[type='submit']").click(timeout=90000)
        p.wait_for_url("**/search", timeout=90000)
        p.wait_for_load_state("networkidle", timeout=60000)

    def s8(p):
        """search results: top + similar case list (5 dim weighted similarity literal 提示)。"""
        p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")

    def s9(p):
        """search results: scroll to similar cases section (case 一覧 + 類似度 5 次元 score)。"""
        p.evaluate("window.scrollTo({top: 400, behavior: 'smooth'})")

    def s10(p):
        """navigate to /assistant (Lilli 対話 panel へ)。"""
        p.goto(f"{UVICORN_URL}/assistant")
        p.wait_for_load_state("networkidle")
        p.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")

    def s11(p):
        """lilli form show (query + user_role select 提示)。"""
        p.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")

    def s12(p):
        """lilli 実行 (placeholder query で submit、 LLM listwise + audit log emit 全 active)。"""
        p.locator("textarea[name='query']").fill(
            "Day-1 で組合存続 vs 解消 path の判断、 同族経営 + 関西本社 + 製造業 retention rate を最大化する経営統合strategy。"
        )
        p.wait_for_timeout(400)
        p.locator("button[type='submit']").click(timeout=90000)
        p.wait_for_url("**/assistant", timeout=90000)
        p.wait_for_load_state("networkidle", timeout=60000)

    def s13(p):
        """lilli response: top (リリ recommendation + LIL audit id 提示)。"""
        p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")

    def s14(p):
        """lilli response: scroll to citation array + similar cases section。"""
        p.evaluate("window.scrollTo({top: 500, behavior: 'smooth'})")

    def s15(p):
        """landing footer へ back (合成データ only + 移植段階 license note)。"""
        p.goto(f"{UVICORN_URL}/")
        p.wait_for_load_state("networkidle")
        p.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")

    def s16(p):
        """closing: 経営の責務を、 次の人へ (footer 静止)。"""
        p.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'})")

    return [
        # narration 16 件 (video-pipeline SSoT § 3 順守: 「、」 max + 空白除去 + jargon 漢字化 + Mode 8 brand カタカナ化)
        # duration 初期値は低め、 auto-sync logic が actual WAV + margin に literal 上書き (SSoT § 2)
        Scene("S1", 6.5, s1, "マイス。経営統合知識ベースのエーアイのご紹介です。"),
        Scene("S2", 8.0, s2, "本ツールは過去の経営統合事例と公開ペーパーをAIが構造化、若手コンサルの判断を支援します。"),
        Scene("S3", 8.0, s3, "関係性検索と単語の形態素解析、五次元類似度の組合せで競合に未収録の自社実績層を活かします。"),
        Scene("S4", 7.5, s4, "八項目の品質ゲートと累計248件の自動試験、既知脆弱性ゼロを継続的に検証しています。"),
        Scene("S5", 7.0, s5, "では実機で類似事例検索からご覧ください。"),
        Scene("S6", 7.5, s6, "業種、規模、文化、財務、統合タイプの五次元で過去事例を絞り込めます。"),
        Scene("S7", 8.5, s7, "ディーワンで組合存続を決定する場合の関西本社、製造業事例を検索します。"),
        Scene("S8", 8.0, s8, "五次元の重み付き類似度で最も近い事例を上位から自動提示します。"),
        Scene("S9", 8.0, s9, "業種文化財務の各次元別スコアと総合類似度を並列表示、根拠まで一目で確認できます。"),
        Scene("S10", 7.0, s10, "続いてリリ型対話を実行します。"),
        Scene("S11", 7.5, s11, "若手コンサルが状況を入力すると、過去事例とペーパー引用つき推奨を生成します。"),
        Scene("S12", 8.5, s12, "リテンション率最大化の経営統合戦略を問い合わせます、回答生成には数秒かかります。"),
        Scene("S13", 8.0, s13, "リリは推奨理由と引用元事例、関連ペーパーを明示、監査証跡も自動保存します。"),
        Scene("S14", 8.0, s14, "全推奨に引用配列が紐付き、若手コンサルでも判断根拠の検証が可能です。"),
        Scene("S15", 7.5, s15, "現段階は試作のため合成事例のみ、移植時に実事例とペーパー個別ライセンスを確認します。"),
        Scene("S16", 8.5, s16, "マイス。経営の責務を、次の人へ。ご清聴ありがとうございました。"),
    ]


SCENES = _scenes_factory()


# ─── helpers (T1-T4 literal inherit、 cross-PJ universal) ──────────

def info(msg: str) -> None:
    print(f"[produce_video] {msg}", flush=True)


def check_preconditions() -> None:
    """uvicorn / AivisSpeech / ffmpeg / playwright + chromium の起動確認 (T1-T4 literal inherit)。"""
    errors = []

    try:
        r = requests.get(f"{UVICORN_URL}/health", timeout=3)
        assert r.status_code == 200
        info(f"OK uvicorn live ({UVICORN_URL}/health = 200)")
    except Exception as e:
        errors.append(f"uvicorn 起動不能: {UVICORN_URL} ({e}). 別 shell で uvicorn を起動してください")

    try:
        r = requests.get(f"{ENGINE_URL}/version", timeout=3)
        assert r.status_code == 200
        info(f"OK AivisSpeech engine live ({ENGINE_URL}/version = {r.text.strip()})")
    except Exception as e:
        hint = ".vendor/aivis-engine/Windows-x64/run.exe --host 127.0.0.1 --port 10101 で起動してください (T1-T4 binary cross-PJ 共有可)"
        errors.append(f"AivisSpeech engine 起動不能: {ENGINE_URL} ({e}). {hint}")

    if shutil.which("ffmpeg") is None:
        errors.append("ffmpeg が PATH に不在。 `winget install Gyan.FFmpeg` で install してください")
    else:
        info(f"OK ffmpeg ({shutil.which('ffmpeg')})")

    try:
        from playwright.sync_api import sync_playwright  # noqa
        info("OK playwright (Python binding)")
    except ImportError:
        errors.append("playwright 未 install。 `pip install playwright && playwright install chromium` を実行してください")

    if errors:
        info("==== precondition error ====")
        for e in errors:
            info(f"  - {e}")
        sys.exit(1)


def aivis_synthesize(text: str) -> bytes:
    """AivisSpeech HTTP API で WAV bytes 生成 (Style-Bert-VITS2、 素 AI prosody、 T1-T4 literal inherit)。"""
    q = requests.post(
        f"{ENGINE_URL}/audio_query",
        params={"text": text, "speaker": SPEAKER_ID},
        timeout=15,
    )
    q.raise_for_status()
    q_json = q.json()
    if PITCH_SCALE != 0.0:
        q_json["pitchScale"] = PITCH_SCALE
    s = requests.post(
        f"{ENGINE_URL}/synthesis",
        params={"speaker": SPEAKER_ID},
        json=q_json,
        timeout=60,
    )
    s.raise_for_status()
    return s.content


def ffprobe_duration(path: Path) -> float:
    """ffprobe で WAV/WebM の長さ秒を取得 (T1-T4 literal inherit)。"""
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    )
    return float(out.decode().strip())


def make_padded_wav(scene: Scene, raw_wav_path: Path, out_path: Path, lead_in_sec: float | None = None) -> None:
    """raw WAV を scene.duration に合わせて lead-in + trail-out silence で sandwich pad (T1-T4 literal inherit)。"""
    lead = LEAD_IN_SEC if lead_in_sec is None else lead_in_sec
    raw_dur = ffprobe_duration(raw_wav_path)
    if raw_dur > scene.duration - lead - TRAIL_OUT_SEC:
        info(f"  WARN [{scene.id}] narration {raw_dur:.2f}s が scene {scene.duration:.1f}s (lead={lead:.2f}s) に対し tight、 trail_out 縮小")

    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(raw_wav_path),
            "-af", f"adelay={int(lead * 1000)}|{int(lead * 1000)},apad=whole_dur={scene.duration}",
            "-ar", "24000", "-ac", "1",
            str(out_path),
        ],
        check=True,
    )


def concat_narration(scene_padded_wavs: list[Path], out_path: Path) -> None:
    """全 scene padded WAV を concat demuxer で 1 本に結合 (T1-T4 literal inherit)。"""
    concat_list = TEMP_DIR / "concat_audio.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in scene_padded_wavs),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(out_path),
        ],
        check=True,
    )


def record_demo() -> Path:
    """Playwright で demo flow を録画、 WebM path 返却 (T1-T4 literal inherit、 SSoT § 4 Phase 2)。"""
    from playwright.sync_api import sync_playwright

    info("Playwright Chromium 起動中... (action-then-narration timing mode)")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--hide-scrollbars"],
        )
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(TEMP_DIR),
            record_video_size=VIEWPORT,
        )
        page = context.new_page()

        for scene in SCENES:
            raw_dur = getattr(scene, "raw_duration", 0.0)
            info(f"  [{scene.id}] action: {scene.narration[:30]}... (narration_raw={raw_dur:.2f}s)")
            t0 = time.time()
            scene.action(page)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            scene.action_elapsed = time.time() - t0
            narration_window_sec = raw_dur + SETTLE_BUFFER_SEC + TRAIL_OUT_SEC
            info(f"    action_elapsed={scene.action_elapsed:.2f}s, narration_window={narration_window_sec:.2f}s")
            page.wait_for_timeout(int(narration_window_sec * 1000))

        context.close()
        browser.close()

    webms = sorted(TEMP_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    if not webms:
        raise RuntimeError(f"WebM が {TEMP_DIR} に生成されなかった")
    return webms[-1]


def _fmt_srt_time(t: float) -> str:
    """SRT timestamp 形式 (HH:MM:SS,mmm) (T1-T4 literal inherit)。"""
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def generate_srt(out_path: Path) -> None:
    """16 scene narration を SRT に literal 出力。 action_elapsed set 済なら action-aware lead 使用。"""
    lines: list[str] = []
    cum = 0.0
    for i, scene in enumerate(SCENES, 1):
        action_elapsed = getattr(scene, "action_elapsed", None)
        lead = (action_elapsed + SETTLE_BUFFER_SEC) if action_elapsed is not None else LEAD_IN_SEC
        start = cum + lead
        end = cum + scene.duration - TRAIL_OUT_SEC
        cum += scene.duration
        lines.append(f"{i}\n{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n{scene.narration}\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def compose_final(webm: Path, narration: Path, out_mp4: Path) -> None:
    """WebM + narration WAV → MP4 (1080p / H.264 / AAC) + 字幕 burn-in + 末尾クレジット overlay (T1-T4 literal inherit)。

    drawtext / subtitles escape 戦略 + 末尾 7 秒 enable + Yu Gothic UI Bold + MarginV=30 全 T1-T4 同 logic。
    クレジット text は drawtext (視覚 only、 letter spelling 発火しない) のため roman OK。
    """
    credit_path = TEMP_DIR / "credit.txt"
    credit_path.write_text(
        "MAIS PMI Knowledge Base (PoC) / AivisSpeech: まお おちついた / 合成データ only",
        encoding="utf-8",
    )

    srt_path = TEMP_DIR / "narration.srt"
    generate_srt(srt_path)

    fontfile_escaped = "C\\:/Windows/Fonts/YuGothM.ttc"
    textfile_escaped = credit_path.as_posix().replace(":", "\\:")
    srt_escaped = srt_path.as_posix().replace(":", "\\:")

    narration_dur = ffprobe_duration(narration)
    video_dur = ffprobe_duration(webm)
    enable_from = max(0.0, narration_dur - 7.0)
    pad_sec = max(0.0, narration_dur - video_dur + 0.2)
    tpad_filter = f"tpad=stop_mode=clone:stop_duration={pad_sec:.2f}" if pad_sec > 0.01 else None

    subtitles_filter = (
        f"subtitles='{srt_escaped}':"
        "force_style='FontName=Yu Gothic UI Semibold,"
        "Fontsize=22,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,"
        "BackColour=&H80000000&,BorderStyle=1,Outline=2,Shadow=1,"
        "MarginV=30,Alignment=2'"
    )

    drawtext_filter = (
        f"drawtext=fontfile='{fontfile_escaped}':"
        f"textfile='{textfile_escaped}':"
        "fontcolor=white:fontsize=26:"
        "x=(w-text_w)/2:y=h-th-40:"
        "box=1:boxcolor=black@0.75:boxborderw=14:"
        f"enable='gte(t,{enable_from:.2f})'"
    )

    vf_parts = [f for f in (tpad_filter, subtitles_filter, drawtext_filter) if f]
    vf_chain = ",".join(vf_parts)
    if tpad_filter:
        info(f"  tpad: video {video_dur:.2f}s → narration {narration_dur:.2f}s (clone {pad_sec:.2f}s 末尾 frame)")

    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(webm),
            "-i", str(narration),
            "-vf", vf_chain,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-metadata", f"comment=AivisSpeech:speaker_id={SPEAKER_ID} / MAIS PMI Knowledge Base PoC / synthetic data only",
            str(out_mp4),
        ],
        check=True,
    )


# ─── main orchestrator ───────────────────────────────────────────────

def main() -> int:
    narration_only = "--narration-only" in sys.argv
    info("=== MAIS PMI Knowledge Base demo video pipeline (action-then-narration model) ===")
    if narration_only:
        info("(--narration-only mode: AivisSpeech synthesis のみ実行、 Playwright + ffmpeg compose skip)")
    OUTPUT_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)

    info("\n[0/3] precondition check")
    if narration_only:
        try:
            r = requests.get(f"{ENGINE_URL}/version", timeout=3)
            assert r.status_code == 200
            info(f"OK AivisSpeech engine live ({ENGINE_URL}/version = {r.text.strip()})")
        except Exception as e:
            info(f"AivisSpeech engine 起動不能: {ENGINE_URL} ({e})")
            sys.exit(1)
        if shutil.which("ffmpeg") is None:
            info("ffmpeg が PATH に不在")
            sys.exit(1)
        info(f"OK ffmpeg ({shutil.which('ffmpeg')})")
    else:
        check_preconditions()

    info(f"\n[1/4] AivisSpeech で {len(SCENES)} scene の raw narration WAV 生成 (padding は phase 3 で)")
    for scene in SCENES:
        raw = TEMP_DIR / f"{scene.id}_raw.wav"
        wav_bytes = aivis_synthesize(scene.narration)
        raw.write_bytes(wav_bytes)
        scene.raw_duration = ffprobe_duration(raw)
        info(f"  [{scene.id}] raw_duration={scene.raw_duration:.2f}s ({scene.narration[:25]}...)")

    if narration_only:
        info("\n[narration-only fallback] padded WAV を legacy fixed lead で build")
        padded_wavs: list[Path] = []
        for scene in SCENES:
            raw = TEMP_DIR / f"{scene.id}_raw.wav"
            padded = TEMP_DIR / f"{scene.id}_padded.wav"
            scene.duration = round(scene.raw_duration + LEAD_IN_SEC + TRAIL_OUT_SEC + 0.3, 1)
            make_padded_wav(scene, raw, padded)
            padded_wavs.append(padded)
        narration_wav = TEMP_DIR / "narration_full.wav"
        concat_narration(padded_wavs, narration_wav)
        listen_path = OUTPUT_DIR / "narration_only_preview.wav"
        shutil.copy(narration_wav, listen_path)
        return 0

    info(f"\n[2/4] Playwright で demo flow 録画 (action-then-narration model、 scene.action_elapsed 計測)")
    webm = record_demo()
    video_dur = ffprobe_duration(webm)
    info(f"  WebM: {webm.name} = {video_dur:.2f}s")
    info(f"  action_elapsed per scene (settled state 到達 wall-clock):")
    for scene in SCENES:
        info(f"    [{scene.id}] action_elapsed={scene.action_elapsed:.2f}s")

    info(f"\n[3/4] padded WAV build (lead_in = action_elapsed + {SETTLE_BUFFER_SEC}s settle buffer)")
    padded_wavs: list[Path] = []
    for scene in SCENES:
        raw = TEMP_DIR / f"{scene.id}_raw.wav"
        padded = TEMP_DIR / f"{scene.id}_padded.wav"
        lead = scene.action_elapsed + SETTLE_BUFFER_SEC
        scene.duration = round(lead + scene.raw_duration + TRAIL_OUT_SEC, 2)
        make_padded_wav(scene, raw, padded, lead_in_sec=lead)
        padded_wavs.append(padded)
        info(f"  [{scene.id}] lead={lead:.2f}s + raw={scene.raw_duration:.2f}s + trail={TRAIL_OUT_SEC}s = scene.duration={scene.duration}s")

    narration_wav = TEMP_DIR / "narration_full.wav"
    concat_narration(padded_wavs, narration_wav)
    total_audio = ffprobe_duration(narration_wav)
    info(f"  narration 結合完了: {narration_wav.name} = {total_audio:.2f}s (video {video_dur:.2f}s と 同期想定)")

    info("\n[4/4] ffmpeg で MP4 最終合成 + 末尾クレジット overlay + SRT burn-in")
    out_mp4 = OUTPUT_DIR / "mais_pmi_knowledge_base_demo.mp4"
    compose_final(webm, narration_wav, out_mp4)
    final_dur = ffprobe_duration(out_mp4)
    size_mb = out_mp4.stat().st_size / 1024 / 1024
    info(f"  完成: {out_mp4} = {final_dur:.2f}s / {size_mb:.1f} MB")

    info("\n=== Done ===")
    info(f"動画 = {out_mp4.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
