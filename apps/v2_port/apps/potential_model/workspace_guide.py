"""Manual regional guides. Navigation is entirely local to the browser tab.

Targets belong to the app: ``data-workspace-guide="target-id"`` and optionally
``data-workspace-guide-kind="panel|block|map|self"``. Panel markers live inside
their native expander. A map marker's element container immediately precedes
the map iframe container; the guide never enters an iframe. No analytical
values, source selections, layers or submissions are changed by this module.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import streamlit as st

GUIDE_VERSION = "v1"
_LANGUAGES = ("sv", "nb", "da", "en")
_LABELS = {
    "launch": ("Visa guide", "Vis veiledning", "Vis vejledning", "Show guide"),
    "resume": ("Fortsätt guiden", "Fortsett veiledningen", "Fortsæt vejledningen", "Resume guide"),
    "close": ("Stäng guiden", "Lukk veiledningen", "Luk vejledningen", "Close guide"),
    "pause": ("Pausa", "Pause", "Pause", "Pause"),
    "previous": ("Föregående", "Forrige", "Forrige", "Previous"),
    "next": ("Nästa", "Neste", "Næste", "Next"),
    "done": ("Klart", "Ferdig", "Færdig", "Done"),
    "step": ("Steg {index} av {count}", "Trinn {index} av {count}", "Trin {index} af {count}", "Step {index} of {count}"),
    "missing": (
        "Den här delen visas inte just nu. Du kan fortsätta till nästa steg.",
        "Denne delen vises ikke nå. Du kan fortsette til neste trinn.",
        "Denne del vises ikke lige nu. Du kan fortsætte til næste trin.",
        "This section is not currently visible. You can continue to the next step.",
    ),
}

# IDs and target IDs are independent of wording, language and step number.
_STEPS = (
    ("intro", "region",
     ("Utforska Bornholm", "Utforsk Bornholm", "Udforsk Bornholm", "Explore Bornholm"),
     ("Kartan visar möjlig etableringsyta för vind och sol. Om ytbehovet inte ryms kan du undersöka andra restriktionslager, större anslutningsavstånd eller en annan installerad effekt för vindkraft och marksol. Du väljer själv vilka ändringar du vill prova.",
      "Kartet viser mulig etableringsareal for vind og sol. Hvis arealbehovet ikke får plass, kan du undersøke andre restriksjonslag, større tilkoblingsavstand eller en annen installert effekt for vindkraft og sol på bakken. Du velger selv hvilke endringer du vil prøve.",
      "Kortet viser muligt etableringsareal for vind og sol. Hvis arealbehovet ikke kan rummes, kan du undersøge andre restriktionslag, større tilslutningsafstand eller en anden installeret effekt for vindkraft og sol på land. Du vælger selv, hvilke ændringer du vil prøve.",
      "The map shows potential development area for wind and solar. If the land requirement does not fit, explore different restriction layers, a greater connection distance or different installed wind and ground-mounted solar capacity. You choose which changes to try.")),
    ("wind-nature", "wind-nature",
     ("Natur och vind", "Natur og vind", "Natur og vind", "Nature and wind"),
     ("Prova att stänga av hela gruppen Skyddad natur i vindpanelen. Ändringen är ett utkast. Fortsätt till elnätsfiltret i nästa steg innan du trycker på Använd ändringar.",
      "Prøv å slå av hele Natur-gruppen i vindpanelet. Endringen er et utkast. Fortsett til strømnettfilteret i neste trinn før du bruker vindvalgene.",
      "Prøv at slå hele Natur-gruppen fra i vindpanelet. Ændringen er en kladde. Fortsæt til elnetfilteret i næste trin, før du anvender vindvalgene.",
      "Try turning off the entire Nature group in the wind panel. This change is a draft. Continue to the grid filter in the next step before applying your wind choices.")),
    ("wind-grid", "wind-grid-apply",
     ("Elnät och tillämpning", "Strømnett og bruk", "Elnet og anvendelse", "Grid and Apply"),
     ("Prova att öka Största anslutningsavstånd för att undersöka mer yta. Avståndet säger inget om ledig nätkapacitet. Tryck på Använd ändringar under vindgrupperna för att tillämpa både naturvalet och avståndet tillsammans.",
      "Prøv å øke maksimal tilkoblingsavstand for å undersøke mer areal. Avstanden sier ikke noe om ledig nettkapasitet. Bruk knappen under vindgruppene for å ta i bruk både naturvalget og avstanden sammen.",
      "Prøv at øge den maksimale tilslutningsafstand for at undersøge mere areal. Afstanden siger intet om ledig netkapacitet. Brug knappen under vindgrupperne for at anvende både naturvalget og afstanden sammen.",
      "Try increasing the maximum connection distance to explore more land. Distance does not establish available grid capacity. Use Apply below the wind groups to apply the nature choice and distance together.")),
    ("mix", "mix",
     ("Vindkraft och marksol i MW", "Vindkraft og sol på bakken i MW", "Vindkraft og sol på land i MW", "Wind and ground-mounted solar in MW"),
     ("I Energimodellering till vänster väljer du total installerad effekt med två oberoende reglage, vardera 0–200 MW. Ändra vindkraft och marksol och tryck sedan på Använd ändringar för att uppdatera resultaten. Årsproduktionen saknas i underlaget.",
      "I Energimodellering til venstre velger du samlet installert effekt med to uavhengige skyveknapper, hver fra 0–200 MW. Endre vindkraft og sol på bakken, og trykk deretter på Bruk endringer for å oppdatere resultatene. Årsproduksjon mangler i datagrunnlaget.",
      "I Energimodellering til venstre vælger du samlet installeret effekt med to uafhængige skydere, hver fra 0–200 MW. Ændr vindkraft og sol på land, og tryk derefter på Anvend ændringer for at opdatere resultaterne. Årsproduktion mangler i datagrundlaget.",
      "In Energy modelling on the left, choose total installed capacity with two independent sliders, each from 0–200 MW. Change wind and ground-mounted solar, then press Apply changes to update the results. Annual generation is unavailable in the source data.")),
    ("scenario", "mix",
     ("EML:s referensvärden", "EMLs referanseverdier", "EML's referenceværdier", "EML's reference values"),
     ("De diskreta markeringarna under reglagen visar kapaciteterna för EML:s tre referensår. Jämför dina val med dessa värden. Referensvärdena inkluderar befintlig kapacitet. Återställ standardvärden återgår till appens startvärden.",
      "De diskrete markeringene under skyveknappene viser kapasitetene for EMLs tre referanseår. Sammenlign valgene dine med disse verdiene. Referanseverdiene inkluderer eksisterende kapasitet. Gjenopprett standardverdier går tilbake til appens startverdier.",
      "De diskrete markeringer under skyderne viser kapaciteterne for EML's tre referenceår. Sammenlign dine valg med disse værdier. Referenceværdierne inkluderer eksisterende kapacitet. Gendan standardværdier vender tilbage til appens startværdier.",
      "The subtle markers below the sliders show capacities for EML's three reference years. Compare your choices with these values. The reference values include existing capacity. Restore default values returns to the app's starting values.")),
    ("social", "social",
     ("Social acceptans", "Sosial aksept", "Social accept", "Social acceptance"),
     ("Här kan social acceptans bli ytterligare ett perspektiv på möjliga etableringar. Dagens funktion använder syntetiska testdata. Verkliga underlag från IVL är ett planerat tillskott.",
      "Prøv innstillingene for sosial aksept og bruk dem hvis du vil sammenligne resultater. Grunnlaget er syntetiske testdata, ikke observert aksept. Fremtidige data fra IVL skal erstatte testdataene.",
      "Prøv indstillingerne for social accept, og anvend dem, hvis du vil sammenligne resultater. Grundlaget er syntetiske testdata, ikke observeret accept. Fremtidige data fra IVL skal erstatte testdataene.",
      "Try the social acceptance settings and apply them if you want to compare results. These are synthetic test data, not observed acceptance. Future IVL data are intended to replace the test data.")),
    ("potential-map", "map",
     ("Teknisk potential på kartan", "Teknisk potensial på kartet", "Teknisk potentiale på kortet", "Technical potential on the map"),
     ("Grönt betyder potential för båda teknikerna, blått vind, gult sol och mörkrött olämplig yta enligt tillämpade regler. Vid utzoomning visas den dominerande kategorin, inte varje plats i hexagonen. Guiden tänder inga kartlager.",
      "Grønt betyr potensial for begge teknologiene, blått vind, gult sol og mørkerødt uegnet areal etter reglene som er brukt. Ved utzooming vises den dominerende kategorien, ikke hvert sted i heksagonen. Veiledningen slår ikke på kartlag.",
      "Grønt betyder potentiale for begge teknologier, blåt vind, gult sol og mørkerødt uegnet areal efter de anvendte regler. Ved udzoomning vises den dominerende kategori, ikke hvert sted i hexagonen. Vejledningen tænder ingen kortlag.",
      "Green means potential for both technologies, blue wind, yellow solar, and dark red unsuitable area under the applied rules. At coarse zoom, color shows the dominant category, not every location in the hexagon. The guide does not enable map layers.")),
    ("scenario-map", "map",
     ("Scenariot på kartan", "Scenarioet på kartet", "Scenariet på kortet", "The scenario on the map"),
     ("Scenariofärgerna är blått för vind och gulorange för sol. Mörkgrönt visar båda i samma visningshexagon; det betyder inte att anläggningarna överlappar fysiskt.",
      "Scenariofargene er blått for vind og guloransje for sol. Mørkegrønt viser begge i samme visningsheksagon; det betyr ikke at anleggene overlapper fysisk.",
      "Scenariefarverne er blåt for vind og gulorange for sol. Mørkegrønt viser begge i samme visningshexagon; det betyder ikke, at anlæggene overlapper fysisk.",
      "Scenario colors are blue for wind and yellow-orange for solar. Dark green shows both in the same display hexagon; it does not mean the installations physically overlap.")),
    ("outside-map", "map",
     ("Utanför potentialytan", "Utenfor potensialarealet", "Uden for potentialearealet", "Outside the potential area"),
     ("Om scenariot kräver mer yta än den beräknade potentialen kan kartan även visa ett schematiskt område utanför potentialytan. Läs kartans teckenförklaring; detta är inte en exakt lokalisering.",
      "Hvis scenarioet krever mer areal enn det beregnede potensialet, kan kartet også vise et skjematisk område utenfor potensialarealet. Les kartforklaringen; dette er ikke en nøyaktig plassering.",
      "Hvis scenariet kræver mere areal end det beregnede potentiale, kan kortet også vise et skematisk område uden for potentialearealet. Læs signaturforklaringen; dette er ikke en præcis placering.",
      "If the scenario needs more area than the calculated potential, the map can also show a schematic area outside it. Read the map legend; this is not an exact location.")),
    ("results", "results",
     ("Läs resultatet", "Les resultatet", "Læs resultatet", "Read the results"),
     ("Jämför tillämpat scenario, kapacitet i MW och beräknad yta i resultatpanelen. Totalytan summerar teknikernas ytor, inte unik mark vid överlapp. Där finns även regional kontext. Du kan starta guiden igen när du vill.",
      "Sammenlign scenarioet som er brukt, kapasitet i MW og beregnet areal i resultatpanelet. Totalarealet summerer teknologienes arealer, ikke unikt areal ved overlapp. Der finnes også regional kontekst. Du kan starte veiledningen igjen når du vil.",
      "Sammenlign det anvendte scenarie, kapacitet i MW og beregnet areal i resultatpanelet. Totalarealet summerer teknologiernes arealer, ikke unikt areal ved overlap. Her findes også regional kontekst. Du kan starte vejledningen igen, når du vil.",
      "Compare the applied scenario, capacity in MW and calculated area in the results panel. Total area sums the technology areas, not unique land where they overlap. It also provides regional context. Start the guide again whenever you like.")),
)

_ASSETS = Path(__file__).parent
_COMPONENT = st.components.v2.component(
    "speedlocal_workspace_guide",
    html='<div data-workspace-guide-client><button type="button" data-guide-action="launch"></button></div>\n',
    js=_ASSETS.joinpath("workspace_guide.js").read_text(encoding="utf-8"),
    css=_ASSETS.joinpath("workspace_guide.css").read_text(encoding="utf-8"),
)


def guide_steps(language: str = "sv") -> list[dict[str, str]]:
    """Return independent translated step data, without runtime state."""
    index = _LANGUAGES.index(language) if language in _LANGUAGES else 3
    return [dict(id=step_id, target=target, title=title[index], body=body[index])
            for step_id, target, title, body in _STEPS]


def render_workspace_guide(
    region_id: str,
    language: str = "sv",
    *,
    steps: Sequence[Mapping[str, str]] | None = None,
    launch_label: str | None = None,
) -> None:
    """Mount the manual guide; the caller owns capability/rollout gating."""
    index = _LANGUAGES.index(language) if language in _LANGUAGES else 3
    rendered_steps = [dict(step) for step in steps] if steps is not None else guide_steps(language)
    if any(not all(isinstance(step.get(key), str) and step[key]
                   for key in ("id", "target", "title", "body")) for step in rendered_steps):
        raise ValueError("Guide steps require nonempty id, target, title and body strings")
    if len(rendered_steps) != 10 or len({step["id"] for step in rendered_steps}) != 10:
        raise ValueError("Workspace guides require ten uniquely identified steps")
    data: dict[str, Any] = {
        # A real app render pauses the guide even when its translated copy is
        # unchanged. This client input never emits a server event.
        "render_token": uuid4().hex,
        "region": region_id,
        "version": GUIDE_VERSION,
        "language": _LANGUAGES[index],
        "steps": rendered_steps,
        "labels": {key: values[index] for key, values in _LABELS.items()},
        "swatches": {
            "potential-map": [
                {"color": "#15803d", "label": ("Båda", "Begge", "Begge", "Both")[index]},
                {"color": "#2563eb", "label": ("Vind", "Vind", "Vind", "Wind")[index]},
                {"color": "#facc15", "label": ("Sol", "Sol", "Sol", "Solar")[index]},
                {"color": "#991b1b", "label": ("Olämplig", "Uegnet", "Uegnet", "Unsuitable")[index]},
            ],
            "scenario-map": [
                {"color": "#005A8D", "border": "transparent", "label": ("Vind", "Vind", "Vind", "Wind")[index]},
                {"color": "#F2B01E", "border": "transparent", "label": ("Sol", "Sol", "Sol", "Solar")[index]},
                {"color": "#145A32", "border": "transparent", "label": ("Båda i visningshexagonen", "Begge i visningsheksagonen", "Begge i visningshexagonen", "Both in the display hexagon")[index]},
            ],
        },
    }
    if launch_label is not None:
        data["labels"]["launch"] = launch_label
    _COMPONENT(data=data, key=f"workspace-guide:{GUIDE_VERSION}:{region_id}", width="content", height="content")
