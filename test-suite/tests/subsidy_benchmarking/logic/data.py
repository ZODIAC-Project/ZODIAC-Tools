import random
import pytest

# --- clean match (2×2, unambiguous) ---
CLEAN_CUSTOMERS = [
    {"id": "cust-1", "text": "Kleines Handwerksunternehmen, sucht Förderung für Digitalisierung."},
    {"id": "cust-2", "text": "Landwirtschaftlicher Betrieb, sucht Förderung für Nachhaltigkeit."},
]
CLEAN_SUBSIDIES = [
    {"id": "sub-1", "text": "Digitalisierungsförderung für kleine Handwerksbetriebe."},
    {"id": "sub-2", "text": "Nachhaltigkeitsförderung für landwirtschaftliche Betriebe."},
]
CLEAN_EXPECTED = {"cust-1": "sub-1", "cust-2": "sub-2"}

# --- no-match (one subsidy has no valid recipient in the customer list) ---
NOMATCH_CUSTOMERS = CLEAN_CUSTOMERS
NOMATCH_SUBSIDIES = CLEAN_SUBSIDIES + [
    {"id": "sub-3", "text": "Förderung für Filmproduktionsfirmen im Bereich Animation."},
]
NOMATCH_EXPECTED = CLEAN_EXPECTED  # sub-3 should not appear in any result

# --- distractor: two subsidies share a surface keyword, only one actually fits ---
DISTRACTOR_CUSTOMERS = [
    {"id": "cust-1", "text": "Kleines Café mit 4 Mitarbeitenden, sucht Förderung für eine Solaranlage auf dem Dach."},
]
DISTRACTOR_SUBSIDIES = [
    {"id": "sub-a", "text": "Solarförderung für Privathaushalte und Eigenheime."},
    {"id": "sub-b", "text": "Solarförderung für kleine und mittlere Gewerbebetriebe."},
]
DISTRACTOR_EXPECTED = {"cust-1": "sub-b"}  # sub-a is superficially similar (keyword "Solar") but wrong recipient type

# --- scale: N clearly-tagged domain pairs, subsidies shuffled so position != answer ---
_DOMAINS = [
    "Solartechnik", "Wasserwirtschaft", "Textilproduktion", "Holzverarbeitung", "Elektromobilität",
    "Bäckerei", "Metallbau", "IT-Dienstleistung", "Gartenbau", "Fischerei",
    "Weinbau", "Möbeltischlerei", "Uhrmacherei", "Glasbläserei", "Imkerei",
]

def build_scale_dataset(n: int = 15):
    domains = _DOMAINS[:n]
    customers = [{"id": f"cust-{i+1}", "text": f"Betrieb im Bereich {d}, sucht Förderung."}
                 for i, d in enumerate(domains)]
    subsidies = [{"id": f"sub-{i+1}", "text": f"Förderprogramm speziell für Betriebe im Bereich {d}."}
                 for i, d in enumerate(domains)]
    expected = {c["id"]: s["id"] for c, s in zip(customers, subsidies)}
    random.Random(42).shuffle(subsidies)  
    return customers, subsidies, expected