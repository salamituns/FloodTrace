#!/usr/bin/env python3
"""Compile events/<id>/evidence.geojson from named source locations.

Accuracy over coverage: every location, time and quote is taken from a
source that was read (or from its headline/snippet if blocked).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geocode import geocode_many, in_bbox

ROOT = Path(__file__).resolve().parents[1]
BBOX = [2.70, 6.38, 4.35, 6.75]

# Neighbourhood centres used only when Nominatim misses or is implausible.
# Confidence must be lowered when these are used.
MANUAL = {
    "Alapomeji, Lagos": (3.399, 6.548),
    "Olopomeji, Lagos": (3.399, 6.548),
    "Iyana Oworo, Lagos": (3.403, 6.548),
    "Labora, Ibeju-Lekki, Lagos": (3.92, 6.48),
    "Abijo, Lagos": (3.72, 6.47),
    "Majek, Lagos": (3.68, 6.46),
    "Greenland Estate, Mende, Lagos": (3.386, 6.569),
    "Cameroun Street, Mushin, Lagos": (3.343, 6.533),
    "Sholuyi, Gbagada, Lagos": (3.389, 6.557),
    "Kusenla, Lekki, Lagos": (3.500, 6.437),
    "Alpha Beach Road, Lekki, Lagos": (3.515, 6.430),
    "Jakande Estate, Isolo, Lagos": (3.320, 6.535),
    "Awolowo Road, Ikeja, Lagos": (3.351, 6.596),
    "Eredo, Ibeju-Lekki, Lagos": (3.98, 6.55),
    "Bogije, Lagos": (3.76, 6.48),
    "Lekki, Lagos": (3.52, 6.44),
    "Oworonshoki, Lagos": (3.405, 6.555),
    "Lekki Phase 2, Lagos": (3.56, 6.455),
    "Gbagada Expressway, Lagos": (3.384, 6.548),
}

# Nominatim sometimes matches a same-named street in another district.
IMPLAUSIBLE = {
    "Bogije, Lagos": ("Amuwo", "Festac", "Mile 2"),
    "Abijo, Lagos": ("Dolphin", "Ikoyi"),
    "Majek, Lagos": ("Fagba", "Ojokoro", "Phillip Majek"),
    "Lekki, Lagos": ("Ibeju Lekki",),
    "Oworonshoki, Lagos": ("Cele", "Isolo"),
    "Lekki Phase 2, Lagos": ("Phase I", "Maroko", "Hendrison"),
    "Gbagada Expressway, Lagos": ("Burger King",),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def records() -> list[dict]:
    """One dict per (source, location). Quotes are verbatim and ≤ 25 words."""
    v = "vanguard-2024-06-27"
    td = "thisday-2024-07-03"
    dt = "dailytrust-2024-07-03"
    ca = "thecable-2024-07-03"
    bbc = "bbcpidgin-2024-07-03"
    dp = "dailypost-2024-07-03"
    pu = "punch-2024-07-07"
    ch = "channelstv-2024-07-03"

    def r(**kwargs):
        kwargs.setdefault("verified", False)
        kwargs.setdefault("depth_note", None)
        kwargs.setdefault("quote", None)
        kwargs.setdefault("observed_at", None)
        kwargs.setdefault("time_confidence", "unknown")
        return kwargs

    return [
        # --- Vanguard 27 Jun 2024 (read) ---
        r(
            source_id=v, kind="news_report", publisher="Vanguard",
            source_url="https://www.vanguardngr.com/2024/06/48hrs-rainfall-agungi-lekki-environs-in-lagos-submerge-in-flood/",
            published_at="2024-06-27T18:56:56+01:00",
            observed_at="2024-06-27T12:00:00+01:00", time_confidence="day",
            location_name="Agungi", location_confidence="neighbourhood",
            query="Agungi, Lekki, Lagos",
            claim="Flooding after 48 hours of rain; collector too small for storm water.",
            quote="the collector they have there is too small to serve the volume of storm water",
            read_status="read",
        ),
        r(
            source_id=v, kind="official_statement", publisher="Vanguard",
            source_url="https://www.vanguardngr.com/2024/06/48hrs-rainfall-agungi-lekki-environs-in-lagos-submerge-in-flood/",
            published_at="2024-06-27T18:56:56+01:00",
            observed_at="2024-06-27T12:00:00+01:00", time_confidence="day",
            location_name="Freedom Park Road/Kusenla Junction",
            location_confidence="point", query="Kusenla, Lekki, Lagos",
            claim="EFAG deployed during rain to clear collector debris.",
            quote="Emergency Flood Abatement Gang were deployed while the rain was ongoing",
            read_status="read",
        ),
        r(
            source_id=v, kind="official_statement", publisher="Vanguard",
            source_url="https://www.vanguardngr.com/2024/06/48hrs-rainfall-agungi-lekki-environs-in-lagos-submerge-in-flood/",
            published_at="2024-06-27T18:56:56+01:00",
            observed_at="2024-06-27T12:00:00+01:00", time_confidence="day",
            location_name="Alpha Beach Road", location_confidence="street",
            query="Alpha Beach Road, Lekki, Lagos",
            claim="System 156 flooding; dredging of channel to start.",
            quote="the flooding issue on System 156 (Up- stream) Alpha Beach Road has been a recurring problem",
            read_status="read",
        ),
        # --- ThisDay 3 Jul 2024 (read) ---
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Third Mainland Bridge entrances",
            location_confidence="street", query="Third Mainland Bridge, Lagos",
            claim="Commuters stranded; major entrances to the bridge severely flooded.",
            quote="severe flooding of major roads, including major entrances leading to the Third Mainland Bridge",
            depth_note="submerged cars",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Iyana-Oworo-Alapomeji", location_confidence="neighbourhood",
            query="Iyana Oworo, Lagos",
            claim="Severe flooding left commuters stranded.",
            quote="including Iyana-Oworo-Alapomeji, Ketu-Alapere, Oshodi-Mafoluku, Aboru",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Ketu-Alapere", location_confidence="neighbourhood",
            query="Alapere, Ketu, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Oshodi-Mafoluku", location_confidence="neighbourhood",
            query="Mafoluku, Oshodi, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Aboru", location_confidence="neighbourhood",
            query="Aboru, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Iyana ipaja", location_confidence="neighbourhood",
            query="Iyana Ipaja, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Iyana Iba", location_confidence="neighbourhood",
            query="Iyana Iba, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Isheri/Idimu-LASU", location_confidence="neighbourhood",
            query="Idimu, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Ijegun-Abaranje", location_confidence="neighbourhood",
            query="Ijegun, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Ikate", location_confidence="neighbourhood",
            query="Ikate, Lekki, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Egbeda-Akowonjo", location_confidence="neighbourhood",
            query="Egbeda, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Jakande Estate", location_confidence="neighbourhood",
            query="Jakande Estate, Isolo, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Ogba", location_confidence="neighbourhood",
            query="Ogba, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Okota", location_confidence="neighbourhood",
            query="Okota, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="news_report", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Lekki -Ajah axis", location_confidence="neighbourhood",
            query="Ajah, Lagos",
            claim="Listed among neighbourhoods with severe flooding.",
            read_status="read",
        ),
        r(
            source_id=td, kind="official_statement", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T09:00:00+01:00", time_confidence="day",
            location_name="Olopo Meji inward 3rd Mainland",
            location_confidence="point", query="Olopomeji, Lagos",
            claim="Wahab: flash flood from intense rain, duration and high lagoon tide.",
            quote="flash flood that is due to the high intensity of the rain, long duration rain coupled with high tidal lagoon level",
            read_status="read",
        ),
        r(
            source_id=td, kind="official_statement", publisher="ThisDay",
            source_url="https://www.thisdaylive.com/index.php/2024/07/03/torrential-rain-causes-widespread-flooding-in-lagos/",
            published_at="2024-07-03T00:00:00+01:00",
            observed_at="2024-07-03T09:00:00+01:00", time_confidence="day",
            location_name="Alapomeji section of Iyana Oworo",
            location_confidence="point", query="Alapomeji, Lagos",
            claim="EFAG deployed; Wahab said the road was then free of rainwater.",
            quote="The EFAG team from the Lagos State Ministry of the Environment and Water Resources @LasgMOE were deployed",
            read_status="read",
        ),
        # --- Daily Trust 3 Jul 2024 13:05 WAT (read) ---
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Labora", location_confidence="neighbourhood",
            query="Labora, Ibeju-Lekki, Lagos",
            claim="Resident said house submerged; no functional drainage at new site.",
            quote="There is too much water flowing into my compound, the entire house is submerged.",
            depth_note="entire house is submerged",
            read_status="read",
        ),
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Ibeju-Lekki Expressway", location_confidence="street",
            query="Ibeju-Lekki Expressway, Lagos",
            claim="Perennial flooding attributed to blocked drains.",
            read_status="read",
        ),
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Epe", location_confidence="neighbourhood",
            query="Epe, Lagos",
            claim="Named among areas flooded after hours of rain.",
            read_status="read",
        ),
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Eredo", location_confidence="neighbourhood",
            query="Eredo, Ibeju-Lekki, Lagos",
            claim="Named among areas flooded after hours of rain.",
            read_status="read",
        ),
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Bogije", location_confidence="neighbourhood",
            query="Bogije, Lagos",
            claim="Named among areas flooded after hours of rain.",
            read_status="read",
        ),
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Abijon", location_confidence="neighbourhood",
            query="Abijo, Lagos",
            claim="Named among areas flooded after hours of rain.",
            read_status="read",
        ),
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Sangotedo", location_confidence="neighbourhood",
            query="Sangotedo, Lagos",
            claim="Flooded; resident urged completion of road repairs.",
            read_status="read",
        ),
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Awoyaya", location_confidence="neighbourhood",
            query="Awoyaya, Lagos",
            claim="Named among flooded roads during rehabilitation works.",
            read_status="read",
        ),
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Abraham Adesanya", location_confidence="street",
            query="Abraham Adesanya, Lagos",
            claim="Road flooded amid ongoing rehabilitation works.",
            read_status="read",
        ),
        r(
            source_id=dt, kind="news_report", publisher="Daily Trust",
            source_url="https://dailytrust.com/flood-takes-over-houses-roads-in-lagos/",
            published_at="2024-07-03T13:05:19+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Majek", location_confidence="neighbourhood",
            query="Majek, Lagos",
            claim="Named among flooded roads in Ibeju-Lekki.",
            read_status="read",
        ),
        # --- TheCable 3 Jul 2024 (read, photo story) ---
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Iyana-Oworonshoki link to the Third Mainland Bridge",
            location_confidence="street", query="Oworonshoki, Lagos",
            claim="Major road underwater after rain that began around 2am.",
            quote="The rain began around 2am. Some residents woke up to find their homes and estates flooded.",
            depth_note="homes and estates flooded",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Surulere", location_confidence="lga",
            query="Surulere, Lagos",
            claim="Named among parts of Lagos affected by the flood.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Ijesha", location_confidence="neighbourhood",
            query="Ijesha, Lagos",
            claim="Named among parts of Lagos affected by the flood.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Okokomaiko", location_confidence="neighbourhood",
            query="Okokomaiko, Lagos",
            claim="Named among parts of Lagos affected by the flood.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Greenland Estate in Mende", location_confidence="point",
            query="Greenland Estate, Mende, Lagos",
            claim="Named among parts of Lagos affected by the flood.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Gbagada", location_confidence="neighbourhood",
            query="Gbagada, Lagos",
            claim="Named among flooded areas; tweet in article shows flooding there.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Oshodi", location_confidence="neighbourhood",
            query="Oshodi, Lagos",
            claim="Named among parts of Lagos affected by the flood.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Isolo", location_confidence="neighbourhood",
            query="Isolo, Lagos",
            claim="Named among parts of Lagos affected by the flood.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Lekki", location_confidence="neighbourhood",
            query="Lekki, Lagos",
            claim="Named among parts of Lagos affected by the flood.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Ikoyi", location_confidence="neighbourhood",
            query="Ikoyi, Lagos",
            claim="Named among parts of Lagos affected by the flood.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Ikeja", location_confidence="neighbourhood",
            query="Ikeja, Lagos",
            claim="Named among parts of Lagos affected by the flood.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="LASU/Iba-Ojo road", location_confidence="street",
            query="LASU, Ojo, Lagos",
            claim="Named as a major flooded road.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Awolowo Road in Ikeja", location_confidence="street",
            query="Awolowo Road, Ikeja, Lagos",
            claim="Named as a major flooded road.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Apapa-Gbagada expressway", location_confidence="street",
            query="Gbagada Expressway, Lagos",
            claim="Named as a major flooded road.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="news_photo", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T02:00:00+01:00", time_confidence="approx",
            location_name="Alagbado", location_confidence="neighbourhood",
            query="Alagbado, Lagos",
            claim="Motorists and commuters stranded due to flooding.",
            read_status="read",
        ),
        r(
            source_id=ca, kind="social_post", publisher="TheCable",
            source_url="https://www.thecable.ng/photos-commuters-stranded-homes-submerged-as-flood-ravages-lagos/",
            published_at="2024-07-03T13:13:02+01:00",
            observed_at="2024-07-03T08:00:00+01:00", time_confidence="approx",
            location_name="Iyana-Oworo, Olopo meji area heading to 3rd Mainland Bridge",
            location_confidence="point", query="Olopomeji, Lagos",
            claim="Tweet: completely flooded, traffic extending to Alapere.",
            quote="Iyana-Oworo, Olopo meji area heading to 3rd Mainland Bridge this morning is completely flooded",
            read_status="read",
        ),
        # --- BBC Pidgin 3 Jul 2024 (read) ---
        r(
            source_id=bbc, kind="official_statement", publisher="BBC News Pidgin",
            source_url="https://www.bbc.com/pidgin/articles/czvxdzwr97go",
            published_at="2024-07-03T13:01:53+01:00",
            observed_at="2024-07-03T09:37:00+01:00", time_confidence="exact",
            location_name="No 12 Cameroun street Mushin",
            location_confidence="point", query="Cameroun Street, Mushin, Lagos",
            claim="LASEMA: seven people rescued after two-storey building collapse.",
            quote="Di response team say dem ansa one call for help around 9:37am for No 12 Cameroun street Mushin",
            read_status="read",
        ),
        r(
            source_id=bbc, kind="news_report", publisher="BBC News Pidgin",
            source_url="https://www.bbc.com/pidgin/articles/czvxdzwr97go",
            published_at="2024-07-03T13:01:53+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Iyana oworo", location_confidence="neighbourhood",
            query="Iyana Oworo, Lagos",
            claim="Resident Taiwo Ajisafe could not go to work; house floods after downpour.",
            read_status="read",
        ),
        r(
            source_id=bbc, kind="news_report", publisher="BBC News Pidgin",
            source_url="https://www.bbc.com/pidgin/articles/czvxdzwr97go",
            published_at="2024-07-03T13:01:53+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Olopo Meji / 3rd mainland bridge",
            location_confidence="point", query="Olopomeji, Lagos",
            claim="Main entry to Third Mainland Bridge seriously flooded; traffic to Alapere.",
            quote="Iyana-Oworo, Olopo Meji areas wey be di main entry point for 3rd mainland bridge bin dey seriously flooded",
            read_status="read",
        ),
        r(
            source_id=bbc, kind="news_report", publisher="BBC News Pidgin",
            source_url="https://www.bbc.com/pidgin/articles/czvxdzwr97go",
            published_at="2024-07-03T13:01:53+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Ipaja", location_confidence="neighbourhood",
            query="Ipaja, Lagos",
            claim="Resident said house sank under water in two hours; car fuel tank flooded.",
            quote="Two hours na wetin e take Mary-Jane Ukeme house to sink under water",
            depth_note="house sink under water; motor bin sink",
            read_status="read",
        ),
        r(
            source_id=bbc, kind="news_report", publisher="BBC News Pidgin",
            source_url="https://www.bbc.com/pidgin/articles/czvxdzwr97go",
            published_at="2024-07-03T13:01:53+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Lekki", location_confidence="neighbourhood",
            query="Lekki, Lagos",
            claim="Named in headline as hit by early morning continuous rain.",
            quote="Lagos flood: Lekki, Oshodi, Iyano-Oworo hit as early morning continuous rain cause damage",
            read_status="read",
        ),
        r(
            source_id=bbc, kind="news_report", publisher="BBC News Pidgin",
            source_url="https://www.bbc.com/pidgin/articles/czvxdzwr97go",
            published_at="2024-07-03T13:01:53+01:00",
            observed_at="2024-07-03T03:00:00+01:00", time_confidence="approx",
            location_name="Oshodi", location_confidence="neighbourhood",
            query="Oshodi, Lagos",
            claim="Named in headline as hit by early morning continuous rain.",
            read_status="read",
        ),
        # --- Daily Post 3 Jul 2024 (read, video) ---
        r(
            source_id=dp, kind="video", publisher="Daily Post",
            source_url="https://dailypost.ng/2024/07/03/flood-takes-over-residential-areas-in-ibeju-lekki-video/",
            published_at="2024-07-03T12:30:02+01:00",
            observed_at="2024-07-03T08:00:00+01:00", time_confidence="approx",
            location_name="Labora area of Ibeju-Lekki", location_confidence="neighbourhood",
            query="Labora, Ibeju-Lekki, Lagos",
            claim="House submerged; resident said no drainage at new site.",
            quote="There is too much water flowing into my compound, the entire house is submerged.",
            depth_note="entire house is submerged",
            read_status="read",
        ),
        r(
            source_id=dp, kind="video", publisher="Daily Post",
            source_url="https://dailypost.ng/2024/07/03/flood-takes-over-residential-areas-in-ibeju-lekki-video/",
            published_at="2024-07-03T12:30:02+01:00",
            observed_at="2024-07-03T08:00:00+01:00", time_confidence="approx",
            location_name="Sholuyi Gbagada", location_confidence="neighbourhood",
            query="Sholuyi, Gbagada, Lagos",
            claim="Embedded video described as mainland report from Sholuyi Gbagada.",
            read_status="read",
        ),
        r(
            source_id=dp, kind="video", publisher="Daily Post",
            source_url="https://dailypost.ng/2024/07/03/flood-takes-over-residential-areas-in-ibeju-lekki-video/",
            published_at="2024-07-03T12:30:02+01:00",
            observed_at="2024-07-03T08:00:00+01:00", time_confidence="approx",
            location_name="Sangotedo", location_confidence="neighbourhood",
            query="Sangotedo, Lagos",
            claim="Named among flooded Ibeju-Lekki areas; road repairs incomplete.",
            read_status="read",
        ),
        r(
            source_id=dp, kind="video", publisher="Daily Post",
            source_url="https://dailypost.ng/2024/07/03/flood-takes-over-residential-areas-in-ibeju-lekki-video/",
            published_at="2024-07-03T12:30:02+01:00",
            observed_at="2024-07-03T08:00:00+01:00", time_confidence="approx",
            location_name="Awoyaya", location_confidence="neighbourhood",
            query="Awoyaya, Lagos",
            claim="Named among flooded Ibeju-Lekki areas.",
            read_status="read",
        ),
        # --- Punch 7 Jul 2024 about 4 Jul rain (read) ---
        r(
            source_id=pu, kind="news_report", publisher="Punch",
            source_url="https://punchng.com/10-hour-rainfall-lekki-ikoyi-residents-flee-luxury-mansions-as-flood-ravages-homes-streets/",
            published_at="2024-07-07T13:20:29+01:00",
            observed_at="2024-07-04T12:00:00+01:00", time_confidence="day",
            location_name="Lekki Phase II", location_confidence="neighbourhood",
            query="Lekki Phase 2, Lagos",
            claim="Roads impassable; cars half-submerged; residents fled homes.",
            quote="Roads were impassable when our correspondent visited a popular estate in the Lekki Phase II area",
            depth_note="three cars ... half-submerged; water almost at knee level",
            read_status="read",
        ),
        r(
            source_id=pu, kind="news_report", publisher="Punch",
            source_url="https://punchng.com/10-hour-rainfall-lekki-ikoyi-residents-flee-luxury-mansions-as-flood-ravages-homes-streets/",
            published_at="2024-07-07T13:20:29+01:00",
            observed_at="2024-07-04T12:00:00+01:00", time_confidence="day",
            location_name="Ikoyi", location_confidence="neighbourhood",
            query="Ikoyi, Lagos",
            claim="Residents fled luxury homes after more than 10 hours of rain.",
            read_status="read",
        ),
        r(
            source_id=pu, kind="news_report", publisher="Punch",
            source_url="https://punchng.com/10-hour-rainfall-lekki-ikoyi-residents-flee-luxury-mansions-as-flood-ravages-homes-streets/",
            published_at="2024-07-07T13:20:29+01:00",
            observed_at="2024-07-04T12:00:00+01:00", time_confidence="day",
            location_name="Ajah", location_confidence="neighbourhood",
            query="Ajah, Lagos",
            claim="Residents used canoes on flooded streets; markets abandoned.",
            quote="In Ajah, residents used canoes to navigate flooded streets.",
            read_status="read",
        ),
        r(
            source_id=pu, kind="news_report", publisher="Punch",
            source_url="https://punchng.com/10-hour-rainfall-lekki-ikoyi-residents-flee-luxury-mansions-as-flood-ravages-homes-streets/",
            published_at="2024-07-07T13:20:29+01:00",
            observed_at="2024-07-04T12:00:00+01:00", time_confidence="day",
            location_name="Lekki", location_confidence="neighbourhood",
            query="Lekki, Lagos",
            claim="Living rooms flooded; residents moved to hotels.",
            quote="I woke up to find my living room submerged in water.",
            depth_note="living room submerged; water almost at knee level",
            read_status="read",
        ),
        r(
            source_id=pu, kind="official_statement", publisher="Punch",
            source_url="https://punchng.com/10-hour-rainfall-lekki-ikoyi-residents-flee-luxury-mansions-as-flood-ravages-homes-streets/",
            published_at="2024-07-07T13:20:29+01:00",
            observed_at="2024-07-03T12:00:00+01:00", time_confidence="day",
            location_name="Olopomeji", location_confidence="point",
            query="Olopomeji, Lagos",
            claim="Ministry said emergency responders cleared refuse-blocked water paths.",
            quote="we deployed our emergency responders to some areas like Olopomeji",
            read_status="read",
        ),
        # --- Channels TV 3 Jul 2024 (read) ---
        r(
            source_id=ch, kind="official_statement", publisher="Channels Television",
            source_url="https://www.channelstv.com/2024/07/03/lagos-calls-for-calm-after-wednesdays-torrential-rainfall/",
            published_at="2024-07-03T15:37:45+01:00",
            observed_at="2024-07-03T09:00:00+01:00", time_confidence="approx",
            location_name="Iyana Oworo linking the Third Mainland",
            location_confidence="street", query="Iyana Oworo, Lagos",
            claim="Wahab: about nine hours of rain; EFAG cleared Iyana Oworo.",
            quote="the flash floods which inundated areas like Iyana Oworo linking the Third Mainland",
            depth_note="a foot of flowing water with high tide",
            read_status="read",
        ),
    ]


def hit_is_implausible(query: str, hit: dict) -> bool:
    name = hit.get("display_name") or ""
    for token in IMPLAUSIBLE.get(query, ()):
        if token in name:
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
    queries = list(dict.fromkeys(r["query"] for r in recs))
    hits = geocode_many(queries, BBOX)

    features = []
    unresolved = []
    for rec in recs:
        placed = resolve(rec, hits)
        if placed is None:
            unresolved.append(f"{rec['source_id']}: {rec['location_name']} ({rec['query']})")
            continue
        lon, lat, method, conf = placed
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {
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
            },
        })

    extra_sources = {
        "channelstv-2024-07-03": (
            "https://www.channelstv.com/2024/07/03/"
            "lagos-calls-for-calm-after-wednesdays-torrential-rainfall/"
        ),
    }
    event.setdefault("sources", {}).update(extra_sources)
    event_path.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")

    payload = {
        "type": "FeatureCollection",
        "meta": {
            "compiled_at": utc_now(),
            "method": (
                "Read named sources; one point per (source, location); "
                "Nominatim geocode inside AOI bbox, 1 req/s; "
                "manual neighbourhood centre only if Nominatim missed."
            ),
            "notes": (
                "Quotes are verbatim excerpts ≤ 25 words. "
                "Ifo, Ogun (TheCable) omitted — outside AOI. "
                "Punch dates the 10-hour rain Wednesday 4 July as published; "
                "ThisDay/BBC/Channels describe Wednesday 3 July. "
                "No locations, times or quotes were inferred beyond the text."
            ),
            "unresolved": unresolved,
            "bbox": BBOX,
            "feature_count": len(features),
        },
        "features": features,
    }
    out = event_dir / "evidence.geojson"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    by_conf: dict[str, int] = {}
    by_read: dict[str, set[str]] = {"read": set(), "headline_only": set()}
    for feat in features:
        p = feat["properties"]
        by_conf[p["location_confidence"]] = by_conf.get(p["location_confidence"], 0) + 1
        by_read[p["read_status"]].add(p["source_id"])
    lines = [
        "FloodTrace media evidence",
        f"event: {event.get('id', event_dir.name)}",
        f"features: {len(features)}",
        f"sources read: {len(by_read['read'])} ({sorted(by_read['read'])})",
        f"sources headline_only: {len(by_read['headline_only'])} "
        f"({sorted(by_read['headline_only']) or 'none'})",
        "location_confidence: "
        + ", ".join(f"{k}={v}" for k, v in sorted(by_conf.items())),
        f"unresolved: {unresolved or 'none'}",
        "omitted: Ifo, Ogun (TheCable) — outside AOI; "
        "Punch 'June 3' Mushin collapse not used (BBC dates that rescue 3 July).",
        f"wrote {out}",
    ]
    summary = "\n".join(lines)
    print(summary)
    return summary


def main() -> None:
    event_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "events/lagos-2024-07-03"
    build(event_dir)


if __name__ == "__main__":
    main()
