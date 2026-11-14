"""把 tts/narration.json 的每一句，用三種台灣中文神經語音念成 audio/<聲音>/<id>.mp3。
只重念內容有改的句子（雜湊記在 audio/manifest.json），刪掉已不存在的句子。
本地測試：TTS_FAKE=1 python tts/render.py（不連微軟語音，產生空白檔）
"""
import asyncio, hashlib, json, os, pathlib, sys

FAKE = os.environ.get("TTS_FAKE") == "1"
if not FAKE:
    import edge_tts

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = json.loads((ROOT / "tts" / "narration.json").read_text(encoding="utf-8"))
OUT = ROOT / "audio"
MAN = OUT / "manifest.json"


async def speak(say, voice, rate, pitch, path):
    if FAKE:
        path.write_bytes(b"")
        return
    for attempt in range(5):
        try:
            await edge_tts.Communicate(say, voice, rate=rate, pitch=pitch).save(str(path))
            if path.stat().st_size > 1000:
                await asyncio.sleep(1.2)   # 放慢，避免被限流
                return True
        except Exception as e:  # 偶發的 websocket 中斷／限流
            print("retry", path.name, e)
        await asyncio.sleep(8 * (attempt + 1))
    if path.exists():
        path.unlink()
    print("FAILED", path)   # 先略過，下次執行再補
    return False


async def main():
    force = "--force" in sys.argv
    rate, pitch = spec.get("rate", "+0%"), spec.get("pitch", "+0Hz")
    man = json.loads(MAN.read_text()) if MAN.exists() else {}
    new, missing = {}, 0
    for key, voice in spec["voices"].items():
        d = OUT / key
        d.mkdir(parents=True, exist_ok=True)
        new[key] = {}
        for lid, line in spec["lines"].items():
            say = line["say"] if isinstance(line, dict) else line
            h = hashlib.sha1(f"{voice}|{rate}|{pitch}|{say}".encode()).hexdigest()[:12]
            mp3 = d / f"{lid}.mp3"
            new[key][lid] = h
            if not force and mp3.exists() and man.get(key, {}).get(lid) == h:
                continue
            if await speak(say, voice, rate, pitch, mp3):
                print("ok", key, lid, say)
            else:
                new[key].pop(lid)
                missing += 1
        for f in d.glob("*.mp3"):
            if f.stem not in spec["lines"]:
                f.unlink()
                print("removed", key, f.name)
    MAN.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    print("missing", missing)


asyncio.run(main())
