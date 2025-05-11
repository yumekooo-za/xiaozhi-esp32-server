from config.logger import setup_logging
import json
import asyncio
import time
import os
from typing import List, Dict, Optional, Any
from core.utils.util import get_string_no_punctuation_or_emoji, analyze_emotion
from core.utils.tts_stream_queue import TTSStreamManager, SentenceAudioQueue

TAG = __name__
logger = setup_logging()

emoji_map = {
    "neutral": "😶",
    "happy": "🙂",
    "laughing": "😆",
    "funny": "😂",
    "sad": "😔",
    "angry": "😠",
    "crying": "😭",
    "loving": "😍",
    "embarrassed": "😳",
    "surprised": "😲",
    "shocked": "😱",
    "thinking": "🤔",
    "winking": "😉",
    "cool": "😎",
    "relaxed": "😌",
    "delicious": "🤤",
    "kissy": "😘",
    "confident": "😏",
    "sleepy": "😴",
    "silly": "😜",
    "confused": "🙄",
}


async def sendAudioMessage(conn, audios, text, text_index=0):
    # 发送句子开始消息
    if text is not None:
        emotion = analyze_emotion(text)
        emoji = emoji_map.get(emotion, "🙂")  # 默认使用笑脸
        await conn.websocket.send(
            json.dumps(
                {
                    "type": "llm",
                    "text": emoji,
                    "emotion": emotion,
                    "session_id": conn.session_id,
                }
            )
        )

    if text_index == conn.tts_first_text_index:
        logger.bind(tag=TAG).info(f"发送第一段语音: {text}")
    await send_tts_message(conn, "sentence_start", text)

    # 播放音频
    await sendAudio(conn, audios)

    await send_tts_message(conn, "sentence_end", text)

    # 发送结束消息（如果是最后一个文本）
    if conn.llm_finish_task and text_index == conn.tts_last_text_index:
        await send_tts_message(conn, "stop", None)
        if conn.close_after_chat:
            await conn.close()


# 全局变量用于追踪音频播放
currently_playing_audio = False
audio_play_lock = asyncio.Lock()

# 全局TTS流管理器实例
tts_stream_manager = TTSStreamManager()


# 播放音频
async def sendAudio(conn, audios, pre_buffer=True):
    global currently_playing_audio, audio_play_lock

    # 流控参数优化
    frame_duration = 60  # 帧时长（毫秒），匹配 Opus 编码
    start_time = time.perf_counter()
    play_position = 0
    last_reset_time = time.perf_counter()  # 记录最后的重置时间

    # 仅当第一句话时执行预缓冲
    if pre_buffer:
        pre_buffer_frames = min(3, len(audios))
        for i in range(pre_buffer_frames):
            await conn.websocket.send(audios[i])
        remaining_audios = audios[pre_buffer_frames:]
    else:
        remaining_audios = audios

    # 播放剩余音频帧
    for opus_packet in remaining_audios:
        if conn.client_abort:
            return

        # 每分钟重置一次计时器
        if time.perf_counter() - last_reset_time > 60:
            await conn.reset_timeout()
            last_reset_time = time.perf_counter()

        # 计算预期发送时间
        expected_time = start_time + (play_position / 1000)
        current_time = time.perf_counter()
        delay = expected_time - current_time
        if delay > 0:
            await asyncio.sleep(delay)

        await conn.websocket.send(opus_packet)

        play_position += frame_duration


# 流式处理指定句子文本的TTS音频生成
async def process_sentence_tts_stream(conn, text: str, text_index: int):
    """
    流式处理单个句子的TTS生成，并加入句子队列

    Args:
        conn: 连接对象，包含TTS提供者
        text: 要转换的文本
        text_index: 句子索引
    """
    if text is None or len(text) <= 0:
        logger.bind(tag=TAG).info(f"无需TTS转换，文本为空")
        # 标记空句子已完成
        tts_stream_manager.mark_sentence_TTS_completed(text_index)
        return

    # 确保句子队列存在
    sentence_queue = tts_stream_manager.get_sentence_queue(text_index)
    if not sentence_queue:
        sentence_queue = tts_stream_manager.create_sentence_queue(text, text_index)

    # 在TTS开始之前就准备好发送状态，这样可以让客户端提前准备
    if text_index == conn.tts_first_text_index:
        logger.bind(tag=TAG).info(f"预处理第一段语音: {text}")
        # 发送情感分析消息
        emotion = analyze_emotion(text)
        emoji = emoji_map.get(emotion, "🙂")  # 默认使用笑脸
        await conn.websocket.send(
            json.dumps(
                {
                    "type": "llm",
                    "text": emoji,
                    "emotion": emotion,
                    "session_id": conn.session_id,
                }
            )
        )

    try:
        # 定义简化的音频帧回调函数，只负责将音频帧添加到队列
        async def frame_callback(opus_frame):
            if conn.client_abort:
                return

            # 仅将帧添加到句子队列，不做其他处理
            if opus_frame:
                tts_stream_manager.add_audio_frame(text_index, opus_frame)

        # 开始流式TTS生成
        logger.bind(tag=TAG).info(f"开始流式生成TTS: {text} (索引: {text_index})")
        await conn.tts.text_to_speak_stream(text, text_index, frame_callback)

        # 不需要在此处发送音频，所有发送由monitor_and_send_sentences处理

        # 标记句子TTS生成完成
        tts_stream_manager.mark_sentence_TTS_completed(text_index)
        logger.bind(tag=TAG).info(f"TTS生成完成: {text} (索引: {text_index})")

    except Exception as e:
        logger.bind(tag=TAG).error(f"流式TTS生成失败 {text}: {e}")
        # 即使出错，也标记为完成，以便队列可以继续处理下一个句子
        tts_stream_manager.mark_sentence_TTS_completed(text_index)


# 监控句子队列并发送音频
async def monitor_and_send_sentences(conn):
    """监控并按序发送所有句子队列中的音频"""
    if conn.client_abort:
        return

    # 设置TTS流管理器的客户端状态
    tts_stream_manager.client_abort = conn.client_abort
    tts_stream_manager.session_id = conn.session_id
    logger.bind(tag=TAG).info(f"开始监控句子队列")
    try:
        await tts_stream_manager.monitor_and_send(
            lambda text, audio_frames, index, state: _send_sentence_audio(
                conn, text, audio_frames, index, state
            )
        )
    except Exception as e:
        logger.bind(tag=TAG).error(f"监控并发送句子音频失败: {e}")
    finally:
        # 处理完成后始终发送停止信号，无论llm_finish_task状态如何
        await send_tts_message(conn, "stop", None)
        # tts_stream_manager.reset()
        logger.bind(tag=TAG).info("所有句子处理完成，发送TTS停止信号")
        # 如果需要关闭连接则关闭
        if conn.close_after_chat:
            await conn.close()


# 发送单个句子的音频
async def _send_sentence_audio(
    conn, text: str, audio_frames: List[bytes], index: int, state: int
):
    """发送单个句子的音频（由监控器调用）"""
    # 发送句子开始状态
    if index == conn.tts_first_text_index:
        logger.bind(tag=TAG).info(f"发送第一段语音: {text}")

    # 发送情感分析消息
    emotion = analyze_emotion(text)
    emoji = emoji_map.get(emotion, "🙂")  # 默认使用笑脸
    await conn.websocket.send(
        json.dumps(
            {
                "type": "llm",
                "text": emoji,
                "emotion": emotion,
                "session_id": conn.session_id,
            }
        )
    )

    # 发送句子开始消息
    if state == "sentence_start" or "all_completed":
        logger.bind(tag=TAG).debug(f"发送给客户端开始句子标志: {text}")
        await send_tts_message(conn, "sentence_start", text)

    # 播放音频
    if audio_frames:
        logger.bind(tag=TAG).debug(
            f"发送给客户端: {text}，共计{len(audio_frames)}帧音频"
        )
        await sendAudio(conn, audio_frames, state == 0)
        logger.bind(tag=TAG).debug(
            f"完成发送给客户端: {text}，共计{len(audio_frames)}帧音频"
        )

    # 发送句子结束状态
    if state == "sentence_end" or "all_completed":
        logger.bind(tag=TAG).debug(f"发送给客户端结束句子标志: {text}")
        await send_tts_message(conn, "sentence_end", text)
        
        # 标记该句子的音频已发送完成，允许处理下一个句子
        sentence_queue = tts_stream_manager.get_sentence_queue(index)
        if sentence_queue:
            sentence_queue.mark_sent_completed()
            logger.bind(tag=TAG).debug(
                f'标记句子音频发送完成: 索引={index}, 文本="{text}"'
            )


async def send_tts_message(conn, state, text=None):
    """发送 TTS 状态消息"""
    message = {"type": "tts", "state": state, "session_id": conn.session_id}
    if text is not None:
        message["text"] = text

    # TTS播放结束
    if state == "stop":
        # 播放提示音
        tts_notify = conn.config.get("enable_stop_tts_notify", False)
        if tts_notify:
            stop_tts_notify_voice = conn.config.get(
                "stop_tts_notify_voice", "config/assets/tts_notify.mp3"
            )
            audios, duration = conn.tts.audio_to_opus_data(stop_tts_notify_voice)
            await sendAudio(conn, audios)
        # 清除服务端讲话状态
        conn.clearSpeakStatus()

    # 发送消息到客户端
    await conn.websocket.send(json.dumps(message))


async def send_stt_message(conn, text):
    """发送 STT 状态消息"""
    stt_text = get_string_no_punctuation_or_emoji(text)
    await conn.websocket.send(
        json.dumps({"type": "stt", "text": stt_text, "session_id": conn.session_id})
    )
    await send_tts_message(conn, "start")
