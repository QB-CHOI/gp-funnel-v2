"""
Gemini Vision OCR — 쓸 수 있는 모델을 실행 시점에 물어보고 고른다.

왜 물어보는가:
  처음에는 모델 이름을 코드에 박아 두었다(gemini-1.5-flash 등). 구글이 옛
  모델을 내리는 순간 전부 404가 나는데, 화면에는 '인식 실패'로만 보여서
  '제미나이는 오류가 잦다'는 결론이 났고 기능이 통째로 꺼졌다. 무엇이 살아
  있는지는 우리가 알 수 없다 — 목록을 받아 고르고, 조회가 막히면 마지막으로
  알려진 이름들로 떨어진다.

  이 경로는 apt(tesseract)와 무관해서, 스트림릿 서버 이미지가 고장 나도
  인식이 계속 된다. 2026-09-08 데비안 11 만료로 tesseract를 뗀 뒤 주 경로.
"""
import base64
import io
import json
import re
import requests
from PIL import Image

_BASE = "https://generativelanguage.googleapis.com"

# 조회가 실패했을 때만 쓰는 최후의 보루. 여기 이름도 언젠가 내려간다는
# 전제로 둔다 — 그래서 '조회 우선, 목록은 백업'이다.
_FALLBACK_MODELS = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

# 이미지를 못 읽거나 우리 용도에 맞지 않는 모델들. 이름으로 거른다.
_EXCLUDE = ("embedding", "aqa", "tts", "imagen", "veo", "image-generation",
            "live", "native-audio", "computer-use", "robotics")

_MODEL_CACHE: dict = {}      # {api_key: [모델명, ...]} — 호출마다 목록을 받지 않도록


def _rank(name: str) -> tuple:
    """새 버전 > flash > 일반판 순으로 점수. 정렬 키로 쓴다(내림차순)."""
    m = re.search(r"(\d+)\.(\d+)", name)
    ver = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    is_flash = 1 if "flash" in name else 0          # 싸고 빠르다. OCR엔 충분
    is_lite  = 1 if "lite" in name else 0           # 더 싸지만 인식이 떨어진다
    is_plain = 0 if any(k in name for k in ("preview", "exp")) else 1
    return (ver, is_flash, is_plain, -is_lite)


def _models(api_key: str) -> list:
    """쓸 수 있는 모델을 좋은 순서로. 조회 실패 시 백업 목록."""
    if api_key in _MODEL_CACHE:
        return _MODEL_CACHE[api_key]
    names = []
    try:
        r = requests.get(f"{_BASE}/v1beta/models", params={"key": api_key},
                         timeout=20)
        r.raise_for_status()
        for m in r.json().get("models", []):
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            n = m.get("name", "").split("/")[-1]
            if not n or any(k in n for k in _EXCLUDE):
                continue
            names.append(n)
        names.sort(key=_rank, reverse=True)
    except Exception:
        names = []
    result = (names or _FALLBACK_MODELS)[:4]   # 넷이면 충분하다. 더 돌면 느리다
    _MODEL_CACHE[api_key] = result
    return result


def _encode_image(image: Image.Image) -> tuple[str, str]:
    """이미지를 최대 1600px JPEG로 압축해 (base64, mime_type) 반환."""
    img = image.convert("RGB")
    w, h = img.size
    if max(w, h) > 1600:
        ratio = 1600 / max(w, h)
        resample = getattr(getattr(Image, "Resampling", None), "LANCZOS", None) or Image.LANCZOS
        img = img.resize((int(w * ratio), int(h * ratio)), resample)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"


def _call_model(model: str, img_b64: str, mime_type: str,
                prompt: str, api_key: str) -> dict:
    """단일 모델 호출. 응답 dict 반환, 실패 시 예외."""
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime_type, "data": img_b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 512},
    }
    url = f"{_BASE}/v1beta/models/{model}:generateContent?key={api_key}"
    resp = requests.post(url, json=body, timeout=45)
    if resp.status_code == 200:
        return resp.json()
    try:
        err = resp.json().get("error", {}).get("message", resp.text[:200])
    except Exception:
        err = resp.text[:200]
    raise RuntimeError(f"[{resp.status_code}] {model}: {err}")


def extract_members(image: Image.Image, api_key: str, rooms: dict) -> list:
    """Gemini Vision으로 채팅방 인원 추출. 모델 순서대로 시도."""
    img_b64, mime_type = _encode_image(image)

    room_list = "\n".join(
        f"- room_num={num}, name=\"{name}\"" for num, name in rooms.items()
    )
    prompt = (
        "이 이미지는 카카오톡 오픈채팅방 목록 스크린샷입니다.\n\n"
        "【중요 구분】\n"
        "- 왼쪽 원형 배지 안의 숫자(예: 32, 35)는 채팅방 식별 번호입니다. 인원 수가 아닙니다.\n"
        "- 인원 수는 채팅방 이름 텍스트 끝 부분에 공백으로 구분되어 나타나는 숫자입니다.\n"
        "  예시: '황금후추 채팅방35(사주3) 545' → 인원=545\n\n"
        f"등록된 채팅방:\n{room_list}\n\n"
        "규칙:\n"
        "1. 채팅방 이름에 포함된 숫자(채팅방N)로 room_num 매칭\n"
        "2. 인원 수는 채팅방 이름 바로 뒤 숫자 (50~9999 범위)\n"
        "3. 왼쪽 원형 배지 숫자는 절대 인원 수로 사용하지 말 것\n"
        "4. 명확히 보이지 않는 방은 제외\n"
        "5. 쉼표 제거 후 정수 반환 (1,234 → 1234)\n\n"
        "JSON으로만 응답:\n"
        "{\"results\": [{\"room_num\": 35, \"members\": 545}]}"
    )

    errors = []
    for model in _models(api_key):
        try:
            data = _call_model(model, img_b64, mime_type, prompt, api_key)
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            result = _parse_response(text, rooms)
            if result:
                return result
        except Exception as e:
            errors.append(str(e))
            continue

    # 한 모델이 죽어서 실패한 것인지, 키·할당량 문제인지 구분이 되어야
    # 사람이 다음에 무엇을 할지 안다. 시도한 모델 이름을 그대로 남긴다.
    _MODEL_CACHE.pop(api_key, None)      # 목록이 낡았을 수 있다. 다음엔 다시 조회
    raise RuntimeError("Gemini 인식 실패 — 시도한 모델: "
                       + ", ".join(_models(api_key)) + "\n"
                       + "\n".join(errors[:4]))


def _parse_response(text: str, rooms: dict) -> list:
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group())
        valid = []
        for r in data.get("results", []):
            rn = int(r.get("room_num", 0))
            m  = int(r.get("members", 0))
            if rn in rooms and 1 <= m <= 99999 and m != rn:
                valid.append({"room_num": rn, "members": m})
        return valid
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
