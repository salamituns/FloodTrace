#!/usr/bin/env python3
"""Compile events/lagos-2011-07-10/evidence.geojson from named sources.

Accuracy over coverage: locations, times, numbers and quotes come only
from pages that were read (or from a headline/snippet if blocked).
Non-Lagos places (Ibadan, Katsina, Akute/Alagbole/Denro) are omitted.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geocode import geocode_many, in_bbox
from quotes import clip_quote

ROOT = Path(__file__).resolve().parents[1]
BBOX = [2.70, 6.38, 4.35, 6.75]
EVENT_DIR = ROOT / "events/lagos-2011-07-10"

# Neighbourhood centres used only when Nominatim misses or is implausible.
MANUAL = {
    "Dopemu, Agege, Lagos": (3.315, 6.612),
    "Aboru, Lagos": (3.288, 6.642),
    "Agbado-Oke Odo, Lagos": (3.285, 6.658),
    "Ogba, Ikeja, Lagos": (3.342, 6.632),
    "Agege, Lagos": (3.323, 6.622),
    "Orile-Agege, Lagos": (3.308, 6.618),
    "Iyana-Ipaja, Lagos": (3.296, 6.608),
    "Ikoyi, Lagos": (3.434, 6.454),
    "Victoria Island, Lagos": (3.421, 6.428),
    "Apapa, Lagos": (3.365, 6.448),
    "Lekki, Lagos": (3.52, 6.44),
    "Ajegunle, Ajeromi-Ifelodun, Lagos": (3.341, 6.454),
    "Okatapo Street, Ajegunle, Lagos": (3.341, 6.454),
    "Young Lane, Ajegunle, Lagos": (3.341, 6.454),
    "Jakande Estate, Isolo, Lagos": (3.320, 6.535),
    "Olodi Apapa, Lagos": (3.348, 6.452),
    "Oyingbo, Lagos": (3.383, 6.478),
    "Alagbado, Lagos": (3.255, 6.672),
    "Obadeyi, Abeokuta Expressway, Lagos": (3.285, 6.635),
    "Adesokan Street, Dopemu, Lagos": (3.315, 6.612),
    "Odejobi Street, Iju, Agege, Lagos": (3.338, 6.638),
    "Isheri North, Lagos": (3.268, 6.645),
    "Silverbird, Lekki, Lagos": (3.415, 6.428),
    "Mobil Filling Station, Ogba, Lagos": (3.342, 6.632),
    "Abattoir canal, Orile-Agege, Lagos": (3.308, 6.618),
    "Mustapha Street, Ajegunle, Lagos": (3.341, 6.454),
    "Lawani Street, Ajegunle, Lagos": (3.341, 6.454),
    "Rashidi Street, Ajegunle, Lagos": (3.341, 6.454),
    "Apana Street, Ajegunle, Lagos": (3.341, 6.454),
    "Babatunde Street, Ajegunle, Lagos": (3.341, 6.454),
    "Isikalu Lane, Ajegunle, Lagos": (3.341, 6.454),
    "Apapa-Oshodi Expressway, Lagos": (3.345, 6.468),
    "Ojota, Lagos": (3.379, 6.586),
    "Ketu, Lagos": (3.390, 6.590),
    "Ifako-Ijaiye, Lagos": (3.328, 6.650),
    "Utility Street, Ifako-Ijaiye, Lagos": (3.328, 6.650),
    "Allen Avenue, Ikeja, Lagos": (3.355, 6.601),
    "Alapere, Ketu, Lagos": (3.392, 6.592),
    "Ojuelegba, Surulere, Lagos": (3.364, 6.509),
    "Ajao Street, Surulere, Lagos": (3.355, 6.505),
    "Randle Avenue, Surulere, Lagos": (3.360, 6.500),
    "Akinola, Agbado-Oke Odo, Lagos": (3.285, 6.658),
    "Alabede, Agbado-Oke Odo, Lagos": (3.285, 6.658),
    "Awolowo Way, Ikeja, Lagos": (3.351, 6.596),
    "Oshodi, Lagos": (3.336, 6.556),
    "Ejigbo, Lagos": (3.305, 6.548),
    "Owode Onirin, Lagos": (3.398, 6.608),
    "Ajegunle, Ikorodu, Lagos": (3.508, 6.618),
    "Casso, Alagbado, Lagos": (3.255, 6.672),
    "Akera, Alagbado, Lagos": (3.255, 6.672),
    "Cele Express, Isolo, Lagos": (3.318, 6.538),
    "Ikotun, Lagos": (3.268, 6.558),
    "Oniwaya, Agege, Lagos": (3.323, 6.625),
    "Gbagada, Lagos": (3.389, 6.557),
    "Oworonshoki, Lagos": (3.405, 6.555),
    "Lagos, Nigeria": (3.40, 6.45),
    "Ijaiye, Lagos": (3.328, 6.650),
}

IMPLAUSIBLE = {
    "Lekki, Lagos": ("Ibeju Lekki", "Free Trade"),
    "Ajegunle, Ikorodu, Lagos": ("Ajeromi", "Ifelodun", "Olodi"),
    "Ajegunle, Ajeromi-Ifelodun, Lagos": ("Ikorodu",),
    "Okatapo Street, Ajegunle, Lagos": ("Ikorodu",),
    "Alagbado, Lagos": ("Festac", "Amuwo"),
    "Ogba, Ikeja, Lagos": ("Ogba Zoo",),
    "Isheri North, Lagos": ("Berger",),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def records() -> list[dict]:
    vg12 = "vanguard-2011-07-12"
    vg15 = "vanguard-2011-07-15"
    aj = "aljazeera-2011-07-13"
    sd = "solardaily-2011-07-11"
    rw = "reliefweb-2011"
    ifrc = "ifrc-dref-2011-07-25"
    ng = "newsghana-2011"

    vg12_url = "https://www.vanguardngr.com/2011/07/lagos-flood-kills-25/"
    vg15_url = (
        "https://www.vanguardngr.com/2011/07/"
        "lagos-floods-residents-senate-blame-fashola-jonathan/"
    )
    vg12_pub = "2011-07-12T00:34:35+00:00"
    vg15_pub = "2011-07-15T18:04:27+00:00"
    sun = "2011-07-10T12:00:00+01:00"
    mon = "2011-07-11T12:00:00+01:00"

    def r(**kwargs):
        kwargs.setdefault("verified", False)
        kwargs.setdefault("depth_note", None)
        kwargs.setdefault("quote", None)
        kwargs.setdefault("observed_at", None)
        kwargs.setdefault("time_confidence", "unknown")
        kwargs.setdefault("original_url", None)
        kwargs["quote"] = clip_quote(kwargs.get("quote"))
        return kwargs

    return [
        # --- Vanguard 12 Jul 2011 (read) ---
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Dopemu", location_confidence="neighbourhood",
            query="Dopemu, Agege, Lagos",
            claim="Corpses recovered from canal after Sunday rain; 25 citywide including 11 children.",
            quote="The corpses were recovered from two canals at Dopemu and Aboru",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at="2011-07-11T06:00:00+01:00", time_confidence="approx",
            location_name="Aboru community, Agbado-Okeodo LCDA",
            location_confidence="neighbourhood", query="Aboru, Lagos",
            claim="Three bodies removed Monday morning; suspected drowned in Sunday rain.",
            quote="three dead bodies suspected to have drowned as a result of the previous day's rainfall were removed at Aboru community",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Agbado-Oke Odo LCDA",
            location_confidence="lga", query="Agbado-Oke Odo, Lagos",
            claim="Named with old Alimosho as area of canal body recoveries.",
            quote="two canals at Dopemu and Aboru, in old Alimosho Local Government Area and Agbado-Oke Odo",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=mon, time_confidence="day",
            location_name="Mobil Filling Station, Ogba",
            location_confidence="point",
            query="Mobil Filling Station, Ogba, Lagos",
            claim="Company fence collapsed due to flood; Fashola inspected.",
            quote="Mobil Filling Station, Ogba, where the fence of a company collapsed due to flood",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=mon, time_confidence="day",
            location_name="Odejobi Street off Iju Road, Agege",
            location_confidence="street",
            query="Odejobi Street, Iju, Agege, Lagos",
            claim="Among worst-hit streets Fashola inspected on Monday.",
            quote="Some of the worst-hit areas which Fashola inspected included: Mobil Filling Station, Ogba",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=mon, time_confidence="day",
            location_name="Abattoir canal, Orile-Agege",
            location_confidence="neighbourhood",
            query="Abattoir canal, Orile-Agege, Lagos",
            claim="Among worst-hit sites on the governor's inspection.",
            quote="Abattoir canal in Orile-Agege Local Government Area",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Obadeyi Busstop, Abeokuta–Lagos Expressway",
            location_confidence="point",
            query="Obadeyi, Abeokuta Expressway, Lagos",
            claim="Failed portion of the expressway; Fashola said the road was virtually lost.",
            quote="Abeokuta – Lagos Expressway failed portion of the road at Obadeyi Busstop",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Aboru canal, Iyana-Ipaja end of Abeokuta-Lagos Expressway",
            location_confidence="neighbourhood",
            query="Iyana-Ipaja, Lagos",
            claim="Aboru canal at the Iyana-Ipaja end listed among worst-hit sites.",
            quote="Aboru canal, at Iyana-Ipaja end of Abeokuta-Lagos Expressway among others",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Ikoyi", location_confidence="neighbourhood",
            query="Ikoyi, Lagos",
            claim="High-brow area affected; vehicles, office and household property destroyed.",
            quote="The flood also affected high brow areas including Ikoyi, Victoria Island and Apapa",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Victoria Island", location_confidence="neighbourhood",
            query="Victoria Island, Lagos",
            claim="High-brow area affected; vehicles and household property destroyed.",
            quote="The flood also affected high brow areas including Ikoyi, Victoria Island and Apapa",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Apapa", location_confidence="neighbourhood",
            query="Apapa, Lagos",
            claim="High-brow area affected; vehicles and household property destroyed.",
            quote="The flood also affected high brow areas including Ikoyi, Victoria Island and Apapa",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Silver-Bird Communications, Lekki",
            location_confidence="point", query="Silverbird, Lekki, Lagos",
            claim="Premises submerged; television transmission disrupted temporarily.",
            quote="The premises of Silver-Bird Communications, Lekki in Lagos Island and Channels Television",
            depth_note="premises submerged",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Channels Television, Isheri North",
            location_confidence="point", query="Isheri North, Lagos",
            claim="Premises submerged along Lagos-Ibadan Expressway; transmission disrupted.",
            quote="Channels Television, Isheri North, along Lagos Ibadan Expressway were submerged by the flood",
            depth_note="premises submerged",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=mon, time_confidence="day",
            location_name="16, Adesokan Street, Dopemu, Agege",
            location_confidence="street",
            query="Adesokan Street, Dopemu, Lagos",
            claim="Fire service recovered 22-year-old Muri Olanrewaju from a flooded sewage tank.",
            quote="removed the corpse of a 22-year old Muri Olanrewaju who died inside a sewage tank",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at="2011-07-10T21:00:00+01:00", time_confidence="approx",
            location_name="Akara, Alagbado", location_confidence="neighbourhood",
            query="Alagbado, Lagos",
            claim="Unconfirmed report: young man about 25 killed when a wall fell Sunday night.",
            quote="unconfirmed report in Akara area of Alagbado, had it that a yet to be identified young man",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Ajegunle", location_confidence="neighbourhood",
            query="Ajegunle, Ajeromi-Ifelodun, Lagos",
            claim="Over 28 families homeless; four buildings caved in; no life lost there.",
            quote="over twenty-eight families have been rendered homeless, as four buildings",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at="2011-07-10T18:30:00+01:00", time_confidence="exact",
            location_name="Number 8 Okatapo street, Ajegunle",
            location_confidence="street",
            query="Okatapo Street, Ajegunle, Lagos",
            claim="Building caved in about 6.30pm Sunday.",
            quote="Number 8 Okatapo street, according to report, caved in at about 6.30pm, Sunday",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at="2011-07-11T07:30:00+01:00", time_confidence="approx",
            location_name="Number 4A Okatapo street, Ajegunle",
            location_confidence="street",
            query="Okatapo Street, Ajegunle, Lagos",
            claim="Part of 4A collapsed about 7.30am Monday.",
            quote="part of number 4A collapsed yesterday at about 7.30am",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at="2011-07-11T16:00:00+01:00", time_confidence="approx",
            location_name="Number 7 Okatapo street and Young lane, Ajegunle",
            location_confidence="street",
            query="Young Lane, Ajegunle, Lagos",
            claim="Numbers 7 and Young lane caved in about 4pm Monday.",
            quote="At about 4pm, numbers 7 and that on Young lane also caved in",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at="2011-07-10T23:00:00+01:00", time_confidence="approx",
            location_name="Jakande estate, Oke-Afa Isolo",
            location_confidence="neighbourhood",
            query="Jakande Estate, Isolo, Lagos",
            claim="Woman and 11-month-old baby carried by flood Sunday night; residents rescued them.",
            quote="a woman and her eleven-month -old baby escaped death by the whiskers Sunday night",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=mon, time_confidence="day",
            location_name="Olodi Apapa", location_confidence="neighbourhood",
            query="Olodi Apapa, Lagos",
            claim="Residents sacked from homes; still bailing water from apartments.",
            quote="a visit to Olodi Apapa and Ajegunle areas of Lagos, revealed the sufferings",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=mon, time_confidence="day",
            location_name="Mustapha, Lawani, Rashidi, Apana, Babatunde, Isikalu lane, Ajegunle",
            location_confidence="street",
            query="Mustapha Street, Ajegunle, Lagos",
            claim="Named streets most affected; residents bailing water from apartments.",
            quote="Mustapha, Lawani, Rashidi, Apana, Babatunde,Isikalu lane among other streets were most affected",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Orile", location_confidence="neighbourhood",
            query="Orile-Agege, Lagos",
            claim="Most shanties around Orile completely brought down by the rain.",
            quote="Most shanties around Orile and Oyingbo were completely brought down by the rain",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="news_report", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=sun, time_confidence="day",
            location_name="Oyingbo", location_confidence="neighbourhood",
            query="Oyingbo, Lagos",
            claim="Most shanties around Oyingbo completely brought down by the rain.",
            quote="Most shanties around Orile and Oyingbo were completely brought down by the rain",
            read_status="read",
        ),
        r(
            source_id=vg12, kind="official_statement", publisher="Vanguard",
            source_url=vg12_url, published_at=vg12_pub,
            observed_at=mon, time_confidence="day",
            location_name="Agege", location_confidence="neighbourhood",
            query="Agege, Lagos",
            claim="Fashola inspected flood-prone Agege; warned occupants of canal buildings to leave.",
            quote="we are coming to take possession, we are not going to risk human lives anymore",
            read_status="read",
        ),
        # --- Vanguard 15 Jul 2011 (read) ---
        r(
            source_id=vg15, kind="news_photo", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Apapa/Oshodi Expressway",
            location_confidence="street",
            query="Apapa-Oshodi Expressway, Lagos",
            claim="Expressway flooded after heavy downpour; traffic build-ups for motorists.",
            quote="Apapa/Oshodi Expressway flooded due to heavy down pour thereby causing traffic buildups",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Victoria Island", location_confidence="neighbourhood",
            query="Victoria Island, Lagos",
            claim="High-brow Victoria Island and Lekki also flooded that Sunday.",
            quote="the government did not even come to the aid of the high brow Victoria Island and Lekki",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Lekki", location_confidence="lga",
            query="Lekki, Lagos",
            claim="Lekki flooded that Sunday with Victoria Island.",
            quote="the high brow Victoria Island and Lekki, described by CNN as the most expensive slum",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Agbado Oke-Odo LCDA", location_confidence="lga",
            query="Agbado-Oke Odo, Lagos",
            claim="Vice chairman: at least 10 drowned in a canal, including a woman and infant.",
            quote="at least 10 persons drowned in a canal because they could not distinguish between the roads",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Agege", location_confidence="neighbourhood",
            query="Agege, Lagos",
            claim="Thousands sacked from homes by overflow of water.",
            quote="Thousands of others were sacked from their homes by the overflow of water in Agege, Agbado",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Ijaiye", location_confidence="neighbourhood",
            query="Ijaiye, Lagos",
            claim="Named among areas where thousands were sacked from homes.",
            quote="overflow of water in Agege, Agbado, Ijaiye, Aboru, Ojota, Ketu, and Apapa",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Aboru", location_confidence="neighbourhood",
            query="Aboru, Lagos",
            claim="Named among areas where thousands were sacked from homes.",
            quote="overflow of water in Agege, Agbado, Ijaiye, Aboru, Ojota, Ketu, and Apapa",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Ojota", location_confidence="neighbourhood",
            query="Ojota, Lagos",
            claim="Named among areas where thousands were sacked from homes.",
            quote="overflow of water in Agege, Agbado, Ijaiye, Aboru, Ojota, Ketu, and Apapa",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Ketu", location_confidence="neighbourhood",
            query="Ketu, Lagos",
            claim="Named among areas where thousands were sacked from homes.",
            quote="overflow of water in Agege, Agbado, Ijaiye, Aboru, Ojota, Ketu, and Apapa",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Apapa", location_confidence="neighbourhood",
            query="Apapa, Lagos",
            claim="Named among areas where thousands were sacked from homes.",
            quote="overflow of water in Agege, Agbado, Ijaiye, Aboru, Ojota, Ketu, and Apapa",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Utility Street, Ifako Ijaiye",
            location_confidence="street",
            query="Utility Street, Ifako-Ijaiye, Lagos",
            claim="A building collapsed and buried a teenager in the rubble.",
            quote="A building on Utility Street in Ifako Ijaiye Council collapsed and buried a teenager",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Akera, Alagbado",
            location_confidence="neighbourhood",
            query="Akera, Alagbado, Lagos",
            claim="A man died instantly when a fence fell on him.",
            quote="In Akera, Alagbado, a man died instantly when a fence fell on him",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at="2011-07-11T08:00:00+01:00", time_confidence="approx",
            location_name="16, Adesokan Street, Dopemu",
            location_confidence="street",
            query="Adesokan Street, Dopemu, Lagos",
            claim="Corpse of 22-year-old Muri Olanrewaju retrieved Monday morning from a sewage cistern.",
            quote="The corpse of a 22-year-old boy, Muri Olanrewaju, was retrieved on Monday morning",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at="2011-07-10T21:00:00+01:00", time_confidence="approx",
            location_name="Allen Avenue, Ikeja",
            location_confidence="street",
            query="Allen Avenue, Ikeja, Lagos",
            claim="Five girls, including a three-month-old, died of generator fumes after rain trapped them.",
            quote="Five girls, one of them a three-month-old baby, were found dead in a restaurant on Allen Avenue",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at="2011-07-10T23:00:00+01:00", time_confidence="approx",
            location_name="10, Odejobi Street, Iju",
            location_confidence="street",
            query="Odejobi Street, Iju, Agege, Lagos",
            claim="Rooms taken over by flood; household slept at church at Cement Bus stop.",
            quote="The rooms were taken over by flood; we were scared because the rain did not stop until about 11 p.m.",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at="2011-07-10T19:00:00+01:00", time_confidence="approx",
            location_name="Alapere, Ketu",
            location_confidence="neighbourhood",
            query="Alapere, Ketu, Lagos",
            claim="One-room apartment overtaken by flood about 7 p.m. Sunday.",
            quote="meet her one-room apartment in Alapere, Ketu overtaken by flood",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Jakande Estate, Isolo",
            location_confidence="neighbourhood",
            query="Jakande Estate, Isolo, Lagos",
            claim="Resident spent six hours Ojota to Anthony; flood at Ketu described as scary.",
            quote="I drove from my house on Jakande Estate, Isolo to Mile 12 around 3 p.m.",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Ajao Street, Surulere",
            location_confidence="street",
            query="Ajao Street, Surulere, Lagos",
            claim="Street flooded; vehicular movement obstructed.",
            quote="In Surulere, streets such as Ajao, Randle and Ojuelegba were flooded",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Randle, Surulere",
            location_confidence="street",
            query="Randle Avenue, Surulere, Lagos",
            claim="Street flooded; vehicular movement obstructed.",
            quote="In Surulere, streets such as Ajao, Randle and Ojuelegba were flooded",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Ojuelegba, Surulere",
            location_confidence="neighbourhood",
            query="Ojuelegba, Surulere, Lagos",
            claim="Street flooded; vehicular movement obstructed.",
            quote="In Surulere, streets such as Ajao, Randle and Ojuelegba were flooded",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Akinola, Agbado-Oke Odo LCDA",
            location_confidence="neighbourhood",
            query="Akinola, Agbado-Oke Odo, Lagos",
            claim="Residents along the canal bailed flood water from houses.",
            quote="In Akinola and Alabede under the Agbado-Oke Odo Local Council Development Area",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Alabede, Agbado-Oke Odo LCDA",
            location_confidence="neighbourhood",
            query="Alabede, Agbado-Oke Odo, Lagos",
            claim="Residents along the canal bailed flood water from houses.",
            quote="In Akinola and Alabede under the Agbado-Oke Odo Local Council Development Area",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Awolowo Way, Ikeja",
            location_confidence="street",
            query="Awolowo Way, Ikeja, Lagos",
            claim="Listed among other affected areas.",
            quote="Other affected areas include Awolowo Way in Ikeja, some parts of Oshodi, Ejigbo",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Oshodi", location_confidence="neighbourhood",
            query="Oshodi, Lagos",
            claim="Some parts of Oshodi listed among affected areas.",
            quote="Other affected areas include Awolowo Way in Ikeja, some parts of Oshodi, Ejigbo",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Ejigbo", location_confidence="neighbourhood",
            query="Ejigbo, Lagos",
            claim="Listed among other affected areas.",
            quote="Other affected areas include Awolowo Way in Ikeja, some parts of Oshodi, Ejigbo",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Owode Onirin", location_confidence="neighbourhood",
            query="Owode Onirin, Lagos",
            claim="Listed among other affected areas.",
            quote="Owode Onirin and Ajegunle in Ikorodu",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Ajegunle in Ikorodu",
            location_confidence="neighbourhood",
            query="Ajegunle, Ikorodu, Lagos",
            claim="Ikorodu Ajegunle listed among other affected areas (not Ajeromi Ajegunle).",
            quote="Owode Onirin and Ajegunle in Ikorodu",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="news_report", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="approx",
            location_name="Casso area of Alagbado",
            location_confidence="neighbourhood",
            query="Casso, Alagbado, Lagos",
            claim="Water on the street above kneecap level in the evening.",
            quote="the water level on his street as in the evening was above kneel cap level",
            depth_note="above kneecap level",
            read_status="read",
        ),
        r(
            source_id=vg15, kind="official_statement", publisher="Vanguard",
            source_url=vg15_url, published_at=vg15_pub,
            observed_at=sun, time_confidence="day",
            location_name="Lagos channels / lagoon",
            location_confidence="lga",
            query="Lagos, Nigeria",
            claim="Tunji Bello: channels locked by high tide in the Atlantic and Lagoon.",
            quote="the channels that are meant to discharge water from the roads and drainages are completely locked",
            read_status="read",
        ),
        # --- Al Jazeera 13 Jul 2011 (read) ---
        r(
            source_id=aj, kind="news_report", publisher="Al Jazeera",
            source_url="https://www.aljazeera.com/news/2011/7/13/flash-flooding-hits-lagos",
            published_at="2011-07-13T14:09:35+00:00",
            observed_at=sun, time_confidence="day",
            location_name="Lagos", location_confidence="lga",
            query="Lagos, Nigeria",
            claim="At least 20 died in Lagos; water knee high in many places.",
            quote="Worst hit is Lagos where at least 20 people have died so far",
            depth_note="knee high in many places",
            read_status="read",
        ),
        # --- Solar Daily / AFP 12 Jul 2011 (read; event.json URL redirected) ---
        r(
            source_id=sd, kind="official_statement", publisher="AFP / Solar Daily",
            source_url=(
                "https://www.solardaily.com/reports/"
                "Floods_kill_at_least_20_in_Nigerias_largest_city_999.html"
            ),
            original_url=(
                "https://www.solardaily.com/reports/"
                "Floods_kill_at_least_20_in_Nigerias_largest_city_999.html"
            ),
            published_at="2011-07-12T00:00:00+00:00",
            observed_at=sun, time_confidence="day",
            location_name="Lagos", location_confidence="lga",
            query="Lagos, Nigeria",
            claim="NEMA: not less than 20 killed including children on Sunday; Adebiyi had a partial 18.",
            quote="Not less than 20 people including children were killed in the Lagos flooding on Sunday",
            read_status="read",
        ),
        # --- ReliefWeb disaster page (read). Ibadan death figures omitted. ---
        r(
            source_id=rw, kind="news_report", publisher="ReliefWeb / IFRC",
            source_url="https://reliefweb.int/disaster/ff-2011-000088-nga",
            published_at=None,
            observed_at="2011-07-10T05:00:00+01:00", time_confidence="day",
            location_name="Lagos State", location_confidence="lga",
            query="Lagos, Nigeria",
            claim="IFRC: 17-hour downpour 10–14 July 2011 caused severe flooding in Lagos State.",
            quote="A 17-hour continuous and heavy downpour of rains that occurred in Lagos State",
            read_status="read",
        ),
        # --- IFRC DREF 25 Jul 2011 (read). Akute/Alagbole/Denro omitted (Ogun). ---
        r(
            source_id=ifrc, kind="news_report", publisher="IFRC",
            source_url="https://reliefweb.int/report/nigeria/nigeria-flash-floods-dref-operation-n%C2%B0-mdrng010",
            original_url="https://reliefweb.int/attachments/5f8cfd60-44c4-3174-a3ef-c42d1d84bd67/MDRNG010.pdf",
            published_at="2011-07-25T00:00:00+00:00",
            observed_at="2011-07-10T05:00:00+01:00", time_confidence="approx",
            location_name="Lagos metropolis", location_confidence="lga",
            query="Lagos, Nigeria",
            claim="Rain from about 5 a.m. 10 July lasting 17 hours; media said 20 dead by 11 July.",
            quote="A heavy downpour that started about 5 a.m. in the early hours of 10 July, 2011 and lasting 17 hours",
            read_status="read",
        ),
        r(
            source_id=ifrc, kind="news_report", publisher="IFRC",
            source_url="https://reliefweb.int/report/nigeria/nigeria-flash-floods-dref-operation-n%C2%B0-mdrng010",
            original_url="https://reliefweb.int/attachments/5f8cfd60-44c4-3174-a3ef-c42d1d84bd67/MDRNG010.pdf",
            published_at="2011-07-25T00:00:00+00:00",
            observed_at=sun, time_confidence="day",
            location_name="Oniwaya, Agege", location_confidence="neighbourhood",
            query="Oniwaya, Agege, Lagos",
            claim="NRCS: building collapse in Oniwaya area of Agege.",
            quote="collapse of building in areas like Oniwaya area of Agege, Gbagada/Oworonshoki, Aboru",
            read_status="read",
        ),
        r(
            source_id=ifrc, kind="news_report", publisher="IFRC",
            source_url="https://reliefweb.int/report/nigeria/nigeria-flash-floods-dref-operation-n%C2%B0-mdrng010",
            original_url="https://reliefweb.int/attachments/5f8cfd60-44c4-3174-a3ef-c42d1d84bd67/MDRNG010.pdf",
            published_at="2011-07-25T00:00:00+00:00",
            observed_at=sun, time_confidence="day",
            location_name="Gbagada/Oworonshoki", location_confidence="neighbourhood",
            query="Gbagada, Lagos",
            claim="NRCS: building collapse in Gbagada/Oworonshoki.",
            quote="collapse of building in areas like Oniwaya area of Agege, Gbagada/Oworonshoki, Aboru",
            read_status="read",
        ),
        r(
            source_id=ifrc, kind="news_report", publisher="IFRC",
            source_url="https://reliefweb.int/report/nigeria/nigeria-flash-floods-dref-operation-n%C2%B0-mdrng010",
            original_url="https://reliefweb.int/attachments/5f8cfd60-44c4-3174-a3ef-c42d1d84bd67/MDRNG010.pdf",
            published_at="2011-07-25T00:00:00+00:00",
            observed_at=sun, time_confidence="day",
            location_name="Oworonshoki", location_confidence="neighbourhood",
            query="Oworonshoki, Lagos",
            claim="Paired with Gbagada among areas of building collapse.",
            quote="collapse of building in areas like Oniwaya area of Agege, Gbagada/Oworonshoki, Aboru",
            read_status="read",
        ),
        r(
            source_id=ifrc, kind="news_report", publisher="IFRC",
            source_url="https://reliefweb.int/report/nigeria/nigeria-flash-floods-dref-operation-n%C2%B0-mdrng010",
            original_url="https://reliefweb.int/attachments/5f8cfd60-44c4-3174-a3ef-c42d1d84bd67/MDRNG010.pdf",
            published_at="2011-07-25T00:00:00+00:00",
            observed_at=sun, time_confidence="day",
            location_name="Aboru", location_confidence="neighbourhood",
            query="Aboru, Lagos",
            claim="NRCS: building collapse among other areas including Aboru.",
            quote="collapse of building in areas like Oniwaya area of Agege, Gbagada/Oworonshoki, Aboru",
            read_status="read",
        ),
        # --- News Ghana 24 Jun 2012 recalling 10 Jul 2011 (read) ---
        r(
            source_id=ng, kind="news_report", publisher="News Ghana / Daily Times",
            source_url="https://www.newsghana.com.gh/lagos-to-experience-week-long-rainfall/",
            published_at="2012-06-24T11:31:26+00:00",
            observed_at=sun, time_confidence="day",
            location_name="Ogba", location_confidence="neighbourhood",
            query="Ogba, Ikeja, Lagos",
            claim="Recall of 10 July 2011: houses in Ogba heavily flooded after rain over 15 hours.",
            quote="houses in places such as Ogba, Agege, Lekki, and others, were heavily flooded",
            read_status="read",
        ),
        r(
            source_id=ng, kind="news_report", publisher="News Ghana / Daily Times",
            source_url="https://www.newsghana.com.gh/lagos-to-experience-week-long-rainfall/",
            published_at="2012-06-24T11:31:26+00:00",
            observed_at=sun, time_confidence="day",
            location_name="Agege", location_confidence="neighbourhood",
            query="Agege, Lagos",
            claim="Recall of 10 July 2011: houses in Agege heavily flooded.",
            quote="houses in places such as Ogba, Agege, Lekki, and others, were heavily flooded",
            read_status="read",
        ),
        r(
            source_id=ng, kind="news_report", publisher="News Ghana / Daily Times",
            source_url="https://www.newsghana.com.gh/lagos-to-experience-week-long-rainfall/",
            published_at="2012-06-24T11:31:26+00:00",
            observed_at=sun, time_confidence="day",
            location_name="Lekki", location_confidence="lga",
            query="Lekki, Lagos",
            claim="Recall of 10 July 2011: houses in Lekki heavily flooded.",
            quote="houses in places such as Ogba, Agege, Lekki, and others, were heavily flooded",
            read_status="read",
        ),
    ]


def _norm(text: str) -> str:
    return (text or "").casefold()


def hit_is_implausible(query: str, hit: dict) -> bool:
    blob = " ".join(
        str(hit.get(k, ""))
        for k in ("display_name", "name")
    )
    addr = hit.get("address") or {}
    if isinstance(addr, dict):
        blob += " " + " ".join(str(v) for v in addr.values())
    blob_n = _norm(blob)
    for token in IMPLAUSIBLE.get(query, ()):
        if _norm(token) in blob_n:
            return True
    return False


def resolve(rec: dict, hits: dict) -> tuple[float, float, str, str] | None:
    query = rec["query"]
    hit = hits.get(query)
    if hit and not hit_is_implausible(query, hit):
        return (
            hit["lon"],
            hit["lat"],
            f"nominatim:{query}",
            rec["location_confidence"],
        )
    if query in MANUAL:
        lon, lat = MANUAL[query]
        if in_bbox(lon, lat, BBOX):
            conf = rec["location_confidence"]
            if conf == "point":
                conf = "neighbourhood"
            return lon, lat, f"manual: neighbourhood centre for {query}", conf
    return None


def build(event_dir: Path) -> str:
    event_path = event_dir / "event.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    recs = records()
    for rec in recs:
        n = len((rec.get("claim") or "").split())
        if n > 20:
            raise SystemExit(f"claim too long ({n} words): {rec['location_name']}")
        rec["quote"] = clip_quote(rec.get("quote"))
        q = rec.get("quote") or ""
        if q and len(q.split()) > 25:
            raise SystemExit(f"quote too long ({len(q.split())} words): {q}")

    queries = list(dict.fromkeys(r["query"] for r in recs))
    hits = geocode_many(queries, BBOX)

    features = []
    unresolved = []
    for rec in recs:
        placed = resolve(rec, hits)
        if placed is None:
            unresolved.append(
                f"{rec['source_id']}: {rec['location_name']} ({rec['query']})"
            )
            continue
        lon, lat, method, conf = placed
        props = {
            "id": f"ev-{len(features)+1:03d}",
            "kind": rec["kind"],
            "source_id": rec["source_id"],
            "source_url": rec["source_url"],
            "publisher": rec["publisher"],
            "published_at": rec["published_at"],
            "observed_at": rec["observed_at"],
            "time_confidence": rec["time_confidence"],
            "location_name": rec["location_name"],
            "location_confidence": conf,
            "geocode_method": method,
            "claim": rec["claim"],
            "depth_note": rec["depth_note"],
            "quote": rec["quote"],
            "verified": False,
            "read_status": rec["read_status"],
        }
        if rec.get("original_url"):
            props["original_url"] = rec["original_url"]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(lon, 6), round(lat, 6)],
            },
            "properties": props,
        })

    extra_sources = {
        "vanguard-2011-07-12": (
            "https://www.vanguardngr.com/2011/07/lagos-flood-kills-25/"
        ),
        "vanguard-2011-07-15": (
            "https://www.vanguardngr.com/2011/07/"
            "lagos-floods-residents-senate-blame-fashola-jonathan/"
        ),
        "ifrc-dref-2011-07-25": (
            "https://reliefweb.int/report/nigeria/"
            "nigeria-flash-floods-dref-operation-n%C2%B0-mdrng010"
        ),
        "pmnews-2011-07-14": (
            "https://pmnewsnigeria.com/2011/07/14/"
            "one-month-rain-fell-in-lagos-on-sunday/"
        ),
    }
    event.setdefault("sources", {}).update(extra_sources)
    event_path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")

    payload = {
        "type": "FeatureCollection",
        "meta": {
            "compiled_at": utc_now(),
            "method": (
                "Read named 2011 sources; one point per (source, location); "
                "Nominatim geocode inside AOI bbox, 1 req/s; "
                "manual neighbourhood centre only if Nominatim missed or "
                "matched the wrong district. Wayback not required for live pages."
            ),
            "notes": (
                "Quotes are verbatim excerpts ≤ 25 words. "
                "Ibadan death figures on ReliefWeb omitted (not Lagos). "
                "Katsina deaths on Solar Daily/AFP omitted. "
                "IFRC Denro/Akute/Alagbole omitted (Ogun outskirts). "
                "Allen Avenue deaths are generator fumes after rain, not drowning. "
                "Ajegunle, Ajeromi (28 families) kept separate from Ajegunle, Ikorodu. "
                "Vanguard 12 Jul marks the Alagbado wall death unconfirmed; "
                "15 Jul reports a fence death in Akera, Alagbado. "
                "News Ghana is a 2012 recall of 10 July 2011. "
                "No locations, times, numbers or quotes were inferred beyond the text."
            ),
            "unresolved": unresolved,
            "bbox": BBOX,
            "feature_count": len(features),
            "omitted": [
                "Ibadan / Oyo deaths (ReliefWeb Gov't of Nigeria 30 Aug 2011)",
                "Katsina nine deaths (AFP via Solar Daily)",
                "Denro, Akute, Alagbole bridge (IFRC; outskirts of Lagos State)",
                "ThisDay 15 Jul 2011 (cited in papers; page not readable)",
                "Punch 2011 archive (no matching article found)",
            ],
        },
        "features": features,
    }
    out = event_dir / "evidence.geojson"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    by_conf: dict[str, int] = {}
    by_read: dict[str, set[str]] = {"read": set(), "headline_only": set()}
    by_method = {"nominatim": 0, "manual": 0}
    for feat in features:
        p = feat["properties"]
        by_conf[p["location_confidence"]] = by_conf.get(
            p["location_confidence"], 0
        ) + 1
        by_read[p["read_status"]].add(p["source_id"])
        if p["geocode_method"].startswith("nominatim"):
            by_method["nominatim"] += 1
        else:
            by_method["manual"] += 1
    archive_n = sum(1 for f in features if "original_url" in f["properties"])
    lines = [
        "FloodTrace media evidence",
        f"event: {event.get('id', event_dir.name)}",
        f"features: {len(features)}",
        f"sources read: {len(by_read['read'])} ({sorted(by_read['read'])})",
        f"sources headline_only: {len(by_read['headline_only'])} "
        f"({sorted(by_read['headline_only']) or 'none'})",
        f"sources with original_url/archive field: {archive_n} features",
        "location_confidence: "
        + ", ".join(f"{k}={v}" for k, v in sorted(by_conf.items())),
        f"geocode: nominatim={by_method['nominatim']}, "
        f"manual={by_method['manual']}",
        f"unresolved: {unresolved or 'none'}",
        "omitted: Ibadan deaths; Katsina; Akute/Alagbole/Denro; unread ThisDay/Punch.",
        f"wrote {out}",
    ]
    summary = "\n".join(lines)
    print(summary)
    return summary


def main() -> None:
    event_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else EVENT_DIR
    build(event_dir)


if __name__ == "__main__":
    main()
