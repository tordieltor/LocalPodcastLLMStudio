"""
LocalPodcastLLMStudio - Prompt Engineering & Persona Templates
Bilingual (Norwegian Bokmål / English), 4-tier episode length presets,
3-tier style/tone configurations, and 3-tier document grounding engine
for two-host podcast dialogue.
"""

from enum import Enum
from typing import Any

# ==============================================================================
# Grounding Modes & Anti-Hallucination Directives
# ==============================================================================


class GroundingMode(str, Enum):
    """Grounding modes for podcast dialogue generation."""

    STRICT = "strict"
    CREATIVE = "creative"
    OPEN_TOPIC = "open_topic"


GROUNDING_MODE_PRESETS: dict[str, dict[str, Any]] = {
    "strict": {
        "id": "strict",
        "name_en": "Strict Source-Only",
        "name_nb": "Streng kildetroskap",
        "badge": "100% Document Fidelity",
        "description_en": (
            "Strict adherence to provided document. Forbids inventing external facts, "
            "unmentioned statistics, or fabricated claims. Hosts acknowledge missing details."
        ),
        "description_nb": (
            "Streng forankring i det oppgitte dokumentet. Forbyr oppspinn av eksterne fakta, "
            "tall eller påstander. Programlederne erkjenner eksplisitt manglende detaljer."
        ),
        "anti_hallucination_level": "strict",
    },
    "creative": {
        "id": "creative",
        "name_en": "Creative Analogy & Synthesis",
        "name_nb": "Kreativ analogi & syntese",
        "badge": "Grounded Insights + Analogies",
        "description_en": (
            "Grounds core insights in document while allowing relatable real-world analogies, "
            "metaphors, and conversational illustrative examples."
        ),
        "description_nb": (
            "Forankrer kjerneinnsikten i dokumentet, men tillater levende hverdagsanalogier, "
            "metaforer og illustrerende eksempler."
        ),
        "anti_hallucination_level": "moderate",
    },
    "open_topic": {
        "id": "open_topic",
        "name_en": "Open Topic / Scratch",
        "name_nb": "Åpent tema / Fritt manus",
        "badge": "Free Generative Synthesis",
        "description_en": (
            "Free generative synthesis from topic prompt without document constraints. "
            "Generates rich perspectives, background, and engaging scenarios."
        ),
        "description_nb": (
            "Fri generering og idéutvikling basert på tema uten dokumentbegrensninger. "
            "Skaper fyldige perspektiver, bakgrunn og engasjerende samtaler."
        ),
        "anti_hallucination_level": "none",
    },
}

GROUNDING_MODE_ALIASES: dict[str, str] = {
    "strict": "strict",
    "strict_source_only": "strict",
    "strict_source": "strict",
    "strict-source": "strict",
    "source_only": "strict",
    "source-only": "strict",
    "source": "strict",
    "factual": "strict",
    "streng": "strict",
    "kildetro": "strict",
    "kilde": "strict",
    "creative": "creative",
    "creative_analogy": "creative",
    "creative-analogy": "creative",
    "creative_synthesis": "creative",
    "analogy": "creative",
    "synthesis": "creative",
    "metaphor": "creative",
    "kreativ": "creative",
    "open_topic": "open_topic",
    "open-topic": "open_topic",
    "open": "open_topic",
    "topic": "open_topic",
    "scratch": "open_topic",
    "free": "open_topic",
    "fritt": "open_topic",
    "tema": "open_topic",
    "åpent": "open_topic",
    "åpent_tema": "open_topic",
    "apent": "open_topic",
    "apent_tema": "open_topic",
}


def normalize_grounding_mode(mode: str | GroundingMode | Any) -> str:
    """
    Normalizes grounding mode string or enum to 'strict', 'creative', or 'open_topic'.
    Falls back to 'strict' on unrecognized or invalid inputs.
    """
    if isinstance(mode, GroundingMode):
        return mode.value
    if mode is None:
        return GroundingMode.STRICT.value
    raw = str(mode).lower().strip().replace(" ", "_").replace("-", "_")
    aliased = GROUNDING_MODE_ALIASES.get(raw, raw)
    if aliased in GROUNDING_MODE_PRESETS:
        return aliased
    return GroundingMode.STRICT.value


GROUNDING_DIRECTIVES_NB: dict[str, str] = {
    "strict": (
        "STRENG KILDEKONTROLL OG FORANKRING (STRENG KILDETROSKAP):\n"
        "- Samtalen skal KUN basere seg på faktiske opplysninger, data, funn og poenger som eksplisitt finnes i kildematerialet.\n"
        "- STRENGT FORBUDT: Det er strengt forbudt å finne på eller dikte opp eksterne fakta, uprøvde påstander, unevnte statistikker, tall, sitater eller fiktive kilder som ikke forekommer i teksten.\n"
        "- HÅNDTERING AV MANGLENDE DETALJER: Dersom informasjonen mangler eller en forklaring ikke er omtalt i kildematerialet, skal vertene eksplisitt og naturlig anerkjenne denne begrensningen (f.eks. «Dokumentet nevner ikke spesifikt...» eller «Det går ikke kilden nærmere inn på...»).\n"
        "- Hold dere 100 % tro mot forfatterens intensjon og konklusjoner uten spekulative påstander."
    ),
    "creative": (
        "KILDEFORANKRING OG KREATIV ANALOGI & SYNTESE (KREATIVITET OG FORKLARING):\n"
        "- Forankre kjerneinnsiktene, faglige mekanismer, hovedfunn og tall trygt i kildematerialet, slik at kjernebudskap forblir intakt.\n"
        "- LEVENDE ANALOGIER OG METAFORER: Vertene oppfordres sterkt til å bruke hverdagsanalogier, kreative metaforer og illustrative eksempler for å belyse komplekse konsepter og gjøre stoffet engasjerende for lytteren.\n"
        "- RETNINGSLINJER FOR ANALOGIER: Analogi og illustrerende eksempler skal støtte og forklare kildens reelle poenger, og må aldri motbevise eller fabrikkere motstridende fakta."
    ),
    "open_topic": (
        "FRITT TEMA OG ÅPEN DISKUSJON (ÅPENT TEMA / FRITT MANUS):\n"
        "- Samtalen genereres som fri syntese og utforsking basert på det oppgitte temaet, uten binding til et fast kildedokument.\n"
        "- Vertene bruker sin generelle ekspertise, bred allmennkunnskap og varierte perspektiver til å trekke inn relevante eksempler, historiske paralleller og engasjerende problemstillinger.\n"
        "- Oppretthold en logisk, reflektert og engasjerende samtaledynamikk med god faglig troverdighet."
    ),
}

GROUNDING_DIRECTIVES_EN: dict[str, str] = {
    "strict": (
        "GROUNDING & ANTI-HALLUCINATION (STRICT SOURCE-ONLY):\n"
        "- Every fact, figure, claim, and conclusion MUST be derived EXCLUSIVELY from statements explicitly present in the source material.\n"
        "- STRICTLY FORBIDDEN: It is strictly forbidden to fabricate or invent external facts, unmentioned statistics, fabricated claims, research findings, or person names not present in the text.\n"
        "- HANDLING OMISSIONS: If a specific detail, mechanism, or explanation is not covered in the source (lack of information), the hosts MUST explicitly and naturally acknowledge the omission (e.g., 'The document doesn't mention that specifically...' or 'The text leaves that open...').\n"
        "- Adhere strictly and remain 100% faithful to the source material's verified scope without speculative extrapolation."
    ),
    "creative": (
        "GROUNDING & CREATIVE ANALOGY & SYNTHESIS (CREATIVITY & INTUITION):\n"
        "- Anchor all core insights, key mechanisms, baseline findings, and data firmly in the source material so core facts and message remain uncompromised.\n"
        "- VIVID ANALOGIES & METAPHORS: Hosts are strongly encouraged to employ relatable real-world analogies, metaphors, and conversational illustrative examples to clarify complex mechanics and make ideas intuitive.\n"
        "- ANALOGY GUIDELINES: Creative metaphors and illustrative stories must illuminate the document's verified takeaways without distorting or fabricating conflicting data."
    ),
    "open_topic": (
        "OPEN TOPIC & GENERATIVE SYNTHESIS (OPEN TOPIC / SCRATCH):\n"
        "- Open, creative exploration and generative synthesis based on the provided topic prompt, without constraints to a single source document.\n"
        "- Hosts draw upon broad general knowledge, analytical reasoning, and diverse perspectives to explore multiple dimensions, debate nuances, and deliver an engaging, educational dialogue.\n"
        "- Maintain logical coherence, intellectual depth, and internal narrative consistency throughout."
    ),
}

# ==============================================================================
# Episode Format Presets
# ==============================================================================
FORMAT_PRESETS: dict[str, dict[str, Any]] = {
    "quick": {
        "id": "quick",
        "name": "Quick Summary",
        "duration": "~2-3 mins",
        "target_turns": 8,
        "min_turns": 6,
        "max_turns": 8,
        "description_nb": "Kort og konsis oppsummering (6-8 replikker totalt, ~2-3 minutter). Fokus på de viktigste hovedpunktene og umiddelbare konklusjoner.",
        "description_en": "Quick, punchy overview (6-8 turns total, ~2-3 minutes). Focus on high-level takeaways and core conclusions.",
    },
    "standard": {
        "id": "standard",
        "name": "Standard Episode",
        "duration": "~5-7 mins",
        "target_turns": 14,
        "min_turns": 12,
        "max_turns": 16,
        "description_nb": "Balansert standardepisode (12-16 replikker totalt, ~5-7 minutter). God flyt mellom introduksjon, faglige eksempler, drøfting og avrunding.",
        "description_en": "Balanced standard episode (12-16 turns total, ~5-7 minutes). Natural flow covering intro, practical examples, discussion, and recap.",
    },
    "deep_dive": {
        "id": "deep_dive",
        "name": "Deep Dive",
        "duration": "~10-15 mins",
        "target_turns": 22,
        "min_turns": 20,
        "max_turns": 26,
        "description_nb": "Grundig dybdeanalyse (20-26 replikker totalt, ~10-15 minutter). Detaljert utforsking av mekanismer, nyanser, praktiske implikasjoner og motargumenter.",
        "description_en": "Comprehensive deep dive (20-26 turns total, ~10-15 minutes). Thorough exploration of mechanisms, nuances, implications, and counterpoints.",
    },
    "extended": {
        "id": "extended",
        "name": "Extended In-Depth",
        "duration": "~25-30 mins",
        "target_turns": 50,
        "min_turns": 45,
        "max_turns": 60,
        "description_nb": "Omfattende fordypning (45-60 replikker totalt, ~25-30 minutter). Svært detaljert samtale som dekker alle fasetter, historisk bakgrunn, fremtidsperspektiver og dybdeinnsikter.",
        "description_en": "Extended in-depth masterclass (45-60 turns total, ~25-30 minutes). Highly exhaustive dialogue covering historical context, technical details, edge cases, and future outlook.",
    },
}

# Format aliases for backward compatibility
FORMAT_ALIASES: dict[str, str] = {
    "short": "quick",
    "summary": "quick",
    "quick_summary": "quick",
    "std": "standard",
    "standard_episode": "standard",
    "deep": "deep_dive",
    "deepdive": "deep_dive",
    "deep_dive": "deep_dive",
    "in_depth": "extended",
    "indepth": "extended",
    "extended_in_depth": "extended",
    "long": "extended",
}

# ==============================================================================
# Tone and Style Configurations
# ==============================================================================
TONE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "casual": {
        "id": "casual",
        "name": "Casual & Lively",
        "nb": "Uformell, livlig og engasjerende tone med naturlig småprat, varme, humor, hverdagslige metaforer og dynamiske utbrudd ('Aha!', 'Akkurat!', 'Du vil ikke tro det!').",
        "en": "Casual, lively, and warm conversational tone with friendly banter, humor, everyday analogies, and natural reactions ('Aha!', 'Exactly!', 'You won't believe this!').",
    },
    "analytical": {
        "id": "analytical",
        "name": "Analytical & Educational",
        "nb": "Strukturert, analytisk og pedagogisk tone med klare definisjoner, logisk oppbygging, grundige forklaringer og saklig dybde.",
        "en": "Structured, analytical, and educational tone with clear definitions, logical progression, objective breakdowns, and conceptual depth.",
    },
    "debate": {
        "id": "debate",
        "name": "Lively Debate",
        "nb": "Engasjert og tankevekkende debatt med vennlig intellektuell friksjon, djevelens advokat-spørsmål, avveining av fordeler og ulemper, og syntese av synspunkter.",
        "en": "Engaging and thought-provoking debate featuring friendly intellectual friction, devil's advocate questions, weighing pros and cons, and balanced synthesis.",
    },
}

TONE_ALIASES: dict[str, str] = {
    "casual & lively": "casual",
    "lively": "casual",
    "fun": "casual",
    "analytical & educational": "analytical",
    "educational": "analytical",
    "serious": "analytical",
    "lively debate": "debate",
    "discussion": "debate",
}


def normalize_language_code(language: str) -> str:
    """Normalizes language string to 'nb-NO' or 'en-US'."""
    lang_lower = str(language).lower()
    if any(k in lang_lower for k in ["nb", "no", "nor", "bokmål", "norsk"]):
        return "nb-NO"
    return "en-US"


def get_format_config(format_type: str) -> dict[str, Any]:
    """Retrieves format preset dictionary with fallback."""
    key = str(format_type).lower().strip().replace(" ", "_").replace("-", "_")
    key = FORMAT_ALIASES.get(key, key)
    return FORMAT_PRESETS.get(key, FORMAT_PRESETS["standard"])


def get_tone_description(tone_style: str, language: str = "nb-NO") -> str:
    """Retrieves localized tone description."""
    key = str(tone_style).lower().strip().replace(" ", "_").replace("-", "_")
    key = TONE_ALIASES.get(key, key)
    tone_dict = TONE_DESCRIPTIONS.get(key, TONE_DESCRIPTIONS["casual"])
    lang = normalize_language_code(language)
    return tone_dict["nb"] if lang == "nb-NO" else tone_dict["en"]


# ==============================================================================
# System Prompts & Personas
# ==============================================================================

SYSTEM_PROMPT_NB = """Du er en profesjonell podcast-manusforfatter i verdensklasse. Din oppgave er å forvandle kildemateriale eller tema til et engasjerende, naturlig og underholdende to-personers podcast-intervju på flytende norsk (bokmål).

PERSONAER:
- Host 1 (Kari): Den nysgjerrige og energiske programlederen. Hun stiller gode, intuitive spørsmål på vegne av lytteren, reagerer naturlig, bruker hverdagslige metaforer og holder flyten i samtalen i gang.
- Host 2 (Ola): Den kunnskapsrike og artikulerte fageksperten. Han forklarer komplekse konsepter på en klar, fascinerende og lettfattelig måte med konkrete eksempler og faglig dybde.

EPISODE-FORMAT:
- Mål for lengde: {format_name} ({duration})
- Antall replikker: Omtrent {min_turns} til {max_turns} replikker totalt ({target_turns} replikker anbefalt).
- Dynamikk: Veksle annenhver gang mellom "Host 1" og "Host 2". Begynn alltid med Host 1.

TONE OG STIL:
{tone_description}

KILDEFORANKRING:
{grounding_directive}

STRUKTUR:
1. INTRO (1-2 replikker): Kari ønsker lytterne hjertelig velkommen, fanger oppmerksomheten med en spennende innfallsvinkel og introduserer temaet. Ola hilser varmt tilbake.
2. HOVEDDEL ({main_turns} replikker): Kari og Ola utforsker kjerneinnholdet. Kari stiller oppfølgingsspørsmål og ber om forklaringer. Ola deler innsikt, eksempler og aha-opplevelser. Unngå lange monologer; hold hver replikk til 1-3 poengterte setninger.
3. OUTRO (1-2 replikker): En kort og inspirerende oppsummering av viktigste lærdom, og en hyggelig avskjedshilsen til lytterne.

STRENGT UTGÅENDE FORMAT:
Du MÅ svare KUN med et gyldig JSON-array. Ingen innledning, ingen forklaringer, ingen metadata utenom JSON.
Hvert element i arrayet må ha nøyaktig to nøkler: "speaker" (enten "Host 1" eller "Host 2") og "text" (selve replikken).

Eksempel på format:
[
  {{"speaker": "Host 1", "text": "Hei og hjertelig velkommen til dagens episode! I dag skal vi se nærmere på..."}},
  {{"speaker": "Host 2", "text": "Hei Kari! Ja, dette er et utrolig spennende tema som angår oss alle..."}}
]
"""

SYSTEM_PROMPT_EN = """You are a world-class podcast scriptwriter and audio dramatist. Your mission is to transform source material or topics into a broadcast-quality, natural two-host conversational podcast in fluent English.

PERSONAS:
- Host 1 (Jenny): The curious, charismatic host and interviewer. She hooks the audience, asks intuitive questions, uses relatable metaphors, reacts authentically, and steers the pacing.
- Host 2 (Guy): The authoritative yet warm domain expert. He articulates complex mechanics with precision, practical analogies, and clear, memorable takeaways.

EPISODE FORMAT:
- Target length: {format_name} ({duration})
- Turn count: Approximately {min_turns} to {max_turns} dialogue turns in total ({target_turns} turns recommended).
- Pacing: Alternate strictly between "Host 1" and "Host 2". Always begin with Host 1.

TONE AND STYLE:
{tone_description}

GROUNDING DIRECTIVE:
{grounding_directive}

STRUCTURE:
1. INTRO (1-2 turns): Jenny gives a warm welcome, creates an engaging hook, and introduces the episode topic. Guy greets Jenny and sets the stage.
2. CORE DISCUSSION ({main_turns} turns): Jenny and Guy dive into the key ideas. Jenny asks thought-provoking questions and offers reactions; Guy explains mechanisms and nuances with clarity. Avoid lengthy monologues; keep each turn between 1-3 conversational sentences.
3. OUTRO (1-2 turns): A crisp summary of key lessons and a warm, professional sign-off to the audience.

STRICT OUTPUT FORMAT:
You MUST output ONLY a valid JSON array of dialogue turn objects. No intro text, no conversational filler, no markdown fences outside the JSON array.
Each object must have exactly two keys: "speaker" (either "Host 1" or "Host 2") and "text" (the spoken line).

Exact JSON schema example:
[
  {{"speaker": "Host 1", "text": "Welcome back to the podcast everyone! Today we are exploring..."}},
  {{"speaker": "Host 2", "text": "Great to be here, Jenny! This is a fascinating topic because..."}}
]
"""


def build_system_prompt(
    language: str = "nb-NO",
    format_type: str = "standard",
    tone_style: str = "casual",
    grounding_mode: str = "strict",
) -> str:
    """
    Builds the complete LLM system prompt configured for language, length preset, tone, and grounding mode.
    """
    lang = normalize_language_code(language)
    fmt = get_format_config(format_type)
    tone_desc = get_tone_description(tone_style, lang)
    norm_mode = normalize_grounding_mode(grounding_mode)

    directives = GROUNDING_DIRECTIVES_NB if lang == "nb-NO" else GROUNDING_DIRECTIVES_EN
    grounding_directive = directives.get(norm_mode, directives["strict"])

    template = SYSTEM_PROMPT_NB if lang == "nb-NO" else SYSTEM_PROMPT_EN
    main_turns = max(2, fmt["target_turns"] - 3)

    return template.format(
        format_name=fmt["name"],
        duration=fmt["duration"],
        target_turns=fmt["target_turns"],
        min_turns=fmt["min_turns"],
        max_turns=fmt["max_turns"],
        main_turns=main_turns,
        tone_description=tone_desc,
        grounding_directive=grounding_directive,
    ).strip()


def build_user_prompt(
    content: str,
    language: str = "nb-NO",
    grounding_mode: str = "strict",
    is_topic: bool = False,
) -> str:
    """
    Builds the LLM user prompt based on input content, language, grounding mode, and is_topic flag.
    """
    lang = normalize_language_code(language)
    norm_mode = normalize_grounding_mode(grounding_mode)
    cleaned_content = content.strip()

    if is_topic or norm_mode == GroundingMode.OPEN_TOPIC:
        if lang == "nb-NO":
            return (
                f"Lag en fullstendig podcast-episode basert på følgende tema/oppgave:\n\n"
                f"TEMA: {cleaned_content}\n\n"
                f"Husk å levere KUN det gyldige JSON-arrayet med vekslende replikker mellom Host 1 og Host 2."
            )
        else:
            return (
                f"Create a complete podcast episode on the following topic:\n\n"
                f"TOPIC: {cleaned_content}\n\n"
                f"Remember to output ONLY the valid JSON array of alternating turns between Host 1 and Host 2."
            )

    if norm_mode == GroundingMode.CREATIVE:
        if lang == "nb-NO":
            return (
                f"Her er kildematerialet som skal diskuteres i podcasten:\n\n"
                f"--- START KILDEMATERIALE ---\n"
                f"{cleaned_content}\n"
                f"--- SLUTT KILDEMATERIALE ---\n\n"
                f"Lag podcast-manuset forankret i kildematerialet over med engasjerende analogier og pedagogiske eksempler. "
                f"Husk å levere KUN det gyldige JSON-arrayet med vekslende replikker mellom Host 1 og Host 2."
            )
        else:
            return (
                f"Here is the source material to be discussed in the podcast episode:\n\n"
                f"--- START SOURCE MATERIAL ---\n"
                f"{cleaned_content}\n"
                f"--- END SOURCE MATERIAL ---\n\n"
                f"Create the podcast script anchored in the source material above using relatable analogies and illustrative examples. "
                f"Remember to output ONLY the valid JSON array of alternating turns between Host 1 and Host 2."
            )
    else:  # Strict mode (default)
        if lang == "nb-NO":
            return (
                f"Her er kildematerialet som skal diskuteres i podcasten:\n\n"
                f"--- START KILDEMATERIALE ---\n"
                f"{cleaned_content}\n"
                f"--- SLUTT KILDEMATERIALE ---\n\n"
                f"Lag podcast-manuset basert strengt på kildematerialet over uten å finne på eksterne fakta. "
                f"Husk å levere KUN det gyldige JSON-arrayet med vekslende replikker mellom Host 1 og Host 2."
            )
        else:
            return (
                f"Here is the source material to be discussed in the podcast episode:\n\n"
                f"--- START SOURCE MATERIAL ---\n"
                f"{cleaned_content}\n"
                f"--- END SOURCE MATERIAL ---\n\n"
                f"Create the podcast script based strictly on the source material above without inventing external facts. "
                f"Remember to output ONLY the valid JSON array of alternating turns between Host 1 and Host 2."
            )


# ==============================================================================
# Multi-Act Structured Episodic Presets (NOU-guru Architecture)
# ==============================================================================

ACT_SPECS_NB: dict[str, list[dict[str, Any]]] = {
    "quick": [
        {
            "act_num": 1,
            "title": "Hovedoppsummering og kjerneinnsikt",
            "prompt_theme": "Kari og Ola åpner med en engasjert introduksjon av temaet, oppsummerer de viktigste kjernepunktene og konklusjonene, og runder av med en kort avskjed.",
            "target_turns": 8,
            "min_turns": 6,
            "max_turns": 8,
            "is_intro": True,
            "is_outro": True,
        }
    ],
    "standard": [
        {
            "act_num": 1,
            "title": "Innledning og sentrale temaer",
            "prompt_theme": "Kari åpner sendingen med en varm velkomst og engasjerende problemstilling. Ola og Kari diskuterer bakgrunnen, definisjoner og de mest sentrale problemstillingene.",
            "target_turns": 7,
            "min_turns": 6,
            "max_turns": 8,
            "is_intro": True,
            "is_outro": False,
        },
        {
            "act_num": 2,
            "title": "Faglige analyser, konsekvenser og avrunding",
            "prompt_theme": "Kari og Ola drøfter konkrete eksempler, praktiske konsekvenser, oppsummerer hovedlærdommen, og Kari runder av episoden.",
            "target_turns": 7,
            "min_turns": 6,
            "max_turns": 8,
            "is_intro": False,
            "is_outro": True,
        },
    ],
    "deep_dive": [
        {
            "act_num": 1,
            "title": "Innledning, samfunnsbilde og problemstilling",
            "prompt_theme": "Kari åpner sendingen med en engasjert innfallsvinkel og introduserer temaet. Kari og Ola drøfter hvorfor dette temaet er så viktig og hva det overordnede formålet er.",
            "target_turns": 8,
            "min_turns": 7,
            "max_turns": 9,
            "is_intro": True,
            "is_outro": False,
        },
        {
            "act_num": 2,
            "title": "Dybdeanalyse, mekanismer og dilemmaer",
            "prompt_theme": "Kari og Ola dykker dypt ned i faglige detaljer, motstridende hensyn, komplekse mekanismer og konkrete eksempler.",
            "target_turns": 9,
            "min_turns": 8,
            "max_turns": 10,
            "is_intro": False,
            "is_outro": False,
        },
        {
            "act_num": 3,
            "title": "Løsninger, praktiske implikasjoner og oppsummering",
            "prompt_theme": "Ola forklarer de mest lovende løsningene, strukturgrepene og framtidsutsiktene. Kari og Ola oppsummerer lærdommene, og Kari takker for at lytterne hørte på.",
            "target_turns": 8,
            "min_turns": 7,
            "max_turns": 9,
            "is_intro": False,
            "is_outro": True,
        },
    ],
    "extended": [
        {
            "act_num": 1,
            "title": "Innledning, samfunnsoppdrag og mandat",
            "prompt_theme": "Kari åpner sendingen med en engasjert og grundig introduksjon av temaet. Kari og Ola diskuterer hvorfor dette er så avgjørende, hvem aktørene er, og hva det overordnede oppdraget og formålet er.",
            "target_turns": 10,
            "min_turns": 9,
            "max_turns": 12,
            "is_intro": True,
            "is_outro": False,
        },
        {
            "act_num": 2,
            "title": "Historisk bakteppe og strukturelle utfordringer",
            "prompt_theme": "Ola og Kari drøfter samfunnsutviklingen, historiske årsaker og strukturelle utfordringer som har ledet frem til dagens situasjon. Hvilke lover, rammevilkår eller økonomiske faktorer spiller inn?",
            "target_turns": 11,
            "min_turns": 10,
            "max_turns": 13,
            "is_intro": False,
            "is_outro": False,
        },
        {
            "act_num": 3,
            "title": "Kjernefunn, faglige analyser og dilemmaer",
            "prompt_theme": "Kari og Ola analyserer de mest kritiske innsiktene, svakhetene, motstridende hensynene og faglige funnene. Hva er de største uenighetene og dilemmaene i praksis?",
            "target_turns": 12,
            "min_turns": 11,
            "max_turns": 14,
            "is_intro": False,
            "is_outro": False,
        },
        {
            "act_num": 4,
            "title": "Konkrete tiltak, reformer og løsninger",
            "prompt_theme": "Ola forklarer de viktigste konkrete tiltakene, forslagene, reformene og handlingsplanene. Kari utfordrer og drøfter de økonomiske og praktiske konsekvensene for brukerne og samfunnet.",
            "target_turns": 11,
            "min_turns": 10,
            "max_turns": 13,
            "is_intro": False,
            "is_outro": False,
        },
        {
            "act_num": 5,
            "title": "Konklusjoner, fremtidsutsikter og verdig avrunding",
            "prompt_theme": "Kari og Ola oppsummerer utredningens og diskusjonens viktigste lærdommer, historiske betydning og framtidsutsikter. Kari takker for at lytterne hørte på og runder av episoden.",
            "target_turns": 10,
            "min_turns": 9,
            "max_turns": 12,
            "is_intro": False,
            "is_outro": True,
        },
    ],
}

ACT_SPECS_EN: dict[str, list[dict[str, Any]]] = {
    "quick": [
        {
            "act_num": 1,
            "title": "Executive Summary & Core Takeaways",
            "prompt_theme": "Jenny and Guy open with an engaging hook introducing the topic, outline core takeaways, key conclusions, and wrap up with a quick sign-off.",
            "target_turns": 8,
            "min_turns": 6,
            "max_turns": 8,
            "is_intro": True,
            "is_outro": True,
        }
    ],
    "standard": [
        {
            "act_num": 1,
            "title": "Introduction & Key Themes",
            "prompt_theme": "Jenny opens with a warm welcome and compelling problem statement. Guy and Jenny discuss background, core definitions, and key dilemmas.",
            "target_turns": 7,
            "min_turns": 6,
            "max_turns": 8,
            "is_intro": True,
            "is_outro": False,
        },
        {
            "act_num": 2,
            "title": "Practical Analysis, Impacts & Recap",
            "prompt_theme": "Jenny and Guy discuss practical examples, real-world consequences, recap the primary lessons, and Jenny gives a warm sign-off.",
            "target_turns": 7,
            "min_turns": 6,
            "max_turns": 8,
            "is_intro": False,
            "is_outro": True,
        },
    ],
    "deep_dive": [
        {
            "act_num": 1,
            "title": "Introduction, Landscape & Problem Scope",
            "prompt_theme": "Jenny opens with a captivating hook and introduces the subject. Jenny and Guy examine why this matters and the overarching objectives.",
            "target_turns": 8,
            "min_turns": 7,
            "max_turns": 9,
            "is_intro": True,
            "is_outro": False,
        },
        {
            "act_num": 2,
            "title": "In-Depth Analysis, Mechanics & Dilemmas",
            "prompt_theme": "Jenny and Guy dive deep into mechanics, trade-offs, conflicting priorities, technical details, and real-world examples.",
            "target_turns": 9,
            "min_turns": 8,
            "max_turns": 10,
            "is_intro": False,
            "is_outro": False,
        },
        {
            "act_num": 3,
            "title": "Solutions, Practical Applications & Outro",
            "prompt_theme": "Guy explains promising solutions, structural reforms, and future implications. Jenny and Guy summarize key takeaways, and Jenny closes the episode.",
            "target_turns": 8,
            "min_turns": 7,
            "max_turns": 9,
            "is_intro": False,
            "is_outro": True,
        },
    ],
    "extended": [
        {
            "act_num": 1,
            "title": "Introduction, Mandate & Scope",
            "prompt_theme": "Jenny opens with an engaging, thorough introduction to the topic. Jenny and Guy discuss why this is crucial, key stakeholders, and overarching mission.",
            "target_turns": 10,
            "min_turns": 9,
            "max_turns": 12,
            "is_intro": True,
            "is_outro": False,
        },
        {
            "act_num": 2,
            "title": "Historical Context & Structural Challenges",
            "prompt_theme": "Guy and Jenny examine historical evolution, societal factors, and systemic challenges leading to the present situation.",
            "target_turns": 11,
            "min_turns": 10,
            "max_turns": 13,
            "is_intro": False,
            "is_outro": False,
        },
        {
            "act_num": 3,
            "title": "Core Discoveries, Deep Analysis & Critical Nuances",
            "prompt_theme": "Jenny and Guy dissect critical findings, underlying mechanisms, conflicting viewpoints, and major dilemma points.",
            "target_turns": 12,
            "min_turns": 11,
            "max_turns": 14,
            "is_intro": False,
            "is_outro": False,
        },
        {
            "act_num": 4,
            "title": "Concrete Proposals, Action Items & Practical Impact",
            "prompt_theme": "Guy details key solutions, structural reforms, and actionable recommendations. Jenny debates the practical and economic implications for end-users.",
            "target_turns": 11,
            "min_turns": 10,
            "max_turns": 13,
            "is_intro": False,
            "is_outro": False,
        },
        {
            "act_num": 5,
            "title": "Synthesis, Future Outlook & Concluding Sign-Off",
            "prompt_theme": "Jenny and Guy synthesize key learnings, historical significance, and future outlook. Jenny gives a polished, inspirational sign-off to the audience.",
            "target_turns": 10,
            "min_turns": 9,
            "max_turns": 12,
            "is_intro": False,
            "is_outro": True,
        },
    ],
}


def get_act_specs(format_type: str, language: str = "nb-NO") -> list[dict[str, Any]]:
    """Retrieves the list of thematic act specifications for an episode preset."""
    key = str(format_type).lower().strip().replace(" ", "_").replace("-", "_")
    key = FORMAT_ALIASES.get(key, key)
    lang = normalize_language_code(language)
    specs = ACT_SPECS_NB if lang == "nb-NO" else ACT_SPECS_EN
    return specs.get(key, specs["standard"])


def build_act_system_prompt(
    act: dict[str, Any],
    total_acts: int,
    language: str = "nb-NO",
    tone_style: str = "casual",
    grounding_mode: str = "strict",
    next_speaker: str = "Host 1",
) -> str:
    """Builds a specialized prompt for an individual act in a multi-act episode."""
    lang = normalize_language_code(language)
    tone_desc = get_tone_description(tone_style, lang)
    norm_mode = normalize_grounding_mode(grounding_mode)
    directives = GROUNDING_DIRECTIVES_NB if lang == "nb-NO" else GROUNDING_DIRECTIVES_EN
    grounding_directive = directives.get(norm_mode, directives["strict"])

    act_num = act["act_num"]
    act_title = act["title"]
    prompt_theme = act["prompt_theme"]
    target_turns = act.get("target_turns", 10)
    min_turns = act.get("min_turns", 8)
    max_turns = act.get("max_turns", 12)
    is_intro = act.get("is_intro", False)
    is_outro = act.get("is_outro", False)

    if lang == "nb-NO":
        continuity_rule = (
            "1. Dette er AKT 1 (INTRO). Start med at Host 1 ønsker velkommen og setter scenen med en fengende innfallsvinkel."
            if is_intro
            else f"1. VIKTIG: Dette er AKT {act_num} av {total_acts} (PÅGÅENDE SAMTALE). IKKE si 'velkommen' eller 'hei og velkommen' på nytt! Fortsett den eksisterende samtalen sømløst. Start med {next_speaker}."
        )
        ending_rule = (
            "2. Dette er siste akt. Host 1 oppsummerer kort og runder av sendingen med en hyggelig avskjedshilsen."
            if is_outro
            else "2. VIKTIG: IKKE avslutt sendingen eller si 'hadet' eller 'takk for at du hørte på' ennå! Avslutt denne akten med et engasjerende poeng eller overgang til neste tema."
        )

        return f"""Du er en prisvinnende podcast-manusforfatter for en anerkjent radiopodcast.
Skriv AKT {act_num} av {total_acts} ("{act_title}") som en naturlig, engasjerende dialog på flytende norsk (bokmål) mellom Host 1 (Kari - nysgjerrig programleder) og Host 2 (Ola - fagekspert).

TEMA OG FOKUS FOR DENNE AKTEN:
{prompt_theme}

TONE OG STIL:
{tone_desc}

KILDEFORANKRING:
{grounding_directive}

STRENGE KRAV TIL LENGDE OG STRUKTUR:
- Skriv nøyaktig {target_turns} replikker vekselvis mellom Host 1 og Host 2 (minst {min_turns}, maks {max_turns} replikker).
- Hver replikk skal være et fyldig, naturlig avsnitt med gode poenger, forklaringer eller oppfølging (2-4 setninger, 30-55 ord per replikk). Unngå korte one-liners!
- {continuity_rule}
- {ending_rule}

STRENGT UTGÅENDE FORMAT:
Svar KUN med et gyldig JSON-array. Ingen tekst utenom JSON.
[
  {{"speaker": "Host 1", "text": "..."}},
  {{"speaker": "Host 2", "text": "..."}}
]
""".strip()
    else:
        continuity_rule = (
            "1. This is ACT 1 (INTRO). Start with Host 1 giving a warm welcome and setting the hook."
            if is_intro
            else f"1. IMPORTANT: This is ACT {act_num} of {total_acts} (CONTINUATION). DO NOT say 'welcome back' or restart the intro! Seamlessly continue the ongoing conversation. Begin with {next_speaker}."
        )
        ending_rule = (
            "2. This is the final act. Host 1 summarizes key learnings and delivers a polished sign-off."
            if is_outro
            else "2. IMPORTANT: DO NOT conclude or say goodbye yet! End this act with an intriguing takeaway or natural transition."
        )

        return f"""You are a world-class podcast scriptwriter and audio dramatist.
Write ACT {act_num} of {total_acts} ("{act_title}") as a natural, broadcast-quality dialogue in fluent English between Host 1 (Jenny - interviewer) and Host 2 (Guy - domain expert).

TOPIC AND FOCUS FOR THIS ACT:
{prompt_theme}

TONE AND STYLE:
{tone_desc}

GROUNDING DIRECTIVE:
{grounding_directive}

STRICT REQUIREMENTS FOR LENGTH AND PACING:
- Write exactly {target_turns} dialogue turns alternating between Host 1 and Host 2 (minimum {min_turns}, maximum {max_turns} turns).
- Each turn must be a substantive, conversational paragraph (2-4 sentences, 30-55 words per turn). Avoid shallow one-liners!
- {continuity_rule}
- {ending_rule}

STRICT OUTPUT FORMAT:
Respond ONLY with a valid JSON array. No surrounding text.
[
  {{"speaker": "Host 1", "text": "..."}},
  {{"speaker": "Host 2", "text": "..."}}
]
""".strip()


def build_act_user_prompt(
    content: str,
    prev_turns: list[dict[str, str]] | None = None,
    language: str = "nb-NO",
    grounding_mode: str = "strict",
    is_topic: bool = False,
) -> str:
    """Builds the user prompt for an individual act with optional previous context continuity and grounding mode."""
    lang = normalize_language_code(language)
    norm_mode = normalize_grounding_mode(grounding_mode)
    cleaned_content = content.strip()

    prev_context = ""
    if prev_turns and len(prev_turns) > 0:
        turns_snippet = "\n".join(
            [f"{t.get('speaker', 'Host')}: {t.get('text', '')}" for t in prev_turns[-2:]]
        )
        if lang == "nb-NO":
            prev_context = f"\nSISTE REPLIKKER FRA FORRIGE DEL (FOR SØMLØS OVERGANG OG SAMMENHENG):\n{turns_snippet}\n"
        else:
            prev_context = f"\nLAST TURNS FROM PREVIOUS ACT (FOR CONTEXT & SEAMLESS TRANSITION):\n{turns_snippet}\n"

    if is_topic or norm_mode == GroundingMode.OPEN_TOPIC:
        if lang == "nb-NO":
            return (
                f"Tema for podcasten: {cleaned_content}\n"
                f"{prev_context}\n"
                f"Skriv dialogen for denne akten som et gyldig JSON-array."
            )
        else:
            return (
                f"Podcast topic: {cleaned_content}\n"
                f"{prev_context}\n"
                f"Write the dialogue turns for this act as a valid JSON array."
            )
    else:
        if lang == "nb-NO":
            return (
                f"Kildemateriale for podcasten:\n"
                f"--- START KILDEMATERIALE ---\n{cleaned_content}\n--- SLUTT KILDEMATERIALE ---\n"
                f"{prev_context}\n"
                f"Skriv dialogen for denne akten basert på kildematerialet som et gyldig JSON-array."
            )
        else:
            return (
                f"Source material for podcast:\n"
                f"--- START SOURCE MATERIAL ---\n{cleaned_content}\n--- END SOURCE MATERIAL ---\n"
                f"{prev_context}\n"
                f"Write the dialogue turns for this act based on the source material as a valid JSON array."
            )
