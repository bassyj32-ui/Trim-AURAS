"""Evidence: does Job(...) raise on burn_captions=None / 'true' strings / etc.?

Answers: why the upload path silently succeeded with burn_captions omitted,
and whether SQLModel coerces or stores raw strings (a Postgres bool-column
write would fail on a raw string).
"""
import sys

sys.path.insert(0, r"d:\trae\TrimAURAs\TrimAuras")

from app.models import Job


def t(label: str, **kw):
    try:
        j = Job(title="t", source_url="/tmp/x.mp4", **kw)
        k = next(iter(kw))
        v = getattr(j, k)
        print(f"{label:22s} OK      type={type(v).__name__:10s} value={v!r}")
    except Exception as e:
        print(f"{label:22s} RAISES  {type(e).__name__}: {str(e)[:140]}")


if __name__ == "__main__":
    print("SQLModel version:", __import__("sqlmodel").__version__)
    print("pydantic version:", __import__("pydantic").VERSION)
    print("-" * 70)
    t("burn None", burn_captions=None)
    t("burn 'true'", burn_captions="true")
    t("burn 'false'", burn_captions="false")
    t("burn 'yes'", burn_captions="yes")
    t("burn 'on'", burn_captions="on")
    t("burn True", burn_captions=True)
    t("burn 1", burn_captions=1)
    t("burn 'garbage'", burn_captions="garbage")
    t("trim None", trim_silence=None)
    t("trim 'true'", trim_silence="true")
    t("trim False", trim_silence=False)
    t("ph None", preferred_height=None)
    t("ph '720'", preferred_height="720")
    t("ph 'original'", preferred_height="original")
    t("ph 0", preferred_height=0)
    t("ph '0'", preferred_height="0")
