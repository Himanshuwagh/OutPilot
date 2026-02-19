"""
Company name search variants for matching across platforms.

X often uses handles like @Tactfulai (scraped as "Tactful AI") while
LinkedIn/domains use "Tactful". This module provides variants so discovery
and domain lookup can try multiple names.
"""


def get_company_name_variants(company_name: str) -> list[str]:
    """
    Return search variants for a company name so we can match LinkedIn/domains
    when X uses a handle like @Tactfulai (scraped as "Tactful AI") but
    LinkedIn uses "Tactful" only. Tries: original, without trailing AI/ML/Inc, etc.
    """
    name = (company_name or "").strip()
    if not name:
        return []
    seen: set[str] = set()
    out: list[str] = []

    def add(s: str) -> None:
        s = (s or "").strip()
        if s and len(s) >= 2 and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)

    add(name)

    # "Tactful AI" / "Tactfulai" -> also try "Tactful"
    lowered = name.lower()
    for suffix in (
        " ai", " ai.", " ai,", " ml", " ml.", " ml,",
        " artificial intelligence", " machine learning",
        " inc", " inc.", " inc,", " ltd", " ltd.", " llc", " llc.",
        " co", " co.", " corp", " corp.", " company",
    ):
        if lowered.endswith(suffix.rstrip("., ")):
            base = name[: -len(suffix.rstrip("., "))].strip()
            if base:
                add(base)
                break

    # One word ending with "ai" or "ml" (e.g. Tactfulai) -> base name
    if " " not in name and len(name) > 2:
        for end in ("ai", "ml"):
            if lowered.endswith(end) and len(lowered) > len(end):
                base = name[: -len(end)].strip()
                if base:
                    add(base)
                    add(base + " " + end.upper())
                break

    # "X AI" or "X ML" -> add "X"
    parts = name.split()
    if len(parts) >= 2 and parts[-1].upper() in ("AI", "ML"):
        base = " ".join(parts[:-1]).strip()
        if base:
            add(base)

    return out
