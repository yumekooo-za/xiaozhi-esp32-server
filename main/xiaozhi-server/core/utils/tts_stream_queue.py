import asyncio
import time
from typing import Dict, List, Callable, Optional, Any
from config.logger import setup_logging
from threading import Lock

TAG = __name__
logger = setup_logging()


class SentenceAudioQueue:
    """单个句子的音频队列，包含句子文本和对应的音频帧"""

    def __init__(self, text: str, index: int):
        self.text = text  # 句子文本
        self.index = index  # 句子索引
        self.audio_frames = []  # 音频帧队列
        self.completed = False  # 是否完成TTS生成
        self.sent_completed = False  # 是否完成音频发送
        self.created_at = time.time()  # 创建时间
        self.lock = Lock()  # 音频帧队列的线程锁

    def add_frame(self, frame: bytes):
        """添加一个音频帧到队列"""
        with self.lock:
            self.audio_frames.append(frame)

    def mark_completed(self):
        """标记句子TTS生成已完成"""
        self.completed = True

    def is_TTS_completed(self) -> bool:
        """检查句子是否已完成TTS生成"""
        return self.completed

    def is_sent_completed(self) -> bool:
        """检查句子是否已完成音频发送"""
        return self.sent_completed

    def mark_sent_completed(self):
        """标记句子音频已完成发送"""
        self.sent_completed = True

    def has_frames(self) -> bool:
        """检查是否有可用音频帧"""
        with self.lock:
            return len(self.audio_frames) > 0

    def frames_left(self) -> int:
        """检查是否有可用音频帧"""
        with self.lock:
            return len(self.audio_frames)

    def get_all_frames(self) -> List[bytes]:
        """获取所有音频帧并清空队列"""
        with self.lock:
            frames = self.audio_frames.copy()
            self.audio_frames.clear()
            return frames

    def get_frames(self, max_frames: int = 30) -> List[bytes]:
        """获取指定数量的音频帧但不清空整个队列

        Args:
            max_frames: 最大帧数，默认30

        Returns:
            获取的音频帧列表
        """
        with self.lock:
            if not self.audio_frames:
                return []

            # 限制获取的帧数
            frames_count = min(max_frames, len(self.audio_frames))
            frames = self.audio_frames[:frames_count]

            # 从队列中移除已获取的帧
            self.audio_frames = self.audio_frames[frames_count:]

            return frames


class TTSStreamManager:
    """TTS流式管理器，协调多个句子队列的处理和发送"""

    def __init__(self):
        self.sentence_queues: Dict[int, SentenceAudioQueue] = (
            {}
        )  # 句子队列字典，按索引存储
        self.current_index = 1  # 当前处理的句子索引
        self.all_completed = False  # 是否所有句子都已完成
        self.client_abort = False  # 客户端是否中止
        self.session_id = None  # 会话ID

    def reset(self):
        """重置管理器状态"""
        self.sentence_queues.clear()
        self.current_index = 1
        self.all_completed = False
        self.client_abort = False

    def create_sentence_queue(self, text: str, index: int) -> SentenceAudioQueue:
        """创建新的句子队列"""
        queue = SentenceAudioQueue(text, index)
        self.sentence_queues[index] = queue
        logger.bind(tag=TAG).debug(f'创建句子队列: 索引={index}, 文本="{text}"')
        return queue

    def get_sentence_queue(self, index: int) -> Optional[SentenceAudioQueue]:
        """获取指定索引的句子队列"""
        return self.sentence_queues.get(index)

    def add_audio_frame(self, index: int, frame: bytes):
        """添加音频帧到指定句子队列"""
        queue = self.get_sentence_queue(index)
        if queue:
            queue.add_frame(frame)
            # logger.bind(tag=TAG).warning(f"音频帧添加到句子队列，目前队列长度：{len(queue.audio_frames)}，句子索引: {index}")
        else:
            logger.bind(tag=TAG).error(
                f"尝试添加音频帧到不存在的句子队列: 索引={index}"
            )

    def mark_sentence_TTS_completed(self, index: int):
        """标记指定句子TTS生成已完成"""
        queue = self.get_sentence_queue(index)
        if queue:
            queue.mark_completed()
            logger.bind(tag=TAG).debug(
                f'句子TTS生成完成: 索引={index}, 文本="{queue.text}"'
            )
        else:
            logger.bind(tag=TAG).error(
                f"尝试标记不存在的句子队列为已完成: 索引={index}"
            )

    def set_all_completed(self):
        """标记所有句子已处理完成（用于结束处理）"""
        self.all_completed = True
        logger.bind(tag=TAG).info("所有句子处理已标记为完成")

    async def monitor_and_send(
        self, send_callback: Callable[[str, List[bytes], int], Any]
    ):
        """
        监控并发送句子音频数据

        Args:
            send_callback: 回调函数，接收参数(text, audio_frames, index)
        """
        last_frame_time = 0
        frames = []

        while not (self.all_completed and self._all_sentences_processed()):
            if self.client_abort:
                logger.bind(tag=TAG).info("客户端已中止，停止监控句子队列")
                break
            # 检查当前索引的句子队列
            current_queue = self.get_sentence_queue(self.current_index)

            if not current_queue:
                # 当前索引的句子队列不存在，等待片刻
                await asyncio.sleep(0.02)
                continue
            # 队列存在，检查是否有音频数据可发送
            if current_queue.has_frames():
                # 获取队列中的所有音频帧
                logger.bind(tag=TAG).debug(f"len(frames)={len(frames)}")
                frames.extend(current_queue.get_all_frames())
                logger.bind(tag=TAG).debug(f"len(frames) after extend={len(frames)}")
                logger.bind(tag=TAG).debug(
                    f'获取句子音频帧: 索引={current_queue.index}, 文本="{current_queue.text}", 帧数={len(frames)}'
                )
                if frames:
                    current_time = time.time()

                    # 发送策略：
                    # 1. 所有句子：第一次都需要累积至少相当于180ms的音频数据
                    # 2. 后续发送：有多少发多少
                    should_send = True
                    if last_frame_time == 0:
                        # 任何句子的第一次发送，都需要有足够的音频数据

                        if len(frames) < 5:
                            should_send = False
                            logger.bind(tag=TAG).debug(
                                f"等待足够音频:  索引={current_queue.index},当前 {len(frames)} z, 需要5 帧"
                            )
                        else:
                            logger.bind(tag=TAG).debug(
                                f"等到了足够的音频:  索引={current_queue.index},当前 {len(frames)} 帧"
                            )

                    if should_send or current_queue.is_TTS_completed():

                        logger.bind(tag=TAG).debug(
                            f"发送句子音频: 索引={current_queue.index}, "
                            f'文本="{current_queue.text}", 帧数={len(frames)}'
                        )
                        
                        if last_frame_time == 0:
                            state=0
                        elif current_queue.is_TTS_completed():
                            state=2
                        else:
                            state=1
                        try:
                            await send_callback(
                                current_queue.text,
                                frames,
                                current_queue.index,
                                state,
                            )
                        except Exception as e:
                            logger.bind(tag=TAG).error(f"发送句子音频失败: {e}")
                        finally:
                            last_frame_time = current_time
                            frames.clear()
            logger.bind(tag=TAG).info(f"索引={current_queue.index},处理完毕，当前剩余 {len(frames)} 帧，队列剩余{current_queue.frames_left()}帧")
            # 如果当前句子已完成TTS生成且没有更多音频帧，并且已标记为发送完毕，才转到下一个句子
            if (
                current_queue.is_TTS_completed()
                and not current_queue.has_frames()
                and current_queue.is_sent_completed()
            ):
                logger.bind(tag=TAG).debug(
                    f"---------------句子队列已处理并发送完毕: 索引={self.current_index}--------------"
                )
                self.current_index += 1
                logger.bind(tag=TAG).debug(f"开始处理索引={self.current_index}")

            else:
                # 等待一个较短的时间再检查，提高响应性
                await asyncio.sleep(0.02)

        logger.bind(tag=TAG).info("所有句子音频处理完成")

    def _all_sentences_processed(self) -> bool:
        """检查是否所有句子队列都已处理完毕"""
        if not self.sentence_queues:
            logger.bind(tag=TAG).debug("所有句子已处理完毕")
            return True

        # 先检查我们是否已经处理到了最大索引
        max_index = max(self.sentence_queues.keys()) if self.sentence_queues else 1
        if self.current_index <= max_index:
            return False
        logger.debug(f"当前索引: {self.current_index}, 最大索引: {max_index}")

        # 再检查所有句子是否都已完成且没有未处理的音频帧
        for index, queue in self.sentence_queues.items():
            if not queue.is_TTS_completed() or queue.has_frames():
                return False
        logger.debug(f"所有句子已处理完成且没有未处理的音频帧")
        return True
