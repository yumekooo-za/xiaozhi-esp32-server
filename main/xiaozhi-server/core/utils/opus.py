import opuslib_next
import numpy as np
from scipy import signal
import struct


class PCMToOpusConverter:
    def __init__(self, input_sample_rate=24000, output_sample_rate=16000, channels=1, 
                 application=opuslib_next.APPLICATION_AUDIO, frame_size=60, bit_rate=64000):
        """
        初始化PCM到Opus转换器，包含采样率转换
        
        参数:
            input_sample_rate: 输入PCM的采样率 (Hz)
            output_sample_rate: 输出到Opus的采样率 (Hz)
            channels: 通道数 (1=单声道, 2=立体声)
            application: 应用类型 (opuslib.APPLICATION_AUDIO 或 opuslib.APPLICATION_VOIP)
            frame_size: 帧大小 (毫秒)
            bit_rate: 比特率 (bps)
        """
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.channels = channels
        self.frame_size = frame_size
        
        # 计算每帧的样本数 (对于输出采样率)
        self.output_samples_per_frame = int(output_sample_rate * frame_size / 1000)
        
        # 计算输出采样率下每帧的字节大小 (16位采样)
        self.output_bytes_per_frame = self.output_samples_per_frame * channels * 2
        
        # 计算采样率转换比例
        self.resample_ratio = output_sample_rate / input_sample_rate
        
        # 初始化Opus编码器
        self.encoder = opuslib_next.Encoder(output_sample_rate, channels, application)
        self.encoder.bitrate = bit_rate
        
        # 缓存不完整的PCM数据 (输入采样率)
        self.pcm_buffer = b''
        
        # 用于重采样的状态保存
        self.resampler_state = None
        
        self.resampled_bytes_buffer = b""
        
    def _bytes_to_samples(self, pcm_bytes):
        """将PCM字节转换为采样点数组"""
        # 假设PCM数据是16位有符号整数
        format_str = '<' + 'h' * (len(pcm_bytes) // 2)
        return np.array(struct.unpack(format_str, pcm_bytes))
    
    def _samples_to_bytes(self, samples):
        """将采样点数组转换为PCM字节"""
        # 将浮点数四舍五入并转换为整数
        samples = np.clip(samples, -32768, 32767).astype(np.int16)
        return struct.pack('<' + 'h' * len(samples), *samples)
    
    def _resample_chunk(self, pcm_samples):
        """使用scipy.signal.resample_poly进行采样率转换"""
        # 采样率转换: input_rate -> output_rate
        resampled = signal.resample_poly(pcm_samples, 
                                         self.output_sample_rate, 
                                         self.input_sample_rate)
        return resampled
    
    def encode_pcm_chunk(self, pcm_chunk):
        """
        处理输入的PCM数据块，进行采样率转换后编码为Opus
        
        参数:
            pcm_chunk: 24kHz PCM音频数据块 (bytes)
            
        返回:
            list: 包含编码后Opus帧的列表
        """
        # 将新数据添加到缓冲区
        self.pcm_buffer += pcm_chunk
        
        # 计算输入采样率下一帧的字节数
        input_bytes_per_frame = int(self.output_bytes_per_frame / self.resample_ratio)
        
        opus_frames = []
        
        # 处理完整的帧
        while len(self.pcm_buffer) >= input_bytes_per_frame:
            # 提取一个完整的PCM帧
            frame_data = self.pcm_buffer[:input_bytes_per_frame]
            self.pcm_buffer = self.pcm_buffer[input_bytes_per_frame:]
            
            # 转换为采样点数组
            pcm_samples = self._bytes_to_samples(frame_data)
            
            # 采样率转换 (24kHz -> 16kHz)
            resampled_samples = self._resample_chunk(pcm_samples)
            
            # 转回字节
            resampled_bytes = self._samples_to_bytes(resampled_samples)
            self.resampled_bytes_buffer+=resampled_bytes
            # 编码为Opus
            opus_data = self.encoder.encode(resampled_bytes, self.output_samples_per_frame)
            opus_frames.append(opus_data)

        return opus_frames
    
    def flush(self):
        """
        处理缓冲区中剩余的PCM数据
        
        返回:
            bytes: 最后一帧Opus数据，如果有的话
        """
        if not self.pcm_buffer:
            return None
        
        # 计算输入采样率下一帧的字节数
        input_bytes_per_frame = int(self.output_bytes_per_frame / self.resample_ratio)
            
        # 如果有剩余数据，用静音填充至一个完整帧
        if len(self.pcm_buffer) < input_bytes_per_frame:
            padding_size = input_bytes_per_frame - len(self.pcm_buffer)
            self.pcm_buffer += b'\x00' * padding_size
        
        # 转换为采样点数组
        pcm_samples = self._bytes_to_samples(self.pcm_buffer)
        
        # 采样率转换 (24kHz -> 16kHz)
        resampled_samples = self._resample_chunk(pcm_samples)
        
        # 转回字节
        resampled_bytes = self._samples_to_bytes(resampled_samples)
        
        # 编码最后一帧
        opus_data = self.encoder.encode(resampled_bytes, self.output_samples_per_frame)
        self.pcm_buffer = b''
        return opus_data