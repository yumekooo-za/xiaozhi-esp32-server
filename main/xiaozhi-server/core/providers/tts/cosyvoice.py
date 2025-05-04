import os
import uuid
import requests
import sys
sys.path.append("/home/data/xiaozhi-esp32-server/main/xiaozhi-server")
from config.logger import setup_logging
from datetime import datetime
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()

class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.url = config.get("url")
        self.headers = config.get("headers", {})
        self.params = config.get("params")
        self.format = config.get("response_format", "wav")
        self.output_file = config.get("output_dir", "tmp/")

    def generate_filename(self):
        return os.path.join(self.output_file, f"tts-{datetime.now().date()}@{uuid.uuid4().hex}.{self.format}")

    async def text_to_speak(self, text, output_file):
        request_params = {}
        request_params["input"] = text
        request_params["response_format"] = self.format
        for k, v in self.params.items():
            request_params[k] = v
        try:
            with requests.post(self.url, json=request_params, stream=True) as response:
                response.raise_for_status()
                
                # 流式写入文件
                with open(output_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                print(f"音频文件已保存至: {output_file}")
                
        except requests.exceptions.RequestException as e:
            logger.bind(tag=TAG).error(f"Custom TTS请求失败: {response.status_code} - {response.text}")



if __name__ == "__main__":
    import asyncio
    payload = {
            "url": "http://localhost:30053/v1/audio/speech",
            "response_format": "wav",
            "params": {
                "voice": "speech:wjj:xxx:0dfb3c61",
                "sample_rate": 24000,
                "stream": True,
                "speed": 1.0
                }
        }
    tts=TTSProvider(config=payload, delete_audio_file=True)
    async def main():
        await tts.text_to_speak("好的，我需要解决用户遇到的错误", "tmp/test.wav")
    
    asyncio.run(main())