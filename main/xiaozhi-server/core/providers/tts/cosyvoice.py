import os
import uuid
import requests
import sys
import io
import numpy as np
import opuslib_next
from pydub import AudioSegment
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
        # 源采样率和目标采样率
        self.source_sample_rate = 24000  # CosyVoice返回的PCM是24kHz
        self.target_sample_rate = 16000  # Opus编码器使用16kHz
        # 初始化Opus编码器
        self.encoder = opuslib_next.Encoder(self.target_sample_rate, 1, opuslib_next.APPLICATION_AUDIO)
        # 编码参数
        self.frame_duration = 60  # 60ms per frame
        self.source_frame_size = int(self.source_sample_rate * self.frame_duration / 1000)  # 1440 samples/frame at 24kHz
        self.target_frame_size = int(self.target_sample_rate * self.frame_duration / 1000)  # 960 samples/frame at 16kHz
        # 流式回调
        self.stream_callback = None
        # 初始化解码器 (用于保存调试音频)
        self.decoder = opuslib_next.Decoder(self.target_sample_rate, 1)
        
    def generate_filename(self):
        return os.path.join(self.output_file, f"tts-{datetime.now().date()}@{uuid.uuid4().hex}.{self.format}")

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
            
        try:
            logger.bind(tag=TAG).debug(f"开始流式TTS请求: {text}")
            
            # 设置流式请求
            with requests.post(self.url, json=request_params, stream=True, headers=self.headers) as response:
                response.raise_for_status()
                
                # PCM数据缓冲区
                buffer = bytearray()
                frame_size_bytes = self.source_frame_size * 2  # 每帧字节数 (16位 = 2字节/样本，24kHz)
                
                # 流式处理响应
                for chunk in response.iter_content(chunk_size=4096):
                    if not chunk:
                        continue
                        
                    # 添加到缓冲区
                    buffer.extend(chunk)
                    
                    # 当缓冲区大小达到一帧或更多时进行处理
                    while len(buffer) >= frame_size_bytes:
                        # 提取当前帧数据
                        frame_data = buffer[:frame_size_bytes]
                        # 从缓冲区移除已处理数据
                        buffer = buffer[frame_size_bytes:]
                        
                        # 转换为Opus格式
                        opus_frame = self._process_pcm_frame(frame_data)
                        if opus_frame:
                            await self.stream_callback(opus_frame)
                
                # 处理剩余数据
                if buffer:
                    # 如果剩余数据不足一帧，补零
                    if len(buffer) < frame_size_bytes:
                        buffer.extend(b"\x00" * (frame_size_bytes - len(buffer)))
                    
                    opus_frame = self._process_pcm_frame(buffer)
                    if opus_frame:
                        await self.stream_callback(opus_frame)
                
            logger.bind(tag=TAG).debug(f"流式TTS请求完成: {text}")
                
        except Exception as e:
            logger.bind(tag=TAG).error(f"流式TTS请求失败: {e}")
            raise e
            
    def _process_pcm_frame(self, pcm_data):
        """
        处理单帧PCM数据，转换为opus格式
        
        参数:
        - pcm_data: 原始PCM数据（16位，24kHz，单声道）
        
        返回:
        - opus_frame: opus编码帧
        """
        try:
            # 确保数据长度正确
            if len(pcm_data) != self.source_frame_size * 2:
                logger.bind(tag=TAG).error(f"PCM数据长度不正确: {len(pcm_data)} 字节，预期 {self.source_frame_size * 2} 字节")
                return None
                
            # 转换为numpy数组
            np_frame = np.frombuffer(pcm_data, dtype=np.int16)
            
            # 重采样: 24kHz -> 16kHz (比例 2:3)
            # 简易重采样: 每3个样本取2个，适用于24kHz->16kHz
            resampled = np.zeros(self.target_frame_size, dtype=np.int16)
            for i in range(self.target_frame_size):
                src_idx = int(i * 1.5)  # 1.5 = 24000/16000
                if src_idx < len(np_frame):
                    resampled[i] = np_frame[src_idx]
            
            # 编码为opus
            opus_data = self.encoder.encode(resampled.tobytes(), self.target_frame_size)
            return opus_data
            
        except Exception as e:
            logger.bind(tag=TAG).error(f"PCM帧处理失败: {e}")
            return None

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
                
            logger.bind(tag=TAG).debug(f"成功解码 {len(opus_frames)} 帧Opus数据，PCM大小: {len(pcm_buffer)} 字节")
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
            with requests.post(self.url, json=request_params, stream=True, headers=self.headers) as response:
                response.raise_for_status()
                
                # 流式写入文件
                with open(output_file, 'wb') as f:
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
                "speed": 1.0
                }
        }
    tts=TTSProvider(config=payload, delete_audio_file=True)
    async def main():
        await tts.text_to_speak("好的，我需要解决用户遇到的错误", "tmp/test.wav")
    
    asyncio.run(main())
