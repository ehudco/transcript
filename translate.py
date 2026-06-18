"""
Translates a Hebrew SRT string to English using OpenAI, with context lines.
Also provides make_csv() to produce a bilingual CSV from both SRT strings.
"""

import csv
import io
import pysrt
from secret_client import get_secret

CONTEXT_LINES = 5
MODEL = "gpt-4o-mini"


def translate_srt(srt_content: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))

    subs = pysrt.open(io.StringIO(srt_content), encoding="utf-8")
    translated_texts = []

    for idx, sub in enumerate(subs):
        context_start = max(0, idx - CONTEXT_LINES)
        context_block = "\n".join(
            f"{i+1}. {subs[i].text}" for i in range(context_start, idx)
        )
        prompt = (
            "This is a psychotherapy session. Translate the current Hebrew line into natural, "
            "fluent English while preserving emotional tone and nuance. "
            "Use the previous lines as context only — do not translate them.\n\n"
            f"Previous lines:\n{context_block}\n\n"
            f"Current line:\n{sub.text}"
        )
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a translator expert in psychology assisting with Hebrew to English "
                        "translation of psychotherapy sessions while adding a therapeutic tone."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        translated_texts.append(response.choices[0].message.content.strip())

    for sub, translated in zip(subs, translated_texts):
        sub.text = translated

    buf = io.StringIO()
    subs.write_into(buf)
    return buf.getvalue()


def make_csv(hebrew_srt: str, english_srt: str) -> str:
    """Produce a bilingual CSV string from Hebrew and English SRT content."""
    he_subs = pysrt.open(io.StringIO(hebrew_srt), encoding="utf-8")
    en_subs = pysrt.open(io.StringIO(english_srt), encoding="utf-8")

    if len(he_subs) != len(en_subs):
        raise ValueError(
            f"SRT subtitle count mismatch: {len(he_subs)} Hebrew vs {len(en_subs)} English"
        )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["subtitle_number", "timestamps", "hebrew_subtitle", "english_subtitle"])
    for he, en in zip(he_subs, en_subs):
        writer.writerow([
            he.index,
            f"{he.start} --> {he.end}",
            he.text.replace("\n", " "),
            en.text.replace("\n", " "),
        ])
    return buf.getvalue()
