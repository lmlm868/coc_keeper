# tts.py - 讯飞语音合成模块
import hashlib
import base64
import hmac
import json
import os
import time
import ssl
import wave
import io
from urllib.parse import urlencode
import websocket

# 从环境变量读取密钥
APPID = os.getenv("XF_APPID")
APISecret = os.getenv("XF_APISECRET")
APIKey = os.getenv("XF_APIKEY")

if not all([APPID, APISecret, APIKey]):
    raise RuntimeError("请在环境变量中设置 XF_APPID, XF_APISECRET, XF_APIKEY")

class Ws_Param:
    def __init__(self, APPID, APIKey, APISecret, Text):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.Text = Text
        self.CommonArgs = {"app_id": self.APPID}
        self.BusinessArgs = {
            "aue": "raw",
            "auf": "audio/L16;rate=16000",
            "vcn": "aisjiuxu",
            "tte": "utf8",
            "speed": 50,
            "pitch": 55
        }
        self.DataArgs = {
            "status": 2,
            "text": base64.b64encode(self.Text.encode('utf-8')).decode("utf8")
        }

    def create_url(self):
        url = "wss://tts-api.xfyun.cn/v2/tts"
        now = int(time.time())
        date_http = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(now))
        signature_origin = "host: ws-api.xfyun.cn\ndate: " + date_http + "\nGET /v2/tts HTTP/1.1"
        signature_sha = hmac.new(
            self.APISecret.encode('utf-8'),
            signature_origin.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        signature_sha = base64.b64encode(signature_sha).decode()
        authorization_origin = f'api_key="{self.APIKey}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode()
        v = {"authorization": authorization, "date": date_http, "host": "ws-api.xfyun.cn"}
        return url + '?' + urlencode(v)

def synthesize(text: str) -> bytes:
    """
    合成语音，返回 WAV 格式的音频数据（bytes）
    """
    if isinstance(text, bytes):
        text = text.decode('utf-8')
    elif not isinstance(text, str):
        text = str(text)

    wsParam = Ws_Param(APPID, APIKey, APISecret, text)
    audio_buffer = bytearray()
    finished = False

    def on_message(ws, message):
        nonlocal audio_buffer, finished
        try:
            msg = json.loads(message)
            if msg["code"] != 0:
                print(f"语音合成错误: {msg['code']} - {msg.get('message', '')}")
                ws.close()
                return
            audio = base64.b64decode(msg["data"]["audio"])
            audio_buffer.extend(audio)
            if msg["data"]["status"] == 2:
                finished = True
                ws.close()
        except Exception as e:
            print(f"处理消息异常: {e}")
            ws.close()

    def on_error(ws, error):
        print(f"WebSocket错误: {error}")

    def on_close(ws, close_status_code, close_msg):
        nonlocal finished
        if not finished:
            finished = True

    def on_open(ws):
        d = {
            "common": wsParam.CommonArgs,
            "business": wsParam.BusinessArgs,
            "data": wsParam.DataArgs
        }
        ws.send(json.dumps(d))

    websocket.enableTrace(False)
    wsUrl = wsParam.create_url()
    ws = websocket.WebSocketApp(
        wsUrl,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.on_open = on_open
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    if not audio_buffer:
        raise RuntimeError("未获取到音频数据")

    # 将 PCM 数据包装成 WAV
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)   # 16bit
        wf.setframerate(16000)
        wf.writeframes(audio_buffer)
    wav_buffer.seek(0)
    return wav_buffer.read()
