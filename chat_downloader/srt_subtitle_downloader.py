import argparse
import os
from chat_downloader import ChatDownloader
from typing import List


class ChatMessage:
    timestamp_seconds: float
    Author: str
    MessageText: str

    def __init__(self, timestamp_seconds: float, author: str, message_text: str) -> None:
        self.timestamp_seconds = timestamp_seconds
        self.Author = author
        self.MessageText = message_text


class SrtLine:
    Index: int
    StartTimeSeconds: float
    EndTimeSeconds: float
    Author: str
    MessageText: str

    def __init__(self, index: int, start_time_seconds: float, end_time_seconds: float, author: str,
                 message_text: str) -> None:
        self.Index = index
        self.StartTimeSeconds = start_time_seconds
        self.EndTimeSeconds = end_time_seconds
        self.Author = author
        self.MessageText = message_text

    @staticmethod
    def __seconds_to_timestamp(seconds: float):
        int_seconds = int(seconds)
        h, remainder = divmod(abs(int_seconds), 3600)
        m, s = divmod(remainder, 60)
        milliseconds = round(1000 * (float(seconds) - int_seconds))
        return f"{'-' if seconds < 0 else ''}{h:02}:{m:02}:{s:02},{milliseconds:03}"

    def to_string(self) -> str:
        return f'{self.Index}\n{self.__seconds_to_timestamp(self.StartTimeSeconds)} --> {self.__seconds_to_timestamp(self.EndTimeSeconds)}\n<font color="#00FF00">{self.Author}</font>: {self.MessageText}\n\n'


assHeader = """[Script Info]
ScriptType: v4.00+
Collisions: Normal
PlayResX: 640
PlayResY: 480
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Myriad Web Pro Condensed,26,&H00ffffff,&H0000ffff,&H0025253a,&H96000000,0,0,0,0,100,100,0,0.00,1,2,1,2,15,15,20,1

[Events]
Format: Layer, Start, End, Style, Actor, MarginL, MarginR, MarginV, Effect, Text
"""


class AssLine:
    StartTimeSeconds: float
    EndTimeSeconds: float
    Author: str
    MessageText: str

    def __init__(self, start_time_seconds: float, end_time_seconds: float, author: str, message_text: str) -> None:
        self.StartTimeSeconds = start_time_seconds
        self.EndTimeSeconds = end_time_seconds
        self.Author = author
        self.MessageText = message_text

    @staticmethod
    def __seconds_to_timestamp(seconds: float):
        int_seconds = int(seconds)
        h, remainder = divmod(abs(int_seconds), 3600)
        m, s = divmod(remainder, 60)
        hundredths = round(100 * (float(seconds) - int_seconds))
        return f"{'-' if seconds < 0 else ''}{h:01}:{m:02}:{s:02}.{hundredths:02}"

    def to_string(self) -> str:
        fade_milliseconds = round(1000 * (self.EndTimeSeconds - self.StartTimeSeconds) / 20)
        return f'Dialogue: 0,{self.__seconds_to_timestamp(self.StartTimeSeconds)},{self.__seconds_to_timestamp(self.EndTimeSeconds)},,,0000,0000,0000,,{{\\move(320,480,320,360)}}{{\\fad({fade_milliseconds},{fade_milliseconds})}}{{\\1c&H00FF00&}}{self.Author}: {{\\1c&HFFFFFF&}}{self.MessageText}\n'


def even_spaced_timestamp_filter(chat_messages: List[ChatMessage], smoothing_interval_seconds: float = 5):
    """Smooths out chat message timestamps within regularly-spaced intervals, so that timestamps are more evenly-spaced. This helps readability when bursts of several messages occur at nearly the same time."""
    if len(chat_messages) == 0:
        return
    if smoothing_interval_seconds <= 0:
        raise ValueError(f'smoothingIntervalSeconds must be positive, but was {smoothing_interval_seconds}')
    min_index = 0
    max_index = -1
    min_timestamp = 0
    max_timestamp = smoothing_interval_seconds
    last_timestamp = chat_messages[-1].timestamp_seconds
    while min_timestamp < last_timestamp:
        while max_index + 1 < len(chat_messages) and chat_messages[max_index + 1].timestamp_seconds < max_timestamp:
            max_index += 1
        comments_in_interval = max_index - min_index + 1
        if comments_in_interval > 0:
            for i in range(0, comments_in_interval):
                chat_messages[min_index + i].timestamp_seconds = min_timestamp + (
                        2 * i + 1) * smoothing_interval_seconds / (2 * comments_in_interval)
        min_index = max_index + 1
        min_timestamp += smoothing_interval_seconds
        max_timestamp += smoothing_interval_seconds


def parse_chat_messages(chats) -> List[ChatMessage]:
    chat_messages: List[ChatMessage] = []
    for chat in chats:
        message_text: str = chat['message']
        # Replace shorthand emotes, like :partying_face:, with UTF, like 🥳.
        emotes = chat.get('emotes')
        if emotes:
            for emote in emotes:
                utf_id = emote['id']
                shortcuts = emote['shortcuts']
                # "Custom emojis" use sprite images, not UTF characters, and SRT cannot display images, so ignore these.
                is_not_custom_emoji = not emote['is_custom_emoji']
                if utf_id and shortcuts and is_not_custom_emoji:
                    for shortcut in shortcuts:
                        message_text = message_text.replace(shortcut, utf_id)
        chat_messages.append(ChatMessage(
            timestamp_seconds=chat['time_in_seconds'],
            author=chat['author']['name'],
            message_text=message_text))
    return chat_messages


def parse_srt_lines(chat_messages: List[ChatMessage], max_seconds_onscreen: float = 5) -> List[SrtLine]:
    if max_seconds_onscreen <= 0:
        raise ValueError(f'max_seconds_onscreen must be positive, but was {max_seconds_onscreen}')
    srt_lines: List[SrtLine] = []
    for index, chatMessage in enumerate(chat_messages):
        next_timestamp_seconds = chat_messages[index + 1].timestamp_seconds if index + 1 < len(chat_messages) else float(
            "inf")
        srt_lines.append(SrtLine(
            index=index,
            start_time_seconds=chatMessage.timestamp_seconds,
            end_time_seconds=min(next_timestamp_seconds, chatMessage.timestamp_seconds + max_seconds_onscreen),
            author=chatMessage.Author,
            message_text=chatMessage.MessageText))
    return srt_lines


def parse_ass_lines(chat_messages: List[ChatMessage], max_seconds_onscreen: float = 5,
                    grouping_interval_seconds: float = 5, max_subtitles_onscreen: int = 5) -> List[AssLine]:
    if max_seconds_onscreen <= 0:
        raise ValueError(f'max_seconds_onscreen must be positive, but was {max_seconds_onscreen}')
    if grouping_interval_seconds <= 0:
        raise ValueError(f'grouping_interval_seconds must be positive, but was {grouping_interval_seconds}')
    if max_subtitles_onscreen <= 0:
        raise ValueError(f'max_subtitles_onscreen must be positive, but was {max_seconds_onscreen}')
    ass_lines: List[AssLine] = []
    if len(chat_messages) == 0:
        return ass_lines
    min_timestamp = 0
    max_timestamp = grouping_interval_seconds
    last_timestamp = chat_messages[-1].timestamp_seconds
    min_index = 0
    max_index = -1
    while min_timestamp < last_timestamp:
        while max_index + 1 < len(chat_messages) and chat_messages[max_index + 1].timestamp_seconds < max_timestamp:
            max_index += 1
        comments_in_interval = max_index - min_index + 1
        if comments_in_interval > 0:
            subtitles_per_second = comments_in_interval / grouping_interval_seconds
            for i in range(0, comments_in_interval):
                chat_message = chat_messages[min_index + i]
                time_onscreen = min(max_subtitles_onscreen / subtitles_per_second, max_seconds_onscreen)
                ass_lines.append(AssLine(
                    start_time_seconds=chat_message.timestamp_seconds,
                    end_time_seconds=chat_message.timestamp_seconds + time_onscreen,
                    author=chat_message.Author,
                    message_text=chat_message.MessageText))
        min_index = max_index + 1
        min_timestamp += grouping_interval_seconds
        max_timestamp += grouping_interval_seconds
    return ass_lines


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--max_seconds_onscreen', required=False, default=5)
    parser.add_argument('--smoothing_interval_seconds', required=False, default=5)
    parser.add_argument('--title', required=False, default='subtitles')

    subparsers = parser.add_subparsers(dest='command', required=True)
    parser_srt = subparsers.add_parser('srt')
    parser_ass = subparsers.add_parser('ass')
    parser_ass.add_argument('--max_subtitles_onscreen', required=False, default=5)

    args = parser.parse_args()

    chatMessages = parse_chat_messages(ChatDownloader().get_chat(args.url))
    even_spaced_timestamp_filter(chatMessages, args.smoothing_interval_seconds)

    if args.command == 'srt':
        lines = parse_srt_lines(chatMessages, args.max_seconds_onscreen)
    else:
        lines = parse_ass_lines(chatMessages, args.max_seconds_onscreen, args.smoothing_interval_seconds,
                                args.max_subtitles_onscreen)

    filePath = os.path.join(os.getcwd(), f'{args.title}.{args.command}')
    with open(filePath, 'w', encoding='utf-8') as file:
        if args.command != 'srt':
            file.write(assHeader)
        for line in lines:
            file.write(line.to_string())
        print(f'Wrote subtitles to {filePath}')
