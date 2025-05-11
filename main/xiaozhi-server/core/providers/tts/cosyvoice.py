import os
import uuid
import requests
import sys
import io
import numpy as np
import opuslib_next
import numpy as np

sys.path.append("/home/data/xiaozhi-esp32-server/main/xiaozhi-server")
from config.logger import setup_logging
from datetime import datetime
from core.providers.tts.base import TTSProviderBase
from core.utils.opus import PCMToOpusConverter

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    def __init__(
        self,
        config,
        delete_audio_file,
        source_sample_rate=24000,
        output_sample_rate=16000,
    ):
        super().__init__(config, delete_audio_file)
        self.url = config.get("url")
        self.headers = config.get("headers", {})
        self.params = config.get("params")
        self.format = config.get("response_format", "wav")
        self.output_file = config.get("output_dir", "tmp/")
        # 源采样率和目标采样率
        self.source_sample_rate = source_sample_rate  # CosyVoice返回的PCM是24kHz
        self.output_sample_rate = output_sample_rate  # Opus编码器使用16kHz

    def generate_filename(self):
        return os.path.join(
            self.output_file,
            f"tts-{datetime.now().date()}@{uuid.uuid4().hex}.{self.format}",
        )

    async def text_to_speak_stream(self, text, index, stream_callback=None):
        """
        流式TTS，收到PCM音频块即进行处理和回调

        参数:
        - text: 要转换的文本
        - stream_callback: 回调函数
        """

        # 确保回调函数存在
        if not stream_callback:
            logger.bind(tag=TAG).error("未设置流式回调函数")
            return

        request_params = {}
        request_params["input"] = text
        request_params["response_format"] = self.format  # 直接请求PCM格式

        # 确保启用流式参数
        if "stream" not in request_params and self.params.get("stream") is None:
            request_params["stream"] = True
        for k, v in self.params.items():
            request_params[k] = v

        converter = PCMToOpusConverter(
            input_sample_rate=self.source_sample_rate,
            output_sample_rate=self.output_sample_rate,
            channels=1,
        )
        try:
            logger.bind(tag=TAG).info(f"开始流式TTS请求: {text}")

            # 设置流式请求
            with requests.post(
                self.url, json=request_params, stream=True, headers=self.headers
            ) as response:
                response.raise_for_status()

                # 流式处理响应 - 使用更小的chunk大小加快首帧处理速度,48000为1秒的PCM数据
                for chunk in response.iter_content(chunk_size=2048):
                    if not chunk:
                        continue
                    opus_frames = converter.encode_pcm_chunk(chunk)
                    logger.bind(tag=TAG).debug(
                        f"转换一个PCM块，生成了 {len(opus_frames)} 个Opus帧,index={index}"
                    )
                    await stream_callback(opus_frames)

                # 最后剩余帧处理
                final_frame = converter.flush()
                if final_frame:
                    logger.bind(tag=TAG).debug(
                        f"转换最后一个PCM块，生成了 {len(final_frame)} 个Opus帧,,index={index}"
                    )
                    await stream_callback(final_frame)

            logger.bind(tag=TAG).debug(f"流式TTS请求完成: {text}")

        except Exception as e:
            logger.bind(tag=TAG).error(f"流式TTS请求失败: {e}")
            raise e

    # 保留原方法用于兼容
    async def text_to_speak(self, text, output_file):
        request_params = {}
        request_params["input"] = text
        request_params["response_format"] = self.format
        for k, v in self.params.items():
            request_params[k] = v
        try:
            with requests.post(
                self.url, json=request_params, stream=True, headers=self.headers
            ) as response:
                response.raise_for_status()

                # 流式写入文件
                with open(output_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

        except Exception as e:
            logger.bind(tag=TAG).error(f"Cosyvoice TTS请求失败: {e}")
            raise e


if __name__ == "__main__":
    import asyncio

    payload = {
        "url": "http://localhost:30053/v1/audio/speech",
        "response_format": "wav",
        "params": {
            "voice": "speech:wjj:xxx:0dfb3c61",
            "sample_rate": 24000,
            "stream": True,
            "speed": 1.0,
        },
    }
    tts = TTSProvider(config=payload, delete_audio_file=True)

    async def main():
        await tts.text_to_speak("好的，我需要解决用户遇到的错误", "tmp/test.wav")

    asyncio.run(main())
