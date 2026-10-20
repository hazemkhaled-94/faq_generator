"""Synthetic bank and shop corpora as stored lemma lists, de and en."""

import random

from topic_modelling.models import PassageVocabulary

SUBJECTS = {
    ("bank", "en"): {
        "cards": [
            "card",
            "debit",
            "credit",
            "limit",
            "pin",
            "contactless",
            "block",
            "stolen",
            "lost",
            "replacement",
            "chip",
            "statement",
        ],
        "fees": [
            "fee",
            "charge",
            "monthly",
            "annual",
            "price",
            "tariff",
            "overdraft",
            "commission",
            "interest",
            "rate",
            "cost",
            "waiver",
        ],
        "transfers": [
            "transfer",
            "payee",
            "iban",
            "abroad",
            "currency",
            "sepa",
            "instant",
            "standing",
            "order",
            "beneficiary",
            "swift",
            "recipient",
        ],
        "accounts": [
            "account",
            "open",
            "close",
            "joint",
            "savings",
            "current",
            "balance",
            "deposit",
            "holder",
            "statement",
            "minimum",
        ],
    },
    ("bank", "de"): {
        "cards": [
            "karte",
            "debitkarte",
            "kreditkarte",
            "limit",
            "pin",
            "kontaktlos",
            "sperren",
            "gestohlen",
            "verloren",
            "ersatzkarte",
            "chip",
        ],
        "fees": [
            "gebühr",
            "entgelt",
            "monatlich",
            "jährlich",
            "preis",
            "tarif",
            "dispo",
            "provision",
            "zins",
            "zinssatz",
            "kosten",
        ],
        "transfers": [
            "überweisung",
            "empfänger",
            "iban",
            "ausland",
            "währung",
            "sepa",
            "echtzeit",
            "dauerauftrag",
            "begünstigter",
            "swift",
            "auftrag",
        ],
        "accounts": [
            "konto",
            "eröffnung",
            "kündigung",
            "gemeinschaftskonto",
            "sparkonto",
            "girokonto",
            "saldo",
            "einzahlung",
            "inhaber",
            "kontoauszug",
        ],
    },
    ("shop", "en"): {
        "returns": [
            "return",
            "refund",
            "parcel",
            "label",
            "days",
            "condition",
            "exchange",
            "item",
            "original",
            "packaging",
            "receipt",
        ],
        "delivery": [
            "delivery",
            "shipping",
            "courier",
            "tracking",
            "address",
            "days",
            "express",
            "dispatch",
            "carrier",
            "postcode",
        ],
        "payment": [
            "payment",
            "invoice",
            "instalment",
            "paypal",
            "card",
            "checkout",
            "transaction",
            "amount",
            "due",
            "method",
        ],
        "vouchers": [
            "voucher",
            "code",
            "gift",
            "discount",
            "redeem",
            "expiry",
            "balance",
            "promotion",
            "value",
            "coupon",
        ],
    },
    ("shop", "de"): {
        "returns": [
            "rücksendung",
            "erstattung",
            "paket",
            "etikett",
            "tage",
            "zustand",
            "umtausch",
            "artikel",
            "originalverpackung",
            "beleg",
        ],
        "delivery": [
            "lieferung",
            "versand",
            "paketdienst",
            "sendungsverfolgung",
            "adresse",
            "tage",
            "express",
            "zusteller",
            "postleitzahl",
        ],
        "payment": [
            "zahlung",
            "rechnung",
            "ratenzahlung",
            "paypal",
            "karte",
            "kasse",
            "transaktion",
            "betrag",
            "fällig",
            "zahlungsart",
        ],
        "vouchers": [
            "gutschein",
            "code",
            "geschenk",
            "rabatt",
            "einlösen",
            "ablauf",
            "guthaben",
            "aktion",
            "wert",
            "coupon",
        ],
    },
}
COMMON = {
    "en": [
        "customer",
        "service",
        "request",
        "online",
        "app",
        "branch",
        "contact",
        "form",
        "information",
        "condition",
        "period",
    ],
    "de": [
        "kunde",
        "service",
        "antrag",
        "online",
        "app",
        "filiale",
        "kontakt",
        "formular",
        "information",
        "bedingung",
        "zeitraum",
    ],
}


def corpus(domain, language, n, seed=0, first_id=1, length=(15, 40), noise=0.3):
    """Passages over one domain's subjects, a share of their words common."""
    rng = random.Random(seed)
    subjects = SUBJECTS[(domain, language)]
    names = sorted(subjects)
    out = []
    for i in range(n):
        subject = names[i % len(names)]
        size = rng.randint(*length)
        lemmas = [
            rng.choice(COMMON[language])
            if rng.random() < noise
            else rng.choice(subjects[subject])
            for _ in range(size)
        ]
        out.append(PassageVocabulary(id=first_id + i, lemmas=lemmas))
    return out


DEFAULTS = {
    "num_topics": 40,
    "passes": 10,
    "random_state": 42,
    "top_terms": 12,
    "min_weight": 0.05,
    "no_below": 3,
    "no_above": 0.5,
    "passages_per_topic": 40,
}
