import os
import re
import base64
import math
from pathlib import Path
from PIL import Image

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Inches
from services.ai_images import generate_image, image_as_png, validate_image_config

from .ai_client import OpenAICompatibleClient


INVALID_FILENAME = re.compile(r'[<>:"/\\|?*]')


def _safe_stem(title, index):
    stem = INVALID_FILENAME.sub("_", str(title or "")).strip().rstrip(".")
    return stem or f"文章-{index}"


def _next_output_path(directory, title, index, reserved):
    stem = _safe_stem(title, index)
    suffix = 1
    while True:
        label = stem if suffix == 1 else f"{stem} ({suffix})"
        candidate = directory / f"{label}.docx"
        key = os.path.normcase(str(candidate.resolve()))
        if key not in reserved and not candidate.exists() and not (directory / f'{label}_配图').exists():
            reserved.add(key)
            return candidate
        suffix += 1


def _paragraphs(content):
    lines = []
    for raw_line in str(content).replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if line:
            lines.append(line)
    return lines or [str(content).strip()]


def _write_docx(path, title, content, include_title, image_paths=()):
    document = Document()
    if include_title:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(str(title))
        run.bold = True
        run.font.name = "Microsoft YaHei"
        run.font.size = Pt(18)
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    paragraphs = _paragraphs(content)
    image_index = 0
    for index, text in enumerate(paragraphs):
        document.add_paragraph(text)
        # 按正文段落均匀插图，图片少于段落时不会堆在文末。
        while image_index < len(image_paths) and index >= math.floor(image_index * len(paragraphs) / len(image_paths)):
            with Image.open(image_paths[image_index]) as image:
                width = min(5.5, 7 * image.width / image.height)
            document.add_picture(str(image_paths[image_index]), width=Inches(width))
            image_index += 1

    temporary_path = path.with_suffix(".tmp.docx")
    document.save(temporary_path)
    os.replace(temporary_path, path)


class WordGenerationService:
    def __init__(self, chat=None, image_generator=None):
        self._chat = chat or OpenAICompatibleClient().chat
        self._image_generator = image_generator or generate_image

    @staticmethod
    def _build_prompt(title, prompt):
        return (
            "你是中文新媒体文章写作助手。请直接输出可放入 Word 的自然段正文，"
            "不要输出 Markdown、JSON、HTML 或解释。\n"
            f"标题：{title}\n"
            f"写作要求：{prompt}"
        )

    def generate_batch(
        self,
        *,
        titles,
        prompt,
        output_directory,
        provider,
        include_title=True,
        images=None,
    ):
        clean_titles = [str(title).strip() for title in titles if str(title).strip()]
        if not clean_titles:
            raise ValueError("至少需要一个文章标题")
        if not str(prompt).strip():
            raise ValueError("写作提示词不能为空")

        local_images = []
        if images is not None:
            if not isinstance(images, dict) or images.get('mode') not in ('local', 'ai'):
                raise ValueError('配图模式必须是 local 或 ai')
            if images['mode'] == 'local':
                files = images.get('files')
                if not isinstance(files, list) or not 1 <= len(files) <= 4:
                    raise ValueError('请选择 1–4 张本地图片')
                for item in files:
                    try:
                        local_images.append(image_as_png(base64.b64decode(item['data'], validate=True)))
                    except (KeyError, TypeError, ValueError) as error:
                        raise ValueError('本地图片数据无效，请重新选择 PNG、JPEG 或 WebP 图片') from error
            else:
                validate_image_config(images.get('provider'))
                if type(images.get('count')) is not int or not 1 <= images['count'] <= 4:
                    raise ValueError('每篇 AI 配图数量必须为 1–4 张')
                if not isinstance(images.get('prompt'), str) or not images['prompt'].strip():
                    raise ValueError('请填写 AI 配图要求')

        output_directory = Path(output_directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        reserved = set()
        items = []

        for index, title in enumerate(clean_titles, start=1):
            output_path = _next_output_path(output_directory, title, index, reserved)
            try:
                content = self._chat(self._build_prompt(title, prompt), provider)
                image_paths = []
                if images:
                    # 每篇目录独立，避免同名文章或重复生成覆盖原图。
                    image_directory = output_path.parent / f'{output_path.stem}_配图'
                    image_directory.mkdir(exist_ok=False)
                    count = len(local_images) if images['mode'] == 'local' else images['count']
                    for image_index in range(count):
                        image_path = image_directory / f'{image_index + 1:02}.png'
                        if images['mode'] == 'local':
                            image_path.write_bytes(local_images[image_index])
                        else:
                            image_prompt = f"为文章《{title}》生成第 {image_index + 1}/{count} 张配图。\n配图要求：{images['prompt']}\n文章内容：{content}"
                            self._image_generator(images['provider'], image_prompt, image_path)
                        image_paths.append(image_path)
                _write_docx(output_path, title, content, include_title, image_paths)
                items.append(
                    {
                        "order": index,
                        "title": title,
                        "status": "succeeded",
                        "output_path": str(output_path),
                        "error": None,
                        "image_paths": [str(path) for path in image_paths],
                    }
                )
            except Exception as error:
                error_message = str(error)
                for key in (provider.get('api_key'), (images or {}).get('provider', {}).get('apiKey')):
                    if key:
                        error_message = error_message.replace(key, '***')
                items.append(
                    {
                        "order": index,
                        "title": title,
                        "status": "failed",
                        "output_path": None,
                        "error": error_message,
                    }
                )

        return {
            "provider_id": str(provider.get("provider_id", "custom")),
            "items": items,
            "succeeded": sum(item["status"] == "succeeded" for item in items),
            "failed": sum(item["status"] == "failed" for item in items),
        }
