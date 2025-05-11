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
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.url = config.get("url")
        self.headers = config.get("headers", {})
        self.params = config.get("params")
        self.format = config.get("response_format", "wav")
        self.output_file = config.get("output_dir", "tmp/")
        # 源采样率和目标采样率
        self.source_sample_rate = 24000  # CosyVoice返回的PCM是24kHz
        self.target_sample_rate = 16000  # Opus编码器使用16kHz
        # 初始化Opus编码器
        self.encoder = opuslib_next.Encoder(
            self.target_sample_rate, 1, opuslib_next.APPLICATION_AUDIO
        )
        # 编码参数
        self.frame_duration = 60  # 60ms per frame
        self.source_frame_size = int(
            self.source_sample_rate * self.frame_duration / 1000
        )  # 1440 samples/frame at 24kHz
        self.target_frame_size = int(
            self.target_sample_rate * self.frame_duration / 1000
        )  # 960 samples/frame at 16kHz
        self.bytes_per_frame = self.target_frame_size * 1 * 2
        # 流式回调
        self.stream_callback = None
        # 初始化解码器 (用于保存调试音频)
        self.decoder = opuslib_next.Decoder(self.target_sample_rate, 1)

    def generate_filename(self):
        return os.path.join(
            self.output_file,
            f"tts-{datetime.now().date()}@{uuid.uuid4().hex}.{self.format}",
        )

    def set_stream_callback(self, callback):
        """设置流式回调函数"""
        self.stream_callback = callback

    async def text_to_speak_stream(self, text, stream_callback=None):
        """
        流式TTS，收到PCM音频块即进行处理和回调

        参数:
        - text: 要转换的文本
        - stream_callback: 回调函数，若设置则替换之前通过set_stream_callback设置的回调
        """
        # 如果直接提供了回调函数，则使用它
        if stream_callback:
            self.stream_callback = stream_callback

        # 确保回调函数存在
        if not self.stream_callback:
            logger.bind(tag=TAG).error("未设置流式回调函数")
            return

        request_params = {}
        request_params["input"] = text
        request_params["response_format"] = "pcm"  # 直接请求PCM格式
        # 确保启用流式参数
        if "stream" not in request_params and self.params.get("stream") is None:
            request_params["stream"] = True
        for k, v in self.params.items():
            request_params[k] = v

        all_opus_frames = []
        converter = PCMToOpusConverter(
            input_sample_rate=24000, output_sample_rate=16000, channels=1
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
                        f"转换一个PCM块，生成了 {len(opus_frames)} 个Opus帧"
                    )
                    await self.stream_callback(opus_frames)
                    all_opus_frames.extend(opus_frames)

                final_frame = converter.flush()
                if final_frame:
                    logger.bind(tag=TAG).debug(
                        f"转换最后一个PCM块，生成了 {len(final_frame)} 个Opus帧"
                    )
                    await self.stream_callback(final_frame)
                    all_opus_frames.extend(final_frame)

            logger.bind(tag=TAG).debug(f"流式TTS请求完成: {text}")
            # 将all_opus_frames存成.opus文件
            # output_path = self.generate_filename()
            # with open(output_path, 'wb') as f:
            #     f.write(converter.resampled_bytes_buffer)
            # logger.bind(tag=TAG).info(f"Opus文件已保存至: {output_path}")

        except Exception as e:
            logger.bind(tag=TAG).error(f"流式TTS请求失败: {e}")
            raise e

    def decode_opus_frames(self, opus_frames):
        """
        将Opus帧解码为PCM数据

        参数:
        - opus_frames: Opus编码帧列表

        返回:
        - pcm_data: 解码后的PCM数据
        """
        try:
            # 创建PCM数据缓冲区
            pcm_buffer = bytearray()

            # 逐帧解码
            for opus_frame in opus_frames:
                decoded_frame = self.decoder.decode(opus_frame, self.target_frame_size)
                pcm_buffer.extend(decoded_frame)

            logger.bind(tag=TAG).debug(
                f"成功解码 {len(opus_frames)} 帧Opus数据，PCM大小: {len(pcm_buffer)} 字节"
            )
            return bytes(pcm_buffer)

        except Exception as e:
            logger.bind(tag=TAG).error(f"解码Opus帧失败: {e}")
            return b""

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
