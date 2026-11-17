"""Authored Swedish, Norwegian Bokmål, Danish and English presentation copy.

Each row is (sv, nb, da, en). Units, source identities and scenario identities
are parameters or unchanged proper names. Keep named parameters identical.
"""

MESSAGES: dict[str, tuple[str, str, str, str]] = {
    "map.rollup.geometry": (
        "Gränsen visar H3-cellen; värdena är summerade från analysnivån.",
        "Grensen viser H3-cellen; verdiene er summert fra analysenivået.",
        "Grænsen viser H3-cellen; værdierne er summeret fra analyseniveauet.",
        "The outline shows the H3 cell; values are summed from the analysis level.",
    ),
    "map.rollup.dominant": (
        "Dominerande färgklass: {label} ({share} % av ytan)",
        "Dominerende fargeklasse: {label} ({share} % av arealet)",
        "Dominerende farveklasse: {label} ({share} % af arealet)",
        "Dominant colour class: {label} ({share} % of the area)",
    ),
    "map.hex_size.title": (
        "Hexagonstorlek", "Heksagonstørrelse", "Hexagonstørrelse", "Hexagon size",
    ),
    "map.hex_size.global_reference": (
        "Globalt H3-medel", "Globalt H3-gjennomsnitt", "Globalt H3-gennemsnit", "Global H3 mean",
    ),
    "map.hex_size.cell": (
        "Visningshex R{resolution}", "Visningsheksagon R{resolution}",
        "Visningshexagon R{resolution}", "Display hexagon R{resolution}",
    ),
    "map.hex_size.reference": (
        "Ungefärlig yta för en hel hexagon. Kanthex kan vara beskurna; möjlig etableringsyta kan vara mindre.",
        "Omtrentlig areal for en hel heksagon. Kantheksagoner kan være beskåret; mulig etableringsareal kan være mindre.",
        "Omtrentligt areal for en hel hexagon. Kanthexagoner kan være beskåret; muligt etableringsareal kan være mindre.",
        "Approximate area of a full hexagon. Edge hexagons may be clipped; possible establishment area may be smaller.",
    ),
    "map.hex_size.schematic": (
        "Schematisk hexagon", "Skjematisk heksagon", "Skematisk hexagon", "Schematic hexagon",
    ),
    "map.hex_size.schematic_sizes": (
        "Schematiska hexagoner", "Skjematiske heksagoner", "Skematiske hexagoner", "Schematic hexagons",
    ),
    "freshness.expired": ('Resultatet behöver verifieras på nytt. Uppdatera underlaget.',
 'Resultatet må verifiseres på nytt. Oppdater grunnlaget.',
 'Resultatet skal verificeres igen. Opdater grundlaget.',
 'Results need to be verified again. Refresh the inputs.'),
    "debug.coordinates": ("Analysupplösning: R{resolution} · CRS: {crs}.", "Analyseoppløsning: R{resolution} · CRS: {crs}.", "Analyseopløsning: R{resolution} · CRS: {crs}.", "Analysis resolution: R{resolution} · CRS: {crs}."),
    "debug.access": ("Åtkomstklass: {classification}.", "Tilgangsklasse: {classification}.", "Adgangsklasse: {classification}.", "Access classification: {classification}."),
    "landing.kicker": ("Projektöversikt", "Prosjektoversikt", "Projektoversigt", "Project overview"),
    "landing.title": ("landskapspotential", "landskapspotensial", "landskabspotentiale", "landscape potential"),
    "landing.lead": ("Utforska ytan för vind och sol i Bornholm, Trøndelag och Skaraborg. Jämför scenarier och fördelningen mellan vind och sol, och pröva geografiska begränsningar. Kartan och resultaten visar kvarvarande etableringsyta, scenariots ytbehov och hur mycket som ryms inom potentialen. Se hur dina val ändrar balansen mellan behov och möjlig yta.", "Utforsk arealet for vind og sol i Bornholm, Trøndelag og Skaraborg. Sammenlign scenarioer og fordelingen mellom vind og sol, og prøv geografiske begrensninger. Kartet og resultatene viser gjenværende etableringsareal, scenarioets arealbehov og hvor mye som får plass innenfor potensialet. Se hvordan valgene dine endrer balansen mellom behov og mulig areal.", "Udforsk arealet til vind og sol i Bornholm, Trøndelag og Skaraborg. Sammenlign scenarier og fordelingen mellem vind og sol, og afprøv geografiske begrænsninger. Kortet og resultaterne viser resterende etableringsareal, scenariets arealbehov og hvor meget der kan rummes inden for potentialet. Se, hvordan dine valg ændrer balancen mellem behov og muligt areal.", "Explore wind and solar area in Bornholm, Trøndelag and Skaraborg. Compare scenarios and the split between wind and solar, and try geographic constraints. The map and results show remaining establishment area, scenario area demand and how much fits within the potential. See how your choices change the balance between demand and possible area."),
    "landing.navigation": ("Sidans innehåll", "Sidens innhold", "Sidens indhold", "Page contents"),
    "landing.choose_region": ("Välj region", "Velg region", "Vælg region", "Choose a region"),
    "landing.see_model": ("Se modellen", "Se modellen", "Se modellen", "See the model"),
    "landing.see_method": ("Se metod", "Se metoden", "Se metoden", "See the method"),
    "landing.regions_intro": ("Social acceptans är syntetisk i alla tre regioner.", "Sosial aksept er syntetisk i alle tre regioner.", "Social accept er syntetisk i alle tre regioner.", "Social acceptance is synthetic in all three regions."),
    "landing.wait_title": ("Väntetider i prototypen", "Ventetider i prototypen", "Ventetider i prototypen", "Waiting times in the prototype"),
    "landing.wait_evidence": ("Ungefärliga riktvärden från lokala observationer den 13 oktober 2026:", "Omtrentlige veiledende tider fra lokale observasjoner 13. oktober 2026:", "Omtrentlige vejledende tider fra lokale observationer den 13. oktober 2026:", "Approximate guidance from local observations on 13 October 2026:"),
    "landing.wait_advice": ("Vi arbetar med att korta väntetiderna. Vid längre väntan: hämta gärna en kaffe, ta en teknisk paus, en nypa frisk luft eller en kort meditation. Ett beräkningssteg kan ta tid även om indikatorn står still.", "Vi arbeider med å korte ned ventetidene. Ved lengre ventetid: hent gjerne en kaffe, ta en teknisk pause, litt frisk luft eller en kort meditasjon. Et beregningstrinn kan ta tid selv om indikatoren står stille.", "Vi arbejder på at forkorte ventetiderne. Ved længere ventetid: hent gerne en kaffe, tag en teknisk pause, lidt frisk luft eller en kort meditation. Et beregningstrin kan tage tid, selv om indikatoren står stille.", "We are working to reduce waiting times. During a longer wait, feel free to get a coffee, take a technical break, get some fresh air or meditate briefly. A calculation step can take time even when the indicator is stationary."),
    "landing.denmark": ("Danmark", "Danmark", "Danmark", "Denmark"),
    "landing.norway": ("Norge", "Norge", "Norge", "Norway"),
    "landing.sweden": ("Sverige", "Sverige", "Sverige", "Sweden"),
    "landing.prototype": ("Prototyp", "Prototype", "Prototype", "Prototype"),
    "landing.bornholm": ("Det mest underbyggda exemplet, med data från EML:s energimodell och Bornholms geografiska underlag. Kapacitetsscenarierna är preliminära.", "Det best underbygde eksemplet, med data fra EMLs energimodell og Bornholms geografiske data. Kapasitetsscenarioene er foreløpige.", "Det bedst underbyggede eksempel, med data fra EMLs energimodel og Bornholms geografiske data. Kapacitetsscenarierne er foreløbige.", "The most substantiated example, using EML energy-model data and Bornholm's geographic data. Capacity scenarios are preliminary."),
    "landing.trondelag": ("Regionala geografiska underlag och preliminära energiantaganden lånade från Bornholm. Scenarierna är inte regionalt kalibrerade.", "Regionale geografiske data og foreløpige energiantakelser hentet fra Bornholm. Scenarioene er ikke regionalt kalibrert.", "Regionale geografiske data og foreløbige energiantagelser lånt fra Bornholm. Scenarierne er ikke regionalt kalibreret.", "Regional geographic data and preliminary energy assumptions borrowed from Bornholm. The scenarios have not been regionally calibrated."),
    "landing.skaraborg": ("Regionala geografiska underlag och preliminära energiantaganden lånade från Bornholm. Scenarierna är inte regionalt kalibrerade.", "Regionale geografiske data og foreløpige energiantakelser hentet fra Bornholm. Scenarioene er ikke regionalt kalibrert.", "Regionale geografiske data og foreløbige energiantagelser lånt fra Bornholm. Scenarierne er ikke regionalt kalibreret.", "Regional geographic data and preliminary energy assumptions borrowed from Bornholm. The scenarios have not been regionally calibrated."),
    "landing.generic_region": ("Utforska regionens geografiska underlag och scenarier i det gemensamma programmet.", "Utforsk regionens geografiske data og scenarioer i det felles programmet.", "Udforsk regionens geografiske data og scenarier i det fælles program.", "Explore the region's geographic data and scenarios in the shared application."),
    "landing.open_region": ("Öppna {region}", "Åpne {region}", "Åbn {region}", "Open {region}"),
    "landing.unavailable": ("Inte tillgänglig i den här miljön.", "Ikke tilgjengelig i dette miljøet.", "Ikke tilgængelig i dette miljø.", "Unavailable in this environment."),
    "landing.model": ("Modell", "Modell", "Model", "Model"),
    "landing.model_title": ("Vad beräknar appen?", "Hva beregner appen?", "Hvad beregner appen?", "What does the app calculate?"),
    "landing.model_question": ("Givet ett landskap, geografiska underlag och ett scenario: vilka delytor är möjliga för vind och sol, hur mycket yta återstår och hur förhåller den sig till scenariots ytbehov?", "Gitt et landskap, geografiske data og et scenario: hvilke delarealer er mulige for vind og sol, hvor mye areal gjenstår, og hvordan står det i forhold til scenarioets arealbehov?", "Givet et landskab, geografiske data og et scenarie: hvilke delarealer er mulige for vind og sol, hvor meget areal er tilbage, og hvordan forholder det sig til scenariets arealbehov?", "Given a landscape, geographic data and a scenario, which subareas are possible for wind and solar, how much area remains, and how does it compare with the scenario's area demand?"),
    "landing.model_geography": ("Landskapet delas upp i hexagonala analysceller. Vägar, befolkning, natur, kulturmiljö och elnät beskriver olika begränsningar och förutsättningar. Valda restriktioner och avstånd påverkar den återstående etableringsytan. Överlappande begränsningar räknas en gång.", "Landskapet deles inn i sekskantede analyseceller. Veier, befolkning, natur, kulturmiljø og strømnett beskriver ulike begrensninger og forutsetninger. Valgte restriksjoner og avstander påvirker det gjenværende etableringsarealet. Overlappende begrensninger telles én gang.", "Landskabet deles op i sekskantede analyseceller. Veje, befolkning, natur, kulturmiljø og elnet beskriver forskellige begrænsninger og forudsætninger. Valgte restriktioner og afstande påvirker det resterende etableringsareal. Overlappende begrænsninger tælles én gang.", "The landscape is divided into hexagonal analysis cells. Roads, population, nature, cultural environments and the electricity grid describe different constraints and conditions. Selected restrictions and distances affect the remaining establishment area. Overlapping constraints are counted once."),
    "landing.model_energy": ("Scenariots antaganden om energi eller installerad kapacitet översätts till ytbehov för vind och sol. Appen jämför behovet med möjlig yta och visar hur scenariot kan fördelas. Landskapstyper är ett kompletterande kartlager där underlag finns.", "Scenarioets antakelser om energi eller installert kapasitet omregnes til arealbehov for vind og sol. Appen sammenligner behovet med mulig areal og viser hvordan scenarioet kan fordeles. Landskapstyper er et supplerende kartlag der data finnes.", "Scenariets antagelser om energi eller installeret kapacitet omsættes til arealbehov for vind og sol. Appen sammenligner behovet med muligt areal og viser, hvordan scenariet kan fordeles. Landskabstyper er et supplerende kortlag, hvor data findes.", "The scenario's assumptions about energy or installed capacity are converted to area demand for wind and solar. The app compares demand with possible area and shows how the scenario can be allocated. Landscape types are a supplementary map layer where data is available."),
    "landing.model_summary": ("Modellen i korthet", "Modellen kort forklart", "Modellen kort fortalt", "The model at a glance"),
    "landing.step1": ("Välj landskap och scenario.", "Velg landskap og scenario.", "Vælg landskab og scenarie.", "Choose a landscape and scenario."),
    "landing.step2": ("Pröva restriktioner och avstånd.", "Prøv restriksjoner og avstander.", "Afprøv restriktioner og afstande.", "Test restrictions and distances."),
    "landing.step3": ("Jämför möjlig yta med ytbehov.", "Sammenlign mulig areal med arealbehov.", "Sammenlign muligt areal med arealbehov.", "Compare possible area with area demand."),
    "landing.step4": ("Läs karta och resultat tillsammans.", "Les kart og resultater sammen.", "Læs kort og resultater sammen.", "Read the map and results together."),
    "landing.method": ("Metod", "Metode", "Metode", "Method"),
    "landing.method_title": ("Från underlag till landskapspotential", "Fra data til landskapspotensial", "Fra data til landskabspotentiale", "From data to landscape potential"),
    "landing.constraints_title": ("Geografiska begränsningar", "Geografiske begrensninger", "Geografiske begrænsninger", "Geographic constraints"),
    "landing.constraints": ("Ändra ett antagande i taget och jämför med startläget. En analyscell kan vara delvis tillgänglig; den återstående ytan behålls i beräkningen. Underlag och geografisk upplösning skiljer sig mellan regionerna.", "Endre én antakelse om gangen og sammenlign med utgangspunktet. En analysecelle kan være delvis tilgjengelig; det gjenværende arealet beholdes i beregningen. Data og geografisk oppløsning varierer mellom regionene.", "Ændr én antagelse ad gangen og sammenlign med udgangspunktet. En analysecelle kan være delvist tilgængelig; det resterende areal bevares i beregningen. Data og geografisk opløsning varierer mellem regionerne.", "Change one assumption at a time and compare with the starting point. An analysis cell may be partly available; its remaining area is retained in the calculation. Data and geographic resolution differ between regions."),
    "landing.scenario_title": ("Scenario och etableringsyta", "Scenario og etableringsareal", "Scenarie og etableringsareal", "Scenario and establishment area"),
    "landing.scenario": ("Vind och sol har olika ytbehov. Val av scenario, fördelningen mellan vind och sol och geografiska begränsningar påverkar hur mycket som ryms inom potentialen. Ytbehov utanför potentialen visas som en jämförelse, inte som föreslagna etableringsplatser.", "Vind og sol har ulike arealbehov. Valg av scenario, fordelingen mellom vind og sol og geografiske begrensninger påvirker hvor mye som får plass innenfor potensialet. Arealbehov utenfor potensialet vises som en sammenligning, ikke som foreslåtte etableringssteder.", "Vind og sol har forskellige arealbehov. Valg af scenarie, fordelingen mellem vind og sol og geografiske begrænsninger påvirker, hvor meget der kan rummes inden for potentialet. Arealbehov uden for potentialet vises som en sammenligning, ikke som foreslåede placeringer.", "Wind and solar have different area demands. The scenario, the split between wind and solar, and geographic constraints affect how much fits within the potential. Area demand outside the potential is shown as a comparison, not as proposed sites."),
    "landing.uncertainty_title": ("Underlag och osäkerhet", "Data og usikkerhet", "Data og usikkerhed", "Data and uncertainty"),
    "landing.uncertainty": ("Energiscenarierna är preliminära och social acceptans är syntetisk, inte uppmätta åsikter. Saknade data är inte noll. Resultaten är för utforskning och diskussion, inte beslut om placering eller tillstånd.", "Energiscenarioene er foreløpige og sosial aksept er syntetisk, ikke målte meninger. Manglende data er ikke null. Resultatene er til utforskning og diskusjon, ikke beslutninger om plassering eller tillatelser.", "Energiscenarierne er foreløbige og social accept er syntetisk, ikke målte holdninger. Manglende data er ikke nul. Resultaterne er til udforskning og diskussion, ikke beslutninger om placering eller tilladelser.", "Energy scenarios are preliminary and social acceptance is synthetic, not measured opinions. Missing data is not zero. Results are for exploration and discussion, not siting or permitting decisions."),
    "landing.wait_opening": ("Första analysöppningen: cirka 1–3 minuter. Återanvänt underlag kan ge kortare väntan.", "Første åpning av analysen: omtrent 1–3 minutter. Gjenbruk av data kan gi kortere ventetid.", "Første åbning af analysen: cirka 1–3 minutter. Genbrug af data kan give kortere ventetid.", "First analysis opening: about 1–3 minutes. Reused inputs can make it faster."),
    "landing.wait_layers": ("Visa eller dölj redan inlästa kartlager: vanligen direkt, utan att räkna om analysen.", "Vis eller skjul kartlag som allerede er lastet inn: vanligvis med en gang, uten å beregne analysen på nytt.", "Vis eller skjul allerede indlæste kortlag: normalt med det samme, uden at genberegne analysen.", "Show or hide already loaded map layers: usually immediate, without recalculating the analysis."),
    "landing.wait_apply": ("Tillämpa ändrade analysinställningar: cirka ½–1½ minut i tester med ändrade avstånd.", "Bruk endrede analyseinnstillinger: omtrent ½–1½ minutt i tester med endrede avstander.", "Anvend ændrede analyseindstillinger: cirka ½–1½ minut i test med ændrede afstande.", "Apply changed analysis settings: about ½–1½ minutes in tests with changed distances."),
    "landing.wait_limits": ("Tiderna varierar mellan regioner och körningar och är inga garantier. Verifierade kallstartstider och mätningar på Usable saknas ännu. Indikatorn visar vad som pågår; ett steg kan ta tid.", "Tidene varierer mellom regioner og kjøringer og er ingen garantier. Verifiserte kaldstarttider og målinger på Usable mangler fortsatt. Indikatoren viser hva som skjer; et trinn kan ta tid.", "Tiderne varierer mellem regioner og kørsler og er ingen garantier. Verificerede koldstarttider og målinger på Usable mangler endnu. Indikatoren viser, hvad der sker; et trin kan tage tid.", "Times vary by region and run and are not guarantees. Verified cold-start timings and measurements on Usable are not yet available. The indicator shows the current work; a step can take time."),
    "landing.model_compare": ("Börja med regionens startläge. Välj scenario, pröva fördelningen mellan vind och sol och ändra ett avstånd eller en restriktion i taget. Tillämpa ändringarna och jämför med det tidigare resultatet. Du kan undersöka vind och sol var för sig eller tillsammans.", "Begynn med regionens utgangspunkt. Velg scenario, prøv fordelingen mellom vind og sol og endre én avstand eller begrensning om gangen. Bruk endringene og sammenlign med det tidligere resultatet. Du kan undersøke vind og sol hver for seg eller sammen.", "Begynd med regionens udgangspunkt. Vælg scenarie, afprøv fordelingen mellem vind og sol, og ændr én afstand eller begrænsning ad gangen. Anvend ændringerne, og sammenlign med det tidligere resultat. Du kan undersøge vind og sol hver for sig eller sammen.", "Start with the region's initial settings. Choose a scenario, try the split between wind and solar, and change one distance or constraint at a time. Apply changes and compare with the previous result. You can explore wind and solar separately or together."),
    "landing.model_results": ("Läs kartan och resultattabellen tillsammans: kvarvarande yta, scenariots ytbehov och fördelningen inom potentialen beskriver olika saker. Jämförelseytor utanför potentialen visar eventuell brist, inte föreslagna platser. Regionernas underlag och upplösning skiljer sig, så resultaten behöver tolkas i sitt regionala sammanhang.", "Les kartet og resultattabellen sammen: gjenværende areal, scenarioets arealbehov og fordelingen innenfor potensialet beskriver ulike ting. Sammenligningsarealer utenfor potensialet viser eventuell mangel, ikke foreslåtte steder. Regionenes data og oppløsning varierer, så resultatene må tolkes i sin regionale sammenheng.", "Læs kortet og resultattabellen sammen: resterende areal, scenariets arealbehov og fordelingen inden for potentialet beskriver forskellige ting. Sammenligningsarealer uden for potentialet viser en eventuel mangel, ikke foreslåede placeringer. Regionernes data og opløsning varierer, så resultaterne skal fortolkes i deres regionale sammenhæng.", "Read the map and result table together: remaining area, scenario area demand and allocation within the potential describe different things. Comparison areas outside the potential show any shortfall, not proposed sites. Data and resolution differ by region, so interpret results in their regional context."),
    "landing.model_acceptance": ("Social acceptans har separata reglage för påverkan på potentialen och prioritering av fördelningen. Pröva hur de ändrar resultatet. Värdena är syntetiska demonstrationsdata i alla tre regioner och visar modellens beteende, inte invånarnas uppmätta åsikter.", "Sosial aksept har separate innstillinger for påvirkning på potensialet og prioritering av fordelingen. Prøv hvordan de endrer resultatet. Verdiene er syntetiske demonstrasjonsdata i alle tre regioner og viser modellens virkemåte, ikke innbyggernes målte meninger.", "Social accept har separate indstillinger for påvirkning af potentialet og prioritering af fordelingen. Afprøv, hvordan de ændrer resultatet. Værdierne er syntetiske demonstrationsdata i alle tre regioner og viser modellens virkemåde, ikke indbyggernes målte holdninger.", "Social acceptance has separate controls for its effect on potential and its priority in allocation. Try how they change the result. Values are synthetic demonstration data in all three regions and show model behaviour, not measured residents' views."),
    "landing.footer": ("SpeedLocal landskapspotential · Bornholm, Trøndelag och Skaraborg", "SpeedLocal landskapspotensial · Bornholm, Trøndelag og Skaraborg", "SpeedLocal landskabspotentiale · Bornholm, Trøndelag og Skaraborg", "SpeedLocal landscape potential · Bornholm, Trøndelag and Skaraborg"),
    "ui.language": ("Språk", "Språk", "Sprog", "Language"),
    "ui.title": ("Sol- och vindpotential", "Sol- og vindpotensial", "Sol- og vindpotentiale", "Solar and wind potential"),
    "ui.region": ("Region", "Region", "Region", "Region"),
    "ui.scenarios": ("Scenarier", "Scenarioer", "Scenarier", "Scenarios"),
    "ui.scenario": ("Scenario", "Scenario", "Scenarie", "Scenario"),
    "ui.layers": ("Lager", "Lag", "Lag", "Layers"),
    "ui.geographies": ("Geografier", "Geografier", "Geografier", "Geographies"),
    "ui.landscape": ("Landskap", "Landskap", "Landskab", "Landscape"),
    "ui.landscape_types": ("Landskapstyper", "Landskapstyper", "Landskabstyper", "Landscape types"),
    "ui.landscape_structures": ("Landskapstrukturer", "Landskapsstrukturer", "Landskabsstrukturer", "Landscape structures"),
    "ui.landscape_factors": ("Landskapsfaktorer", "Landskapsfaktorer", "Landskabsfaktorer", "Landscape factors"),
    "ui.factor": ("Faktor", "Faktor", "Faktor", "Factor"),
    "ui.h3_resolution": ("H3-upplösning", "H3-oppløsning", "H3-opløsning", "H3 resolution"),
    "ui.h3_rollup": ("H3-rollup", "H3-rollup", "H3-rollup", "H3 rollup"),
    "ui.hex_display": ("Hexvisning", "Hexvisning", "Hexvisning", "Hex display"),
    "ui.selected_resolution": ("Vald upplösning", "Valgt oppløsning", "Valgt opløsning", "Selected resolution"),
    "ui.zoom_resolution": ("Zoomanpassad upplösning", "Zoomtilpasset oppløsning", "Zoomtilpasset opløsning", "Zoom-adaptive resolution"),
    "ui.fast_resolution": ("Snabb visning: vald upplösning", "Rask visning: valgt oppløsning", "Hurtig visning: valgt opløsning", "Fast display: selected resolution"),
    "ui.panel_width": ("Panelbredd", "Panelbredde", "Panelbredde", "Panel width"),
    "ui.toggle_context": ("Visa/dölj kontext", "Vis/skjul kontekst", "Vis/skjul kontekst", "Show/hide context"),
    "ui.map": ("Karta", "Kart", "Kort", "Map"),
    "ui.establishment_area": ("Etableringsyta", "Etableringsareal", "Etableringsareal", "Establishment area"),
    "ui.region_status": ("Regionstatus", "Regionstatus", "Regionstatus", "Region status"),
    "ui.next_package": ("Nästa datapaket", "Neste datapakke", "Næste datapakke", "Next data package"),
    "ui.data_method": ("Data och metod", "Data og metode", "Data og metode", "Data and method"),
    "ui.active_calculations": ("Aktiva beräkningar", "Aktive beregninger", "Aktive beregninger", "Active calculations"),
    "ui.calculation_quality": ("Beräkning och datakvalitet", "Beregning og datakvalitet", "Beregning og datakvalitet", "Calculation and data quality"),
    "ui.energy_modelling": ("Energimodellering", "Energimodellering", "Energimodellering", "Energy modelling"),
    "ui.acceptance": ("Social acceptans", "Sosial aksept", "Social accept", "Social acceptance"),
    "ui.show_acceptance": ("Visa social acceptans", "Vis sosial aksept", "Vis social accept", "Show social acceptance"),
    "ui.show_acceptance_layer": ("Visa social acceptanslager", "Vis lag for sosial aksept", "Vis lag for social accept", "Show social acceptance layer"),
    "ui.acceptance_impact": ("Acceptanspåverkan", "Akseptpåvirkning", "Acceptpåvirkning", "Acceptance impact"),
    "ui.coming_august": ("Kommer i augusti", "Kommer i august", "Kommer i august", "Coming in August"),
    "ui.provided_eml": ("Levereras av EML", "Leveres av EML", "Leveres af EML", "Provided by EML"),
    "ui.provided_ivl": ("Levereras av IVL", "Leveres av IVL", "Leveres af IVL", "Provided by IVL"),
    "ui.wind_potential": ("Landskapspotential Vind", "Landskapspotensial vind", "Landskabspotentiale vind", "Wind landscape potential"),
    "ui.solar_potential": ("Landskapspotential Sol", "Landskapspotensial sol", "Landskabspotentiale sol", "Solar landscape potential"),
    "ui.rooftop": ("Småskalig anläggning på tak", "Småskala anlegg på tak", "Småskala anlæg på tag", "Small-scale rooftop installation"),
    "ui.ground_solar": ("Storskalig anläggning på land", "Storskala anlegg på land", "Storskala anlæg på land", "Large-scale ground installation"),
    "ui.potential_area": ("Potentiell etableringsyta", "Potensielt etableringsareal", "Potentielt etableringsareal", "Potential establishment area"),
    "ui.scenario_area": ("Scenarioyta inom potentialen", "Scenarioareal innenfor potensialet", "Scenarieareal inden for potentialet", "Scenario area within the potential"),
    "ui.outside_area": ("Ytbehov utanför landskapets potential", "Arealbehov utenfor landskapets potensial", "Arealbehov uden for landskabets potentiale", "Area demand outside landscape potential"),
    "ui.population": ("Befolkning", "Befolkning", "Befolkning", "Population"),
    "ui.population_points": ("Befolkningspunkter", "Befolkningspunkter", "Befolkningspunkter", "Population points"),
    "ui.panel_area_person": ("Panelyta per person", "Panelareal per person", "Panelareal per person", "Panel area per person"),
    "ui.distance_population": ("Avstånd till befolkning", "Avstand til befolkning", "Afstand til befolkning", "Distance to population"),
    "ui.apply": ("Använd ändringar", "Bruk endringer", "Anvend ændringer", "Apply changes"),
    "ui.energy_mix": ("Energimix", "Energimiks", "Energimix", "Energy mix"),
    "ui.show_proposed": ("Visa föreslagen etableringsyta", "Vis foreslått etableringsareal", "Vis foreslået etableringsareal", "Show proposed establishment area"),
    "ui.summary": ("Sammanfattning", "Sammendrag", "Sammenfatning", "Summary"),
    "ui.landscape_impact": ("Vind/sol och landskapspåverkan", "Vind/sol og landskapspåvirkning", "Vind/sol og landskabspåvirkning", "Wind/solar and landscape impact"),
    "ui.read_table": ("Så läses tabellen", "Slik leses tabellen", "Sådan læses tabellen", "How to read the table"),
    "ui.advanced": ("Avancerade inställningar", "Avanserte innstillinger", "Avancerede indstillinger", "Advanced settings"),
    "ui.advanced_map": ("Avancerade kartinställningar", "Avanserte kartinnstillinger", "Avancerede kortindstillinger", "Advanced map settings"),
    "ui.wind_share": ("Vindandel", "Vindandel", "Vindandel", "Wind share"),
    "ui.solar_share": ("Solandel", "Solandel", "Solandel", "Solar share"),
    "ui.total_energy": ("Total energi", "Samlet energi", "Samlet energi", "Total energy"),
    "ui.debug": ("Debug och prestanda", "Feilsøking og ytelse", "Fejlsøgning og ydeevne", "Debug and performance"),
    "ui.manifest_paths": ("Manifest och tekniska sökvägar", "Manifest og tekniske filbaner", "Manifest og tekniske stier", "Manifests and technical paths"),
    "ui.display_units": ("Visning och enheter", "Visning og enheter", "Visning og enheder", "Display and units"),
    "ui.hex_details": ("Hexdetaljer och kartmarkörer", "Hexdetaljer og kartmarkører", "Hexdetaljer og kortmarkører", "Hex details and map markers"),
    "ui.selection_details": ("Urval och ytdetaljer", "Utvalg og arealdetaljer", "Udvalg og arealdetaljer", "Selection and area details"),
    "ui.performance": ("Prestanda", "Ytelse", "Ydeevne", "Performance"),
    "ui.landscape_analysis": ("Landskapsanalys", "Landskapsanalyse", "Landskabsanalyse", "Landscape analysis"),
    "ui.visible_layers": ("Lager som visas", "Lag som vises", "Lag som vises", "Visible layers"),
    "ui.core_areas": ("Kärnområden", "Kjerneområder", "Kerneområder", "Core areas"),
    "ui.no_layers": ("Inga lager är tända.", "Ingen lag er slått på.", "Ingen lag er slået til.", "No layers are enabled."),
    "ui.base_available": ("Alla grundmanifest och H3-geometrier finns.", "Alle grunnmanifest og H3-geometrier finnes.", "Alle grundmanifest og H3-geometrier findes.", "All base manifests and H3 geometries are available."),
    "ui.data_missing": ("Data saknas för vissa lager/funktioner. Det är okej i detta läge.", "Data mangler for enkelte lag/funksjoner. Det er greit på dette stadiet.", "Data mangler for visse lag/funktioner. Det er i orden på dette stadie.", "Data is missing for some layers/functions. That is expected at this stage."),
    "ui.no_regions": ("Inga regionmanifest hittades.", "Ingen regionmanifest ble funnet.", "Ingen regionmanifest blev fundet.", "No region manifests found."),
    "ui.planned": ("planerad", "planlagt", "planlagt", "planned"),
    "ui.on": ("På", "På", "Til", "On"),
    "ui.return": ("Till SpeedLocal-översikten", "Til SpeedLocal-oversikten", "Til SpeedLocal-oversigten", "Back to the SpeedLocal overview"),
    "ui.wind": ("Vind", "Vind", "Vind", "Wind"),
    "ui.solar": ("Sol", "Sol", "Sol", "Solar"),
    "ui.energy_scenario": ("Energiscenario", "Energiscenario", "Energiscenarie", "Energy scenario"),
    "ui.reset_scenario": ("Nollställ scenario", "Nullstill scenario", "Nulstil scenarie", "Reset scenario"),
    "ui.reset_rooftop": ("Nollställ taksol", "Nullstill sol på tak", "Nulstil sol på tag", "Reset rooftop solar"),
    "ui.use_mix": ("Använd energimix", "Bruk energimiks", "Anvend energimix", "Apply energy mix"),
    "ui.wind_percent": ("Vindandel (%)", "Vindandel (%)", "Vindandel (%)", "Wind share (%)"),
    "guide.show": ("Visa guide", "Vis veiledning", "Vis guide", "Show guide"),
    "guide.help": ("Öppna en kort genomgång av arbetsytan.", "Åpne en kort gjennomgang av arbeidsflaten.", "Åbn en kort gennemgang af arbejdsfladen.", "Open a short walkthrough of the workspace."),
    "guide.previous": ("Föregående", "Forrige", "Forrige", "Previous"),
    "guide.next": ("Nästa", "Neste", "Næste", "Next"),
    "guide.skip": ("Hoppa över", "Hopp over", "Spring over", "Skip"),
    "guide.pause": ("Pausa", "Pause", "Pause", "Pause"),
    "guide.resume": ("Fortsätt guide", "Fortsett veiledning", "Fortsæt guide", "Resume guide"),
    "guide.try": ("Testa detta", "Prøv dette", "Prøv dette", "Try this"),
    "guide.complete": ("Klart", "Ferdig", "Færdigt", "Done"),
    "guide.close": ("Stäng", "Lukk", "Luk", "Close"),
    "guide.done": ("Klar", "Ferdig", "Færdig", "Done"),
    "guide.no_auto": ("Öppna inte automatiskt igen", "Ikke åpne automatisk igjen", "Åbn ikke automatisk igen", "Do not open automatically again"),
}

MESSAGES.update({
    "result.energy_intro": ("Scenariot motsvarar {p0:.2f} TWh", "Scenarioet tilsvarer {p0:.2f} TWh", "Scenariet svarer til {p0:.2f} TWh", "The scenario represents {p0:.2f} TWh"),
    "result.capacity_intro": ("Scenariot omfattar {p0:.2f} MW installerad effekt", "Scenarioet omfatter {p0:.2f} MW installert effekt", "Scenariet omfatter {p0:.2f} MW installeret effekt", "The scenario includes {p0:.2f} MW installed power"),
    "scenario.energy_option": ("{p0} · {p1:g}× energi", "{p0} · {p1:g}× energi", "{p0} · {p1:g}× energi", "{p0} · {p1:g}× energy"),
    "scenario.land_intensity": ("Markintensitet", "Arealintensitet", "Arealintensitet", "Land intensity"),
    "ui.panel_width_help": ("0% gör panelen minimal. 100% ger nästan hela arbetsytan till panelen.", "0% gjør panelet minimalt. 100% gir nesten hele arbeidsflaten til panelet.", "0% gør panelet minimalt. 100% giver næsten hele arbejdsfladen til panelet.", "0% minimizes the panel. 100% gives almost the entire workspace to the panel."),
    "ui.step": ("Steg", "Trinn", "Trin", "Step"),
    "ui.of": ("av", "av", "af", "of"),
    "ui.population_settlement": ("Befolkning och bebyggelse", "Befolkning og bebyggelse", "Befolkning og bebyggelse", "Population and settlement"),
    "solar.coast_precaution": ("Strandskydd och kustzon kan användas som ett försiktigt kustnära avdrag.", "Strandvern og kystsone kan brukes som et forsiktig kystnært fradrag.", "Strandbeskyttelse og kystzone kan bruges som et forsigtigt kystnært fradrag.", "Shore protection and the coastal zone can provide a precautionary coastal exclusion."),
    "review.source_unavailable": ("Källvisning saknar ett komplett manifestdeklarerat vektorkontrakt.", "Kildevisning mangler en komplett manifestdeklarert vektorkontrakt.", "Kildevisning mangler en komplet manifestdeklareret vektorkontrakt.", "Source display has no complete manifest-declared vector contract."),
    "review.buffer_unavailable": ("Buffertvisning saknar ett komplett manifestdeklarerat vektorkontrakt.", "Buffervisning mangler en komplett manifestdeklarert vektorkontrakt.", "Buffervisning mangler en komplet manifestdeklareret vektorkontrakt.", "Buffer display has no complete manifest-declared vector contract."),
    "review.complete_steps": ("För att slutföra den tekniska granskningen, tillämpa: {p0}.", "For å fullføre den tekniske granskingen, bruk: {p0}.", "For at afslutte den tekniske granskning, anvend: {p0}.", "To complete the technical review, apply: {p0}."),
    "review.result_applied": ("Steg 3 av 3: {p0} har tillämpats. Resultatet är tekniskt och inte regional lämplighet.", "Trinn 3 av 3: {p0} er anvendt. Resultatet er teknisk og viser ikke regional egnethet.", "Trin 3 af 3: {p0} er anvendt. Resultatet er teknisk og viser ikke regional egnethed.", "Step 3 of 3: {p0} has been applied. The result is technical and does not represent regional suitability."),
    "review.full_domain": ("{p0}: inga aktiva filter (hela analysdomänen)", "{p0}: ingen aktive filtre (hele analysedomenet)", "{p0}: ingen aktive filtre (hele analysedomænet)", "{p0}: no active filters (full analysis domain)"),
    "result.solar_population_sources": ("Sol: Befolkning använder {p0} källager med {p1:.0f} m buffert/avstånd{p2}.", "Sol: Befolkning bruker {p0} kildelag med {p1:.0f} m buffer/avstand{p2}.", "Sol: Befolkning bruger {p0} kildelag med {p1:.0f} m buffer/afstand{p2}.", "Solar: Population uses {p0} source layers with {p1:.0f} m buffer/distance{p2}."),
    "table.analysis": ("Analys", "Analyse", "Analyse", "Analysis"),
    "table.measure": ("Mått", "Mål", "Mål", "Measure"),
    "table.category": ("kategori", "kategori", "kategori", "category"),
    "table.equivalent": ("motsvarar", "tilsvarer", "svarer til", "equivalent"),
    "table.step": ("steg", "trinn", "trin", "step"),
    "table.detail": ("detalj", "detalj", "detalje", "detail"),
    "result.yellow": ("gula", "gule", "gule", "yellow"),
    "result.area_demand_value": ("{p0} ytbehov", "{p0} arealbehov", "{p0} arealbehov", "{p0} area demand"),
    "hex.selected_resolution": ("vald H3", "valgt H3", "valgt H3", "selected H3"),
    "shortage.none": ("Inga bristhex", "Ingen underskuddshex", "Ingen underskudshex", "No shortage hexes"),
    "shortage.wind": ("Vind behöver yta", "Vind trenger areal", "Vind kræver areal", "Wind needs area"),
    "shortage.solar": ("Sol behöver yta", "Sol trenger areal", "Sol kræver areal", "Solar needs area"),
    "shortage.area_outside": ("{p0} utanför landskapets potential", "{p0} utenfor landskapets potensial", "{p0} uden for landskabets potentiale", "{p0} outside landscape potential"),
    "shortage.schematic": ("Samma ytbudget visas schematiskt i separata fält utanför regionen, inte som faktisk placering.", "Samme arealbudsjett vises skjematisk i separate felt utenfor regionen, ikke som faktisk plassering.", "Samme arealbudget vises skematisk i separate felter uden for regionen, ikke som faktisk placering.", "The same area budget is shown schematically in separate fields outside the region, not as actual placement."),
    "shortage.symbols": ("Unika ytbehovshex: {p0}. Både vind och sol i samma hex: {p1}. 1 symbol ≈ {p2} hex.", "Unike arealbehovshex: {p0}. Både vind og sol i samme hex: {p1}. 1 symbol ≈ {p2} hex.", "Unikke arealbehovshex: {p0}. Både vind og sol i samme hex: {p1}. 1 symbol ≈ {p2} hex.", "Unique area-demand hexes: {p0}. Both wind and solar in the same hex: {p1}. 1 symbol ≈ {p2} hexes."),
    "reason.language": ("språk", "språk", "sprog", "language"),
    "reason.display": ("visning", "visning", "visning", "display"),
    "map.note_title": ("Gemensam potentialvy", "Felles potensialvisning", "Fælles potentialevisning", "Shared potential view"),
    "map.note_body": ("Kartan visar möjlig etableringsyta och scenarioyta inom potentialen utifrån nuvarande val.", "Kartet viser mulig etableringsareal og scenarioareal innenfor potensialet ut fra gjeldende valg.", "Kortet viser muligt etableringsareal og scenarieareal inden for potentialet ud fra de aktuelle valg.", "The map shows possible establishment area and scenario area within the potential based on current selections."),
    "map.note_empty": ("Kartan uppdateras när minst ett potentiallager är aktivt.", "Kartet oppdateres når minst ett potensiallag er aktivt.", "Kortet opdateres, når mindst ét potentialelag er aktivt.", "The map updates when at least one potential layer is active."),
    "map.warning_label": ("Varning:", "Advarsel:", "Advarsel:", "Warning:"),
    "map.shortage_note": ("Vald mix ryms inte helt: ytbehov utanför potential {area} ({parts}).", "Valgt miks passer ikke helt: arealbehov utenfor potensialet {area} ({parts}).", "Den valgte blanding passer ikke helt: arealbehov uden for potentialet {area} ({parts}).", "The selected mix does not fit completely: area demand outside the potential {area} ({parts})."),
    "map.note_wind_part": ("vind {area} km²", "vind {area} km²", "vind {area} km²", "wind {area} km²"),
    "map.note_solar_part": ("sol {area} km²", "sol {area} km²", "sol {area} km²", "solar {area} km²"),
    "debug.visible_initially": ("visas från start", "vises fra start", "vises fra start", "shown initially"),
    "debug.hidden_initially": ("finns i lagerkontrollen men är släckt från start", "finnes i lagkontrollen, men er slått av fra start", "findes i lagkontrollen, men er slået fra fra start", "available in the layer control but initially hidden"),
    "debug.selected_scenario": ("valt scenario", "valgt scenario", "valgt scenarie", "selected scenario"),
    "result.new_delta": ("+nytt", "+nytt", "+nyt", "+new"),
    "result.new_badge": ("nytt", "nytt", "nyt", "new"),
    "ui.level_middle": ("Mellan", "Middels", "Middel", "Medium"),
    "form.source_name": ("Datakälla: {p0}.", "Datakilde: {p0}.", "Datakilde: {p0}.", "Data source: {p0}."),
    "form.no_automatic_source": ("Ingen datakälla väljs automatiskt. Öppna Datakällor och välj minst en datakälla tillsammans med gruppen innan du använder ändringarna.", "Ingen datakilde velges automatisk. Åpne Datakilder og velg minst én datakilde sammen med gruppen før du bruker endringene.", "Ingen datakilde vælges automatisk. Åbn Datakilder og vælg mindst én datakilde sammen med gruppen, før du anvender ændringerne.", "No data source is selected automatically. Open Data sources and select at least one source along with the group before applying changes."),
    "form.default_source_unavailable": ("Ingen ordinarie datakälla är tillgänglig. Här kan du granska de källor som är kopplade till gruppen.", "Ingen vanlig datakilde er tilgjengelig. Her kan du granske kildene som er knyttet til gruppen.", "Ingen normal datakilde er tilgængelig. Her kan du granske de kilder, der er knyttet til gruppen.", "No default data source is available. Review the sources associated with the group here."),
    "form.default_source": ("Ordinarie datakälla: {p0}. Här kan du granska eller ändra urvalet.", "Vanlig datakilde: {p0}. Her kan du granske eller endre utvalget.", "Normal datakilde: {p0}. Her kan du granske eller ændre udvalget.", "Default data source: {p0}. Review or change the selection here."),
    "form.default_sources": ("Ordinarie datakällor: {p0}. Här kan du granska eller ändra urvalet.", "Vanlige datakilder: {p0}. Her kan du granske eller endre utvalget.", "Normale datakilder: {p0}. Her kan du granske eller ændre udvalget.", "Default data sources: {p0}. Review or change the selection here."),
    "form.join_sources": ("{p0} och {p1}", "{p0} og {p1}", "{p0} og {p1}", "{p0} and {p1}"),
    "loading.statistics": ("Etableringsstatistik", "Etableringsstatistikk", "Etableringsstatistik", "Establishment statistics"),
    "loading.historical_duration": ("Historik: brukar ta ca {p0:.1f} s för kända steg.", "Historikk: tar vanligvis ca. {p0:.1f} s for kjente trinn.", "Historik: tager normalt ca. {p0:.1f} s for kendte trin.", "History: known steps usually take about {p0:.1f} s."),
    "loading.start_steps": ("0/{p0} steg klara. {p1}", "0/{p0} trinn fullført. {p1}", "0/{p0} trin afsluttet. {p1}", "0/{p0} steps complete. {p1}"),
    "loading.progress_steps": ("{p0}/{p1} steg klara: {p2} ({p3:.1f} s). {p4}", "{p0}/{p1} trinn fullført: {p2} ({p3:.1f} s). {p4}", "{p0}/{p1} trin afsluttet: {p2} ({p3:.1f} s). {p4}", "{p0}/{p1} steps complete: {p2} ({p3:.1f} s). {p4}"),
    "loading.status_steps": ("Beräknar karta och potential... {p0}/{p1} steg klara", "Beregner kart og potensial... {p0}/{p1} trinn fullført", "Beregner kort og potentiale... {p0}/{p1} trin afsluttet", "Calculating map and potential... {p0}/{p1} steps complete"),
    "loading.longest_step": (" Längsta steg: {p0} {p1:.1f} s.", " Lengste trinn: {p0} {p1:.1f} s.", " Længste trin: {p0} {p1:.1f} s.", " Longest step: {p0} {p1:.1f} s."),
    "loading.finished": ("Klart på {p0:.1f} s.{p1}", "Ferdig på {p0:.1f} s.{p1}", "Afsluttet på {p0:.1f} s.{p1}", "Completed in {p0:.1f} s.{p1}"),
    "loading.status_finished": ("Beräkning klar på {p0:.1f} s", "Beregning ferdig på {p0:.1f} s", "Beregning afsluttet på {p0:.1f} s", "Calculation completed in {p0:.1f} s"),
    "status.public": ("Publik", "Offentlig", "Offentlig", "Public"),
    "table.h3_cell": ("H3-cell", "H3-celle", "H3-celle", "H3 cell"),
    "table.minimum_distance": ("Minsta avstånd (m)", "Minste avstand (m)", "Mindste afstand (m)", "Minimum distance (m)"),
    "table.intersection": ("Skärning", "Skjæring", "Skæring", "Intersection"),
    "table.rejected": ("Avvisad", "Avvist", "Afvist", "Rejected"),
    "table.rule_acceptance": ("Godkännande", "Regelgodkjenning", "Regelgodkendelse", "Rule acceptance"),
    "table.model_area": ("Modellareal (km²)", "Modellareal (km²)", "Modelareal (km²)", "Model area (km²)"),
    "table.remaining_area": ("Återstående areal (km²)", "Gjenværende areal (km²)", "Resterende areal (km²)", "Remaining area (km²)"),
    "table.potential_percent": ("Potential (%)", "Potensial (%)", "Potentiale (%)", "Potential (%)"),
    "table.cells": ("Celler", "Celler", "Celler", "Cells"),
    "table.rejected_cells": ("Avvisade celler", "Avviste celler", "Afviste celler", "Rejected cells"),
    "table.accepted_cells": ("Godkända celler", "Godkjente celler", "Godkendte celler", "Accepted cells"),
    "table.missing_cells": ("Celler med saknad täckning", "Celler med manglende dekning", "Celler med manglende dækning", "Cells with missing coverage"),
    "table.mean_rule_acceptance": ("Genomsnittligt godkännande", "Gjennomsnittlig regelgodkjenning", "Gennemsnitlig regelgodkendelse", "Mean rule acceptance"),
    "table.threshold": ("Gräns (m)", "Grense (m)", "Grænse (m)", "Threshold (m)"),
    "debug.note_01": ("{p0} visas som separata gula schablonhexar för att inte läsas som sammanhängande markyta.", "{p0} vises som separate gule estimathex for å unngå at de tolkes som sammenhengende landareal.", "{p0} vises som separate gule estimathex for at undgå, at de tolkes som sammenhængende landareal.", "{p0} is shown as separate yellow schematic hexes so it is not interpreted as contiguous land area."),
    "debug.note_02": ("Vindens interna hexberäkning används för att prioritera kärnområden i den gemensamma etableringsytan.", "Vindens interne hexberegning brukes til å prioritere kjerneområder i det felles etableringsarealet.", "Vindens interne hexberegning bruges til at prioritere kerneområder i det fælles etableringsareal.", "The internal wind hex calculation prioritizes core areas in the shared establishment area."),
    "debug.note_03": ("Det sociala acceptanslagret visar den tillämpade resultatkällans tillitsstatus och är inte regional acceptansevidens när källan är provisorisk.", "Laget for sosial aksept viser tillitsstatusen til den anvendte resultatkilden og er ikke regionalt kunnskapsgrunnlag om aksept når kilden er foreløpig.", "Laget for social accept viser tillidsstatus for den anvendte resultatkilde og er ikke regional dokumentation for accept, når kilden er foreløbig.", "The social acceptance layer shows the applied result source's trust status and is not regional acceptance evidence when the source is provisional."),
    "debug.note_04": ("Startläge: {p0} är ofiltrerad över kartans landskapsunderlag för att visa gemensam sol- och vindpotential.", "Utgangspunkt: {p0} er ufiltrert over kartets landskapsdata for å vise felles sol- og vindpotensial.", "Udgangspunkt: {p0} er ufiltreret over kortets landskabsdata for at vise fælles sol- og vindpotentiale.", "Starting point: {p0} is unfiltered across the map's landscape inputs to show shared solar and wind potential."),
    "debug.note_05": ("{p0} använder hela landskapsunderlaget som kandidatbas. Aktiva filter drar bort yta från den basen.", "{p0} bruker hele landskapsdatagrunnlaget som kandidatgrunnlag. Aktive filtre trekker areal fra dette grunnlaget.", "{p0} bruger hele landskabsdatagrundlaget som kandidatgrundlag. Aktive filtre trækker areal fra dette grundlag.", "{p0} uses the complete landscape inputs as the candidate baseline. Active filters exclude area from that baseline."),
    "debug.note_06": ("Befolkningsgruppen tar bort potential inom {p0:.0f} m från {p1} källager.", "Befolkningsgruppen fjerner potensial innenfor {p0:.0f} m fra {p1} kildelag.", "Befolkningsgruppen fjerner potentiale inden for {p0:.0f} m fra {p1} kildelag.", "The population group excludes potential within {p0:.0f} m of {p1} source layers."),
    "debug.note_07": ("{p0}: ändringar tillämpade.", "{p0}: endringer anvendt.", "{p0}: ændringer anvendt.", "{p0}: changes applied."),
    "debug.note_08": ("{p0} beräknas i R{p1}. Hexvisningen är zoomanpassad för granskning.", "{p0} beregnes i R{p1}. Hexvisningen er zoomtilpasset for gransking.", "{p0} beregnes i R{p1}. Hexvisningen er zoomtilpasset til granskning.", "{p0} is calculated at R{p1}. Hex display adapts to zoom for review."),
    "debug.note_09": ("{p0} beräknas i R{p1}. Kartan visar vald H3-upplösning.", "{p0} beregnes i R{p1}. Kartet viser valgt H3-oppløsning.", "{p0} beregnes i R{p1}. Kortet viser valgt H3-opløsning.", "{p0} is calculated at R{p1}. The map shows the selected H3 resolution."),
    "debug.note_10": ("{p0} visar potential efter aktiva filter: blå = vind, gul = sol, grön = båda, röd = inte lämplig.", "{p0} viser potensial etter aktive filtre: blå = vind, gul = sol, grønn = begge, rød = ikke egnet.", "{p0} viser potentiale efter aktive filtre: blå = vind, gul = sol, grøn = begge, rød = ikke egnet.", "{p0} shows potential after active filters: blue = wind, yellow = solar, green = both, red = not suitable."),
    "debug.note_11": ('{p0} {p1} för {p2}. Lagret visar scenariots placering som teknikfärgade kartceller: blå markerar vind, gulorange markerar sol och mörkgrön markerar båda i samma visningshex utan att påstå exakt fysisk överlappning.', '{p0} {p1} for {p2}. Laget viser scenarioets plassering som teknologifargede kartceller: blå markerer vind, guloransje markerer sol, og mørkegrønn markerer begge i samme visningshex uten å hevde nøyaktig fysisk overlapping.', '{p0} {p1} for {p2}. Laget viser scenariets placering som teknologifarvede kortceller: blå markerer vind, gulorange markerer sol, og mørkegrøn markerer begge i samme visningshex uden at hævde præcis fysisk overlapning.', '{p0} is {p1} for {p2}. The layer shows scenario placement as technology-coloured map cells: blue indicates wind, yellow-orange indicates solar, and dark green indicates both in the same display hex without claiming exact physical overlap.'),
    "debug.note_12": ("{p0} visas som separata schematiska jämförelseytor utanför regionen när scenariot inte ryms inom landskapets potential.", "{p0} vises som separate skjematiske sammenligningsarealer utenfor regionen når scenarioet ikke får plass innenfor landskapets potensial.", "{p0} vises som separate skematiske sammenligningsarealer uden for regionen, når scenariet ikke kan rummes inden for landskabets potentiale.", "{p0} is shown as separate schematic comparison areas outside the region when the scenario does not fit within landscape potential."),
    "debug.note_13": ("Teknikdomänen i R{p0} går ända till den verifierade regionsgränsen. {p1} celler har kompletterande landskapskontext och {p2} celler ({p3:.3f} km²) saknar teknisk landskapskontext. Den separata kartan med landskapstyper kan ha annan täckning. Standardtabeller och femgruppsmått behåller sin deklarerade standarddomän.", "Teknologidomenet i R{p0} går helt til den verifiserte regionsgrensen. {p1} celler har supplerende landskapskontekst, og {p2} celler ({p3:.3f} km²) mangler teknisk landskapskontekst. Det separate kartet med landskapstyper kan ha en annen dekning. Standardtabeller og femgruppemål beholder sitt deklarerte standarddomene.", "Teknologidomænet i R{p0} går helt til den verificerede regionsgrænse. {p1} celler har supplerende landskabskontekst, og {p2} celler ({p3:.3f} km²) mangler teknisk landskabskontekst. Det separate kort med landskabstyper kan have en anden dækning. Standardtabeller og femgruppemål beholder deres deklarerede standarddomæne.", "The technology domain at R{p0} reaches the verified region boundary. {p1} cells have supplementary landscape context and {p2} cells ({p3:.3f} km²) lack technical landscape context. The separate landscape-type map may have different coverage. Standard tables and five-group measures retain their declared standard domain."),
    "debug.note_14": ("{p0}{p1} begränsar solpotentialen till yta inom {p2:.0f} m från nätobjekt.", "{p0}{p1} begrenser solpotensialet til areal innenfor {p2:.0f} m fra nettobjekter.", "{p0}{p1} begrænser solpotentialet til areal inden for {p2:.0f} m fra netobjekter.", "{p0}{p1} limits solar potential to area within {p2:.0f} m of grid features."),
    "debug.note_15": ("{p0}{p1} drar av potential med {p2:.0f} m buffert.", "{p0}{p1} trekker fra potensial med {p2:.0f} m buffer.", "{p0}{p1} trækker potentiale fra med {p2:.0f} m buffer.", "{p0}{p1} excludes potential with a {p2:.0f} m buffer."),
    "debug.note_16": ("Solens scenarioyta använder en intern landskaps-/teknikranking inom etableringshex; placeringen visas med potentiallagrets hexagoner.", "Solens scenarioareal bruker en intern landskaps-/teknologirangering innenfor etableringshex; plasseringen vises med potensiallagets heksagoner.", "Solens scenarieareal bruger en intern landskabs-/teknologirangering inden for etableringshex; placeringen vises med potentialelagets hexagoner.", "Solar scenario area uses an internal landscape/technology ranking within establishment hexes; placement is shown with the potential layer hexagons."),
    "debug.note_17": ("Inom landskapspotentialen använder vindens scenarioyta en intern landskaps-/teknikranking och kan välja starka vindlägen även när sol redan valt samma hex; separata ytor vinner där vid lika lämplighet. Vid expansion utanför landskapspotentialen prioriteras i stället celler som sol inte reserverat, följt av närmaste expansionsring och vindrankingen.", "Innenfor landskapspotensialet bruker vindens scenarioareal en intern landskaps-/teknologirangering og kan velge sterke vindlokasjoner selv om sol allerede har valgt samme hex; separate arealer vinner da ved lik egnethet. Ved utvidelse utenfor landskapspotensialet prioriteres i stedet celler som sol ikke har reservert, etterfulgt av nærmeste utvidelsesring og vindrangeringen.", "Inden for landskabspotentialet bruger vindens scenarieareal en intern landskabs-/teknologirangering og kan vælge stærke vindlokationer, selv om sol allerede har valgt samme hex; separate arealer vinder da ved lige egnethed. Ved udvidelse uden for landskabspotentialet prioriteres i stedet celler, som sol ikke har reserveret, efterfulgt af nærmeste udvidelsesring og vindrangeringen.", "Within landscape potential, wind scenario area uses an internal landscape/technology ranking and may select strong wind locations even when solar has already selected the same hex; separate areas win ties in suitability. Expansion outside landscape potential instead prioritizes cells not reserved by solar, followed by the nearest expansion ring and wind ranking."),
    "debug.note_18": ("Vind- och solberäkningarna presenteras gemensamt genom {p0}, som {p1}.", "Vind- og solberegningene presenteres samlet gjennom {p0}, som {p1}.", "Vind- og solberegningerne præsenteres samlet gennem {p0}, som {p1}.", "Wind and solar calculations are presented together through {p0}, which is {p1}."),
    "debug.note_19": ("Acceptanspåverkan {p0:.0f}% tonar samma etableringsyta mot rött där syntetisk social acceptans är låg.", "Akseptpåvirkning {p0:.0f}% toner samme etableringsareal mot rødt der syntetisk sosial aksept er lav.", "Acceptpåvirkning {p0:.0f}% toner samme etableringsareal mod rødt, hvor syntetisk social accept er lav.", "Acceptance influence {p0:.0f}% tints the same establishment area towards red where synthetic social acceptance is low."),
    "debug.note_20": ("Acceptansstyrning {p0:.0f}% prioriterar scenarioytan inom potentialen där syntetisk social acceptans är hög.", "Akseptstyring {p0:.0f}% prioriterer scenarioarealet innenfor potensialet der syntetisk sosial aksept er høy.", "Acceptstyring {p0:.0f}% prioriterer scenariearealet inden for potentialet, hvor syntetisk social accept er høj.", "Acceptance influence {p0:.0f}% prioritizes scenario area within the potential where synthetic social acceptance is high."),
    "debug.note_21": ("Energimodelleringen hittade inga vindceller som uppfyller minsta kärn-/potentialkrav.", "Energimodelleringen fant ingen vindceller som oppfyller minstekrav til kjerne/potensial.", "Energimodelleringen fandt ingen vindceller, som opfylder minimumskrav til kerne/potentiale.", "Energy modelling found no wind cells meeting minimum core/potential requirements."),
    "debug.rooftop_missing": ("Manifeststyrt befolkningsunderlag saknas: {p0}", "Manifeststyrte befolkningsdata mangler: {p0}", "Manifeststyrede befolkningsdata mangler: {p0}", "Manifest-driven population inputs are missing: {p0}"),
    "debug.rooftop_source": ("Befolkningsunderlag: {p0} på H3 R{p1}, aggregerat direkt till R{p2}. Energibokföringen använder källtotalen {p3:,.0f} personer; kartschablonen visar {p4:,.0f} inom analysdomänen ({p5:,.0f} ligger utanför kartdomänen).", "Befolkningsdata: {p0} på H3 R{p1}, aggregert direkte til R{p2}. Energibokføringen bruker kildetotalen {p3:,.0f} personer; kartestimatet viser {p4:,.0f} innenfor analysedomenet ({p5:,.0f} ligger utenfor kartdomenet).", "Befolkningsdata: {p0} på H3 R{p1}, aggregeret direkte til R{p2}. Energibogføringen bruger kildetotalen {p3:,.0f} personer; kortestimatet viser {p4:,.0f} inden for analysedomænet ({p5:,.0f} ligger uden for kortdomænet).", "Population inputs: {p0} at H3 R{p1}, aggregated directly to R{p2}. Energy accounting uses the source total of {p3:,.0f} people; the map estimate shows {p4:,.0f} within the analysis domain ({p5:,.0f} are outside the map domain)."),
    "debug.rooftop_formula": ("Småskalig taksol beräknas från det manifestdeklarerade befolkningsunderlaget × {p0:.0f} m2 panelyta/person.", "Småskala sol på tak beregnes fra de manifestdeklarerte befolkningsdataene × {p0:.0f} m2 panelareal/person.", "Småskala sol på tag beregnes fra de manifestdeklarerede befolkningsdata × {p0:.0f} m2 panelareal/person.", "Small-scale rooftop solar is calculated from manifest-declared population inputs × {p0:.0f} m2 panel area/person."),
    "result.area_overview": ("{p0} och ger ett teknikspecifikt ytanspråk på {p1}. Efter geografiska filter finns {p2} möjlig etableringsyta som tekniksumma (vindpotential + solpotential). Det är alltså inte unik fysisk markyta: samma hex kan räknas en gång för vind och en gång för sol när teknikerna kan samnyttja ytan. Efter eventuell social acceptanspåverkan är motsvarande tekniksumma {p3}. Av ytanspråket placeras {p4} inom potentialområdet, vilket motsvarar {p5:.1f}% av behovet. {p6} När scenariot är placerat återstår {p7} outnyttjad teknikpotential.", "{p0} og gir et teknologispesifikt arealbehov på {p1}. Etter geografiske filtre finnes {p2} mulig etableringsareal som teknologisum (vindpotensial + solpotensial). Dette er derfor ikke unikt fysisk landareal: samme hex kan telles én gang for vind og én gang for sol når teknologiene kan dele arealet. Etter eventuell påvirkning fra sosial aksept er tilsvarende teknologisum {p3}. Av arealbehovet plasseres {p4} innenfor potensialområdet, som tilsvarer {p5:.1f}% av behovet. {p6} Når scenarioet er plassert, gjenstår {p7} uutnyttet teknologipotensial.", "{p0} og giver et teknologispecifikt arealbehov på {p1}. Efter geografiske filtre findes {p2} muligt etableringsareal som teknologisum (vindpotentiale + solpotentiale). Det er derfor ikke unikt fysisk landareal: samme hex kan tælles én gang for vind og én gang for sol, når teknologierne kan dele arealet. Efter eventuel påvirkning fra social accept er den tilsvarende teknologisum {p3}. Af arealbehovet placeres {p4} inden for potentialeområdet, svarende til {p5:.1f}% af behovet. {p6} Når scenariet er placeret, er der {p7} uudnyttet teknologipotentiale tilbage.", "{p0} and creates technology-specific area demand of {p1}. After geographic filters, {p2} of possible establishment area remains as a technology sum (wind potential + solar potential). This is not unique physical land: the same hex may count once for wind and once for solar when the technologies can share area. After any social acceptance influence, the corresponding technology sum is {p3}. Of the area demand, {p4} is allocated within the potential area, representing {p5:.1f}% of demand. {p6} After allocating the scenario, {p7} of unused technology potential remains."),
    "result.outside_note": ("{p0} behöver hanteras utanför potentialområdet.", "{p0} må håndteres utenfor potensialområdet.", "{p0} skal håndteres uden for potentialeområdet.", "{p0} must be handled outside the potential area."),
    "result.no_outside": ("Ingen yta behöver lösas utanför potentialområdet.", "Ingen areal må løses utenfor potensialområdet.", "Intet areal skal løses uden for potentialeområdet.", "No area needs to be met outside the potential area."),
    "result.rooftop_accounting": (" Av solmålets {p0:.2f} TWh bokförs {p1:.2f} TWh som manifeststyrd taksolschablon och {p2:.2f} TWh återstår för marksol.", " Av solmålets {p0:.2f} TWh bokføres {p1:.2f} TWh som manifeststyrt taksolestimat og {p2:.2f} TWh gjenstår for sol på bakken.", " Af solmålets {p0:.2f} TWh bogføres {p1:.2f} TWh som manifeststyret tag-solestimat, og {p2:.2f} TWh er tilbage for sol på land.", " Of the solar target's {p0:.2f} TWh, {p1:.2f} TWh is accounted for as a manifest-driven rooftop solar estimate and {p2:.2f} TWh remains for ground-mounted solar."),
    "result.source_summary": ("Datakälla: {p0} · status {p1} · syntetisk: {p2} · regionalt accepterad: {p3}.", "Datakilde: {p0} · status {p1} · syntetisk: {p2} · regionalt akseptert: {p3}.", "Datakilde: {p0} · status {p1} · syntetisk: {p2} · regionalt accepteret: {p3}.", "Data source: {p0} · status {p1} · synthetic: {p2} · regionally accepted: {p3}."),
    "result.technology": ("teknik", "teknologi", "teknologi", "technology"),
    "result.energy": ("energi", "energi", "energi", "energy"),
    "result.capacity": ("kapacitet", "kapasitet", "kapacitet", "capacity"),
    "result.potential_filtered": ("potential efter filter", "potensial etter filtre", "potentiale efter filtre", "potential after filters"),
    "result.potential_acceptance": ("potential efter acceptanspåverkan", "potensial etter akseptpåvirkning", "potentiale efter acceptpåvirkning", "potential after acceptance influence"),
    "result.within": ("inom potential", "innenfor potensial", "inden for potentiale", "within potential"),
    "result.unused": ("outnyttjad potential", "uutnyttet potensial", "uudnyttet potentiale", "unused potential"),
    "result.outside": ("ytbehov utanför potential", "arealbehov utenfor potensial", "arealbehov uden for potentiale", "area demand outside potential"),
    "result.within_share": ("andel inom potential", "andel innenfor potensial", "andel inden for potentiale", "share within potential"),
    "result.outside_value": ("Utanför potential: {p0}", "Utenfor potensial: {p0}", "Uden for potentiale: {p0}", "Outside potential: {p0}"),
    "result.class": ("klass", "klasse", "klasse", "class"),
    "result.area": ("yta", "areal", "areal", "area"),
    "result.share": ("andel", "andel", "andel", "share"),
    "result.hex": ("hex", "hex", "hex", "hex"),
    "result.low_threshold": ("Låg < {p0:.1f}", "Lav < {p0:.1f}", "Lav < {p0:.1f}", "Low < {p0:.1f}"),
    "result.high_threshold": ("Hög ≥ {p0:.1f}", "Høy ≥ {p0:.1f}", "Høj ≥ {p0:.1f}", "High ≥ {p0:.1f}"),
    "result.missing_zero": ("bidrar med noll till den acceptansjusterade potentialen", "bidrar med null til det akseptjusterte potensialet", "bidrager med nul til det acceptjusterede potentiale", "contribute zero to the acceptance-adjusted potential"),
    "result.missing_retained": ("behåller sin potential eftersom acceptanspåverkan är 0%", "beholder sitt potensial fordi akseptpåvirkningen er 0%", "beholder deres potentiale, fordi acceptpåvirkningen er 0%", "retain their potential because acceptance influence is 0%"),
    "result.scenario_cells": ("Scenario: {p0}. Beräknas på {p1:,} av {p2:,} potentiella etableringshex.", "Scenario: {p0}. Beregnes på {p1:,} av {p2:,} potensielle etableringshex.", "Scenarie: {p0}. Beregnes på {p1:,} af {p2:,} potentielle etableringshex.", "Scenario: {p0}. Calculated on {p1:,} of {p2:,} potential establishment hexes."),
    "result.unknown": ("okänd", "ukjent", "ukendt", "unknown"),
    "result.acceptance_missing": ("Acceptansdata saknas för {p0:,} potentiella hex ({p1:.3f} km²). De förblir okända och {p2}.", "Akseptdata mangler for {p0:,} potensielle hex ({p1:.3f} km²). De forblir ukjente og {p2}.", "Acceptdata mangler for {p0:,} potentielle hex ({p1:.3f} km²). De forbliver ukendte og {p2}.", "Acceptance data is missing for {p0:,} potential hexes ({p1:.3f} km²). They remain unknown and {p2}."),
    "result.hex_count": ("antal hex", "antall hex", "antal hex", "hex count"),
    "result.schematic_budget": ("Schematiska ytbudgethex", "Skjematiske arealbudsjetthex", "Skematiske arealbudgethex", "Schematic area-budget hexes"),
    "result.red_hex": ("Röda hex i etableringslagret", "Røde hex i etableringslaget", "Røde hex i etableringslaget", "Red hexes in the establishment layer"),
    "result.only_wind_hex": ("Potentialhex: endast vind", "Potensialhex: bare vind", "Potentialehex: kun vind", "Potential hexes: wind only"),
    "result.potential_class": ("synlig potentialklass", "synlig potensialklasse", "synlig potentialeklasse", "visible potential class"),
    "result.only_solar_hex": ("Potentialhex: endast sol", "Potensialhex: bare sol", "Potentialehex: kun sol", "Potential hexes: solar only"),
    "result.both_hex": ("Potentialhex: vind och sol", "Potensialhex: vind og sol", "Potentialehex: vind og sol", "Potential hexes: wind and solar"),
    "result.total_hex": ("Totalt antal H3-hex", "Samlet antall H3-hex", "Samlet antal H3-hex", "Total H3 hex count"),
    "result.planning_proxy": ("Planeringsproxy: {p0:,.0f} personer i källtotalen, {p1:.0f} m² panelyta/person och {p2:.1f} kWh/m²/år.", "Planleggingsproxy: {p0:,.0f} personer i kildetotalen, {p1:.0f} m² panelareal/person og {p2:.1f} kWh/m²/år.", "Planlægningsproxy: {p0:,.0f} personer i kildetotalen, {p1:.0f} m² panelareal/person og {p2:.1f} kWh/m²/år.", "Planning proxy: {p0:,.0f} people in the source total, {p1:.0f} m² panel area/person and {p2:.1f} kWh/m²/year."),
    "result.wind_selection": ("Vindurvalet innehåller {p0:.2f} km² potentiell yta inom {p1:.2f} km² hexavtryck. Valbara LP-hex: {p2:,} med {p3:.2f} km² potentiell yta; medelandel i urvalet {p4:.1f}%.", "Vindutvalget inneholder {p0:.2f} km² potensielt areal innenfor {p1:.2f} km² hexavtrykk. Valgbare LP-hex: {p2:,} med {p3:.2f} km² potensielt areal; gjennomsnittlig andel i utvalget {p4:.1f}%.", "Vindudvalget indeholder {p0:.2f} km² potentielt areal inden for {p1:.2f} km² hexaftryk. Valgbare LP-hex: {p2:,} med {p3:.2f} km² potentielt areal; gennemsnitlig andel i udvalget {p4:.1f}%.", "The wind selection contains {p0:.2f} km² of potential area within a {p1:.2f} km² hex footprint. Selectable LP hexes: {p2:,} with {p3:.2f} km² of potential area; mean share in the selection {p4:.1f}%."),
    "result.selection_order": ("Urvalsordning: först kärn-LP med LP ≥ {p0:.0f}% ({p1:,}/{p2:,} valda), sedan kompletterande LP ({p3:,}/{p4:,} valda).", "Utvalgsrekkefølge: først kjerne-LP med LP ≥ {p0:.0f}% ({p1:,}/{p2:,} valgt), deretter supplerende LP ({p3:,}/{p4:,} valgt).", "Udvalgsrækkefølge: først kerne-LP med LP ≥ {p0:.0f}% ({p1:,}/{p2:,} valgt), derefter supplerende LP ({p3:,}/{p4:,} valgt).", "Selection order: first core LP with LP ≥ {p0:.0f}% ({p1:,}/{p2:,} selected), then supplementary LP ({p3:,}/{p4:,} selected)."),
    "result.rooftop_parameter": ("Sol: småskalig takschablon använder {p0:.0f} m² panelyta per person.", "Sol: småskala takestimat bruker {p0:.0f} m² panelareal per person.", "Sol: småskala tagestimat bruger {p0:.0f} m² panelareal per person.", "Solar: the small-scale rooftop estimate uses {p0:.0f} m² panel area per person."),
    "result.wind_open": ("Vind: inga avgränsande lager är valda, så vindpotentialen används som ett öppet startläge.", "Vind: ingen avgrensende lag er valgt, så vindpotensialet brukes som et åpent utgangspunkt.", "Vind: ingen afgrænsende lag er valgt, så vindpotentialet bruges som et åbent udgangspunkt.", "Wind: no restricting layers are selected, so wind potential is used as an open starting point."),
    "result.solar_open": ("Sol: storskalig sol använder landskapsunderlaget utan aktiva avdragsfilter.", "Sol: storskala sol bruker landskapsdataene uten aktive fradragsfiltre.", "Sol: storskala sol bruger landskabsdataene uden aktive fradragsfiltre.", "Solar: large-scale solar uses landscape inputs without active exclusion filters."),
    "result.max_distance": ("maxavstånd", "maksavstand", "maksafstand", "maximum distance"),
    "result.buffer_distance": ("buffert/avstånd", "buffer/avstand", "buffer/afstand", "buffer/distance"),
    "result.wind_filter": ("Vind: {p0} använder {p1} källager med {p2:.0f} m {p3}{p4}.", "Vind: {p0} bruker {p1} kildelag med {p2:.0f} m {p3}{p4}.", "Vind: {p0} bruger {p1} kildelag med {p2:.0f} m {p3}{p4}.", "Wind: {p0} uses {p1} source layers with {p2:.0f} m {p3}{p4}."),
    "result.solar_population_filter": ("Sol: Befolkning använder {p0} källager med {p1:.0f} m buffert/avstånd", "Sol: Befolkning bruker {p0} kildelag med {p1:.0f} m buffer/avstand", "Sol: Befolkning bruger {p0} kildelag med {p1:.0f} m buffer/afstand", "Solar: Population uses {p0} source layers with {p1:.0f} m buffer/distance"),
    "result.solar_proximity": ("Sol: {p0} kräver närhet inom {p1:.0f} m från {p2} källager{p3}.", "Sol: {p0} krever nærhet innenfor {p1:.0f} m fra {p2} kildelag{p3}.", "Sol: {p0} kræver nærhed inden for {p1:.0f} m fra {p2} kildelag{p3}.", "Solar: {p0} requires proximity within {p1:.0f} m of {p2} source layers{p3}."),
    "result.solar_exclusion": ("Sol: {p0} drar av yta med {p1:.0f} m buffert från {p2} källager{p3}.", "Sol: {p0} trekker fra areal med {p1:.0f} m buffer fra {p2} kildelag{p3}.", "Sol: {p0} trækker areal fra med {p1:.0f} m buffer fra {p2} kildelag{p3}.", "Solar: {p0} excludes area using a {p1:.0f} m buffer from {p2} source layers{p3}."),
    "result.solar_filter_effect": ("Solfiltereffekt: {p0} tas bort från den storskaliga solbasen ({p1:.1f}%).", "Solfiltereffekt: {p0} fjernes fra storskala solgrunnlag ({p1:.1f}%).", "Solfiltereffekt: {p0} fjernes fra storskala solgrundlag ({p1:.1f}%).", "Solar filter effect: {p0} is removed from the large-scale solar baseline ({p1:.1f}%)."),
    "result.solar_filter_no_effect": ("Solfilter är aktiva men tar inte bort någon mätbar yta med nuvarande inställningar.", "Solfiltre er aktive, men fjerner ikke noe målbart areal med gjeldende innstillinger.", "Solfiltre er aktive, men fjerner ikke noget målbart areal med de aktuelle indstillinger.", "Solar filters are active but remove no measurable area under the current settings."),
    "result.colour_distribution": ("Färgfördelning i kartan: {p0} av {p1} hexagoner.{p2}", "Fargefordeling i kartet: {p0} av {p1} hexagoner.{p2}", "Farvefordeling i kortet: {p0} af {p1} hexagoner.{p2}", "Map colour distribution: {p0} of {p1} hexagons.{p2}"),
    "result.green": ("gröna", "grønne", "grønne", "green"),
    "result.blue": ("blå", "blå", "blå", "blue"),
    "result.red": ("röda", "røde", "røde", "red"),
    "result.black_schematic": (" Svarta schematiska fält: {p0}.", " Svarte skjematiske felt: {p0}.", " Sorte skematiske felter: {p0}.", " Black schematic fields: {p0}."),
    "result.potential_filtered_html": ("potential<br>efter filter", "potensial<br>etter filtre", "potentiale<br>efter filtre", "potential<br>after filters"),
    "result.potential_acceptance_html": ("potential<br>efter acceptans-<br>påverkan", "potensial<br>etter aksept-<br>påvirkning", "potentiale<br>efter accept-<br>påvirkning", "potential<br>after acceptance<br>influence"),
    "result.outside_html": ("ytbehov utanför<br>potential", "arealbehov utenfor<br>potensial", "arealbehov uden for<br>potentiale", "area demand outside<br>potential"),
    "result.within_html": ("andel inom<br>potential", "andel innenfor<br>potensial", "andel inden for<br>potentiale", "share within<br>potential"),
    "result.custom_mix": ("Egen mix", "Egen miks", "Eget mix", "Custom mix"),
    "result.share_percent": ("Andel (%)", "Andel (%)", "Andel (%)", "Share (%)"),
    "result.energy_twh": ("Energi (TWh)", "Energi (TWh)", "Energi (TWh)", "Energy (TWh)"),
    "result.area_km2": ("Ytbehov (km²)", "Arealbehov (km²)", "Arealbehov (km²)", "Area demand (km²)"),
    "result.capacity_mw": ("Kapacitet (MW)", "Kapasitet (MW)", "Kapacitet (MW)", "Capacity (MW)"),
    "result.acceptance_selected": ("Valt: {p0} · bedömda celler {p1:,} av {p2:,}.", "Valgt: {p0} · vurderte celler {p1:,} av {p2:,}.", "Valgt: {p0} · vurderede celler {p1:,} af {p2:,}.", "Selected: {p0} · assessed cells {p1:,} of {p2:,}."),
    "status.available": ("Tillgänglig lokalt", "Tilgjengelig lokalt", "Tilgængelig lokalt", "Available locally"),
    "status.no_manifest": ("Saknas i manifestet", "Mangler i manifestet", "Mangler i manifestet", "Missing from manifest"),
    "status.data_missing": ("Data saknas", "Data mangler", "Data mangler", "Data missing"),
    "status.not_implemented": ("Inte implementerad", "Ikke implementert", "Ikke implementeret", "Not implemented"),
    "status.not_validated": ("Inte validerad", "Ikke validert", "Ikke valideret", "Not validated"),
    "status.validated": ("Tekniskt validerad", "Teknisk validert", "Teknisk valideret", "Technically validated"),
    "status.accepted": ("Regionalt accepterad", "Regionalt akseptert", "Regionalt accepteret", "Regionally accepted"),
    "timing.html": ("Karta HTML och rendering", "Kart-HTML og visning", "Kort-HTML og visning", "Map HTML and rendering"),
    "timing.ground_solar": ("Sol storskalig", "Sol storskala", "Sol storskala", "Large-scale solar"),
    "timing.small_solar": ("Sol småskalig", "Sol småskala", "Sol småskala", "Small-scale solar"),
    "timing.combined_solar": ("Sol samlad etablering", "Sol samlet etablering", "Sol samlet etablering", "Combined solar establishment"),
    "timing.wind": ("Vindpotential och vindetablering", "Vindpotensial og vindetablering", "Vindpotentiale og vindetablering", "Wind potential and wind establishment"),
    "timing.combined": ("Gemensam etableringsyta", "Felles etableringsareal", "Fælles etableringsareal", "Shared establishment area"),
    "timing.remaining": ("Beräknad kvarvarande tid: ca {p0:.1f} s{p1}.", "Beregnet gjenstående tid: ca. {p0:.1f} s{p1}.", "Beregnet resterende tid: ca. {p0:.1f} s{p1}.", "Estimated remaining time: about {p0:.1f} s{p1}."),
    "timing.no_history": ("Ingen historik ännu; mäter denna körning.", "Ingen historikk ennå; måler denne kjøringen.", "Ingen historik endnu; måler denne kørsel.", "No history yet; measuring this run."),
    "timing.unmeasured": (" plus omätta steg", " pluss umålte trinn", " plus umålte trin", " plus unmeasured steps"),
    "status.data_linked": ("Data kopplad.", "Data tilknyttet.", "Data tilknyttet.", "Data linked."),
    "result.area_demand": ("ytbehov", "arealbehov", "arealbehov", "area demand"),
    "result.total": ("Totalt", "Totalt", "I alt", "Total"),
    "result.fits_value": ("Ryms: {p0:.1f}%", "Får plass: {p0:.1f}%", "Kan rummes: {p0:.1f}%", "Fits: {p0:.1f}%"),
    "result.within_value": ("Inom potential: {p0}", "Innenfor potensial: {p0}", "Inden for potentiale: {p0}", "Within potential: {p0}"),
    "result.resolution_count": ("Totalt antal R{p0}-hex", "Samlet antall R{p0}-hex", "Samlet antal R{p0}-hex", "Total R{p0} hex count"),
    "ui.wind_hex": ("Landskapspotential Vind hexagon", "Landskapspotensial vind hexagon", "Landskabspotentiale vind hexagon", "Wind landscape potential hexagons"),
    "ui.wind_establishment": ("Potentiell etableringsyta Vind", "Potensielt etableringsareal vind", "Potentielt etableringsareal vind", "Potential wind establishment area"),
    "ui.solar_polygon": ("Landskapspotential Sol polygon", "Landskapspotensial sol polygon", "Landskabspotentiale sol polygon", "Solar landscape potential polygon"),
    "ui.solar_hex": ("Landskapspotential Sol hexagon", "Landskapspotensial sol hexagon", "Landskabspotentiale sol hexagon", "Solar landscape potential hexagons"),
    "ui.solar_establishment": ("Potentiell etableringsyta Sol", "Potensielt etableringsareal sol", "Potentielt etableringsareal sol", "Potential solar establishment area"),
    "solar.population_source": ("Sol källa: Befolkningsunderlag", "Solkilde: Befolkningsdata", "Solkilde: Befolkningsdata", "Solar source: Population data"),
    "solar.population_buffer": ("Solbuffert: Befolkningsunderlag", "Solbuffer: Befolkningsdata", "Solbuffer: Befolkningsdata", "Solar buffer: Population data"),
    "solar.protected": ("Skyddad natur", "Beskyttet natur", "Beskyttet natur", "Protected nature"),
    "solar.protected_source": ("Sol källa: Skyddad natur", "Solkilde: Beskyttet natur", "Solkilde: Beskyttet natur", "Solar source: Protected nature"),
    "solar.protected_buffer": ("Solbuffert: Skyddad natur", "Solbuffer: Beskyttet natur", "Solbuffer: Beskyttet natur", "Solar buffer: Protected nature"),
    "solar.protected_help": ("Skyddad natur används som avdrag i storskalig solpotential.", "Beskyttet natur brukes som fradrag i storskala solpotensial.", "Beskyttet natur bruges som fradrag i storskala solpotentiale.", "Protected nature is excluded from large-scale solar potential."),
    "wind.culture": ("kulturmiljöer", "kulturmiljøer", "kulturmiljøer", "cultural environments"),
    "wind.reindeer": ("rennäring / reindrift", "reindrift", "rensdyrdrift", "reindeer husbandry"),
    "solar.forest": ("Markanvändning: skog", "Arealbruk: skog", "Arealanvendelse: skov", "Land use: forest"),
    "solar.forest_source": ("Sol källa: skog", "Solkilde: skog", "Solkilde: skov", "Solar source: forest"),
    "solar.forest_exclusion": ("Solavdrag: skog", "Solfradrag: skog", "Solfradrag: skov", "Solar exclusion: forest"),
    "solar.forest_help": ("Tar bort markdekke/arealdekke skog från storskalig solpotential med samma polygon-, buffert- och H3-aggregeringslogik som skyddad natur och kultur.", "Fjerner markdekke/arealdekke skog fra storskala solpotensial med samme polygon-, buffer- og H3-aggregeringslogikk som beskyttet natur og kultur.", "Fjerner markdekke/arealdekke skov fra storskala solpotentiale med samme polygon-, buffer- og H3-aggregeringslogik som beskyttet natur og kultur.", "Excludes forest land cover from large-scale solar potential using the same polygon, buffer and H3 aggregation logic as protected nature and cultural environments."),
    "solar.forest_caption": ("Skogsfiltret ligger separat från skyddad natur och bygger på N500 markdekke där `objtype = Skog`.", "Skogfilteret er atskilt fra beskyttet natur og bygger på N500 markdekke der `objtype = Skog`.", "Skovfilteret er adskilt fra beskyttet natur og bygger på N500 markdekke, hvor `objtype = Skog`.", "The forest filter is separate from protected nature and uses N500 markdekke where `objtype = Skog`."),
    "solar.roads": ("Vägar", "Veier", "Veje", "Roads"),
    "solar.roads_source": ("Sol källa: Vägar", "Solkilde: Veier", "Solkilde: Veje", "Solar source: Roads"),
    "solar.roads_buffer": ("Solbuffert: Vägar", "Solbuffer: Veier", "Solbuffer: Veje", "Solar buffer: Roads"),
    "solar.roads_caption": ("Vägfiltret prövar respektavstånd till större vägar och allmänna vägstråk.", "Veifilteret prøver avstand til større veier og offentlige veistrekninger.", "Vejfilteret afprøver afstand til større veje og offentlige vejstrækninger.", "The road filter tests setback distances from major roads and public road corridors."),
    "solar.grid": ("Elinfrastruktur / nätanslutning", "Strøminfrastruktur / nettilknytning", "Elinfrastruktur / nettilslutning", "Electricity infrastructure / grid connection"),
    "solar.grid_source": ("Sol källa: Elinfrastruktur", "Solkilde: Strøminfrastruktur", "Solkilde: Elinfrastruktur", "Solar source: Electricity infrastructure"),
    "solar.grid_buffer": ("Sol nära nät: Elinfrastruktur", "Sol nær nett: Strøminfrastruktur", "Sol nær net: Elinfrastruktur", "Solar near grid: Electricity infrastructure"),
    "solar.grid_distance": ("Max avstånd till elinfrastruktur", "Maksavstand til strøminfrastruktur", "Maksafstand til elinfrastruktur", "Maximum distance to electricity infrastructure"),
    "solar.grid_distance_help": ("Yta räknas som storskalig solpotential bara inom valt avstånd till valda nätobjekt.", "Areal regnes som storskala solpotensial bare innenfor valgt avstand til valgte nettobjekter.", "Areal regnes som storskala solpotentiale kun inden for valgt afstand til valgte netobjekter.", "Area counts as large-scale solar potential only within the selected distance of selected grid features."),
    "solar.grid_rule": ("Valda nätlager används som positiv närhetsregel i Storskalig anläggning på land.", "Valgte nettlag brukes som en positiv nærhetsregel i Storskala anlegg på land.", "Valgte netlag bruges som en positiv nærhedsregel i Storskala anlæg på land.", "Selected grid layers provide a positive proximity rule for large-scale ground installation."),
    "solar.grid_legend": ("Inom maxavstånd till elinfrastruktur", "Innenfor maksavstand til strøminfrastruktur", "Inden for maksafstand til elinfrastruktur", "Within maximum distance to electricity infrastructure"),
    "solar.grid_caption": ("Nära nät används som en positiv mask: yta räknas som solpotential bara inom valt avstånd till elinfrastruktur.", "Nær nett brukes som en positiv maske: areal regnes som solpotensial bare innenfor valgt avstand til strøminfrastruktur.", "Nær net bruges som en positiv maske: areal regnes som solpotentiale kun inden for valgt afstand til elinfrastruktur.", "Grid proximity provides a positive mask: area counts as solar potential only within the selected distance to electricity infrastructure."),
    "solar.culture": ("Kulturmiljö", "Kulturmiljø", "Kulturmiljø", "Cultural environment"),
    "solar.culture_source": ("Sol källa: Kulturmiljö", "Solkilde: Kulturmiljø", "Solkilde: Kulturmiljø", "Solar source: Cultural environment"),
    "solar.culture_buffer": ("Solbuffert: Kulturmiljö", "Solbuffer: Kulturmiljø", "Solbuffer: Kulturmiljø", "Solar buffer: Cultural environment"),
    "solar.culture_caption": ("Kulturmiljöfiltret tar bort ytor som träffar valda kulturmiljölager och eventuell buffert.", "Kulturmiljøfilteret fjerner arealer som treffer valgte kulturmiljølag og eventuell buffer.", "Kulturmiljøfilteret fjerner arealer, der rammer valgte kulturmiljølag og eventuel buffer.", "The cultural environment filter excludes areas intersecting selected cultural environment layers and any buffer."),
    "solar.reindeer": ("Rennäring / reindrift", "Reindrift", "Rensdyrdrift", "Reindeer husbandry"),
    "solar.reindeer_source": ("Sol källa: Rennäring", "Solkilde: Reindrift", "Solkilde: Rensdyrdrift", "Solar source: Reindeer husbandry"),
    "solar.reindeer_buffer": ("Solbuffert: Rennäring", "Solbuffer: Reindrift", "Solbuffer: Rensdyrdrift", "Solar buffer: Reindeer husbandry"),
    "solar.reindeer_caption": ("Rennäringsfiltret tar bort ytor som träffar valda reindriftslager och eventuell buffert.", "Reindriftsfilteret fjerner arealer som treffer valgte reindriftslag og eventuell buffer.", "Rensdyrdriftsfilteret fjerner arealer, der rammer valgte rensdyrdriftslag og eventuel buffer.", "The reindeer husbandry filter excludes areas intersecting selected reindeer husbandry layers and any buffer."),
    "solar.coast": ("Strandskydd / kust", "Strandvern / kyst", "Strandbeskyttelse / kyst", "Shore protection / coast"),
    "solar.coast_source": ("Sol källa: Strandskydd / kust", "Solkilde: Strandvern / kyst", "Solkilde: Strandbeskyttelse / kyst", "Solar source: Shore protection / coast"),
    "solar.coast_buffer": ("Solbuffert: Strandskydd / kust", "Solbuffer: Strandvern / kyst", "Solbuffer: Strandbeskyttelse / kyst", "Solar buffer: Shore protection / coast"),
    "solar.coast_caption": ("Strandskydd och kustzon kan användas som avdrag i storskalig solpotential.", "Strandvern og kystsone kan brukes som fradrag i storskala solpotensial.", "Strandbeskyttelse og kystzone kan bruges som fradrag i storskala solpotentiale.", "Shore protection and the coastal zone can be excluded from large-scale solar potential."),
    "language.swedish": ("Svenska", "Svenska", "Svenska", "Svenska"),
    "language.norwegian": ("Norsk", "Norsk", "Norsk", "Norsk"),
    "language.danish": ("Dansk", "Dansk", "Dansk", "Dansk"),
    "language.english": ("English", "English", "English", "English"),
    "ui.release_note": ("Utvecklingsversion - inte färdig produkt", "Utviklingsversjon - ikke ferdig produkt", "Udviklingsversion - ikke færdigt produkt", "Development version - unfinished product"),
    "missing.wind_waiting": ("Vindpotential väntar på H3-/landskapsunderlag och vindregler.", "Vindpotensial venter på H3-/landskapsdata og vindregler.", "Vindpotentiale afventer H3-/landskabsdata og vindregler.", "Wind potential is waiting for H3/landscape inputs and wind rules."),
    "missing.solar_waiting": ("Solpotential väntar på H3-/landskapsunderlag och solregler.", "Solpotensial venter på H3-/landskapsdata og solregler.", "Solpotentiale afventer H3-/landskabsdata og solregler.", "Solar potential is waiting for H3/landscape inputs and solar rules."),
    "missing.acceptance_waiting": ("Social acceptans väntar på regionspecifikt underlag och validering.", "Sosial aksept venter på regionspesifikke data og validering.", "Social accept afventer regionsspecifikke data og validering.", "Social acceptance is waiting for region-specific inputs and validation."),
    "analysis.no_active_filters": ("Inga aktiva filter – hela analysdomänen visas.", "Ingen aktive filtre – hele analysedomenet vises.", "Ingen aktive filtre – hele analysedomænet vises.", "No active filters – the full analysis domain is shown."),
    "analysis.select_group_source": ("Välj minst en grupp och dess datakälla för att skapa ett tekniskt analysresultat.", "Velg minst én gruppe og dens datakilde for å opprette et teknisk analyseresultat.", "Vælg mindst én gruppe og dens datakilde for at oprette et teknisk analyseresultat.", "Select at least one group and its data source to create a technical analysis result."),
    "source.eml_link": ("[Energy Modelling Lab]({p0})", "[Energy Modelling Lab]({p0})", "[Energy Modelling Lab]({p0})", "[Energy Modelling Lab]({p0})"),
})

MESSAGES.update({
    "analysis.requirements_list": ("- `workspace_profile` för den gemensamma UI-strukturen\n- `geography_manifest` med analysdomän och H3-identitet\n- `analysis_manifests` med regionspecifika källor, operationer och parametrar\n- checksumspinnade källartefakter och kompletta observationer bundna till exakt domän\n- implementerad generisk konsument samt teknisk och regional validering\n- `scenario_manifest` och `social_acceptance_manifest` först när de kapabiliteterna ska aktiveras", "- `workspace_profile` for den felles UI-strukturen\n- `geography_manifest` med analysedomene og H3-identitet\n- `analysis_manifests` med regionspesifikke kilder, operasjoner og parametere\n- kontrollsumlåste kildeartefakter og komplette observasjoner knyttet til nøyaktig domene\n- implementert generisk konsument samt teknisk og regional validering\n- `scenario_manifest` og `social_acceptance_manifest` først når disse funksjonene skal aktiveres", "- `workspace_profile` til den fælles UI-struktur\n- `geography_manifest` med analysedomæne og H3-identitet\n- `analysis_manifests` med regionsspecifikke kilder, operationer og parametre\n- kontrolsumlåste kildeartefakter og komplette observationer knyttet til det præcise domæne\n- implementeret generisk konsument samt teknisk og regional validering\n- `scenario_manifest` og `social_acceptance_manifest` først, når disse funktioner skal aktiveres", "- `workspace_profile` for the shared UI structure\n- `geography_manifest` with analysis domain and H3 identity\n- `analysis_manifests` with region-specific sources, operations and parameters\n- checksum-pinned source artifacts and complete observations bound to the exact domain\n- implemented generic consumer plus technical and regional validation\n- `scenario_manifest` and `social_acceptance_manifest` only when those capabilities are to be enabled"),
    "analysis.hex_budget_help": ('Ytbudgethex visar extra ytbehov i separata schematiska fält utanför regionen. Potentiallagret är blått för vind, gult för sol och grönt för vind och sol. Scenariomarkören är blå för vind, gulorange för sol och mörkgrön när båda har yta i samma visningshex; det betyder inte exakt fysisk överlappning.', 'Arealbudsjetthex viser ekstra arealbehov i separate skjematiske felt utenfor regionen. Potensiallaget er blått for vind, gult for sol og grønt for vind og sol. Scenariomarkøren er blå for vind, guloransje for sol og mørkegrønn når begge har areal i samme visningshex; det betyr ikke nøyaktig fysisk overlapping.', 'Arealbudgethex viser ekstra arealbehov i separate skematiske felter uden for regionen. Potentialelaget er blåt for vind, gult for sol og grønt for vind og sol. Scenariemarkøren er blå for vind, gulorange for sol og mørkegrøn, når begge har areal i samme visningshex; det betyder ikke præcis fysisk overlapning.', 'Area-budget hexes show additional area demand in separate schematic fields outside the region. The potential layer is blue for wind, yellow for solar and green for wind and solar. The scenario marker is blue for wind, yellow-orange for solar and dark green when both have area in the same display hex; this does not indicate exact physical overlap.'),
    "analysis.byplanlab": ("[Vill du veta mer om att anlägga sol över land? Läs guiden från Byplanlab.](https://byplanlab.dk/sites/default/files/2025-06/Sol%20over%20land%20-%20Guide%20til%20planl%C3%A6gning%20af%20solenergi.pdf)", "[Vil du vite mer om å etablere sol på land? Les veiledningen fra Byplanlab.](https://byplanlab.dk/sites/default/files/2025-06/Sol%20over%20land%20-%20Guide%20til%20planl%C3%A6gning%20af%20solenergi.pdf)", "[Vil du vide mere om at anlægge sol over land? Læs guiden fra Byplanlab.](https://byplanlab.dk/sites/default/files/2025-06/Sol%20over%20land%20-%20Guide%20til%20planl%C3%A6gning%20af%20solenergi.pdf)", "[Want to learn more about ground-mounted solar? Read the guide from Byplanlab.](https://byplanlab.dk/sites/default/files/2025-06/Sol%20over%20land%20-%20Guide%20til%20planl%C3%A6gning%20af%20solenergi.pdf)"),
    "format.parenthetical": ("{p0} ({p1})", "{p0} ({p1})", "{p0} ({p1})", "{p0} ({p1})"),
    "format.space": ("{p0} {p1}", "{p0} {p1}", "{p0} {p1}", "{p0} {p1}"),
    "format.dot": ("{p0} · {p1}", "{p0} · {p1}", "{p0} · {p1}", "{p0} · {p1}"),
    "format.colon": ("{p0}: {p1}", "{p0}: {p1}", "{p0}: {p1}", "{p0}: {p1}"),
    "freshness.language_changed": ("Språkbyte: samma scenario och resultat.", "Språkbytte: samme scenario og resultater.", "Sprogskift: samme scenarie og resultater.", "Language change: same scenario and results."),
    "freshness.not_rechecked": ("Resultat från senast verifierade underlag. Underlaget har inte kontrollerats på nytt vid språkbytet.", "Resultater fra sist verifiserte datagrunnlag. Datagrunnlaget er ikke kontrollert på nytt ved språkbyttet.", "Resultater fra senest verificerede datagrundlag. Datagrundlaget er ikke kontrolleret igen ved sprogskiftet.", "Results use the last verified inputs. Inputs have not been checked again during the language change."),
    "freshness.inputs_changed": ("Underlaget har ändrats sedan resultatet beräknades. Uppdatera underlaget innan du använder resultatet som aktuellt.", "Datagrunnlaget er endret siden resultatet ble beregnet. Oppdater datagrunnlaget før du bruker resultatet som aktuelt.", "Datagrundlaget er ændret siden resultatet blev beregnet. Opdater datagrundlaget, før du bruger resultatet som aktuelt.", "Inputs have changed since the result was calculated. Refresh the inputs before treating the result as current."),
    "freshness.last_verified": ("Senast verifierat: {p0}.", "Sist verifisert: {p0}.", "Senest verificeret: {p0}.", "Last verified: {p0}."),
    "freshness.refresh": ("Uppdatera underlag", "Oppdater datagrunnlag", "Opdater datagrundlag", "Refresh inputs"),
    "freshness.open_analysis": ("Öppna eller uppdatera analysen för att visa resultaten.", "Åpne eller oppdater analysen for å vise resultatene.", "Åbn eller opdater analysen for at vise resultaterne.", "Open or refresh the analysis to view the results."),
    "analysis.region_identity": ("Regionens identitet stämmer inte med det inlästa manifestet. Arbetsytan förblir stängd.", "Regionens identitet stemmer ikke med det innleste manifestet. Arbeidsflaten forblir stengt.", "Regionens identitet stemmer ikke med det indlæste manifest. Arbejdsfladen forbliver lukket.", "The region identity does not match the loaded manifest. The workspace remains closed."),
    "analysis.region_unreadable": ("Det valda regionmanifestet kunde inte läsas. Ingen annan region öppnas automatiskt.", "Det valgte regionmanifestet kunne ikke leses. Ingen annen region åpnes automatisk.", "Det valgte regionmanifest kunne ikke læses. Ingen anden region åbnes automatisk.", "The selected region manifest could not be read. No other region is opened automatically."),
    "analysis.technical_reason": ("Teknisk orsak: {p0}", "Teknisk årsak: {p0}", "Teknisk årsag: {p0}", "Technical reason: {p0}"),
    "analysis.scenario_binding": ("Scenarioändringarna kunde inte bindas till manifestet. Det senast tillämpade scenariot behålls.", "Scenarioendringene kunne ikke knyttes til manifestet. Det sist anvendte scenarioet beholdes.", "Scenarieændringerne kunne ikke knyttes til manifestet. Det senest anvendte scenarie bevares.", "Scenario changes could not be bound to the manifest. The last applied scenario is retained."),
    "analysis.sources_caption": ("Datakällor och modellmanifest som används i denna region.", "Datakilder og modellmanifest som brukes i denne regionen.", "Datakilder og modelmanifest, der bruges i denne region.", "Data sources and model manifests used in this region."),
    "analysis.active_contracts": ("Aktiva kontrakt läses endast från regionens repoägda delivery-manifest. Äldre arkivmanifest visas inte som använda och kan inte aktivera en arbetsytefunktion.", "Aktive kontrakter leses bare fra regionens leveransemanifest i repoet. Eldre arkivmanifest vises ikke som brukte og kan ikke aktivere en arbeidsflatefunksjon.", "Aktive kontrakter læses kun fra regionens leverancemanifest i repoet. Ældre arkivmanifest vises ikke som anvendte og kan ikke aktivere en arbejdsfladefunktion.", "Active contracts are read only from the region's repository-owned delivery manifest. Older archive manifests are not shown as used and cannot enable a workspace feature."),
    "analysis.active_paths": ("Repo-sökvägarna och JSON-vyn nedan är regionens aktiva arbetsyte- och analysdeklaration för denna körning. Legacy- och runtimeproveniens redovisas separat och aktiverar inga funktioner här.", "Repo-filbanene og JSON-visningen nedenfor er regionens aktive arbeidsflate- og analysebeskrivelse for denne kjøringen. Eldre og runtime-opprinnelse vises separat og aktiverer ingen funksjoner her.", "Repo-stierne og JSON-visningen nedenfor er regionens aktive arbejdsflade- og analysedeklaration for denne kørsel. Ældre og runtime-proveniens vises separat og aktiverer ingen funktioner her.", "The repository paths and JSON view below are the region's active workspace and analysis declarations for this run. Legacy and runtime provenance are reported separately and enable no features here."),
    "analysis.hex_opacity": ("Opacitet hexlager", "Opasitet for hexlag", "Opacitet for hexlag", "Hex layer opacity"),
    "analysis.hex_opacity_help": ("Styr opaciteten för hexlagret {p0}. 0.1 är nästan genomskinligt, 0.9 nästan helt fyllt.", "Styr opasiteten for hexlaget {p0}. 0.1 er nesten gjennomsiktig, 0.9 nesten helt fylt.", "Styr opaciteten for hexlaget {p0}. 0.1 er næsten gennemsigtigt, 0.9 næsten helt udfyldt.", "Control opacity for hex layer {p0}. 0.1 is almost transparent; 0.9 is almost fully filled."),
    "analysis.status_unavailable": ("Status: {p0}. Gemensam resultatpresentation är inte aktiverad i den här granskningsytan.", "Status: {p0}. Felles resultatvisning er ikke aktivert i denne granskningsflaten.", "Status: {p0}. Fælles resultatvisning er ikke aktiveret i denne granskningsflade.", "Status: {p0}. Shared result presentation is not enabled in this review workspace."),
    "analysis.energy_contracts": ("Energimodellering aktiveras först när regionen deklarerar och validerar scenario-, efterfråge- och teknikytkontrakten.", "Energimodellering aktiveres først når regionen deklarerer og validerer scenario-, etterspørsels- og teknologiarealkontraktene.", "Energimodellering aktiveres først, når regionen deklarerer og validerer scenarie-, efterspørgsels- og teknologiarealkontrakterne.", "Energy modelling is enabled only when the region declares and validates scenario, demand and technology-area contracts."),
    "analysis.mean_score": ("Medelpoäng", "Gjennomsnittsskår", "Gennemsnitsscore", "Mean score"),
    "analysis.high_potential": ("Hög potential", "Høyt potensial", "Højt potentiale", "High potential"),
    "analysis.solar_groups": ("Solpanelen använder samma fem grupper från arbetsyteprofilen. Kontroller utan regionspecifikt manifest visas utan påhittade värden.", "Solpanelet bruker de samme fem gruppene fra arbeidsflateprofilen. Kontroller uten regionspesifikt manifest vises uten oppdiktede verdier.", "Solpanelet bruger de samme fem grupper fra arbejdsfladeprofilen. Kontroller uden regionsspecifikt manifest vises uden opdigtede værdier.", "The solar panel uses the same five workspace-profile groups. Controls without a region-specific manifest are shown without invented values."),
    "analysis.use_group": ("Använd {p0}", "Bruk {p0}", "Anvend {p0}", "Use {p0}"),
    "analysis.reason": ("Orsak: {p0}.", "Årsak: {p0}.", "Årsag: {p0}.", "Reason: {p0}."),
    "analysis.wind_structure": ("Vindpanelens struktur kommer från arbetsyteprofilen; regionens analysmanifest avgör lager och interaktion.", "Vindpanelets struktur kommer fra arbeidsflateprofilen; regionens analysemanifest bestemmer lag og interaksjon.", "Vindpanelets struktur kommer fra arbejdsfladeprofilen; regionens analysemanifest bestemmer lag og interaktion.", "The wind panel structure comes from the workspace profile; the region's analysis manifest determines layers and interactions."),
    "analysis.group_readiness": ("De fem standardgrupperna kommer från den gemensamma arbetsyteprofilen. Endast grupper som både deklareras av regionen och klarar sin egen readiness-gate kan användas.", "De fem standardgruppene kommer fra den felles arbeidsflateprofilen. Bare grupper som er deklarert av regionen og har bestått sin egen beredskapskontroll, kan brukes.", "De fem standardgrupper kommer fra den fælles arbejdsfladeprofil. Kun grupper, som er deklareret af regionen og har bestået deres egen beredskabskontrol, kan bruges.", "The five standard groups come from the shared workspace profile. Only groups declared by the region and passing their own readiness checks can be used."),
    "analysis.no_scenario": ("Inget scenario är tillämpat. Gör färdigt formuläret och välj Använd ändringar.", "Det er ikke brukt noe scenario. Fullfør skjemaet og velg Bruk endringer.", "Intet scenarie er anvendt. Udfyld formularen og vælg Anvend ændringer.", "No scenario is applied. Complete the form and select Apply changes."),
    "analysis.capacity_ground": ("Solkapaciteten i underlaget avser marksol. Inget taksolsbidrag dras av.", "Solkapasiteten i datagrunnlaget gjelder sol på bakken. Ingen bidrag fra sol på tak trekkes fra.", "Solkapaciteten i datagrundlaget gælder sol på land. Intet bidrag fra sol på tag trækkes fra.", "Solar capacity in the source data refers to ground-mounted solar. No rooftop solar contribution is deducted."),
    "analysis.rooftop_contribution": ("Taksolschablonen bidrar med {p0:.2f} TWh. Kvar för marksol: {p1:.2f} TWh och {p2:.2f} km².", "Taksolestimatet bidrar med {p0:.2f} TWh. Gjenstår for sol på bakken: {p1:.2f} TWh og {p2:.2f} km².", "Tag-solestimatet bidrager med {p0:.2f} TWh. Tilbage for sol på land: {p1:.2f} TWh og {p2:.2f} km².", "The rooftop solar estimate contributes {p0:.2f} TWh. Remaining for ground-mounted solar: {p1:.2f} TWh and {p2:.2f} km²."),
    "analysis.scenario_failed": ("Det tillämpade scenariot kunde inte köras. Ingen äldre state eller regional fallback används.", "Det anvendte scenarioet kunne ikke kjøres. Ingen tidligere tilstand eller regional reserve brukes.", "Det anvendte scenarie kunne ikke køres. Ingen tidligere tilstand eller regional reserve bruges.", "The applied scenario could not run. No previous state or regional fallback is used."),
    "analysis.rooftop_binding_failed": ("Scenariot kunde inte bindas till den tillämpade taksolsselectionen. Etableringsberäkningen stoppas.", "Scenarioet kunne ikke knyttes til det anvendte taksolvalget. Etableringsberegningen stoppes.", "Scenariet kunne ikke knyttes til det anvendte tag-solvalg. Etableringsberegningen stoppes.", "The scenario could not be bound to the applied rooftop solar selection. The establishment calculation is stopped."),
    "analysis.rooftop_missing": ("Taksol: data saknas. Hela solbehovet räknas därför som marksol; inget taksolsbidrag dras av.", "Sol på tak: data mangler. Hele solbehovet regnes derfor som sol på bakken; ingen bidrag fra sol på tak trekkes fra.", "Sol på tag: data mangler. Hele solbehovet regnes derfor som sol på land; intet bidrag fra sol på tag trækkes fra.", "Rooftop solar: data is missing. All solar demand is therefore treated as ground-mounted solar; no rooftop contribution is deducted."),
    "analysis.no_acceptance": ("Inget acceptansval är tillämpat. Gör färdigt formuläret och välj Använd ändringar.", "Ingen akseptvalg er anvendt. Fullfør skjemaet og velg Bruk endringer.", "Intet acceptvalg er anvendt. Udfyld formularen og vælg Anvend ændringer.", "No acceptance selection is applied. Complete the form and select Apply changes."),
    "analysis.acceptance_failed": ("Det tillämpade acceptansvalet kunde inte köras. Ingen äldre state eller regional fallback används.", "Det anvendte akseptvalget kunne ikke kjøres. Ingen tidligere tilstand eller regional reserve brukes.", "Det anvendte acceptvalg kunne ikke køres. Ingen tidligere tilstand eller regional reserve bruges.", "The applied acceptance selection could not run. No previous state or regional fallback is used."),
    "analysis.establishment_table_help": ("Tabellen visar hur mycket teknikspecifik yta scenariot kräver, hur mycket möjlig teknikpotential som finns efter filter, och om något behöver lösas utanför potentialen.", "Tabellen viser hvor mye teknologispesifikt areal scenarioet krever, hvor mye mulig teknologipotensial som finnes etter filtre, og om noe må løses utenfor potensialet.", "Tabellen viser, hvor meget teknologispecifikt areal scenariet kræver, hvor meget muligt teknologipotentiale der findes efter filtre, og om noget skal løses uden for potentialet.", "The table shows technology-specific area demanded by the scenario, possible technology potential after filters, and whether any demand must be met outside the potential."),
    "analysis.exact_area": ("Vind- och solytan beräknas på R{p0} mot analysdomänens manifestdeklarerade cellarea. Samma exakta teknikytor används i karta, hover, tabell och scenarioyta inom potentialen.", "Vind- og solarealet beregnes på R{p0} mot analysedomenets manifestdeklarerte celleareal. De samme nøyaktige teknologiarealene brukes i kart, pekervisning, tabell og scenarioareal innenfor potensialet.", "Vind- og solarealet beregnes på R{p0} mod analysedomænets manifestdeklarerede celleareal. De samme præcise teknologiarealer bruges i kort, pegevisning, tabel og scenarieareal inden for potentialet.", "Wind and solar area is calculated at R{p0} against the analysis domain's manifest-declared cell area. The same precise technology areas are used in the map, hover, table and scenario allocation within the potential."),
    "analysis.area_when_energy": ("Etableringsytan visas när energimodelleringen är aktiv.", "Etableringsarealet vises når energimodelleringen er aktiv.", "Etableringsarealet vises, når energimodelleringen er aktiv.", "Establishment area is shown when energy modelling is active."),
    "analysis.area_when_potential": ("Etableringsytan visas när vind- och/eller solpotential finns aktiv i kartan.", "Etableringsarealet vises når vind- og/eller solpotensial er aktivt i kartet.", "Etableringsarealet vises, når vind- og/eller solpotentiale er aktivt i kortet.", "Establishment area is shown when wind and/or solar potential is active on the map."),
    "analysis.calculate_when_potential": ("Etableringsytan beräknas när vind- och/eller solpotential finns aktiv i kartan.", "Etableringsarealet beregnes når vind- og/eller solpotensial er aktivt i kartet.", "Etableringsarealet beregnes, når vind- og/eller solpotentiale er aktivt i kortet.", "Establishment area is calculated when wind and/or solar potential is active on the map."),
    "analysis.capacity_disclaimer": ("Preliminära värden från energimodelleringen. Befintlig kapacitet ingår i modellscenariot. MW visar installerad effekt; årsproduktion saknas. Solvärdena avser marksol, utan taksolsavdrag.", "Foreløpige verdier fra energimodelleringen. Eksisterende kapasitet inngår i modellscenarioet. MW viser installert effekt; årsproduksjon mangler. Solverdiene gjelder sol på bakken, uten fradrag for sol på tak.", "Foreløbige værdier fra energimodelleringen. Eksisterende kapacitet indgår i modelscenariet. MW viser installeret effekt; årsproduktion mangler. Solværdierne gælder sol på land, uden fradrag for sol på tag.", "Preliminary energy-modelling values. Existing capacity is included in the model scenario. MW indicates installed power; annual generation is unavailable. Solar values refer to ground-mounted solar, with no rooftop deduction."),
    "analysis.schematic_comparison": ("Schematisk jämförelse av scenariots totala ytbehov med landskapets potential. Visar inte föreslagna etableringar.", "Skjematisk sammenligning av scenarioets samlede arealbehov med landskapets potensial. Viser ikke foreslåtte etableringer.", "Skematisk sammenligning af scenariets samlede arealbehov med landskabets potentiale. Viser ikke foreslåede etableringer.", "Schematic comparison of total scenario area demand with landscape potential. Does not show proposed establishments."),
    "analysis.mix_outside": ("Vald mix ryms inte helt inom landskapets potential. {p0} behöver lösas utanför landskapets potential.", "Valgt miks får ikke fullt plass innenfor landskapets potensial. {p0} må løses utenfor landskapets potensial.", "Det valgte mix kan ikke rummes helt inden for landskabets potentiale. {p0} skal løses uden for landskabets potentiale.", "The selected mix does not fit entirely within landscape potential. {p0} must be met outside landscape potential."),
    "analysis.technology_sum": ("Tabellen jämför scenariots teknikspecifika ytbehov med möjlig yta efter aktiva filter. Totalraden summerar vind och sol och kan därför vara större än den unika fysiska markytan.", "Tabellen sammenligner scenarioets teknologispesifikke arealbehov med mulig areal etter aktive filtre. Totalraden summerer vind og sol og kan derfor være større enn det unike fysiske landarealet.", "Tabellen sammenligner scenariets teknologispecifikke arealbehov med muligt areal efter aktive filtre. Totalrækken summerer vind og sol og kan derfor være større end det unikke fysiske landareal.", "The table compares technology-specific scenario area demand with possible area after active filters. The total row sums wind and solar and can therefore exceed the unique physical land area."),
    "analysis.shared_hex": ('En grön potentialhex kan bära både vind- och solscenarioyta. Mörkgrön scenariomarkör betyder att båda finns i samma visningshex; exakt fysisk överlappning beräknas inte.', 'En grønn potensialhex kan ha både vind- og solscenarioareal. En mørkegrønn scenariomarkør betyr at begge finnes i samme visningshex; nøyaktig fysisk overlapping beregnes ikke.', 'En grøn potentialehex kan have både vind- og solscenarieareal. En mørkegrøn scenariemarkør betyder, at begge findes i samme visningshex; præcis fysisk overlapning beregnes ikke.', 'A green potential hex may contain both wind and solar scenario area. A dark green scenario marker means both are in the same display hex; exact physical overlap is not calculated.'),
    "analysis.change_arrows": ("Pilarna visar förändring sedan föregående beräknade läge.", "Pilene viser endring siden forrige beregnede tilstand.", "Pilene viser ændring siden den foregående beregnede tilstand.", "Arrows show change since the previous calculated state."),
    "analysis.mean_acceptance": ("Medelacceptans", "Gjennomsnittlig aksept", "Gennemsnitlig accept", "Mean acceptance"),
    "analysis.median_acceptance": ("Medianacceptans", "Medianaksept", "Medianaccept", "Median acceptance"),
    "analysis.unit": ("Enhet", "Enhet", "Enhed", "Unit"),
    "analysis.unit_help": ("Byte av enhet ändrar bara hur ytor visas i panelen, inte modellresultatet.", "Enhetsbytte endrer bare hvordan arealer vises i panelet, ikke modellresultatet.", "Skift af enhed ændrer kun, hvordan arealer vises i panelet, ikke modelresultatet.", "Changing the unit only changes area display in the panel, not the model result."),
    "analysis.panel_help": ("Panelen visar om vald mix av vind och sol ryms i de landskap som modellen bedömer som möjliga efter aktiva filter. Kartan färgsätter platser som möjliga för vind, sol, båda teknikerna eller ingen av dem.", "Panelet viser om valgt miks av vind og sol får plass i landskap som modellen vurderer som mulige etter aktive filtre. Kartet fargelegger steder som mulige for vind, sol, begge teknologier eller ingen av dem.", "Panelet viser, om det valgte mix af vind og sol kan rummes i landskaber, som modellen vurderer som mulige efter aktive filtre. Kortet farvelægger steder som mulige for vind, sol, begge teknologier eller ingen af dem.", "The panel shows whether the selected wind and solar mix fits in landscapes the model considers possible after active filters. The map colours locations as possible for wind, solar, both technologies or neither."),
    "analysis.cell_area_help": ("Ytorna summeras från cellernas deklarerade etableringsyta efter filter. Hav ingår inte. Hexmarkörer är en schematisk visning av dessa ytor.", "Arealene summeres fra cellenes deklarerte etableringsareal etter filtre. Hav er ikke inkludert. Hexmarkører viser disse arealene skjematisk.", "Arealerne summeres fra cellernes deklarerede etableringsareal efter filtre. Hav indgår ikke. Hexmarkører viser disse arealer skematisk.", "Areas are summed from cells' declared establishment area after filters. Sea is excluded. Hex markers display these areas schematically."),
    "analysis.solar_row_help": ("Solradens energi är hela solmålet. Solradens ytbehov är endast det kvarvarande markbehovet efter aktiv taksolschablon; taksol ändrar inte kartans geografiska solpotential.", "Solradens energi er hele solmålet. Solradens arealbehov er bare det gjenværende landbehovet etter aktivt taksolestimat; sol på tak endrer ikke kartets geografiske solpotensial.", "Solrækkens energi er hele solmålet. Solrækkens arealbehov er kun det resterende landbehov efter aktivt tag-solestimat; sol på tag ændrer ikke kortets geografiske solpotentiale.", "The solar row's energy is the full solar target. Its area demand is only remaining land demand after the active rooftop solar estimate; rooftop solar does not change geographic solar potential on the map."),
    "analysis.mix_fits": ("Vald mix ryms inom landskapets potential med nuvarande urval.", "Valgt miks får plass innenfor landskapets potensial med gjeldende utvalg.", "Det valgte mix kan rummes inden for landskabets potentiale med det aktuelle udvalg.", "The selected mix fits within landscape potential under the current selection."),
    "analysis.provisional_source": ("Provisorisk datakälla", "Foreløpig datakilde", "Foreløbig datakilde", "Provisional data source"),
    "analysis.acceptance_priority": ("Scenarioytan inom potentialen prioriteras med {p0:.0f}% social acceptansstyrning.", "Scenarioarealet innenfor potensialet prioriteres med {p0:.0f}% styring etter sosial aksept.", "Scenariearealet inden for potentialet prioriteres med {p0:.0f}% styring efter social accept.", "Scenario area within the potential is prioritized with {p0:.0f}% social acceptance influence."),
    "analysis.capacity_summary": ("Preliminära kapaciteter · {p0} · mix {p1:.1f}% vind / {p2:.1f}% sol av total MW · källa {p3}", "Foreløpige kapasiteter · {p0} · miks {p1:.1f}% vind / {p2:.1f}% sol av samlet MW · kilde {p3}", "Foreløbige kapaciteter · {p0} · mix {p1:.1f}% vind / {p2:.1f}% sol af samlet MW · kilde {p3}", "Preliminary capacities · {p0} · mix {p1:.1f}% wind / {p2:.1f}% solar of total MW · source {p3}"),
    "analysis.dummy_summary": ("Dummy/prototypdata · {p0}: {p1:g}x energi · markintensitet {p2} · mix {p3:.0f}% vind / {p4:.0f}% sol · källa {p5} {p6}", "Demo/prototypedata · {p0}: {p1:g}x energi · arealintensitet {p2} · miks {p3:.0f}% vind / {p4:.0f}% sol · kilde {p5} {p6}", "Demo/prototypedata · {p0}: {p1:g}x energi · arealintensitet {p2} · mix {p3:.0f}% vind / {p4:.0f}% sol · kilde {p5} {p6}", "Dummy/prototype data · {p0}: {p1:g}x energy · land intensity {p2} · mix {p3:.0f}% wind / {p4:.0f}% solar · source {p5} {p6}"),
    "analysis.map_resolution": ("Kartan visas som R{p0}. Ytbalans, täckning och scenarioallokering beräknas i R{p1}.", "Kartet vises som R{p0}. Arealbalanse, dekning og scenariofordeling beregnes i R{p1}.", "Kortet vises som R{p0}. Arealbalance, dækning og scenariefordeling beregnes i R{p1}.", "The map is displayed at R{p0}. Area balance, coverage and scenario allocation are calculated at R{p1}."),
    "analysis.map_technical": ("Tekniska kartmått för granskning av hexmarkörer och färgklasser.", "Tekniske kartmål for gransking av hexmarkører og fargeklasser.", "Tekniske kortmål til granskning af hexmarkører og farveklasser.", "Technical map measures for reviewing hex markers and colour classes."),
    "analysis.layer_purpose": ("{p0} visar vind och sol tillsammans. {p1} visar den extra etableringsyta som krävs när scenariot inte ryms.", "{p0} viser vind og sol sammen. {p1} viser det ekstra etableringsarealet som trengs når scenarioet ikke får plass.", "{p0} viser vind og sol sammen. {p1} viser det ekstra etableringsareal, der kræves, når scenariet ikke kan rummes.", "{p0} shows wind and solar together. {p1} shows additional establishment area required when the scenario does not fit."),
    "analysis.hex_stats_missing": ("Hexstatistik saknas för denna vy.", "Hexstatistikk mangler for denne visningen.", "Hexstatistik mangler for denne visning.", "Hex statistics are unavailable for this view."),
    "analysis.rooftop_energy": ("Taksolel", "Strøm fra sol på tak", "Strøm fra sol på tag", "Rooftop solar electricity"),
    "analysis.target_share": ("Andel av solmålet", "Andel av solmålet", "Andel af solmålet", "Share of solar target"),
    "analysis.land_after_rooftop": ("Markbehov efter tak", "Landbehov etter tak", "Landbehov efter tag", "Land demand after rooftop solar"),
    "analysis.area_hex": ("Area per hex", "Areal per hex", "Areal per hex", "Area per hex"),
    "analysis.whole_hex": ("Hela hex behövs", "Hele hex trengs", "Hele hex kræves", "Whole hexes needed"),
    "analysis.selected_wind_hex": ("Valda vindhex", "Valgte vindhex", "Valgte vindhex", "Selected wind hexes"),
    "analysis.area_quality": ("AreaDemand har datakvalitetsvarningar. Se Energimodellering-panelen för detaljer.", "AreaDemand har datakvalitetsadvarsler. Se panelet Energimodellering for detaljer.", "AreaDemand har datakvalitetsadvarsler. Se panelet Energimodellering for detaljer.", "AreaDemand has data quality warnings. See the Energy modelling panel for details."),
    "analysis.allocated_wind": ("Fördelad vindproduktion", "Fordelt vindproduksjon", "Fordelt vindproduktion", "Allocated wind generation"),
    "analysis.area_share": ("Area-share gör att fler hex behövs än den teoretiska jämförelsen med helt fyllda hex.", "Arealandel gjør at flere hex trengs enn i den teoretiske sammenligningen med helt fylte hex.", "Arealandel betyder, at flere hex kræves end i den teoretiske sammenligning med helt udfyldte hex.", "Area share means more hexes are needed than in the theoretical comparison with fully filled hexes."),
    "analysis.wind_outside": ("Vindbehovet ryms inte helt inom landskapets potential. Planeringsval behövs: sänk potentialkrav, släpp in kantzoner, ändra restriktioner, välj ett lägre framtidsscenario eller minska ytbehovet.", "Vindbehovet får ikke fullt plass innenfor landskapets potensial. Planleggingsvalg trengs: senk potensialkrav, tillat kantsoner, endre restriksjoner, velg et lavere framtidsscenario eller reduser arealbehovet.", "Vindbehovet kan ikke rummes helt inden for landskabets potentiale. Planlægningsvalg kræves: sænk potentialekrav, tillad randzoner, ændr restriktioner, vælg et lavere fremtidsscenarie eller reducer arealbehovet.", "Wind demand does not fit entirely within landscape potential. Planning choices are needed: lower potential thresholds, include edge zones, change restrictions, choose a lower future scenario or reduce area demand."),
    "analysis.map_explainer": ("Kartan visar hur aktiva geografiska antaganden formar möjlig etableringsyta och hur scenariot placeras i landskapet.", "Kartet viser hvordan aktive geografiske antakelser former mulig etableringsareal og hvordan scenarioet plasseres i landskapet.", "Kortet viser, hvordan aktive geografiske antagelser former muligt etableringsareal, og hvordan scenariet placeres i landskabet.", "The map shows how active geographic assumptions shape possible establishment area and how the scenario is allocated in the landscape."),
    "analysis.no_filter_summary": ("Inga aktiva geografiska filter kunde sammanfattas för den senaste kartkörningen.", "Ingen aktive geografiske filtre kunne oppsummeres for den siste kartkjøringen.", "Ingen aktive geografiske filtre kunne sammenfattes for den seneste kortkørsel.", "No active geographic filters could be summarized for the latest map run."),
    "analysis.iframe_required": ("Kartan kan inte renderas med den installerade Streamlit-versionen. Uppgradera Streamlit eller använd en version med st.iframe.", "Kartet kan ikke vises med den installerte Streamlit-versjonen. Oppgrader Streamlit eller bruk en versjon med st.iframe.", "Kortet kan ikke vises med den installerede Streamlit-version. Opgrader Streamlit eller brug en version med st.iframe.", "The map cannot render with the installed Streamlit version. Upgrade Streamlit or use a version with st.iframe."),
    "analysis.select_layer": ("Välj minst ett kartlager.", "Velg minst ett kartlag.", "Vælg mindst ét kortlag.", "Select at least one map layer."),
    "analysis.no_map_center": ("Kartvyn saknar ett giltigt manifestdeklarerat centrum eller zoomläge. Inget kartlager visas.", "Kartvisningen mangler et gyldig manifestdeklarert sentrum eller zoomnivå. Ingen kartlag vises.", "Kortvisningen mangler et gyldigt manifestdeklareret centrum eller zoomniveau. Intet kortlag vises.", "The map view has no valid manifest-declared centre or zoom level. No map layer is shown."),
    "analysis.opacity_caption": ("Justera kartopacitet när lager behöver jämföras mer tekniskt.", "Juster kartopasiteten når lag må sammenlignes mer teknisk.", "Juster kortopaciteten, når lag skal sammenlignes mere teknisk.", "Adjust map opacity when layers need a more technical comparison."),
    "analysis.region_label": ("Region: {p0}", "Region: {p0}", "Region: {p0}", "Region: {p0}"),
    "analysis.manifest_review": (":material/warning: Manifest- och granskningsstatus", ":material/warning: Manifest- og granskningsstatus", ":material/warning: Manifest- og granskningsstatus", ":material/warning: Manifest and review status"),
    "analysis.shared_workspace": ("{p0} använder den gemensamma manifeststyrda arbetsytan. Endast deklarerade och validerade delar är aktiva.", "{p0} bruker den felles manifeststyrte arbeidsflaten. Bare deklarerte og validerte deler er aktive.", "{p0} bruger den fælles manifeststyrede arbejdsflade. Kun deklarerede og validerede dele er aktive.", "{p0} uses the shared manifest-driven workspace. Only declared and validated parts are active."),
    "analysis.separate_results": ("Vind och sol visas som separata tekniska resultat när respektive analys har tillämpats. Det gemensamma scenarioresultatet ingår inte i den här granskningsytan.", "Vind og sol vises som separate tekniske resultater når hver analyse er anvendt. Det felles scenarioresultatet inngår ikke i denne granskningsflaten.", "Vind og sol vises som separate tekniske resultater, når hver analyse er anvendt. Det fælles scenarieresultat indgår ikke i denne granskningsflade.", "Wind and solar are shown as separate technical results once each analysis is applied. The shared scenario result is not included in this review workspace."),
    "analysis.area_requirements": ("Etableringsytan visas när H3-geometrier, teknikytor och scenario finns.", "Etableringsarealet vises når H3-geometrier, teknologiarealer og scenario finnes.", "Etableringsarealet vises, når H3-geometrier, teknologiarealer og scenarie findes.", "Establishment area is shown when H3 geometries, technology areas and a scenario are available."),
    "analysis.manifest_domains": ("Arbetsyteprofilen är gemensam; varje geografi och analysdomän måste komma från den aktiva regionens manifest.", "Arbeidsflateprofilen er felles; hver geografi og hvert analysedomene må komme fra den aktive regionens manifest.", "Arbejdsfladeprofilen er fælles; hver geografi og analysedomæne skal komme fra den aktive regions manifest.", "The workspace profile is shared; every geography and analysis domain must come from the active region's manifest."),
    "analysis.scenario_review_only": ("Scenariokontraktet är tillämpat. Den här avgränsade granskningen visar inget gemensamt scenarioresultat.", "Scenariokontrakten er anvendt. Denne avgrensede granskingen viser ikke et felles scenarioresultat.", "Scenariekontrakten er anvendt. Denne afgrænsede granskning viser ikke et fælles scenarieresultat.", "The scenario contract is applied. This bounded review does not show a shared scenario result."),
    "analysis.energy_not_applied": ("Inget energiscenario är tillämpat. Energipanelen visar vilka underlag som är tillgängliga.", "Det er ikke brukt noe energiscenario. Energipanelet viser hvilke data som er tilgjengelige.", "Intet energiscenarie er anvendt. Energipanelet viser, hvilke data der er tilgængelige.", "No energy scenario is applied. The energy panel shows available inputs."),
    "analysis.acceptance_review_only": ("Kontraktet för social acceptans är tillämpat. Den här avgränsade granskningen kopplar det inte till ett gemensamt scenarioresultat.", "Kontrakten for sosial aksept er anvendt. Denne avgrensede granskingen kobler den ikke til et felles scenarioresultat.", "Kontrakten for social accept er anvendt. Denne afgrænsede granskning kobler den ikke til et fælles scenarieresultat.", "The social acceptance contract is applied. This bounded review does not connect it to a shared scenario result."),
    "analysis.acceptance_not_applied": ("Inget acceptansresultat är tillämpat. Acceptanspanelen visar vilka underlag som är tillgängliga.", "Det er ikke brukt noe akseptresultat. Akseptpanelet viser hvilke data som er tilgjengelige.", "Intet acceptresultat er anvendt. Acceptpanelet viser, hvilke data der er tilgængelige.", "No acceptance result is applied. The acceptance panel shows available inputs."),
    "analysis.landscape_invalid": ("Det deklarerade landskapslagret kunde inte valideras. Ingen annan regions landskap eller standardlager används.", "Det deklarerte landskapslaget kunne ikke valideres. Ingen annen regions landskap eller standardlag brukes.", "Det deklarerede landskabslag kunne ikke valideres. Ingen anden regions landskab eller standardlag bruges.", "The declared landscape layer could not be validated. No other region's landscape or default layer is used."),
    "analysis.manifest_workspace": ("{p0}: gemensam manifeststyrd arbetsyta. Varje regiondel aktiveras endast av sitt eget kontrakt.", "{p0}: felles manifeststyrt arbeidsflate. Hver regiondel aktiveres bare av sin egen kontrakt.", "{p0}: fælles manifeststyret arbejdsflade. Hver regionsdel aktiveres kun af sin egen kontrakt.", "{p0}: shared manifest-driven workspace. Each region component is enabled only by its own contract."),
    "analysis.landscape_control": ("Landskapstyper styrs i kartans lagerkontroll när ett validerat landskapskontrakt finns. Hexvisningen är alltid zoomanpassad.", "Landskapstyper styres i kartets lagkontroll når en validert landskapskontrakt finnes. Hexvisningen er alltid zoomtilpasset.", "Landskabstyper styres i kortets lagkontrol, når en valideret landskabskontrakt findes. Hexvisningen er altid zoomtilpasset.", "Landscape types are controlled in the map layer control when a validated landscape contract exists. Hex display always adapts to zoom."),
    "analysis.potential_requirements": ("Kartan visar inte potentiallager förrän minst H3-geometrier och relevant sol-/vindunderlag finns. Regionens standardcenter och zoom används när kartlager saknas.", "Kartet viser ikke potensiallag før minst H3-geometrier og relevante sol-/vinddata finnes. Regionens standardsentrum og zoom brukes når kartlag mangler.", "Kortet viser ikke potentialelag, før mindst H3-geometrier og relevante sol-/vinddata findes. Regionens standardcentrum og zoom bruges, når kortlag mangler.", "The map shows no potential layers until at least H3 geometries and relevant solar/wind inputs are available. The region's default centre and zoom are used when map layers are missing."),
    "analysis.trust_status": ("Tillitsstatus: {p0}. {p1}", "Tillitsstatus: {p0}. {p1}", "Tillidsstatus: {p0}. {p1}", "Trust status: {p0}. {p1}"),
    "analysis.locked_parts": ("Vissa delar saknar manifest, data, implementation eller regional validering och förblir därför låsta.", "Enkelte deler mangler manifest, data, implementering eller regional validering og forblir derfor låst.", "Visse dele mangler manifest, data, implementering eller regional validering og forbliver derfor låst.", "Some parts lack manifests, data, implementation or regional validation and therefore remain locked."),
    "analysis.shared_structure": ("Samma appstruktur används för alla regioner. Saknade delar visas som status, inte som krasch.", "Samme appstruktur brukes for alle regioner. Manglende deler vises som status, ikke som krasj.", "Samme appstruktur bruges for alle regioner. Manglende dele vises som status, ikke som nedbrud.", "All regions use the same application structure. Missing parts appear as status rather than a crash."),
    "analysis.contract_complete": ("Ett manifest räcker inte för att visa potential. Varje aktiverad del behöver ett komplett, reproducerbart och validerat kontrakt från källa till UI.", "Et manifest er ikke nok for å vise potensial. Hver aktivert del trenger en komplett, reproduserbar og validert kontrakt fra kilde til brukergrensesnitt.", "Et manifest er ikke nok til at vise potentiale. Hver aktiveret del kræver en komplet, reproducerbar og valideret kontrakt fra kilde til brugergrænseflade.", "A manifest alone is insufficient to show potential. Every enabled component needs a complete, reproducible and validated contract from source to UI."),
    "analysis.review_geometry": ("Validerad granskningsgeometri · tillitsnivå: {p0}.", "Validert granskningsgeometri · tillitsnivå: {p0}.", "Valideret granskningsgeometri · tillidsniveau: {p0}.", "Validated review geometry · trust level: {p0}."),
    "analysis.no_map_layers": ("Inga kartlager är tända.", "Ingen kartlag er slått på.", "Ingen kortlag er slået til.", "No map layers are enabled."),
    "analysis.wind_solar_applied": ("Vind och sol har tillämpats och visas som separata tekniska resultat.", "Vind og sol er anvendt og vises som separate tekniske resultater.", "Vind og sol er anvendt og vises som separate tekniske resultater.", "Wind and solar are applied and shown as separate technical results."),
    "analysis.group_enable_defaults": ("Aktiverar {p0} med gruppens ordinarie datakälla eller datakällor. Öppna Datakällor om du vill granska eller ändra urvalet.", "Aktiverer {p0} med gruppens vanlige datakilde eller datakilder. Åpne Datakilder for å granske eller endre utvalget.", "Aktiverer {p0} med gruppens normale datakilde eller datakilder. Åbn Datakilder for at granske eller ændre udvalget.", "Enables {p0} with the group's default data source or sources. Open Data sources to review or change the selection."),
    "analysis.group_enable_sources": ("Aktiverar {p0} först när minst en datakälla också är vald. Öppna Datakällor och välj källa innan du använder ändringarna.", "Aktiverer {p0} først når minst én datakilde også er valgt. Åpne Datakilder og velg en kilde før du bruker endringene.", "Aktiverer {p0} først, når mindst én datakilde også er valgt. Åbn Datakilder og vælg en kilde, før du anvender ændringerne.", "Enables {p0} only when at least one data source is also selected. Open Data sources and select a source before applying changes."),
    "analysis.data_sources": ("Datakällor", "Datakilder", "Datakilder", "Data sources"),
    "analysis.no_source_layers": ("Inga källager är kopplade till {p0}.", "Ingen kildelag er knyttet til {p0}.", "Ingen kildelag er knyttet til {p0}.", "No source layers are associated with {p0}."),
    "analysis.vector_opacity": ("Opacitet polygoner och linjer", "Opasitet for polygoner og linjer", "Opacitet for polygoner og linjer", "Polygon and line opacity"),
    "analysis.opacity_help": ("0.1 är nästan genomskinligt. 0.9 är nästan helt fyllt.", "0.1 er nesten gjennomsiktig. 0.9 er nesten helt fylt.", "0.1 er næsten gennemsigtigt. 0.9 er næsten helt udfyldt.", "0.1 is almost transparent. 0.9 is almost fully filled."),
    "analysis.timing_help": ("Tidslogg för den senaste körningen. Den mäter Python- och HTML-byggsteg; webbläsarens egen ritning kan tillkomma.", "Tidslogg for den siste kjøringen. Den måler Python- og HTML-byggtrinn; nettleserens egen tegning kan komme i tillegg.", "Tidslog for den seneste kørsel. Den måler Python- og HTML-byggetrin; browserens egen tegning kan komme oveni.", "Timing log for the latest run. It measures Python and HTML build steps; browser rendering may add time."),
    "analysis.timing_summary": ("Summa mätta steg: {p0:.2f} s. Långsammast: {p1} ({p2:.2f} s).", "Sum målte trinn: {p0:.2f} s. Tregest: {p1} ({p2:.2f} s).", "Sum af målte trin: {p0:.2f} s. Langsomst: {p1} ({p2:.2f} s).", "Total measured steps: {p0:.2f} s. Slowest: {p1} ({p2:.2f} s)."),
    "analysis.display_reuse": ("Visningsändring ({p0}): återanvänder senaste beräknade karta och potential. Ingen ny potentialberäkning körs.", "Visningsendring ({p0}): gjenbruker sist beregnede kart og potensial. Ingen ny potensialberegning kjøres.", "Visningsændring ({p0}): genbruger senest beregnede kort og potentiale. Ingen ny potentialeberegning køres.", "Display change ({p0}): reuses the latest calculated map and potential. No new potential calculation runs."),
    "analysis.display_reused": ("Den senaste visningsändringen återanvände redan beräknade resultat. Samma princip används nu för språk, paneler, kartvy och opacitet.", "Den siste visningsendringen gjenbrukte allerede beregnede resultater. Samme prinsipp brukes nå for språk, paneler, kartvisning og opasitet.", "Den seneste visningsændring genbrugte allerede beregnede resultater. Samme princip bruges nu for sprog, paneler, kortvisning og opacitet.", "The latest display change reused existing calculated results. The same principle applies to language, panels, map view and opacity."),
    "analysis.map_review": ("Kartgranskning", "Kartgransking", "Kortgranskning", "Map review"),
    "analysis.display_only": ("Dessa val ändrar bara kartan. De påverkar inte analysen eller resultattabellen.", "Disse valgene endrer bare kartet. De påvirker ikke analysen eller resultattabellen.", "Disse valg ændrer kun kortet. De påvirker ikke analysen eller resultattabellen.", "These options change only the map. They do not affect the analysis or result table."),
    "analysis.show_source": ("Visa källa i kartan", "Vis kilde i kartet", "Vis kilde i kortet", "Show source on the map"),
    "analysis.source_manifest": ("Källan läses från solanalysens manifest.", "Kilden leses fra solanalysens manifest.", "Kilden læses fra solanalysens manifest.", "The source is read from the solar analysis manifest."),
    "analysis.show_buffer": ("Visa buffert i kartan", "Vis buffer i kartet", "Vis buffer i kortet", "Show buffer on the map"),
    "analysis.buffer_solar": ("Bufferten byggs från solmanifestets tillämpade källor och analysavstånd.", "Bufferen bygges fra solmanifestets anvendte kilder og analyseavstander.", "Bufferen bygges fra solmanifestets anvendte kilder og analyseafstande.", "The buffer is built from the solar manifest's applied sources and analysis distances."),
    "analysis.guide_unavailable": ("Guiden kräver Streamlit components och kan inte visas i den här miljön.", "Veiledningen krever Streamlit-komponenter og kan ikke vises i dette miljøet.", "Guiden kræver Streamlit-komponenter og kan ikke vises i dette miljø.", "The guide requires Streamlit components and cannot be shown in this environment."),
    "analysis.buffer_vector": ("Bufferten byggs direkt från de manifestdeklarerade vektorkällorna i regionens meterbaserade CRS.", "Bufferen bygges direkte fra de manifestdeklarerte vektorkildene i regionens meterbaserte CRS.", "Bufferen bygges direkte fra de manifestdeklarerede vektorkilder i regionens meterbaserede CRS.", "The buffer is built directly from manifest-declared vector sources in the region's metre-based CRS."),
    "analysis.buffer_ready": ("Buffertvisning aktiveras när gruppens vektorkontrakt har migrerats.", "Buffervisning aktiveres når gruppens vektorkontrakt er migrert.", "Buffervisning aktiveres, når gruppens vektorkontrakt er migreret.", "Buffer display is enabled once the group's vector contract has migrated."),
    "analysis.wind_source_layers": ("Vind: aktiva källager", "Vind: aktive kildelag", "Vind: aktive kildelag", "Wind: active source layers"),
    "analysis.wind_buffers": ("Vind: buffertgrupper", "Vind: buffergrupper", "Vind: buffergrupper", "Wind: buffer groups"),
    "analysis.wind_mean": ("Vind: genomsnittlig potential per analyscell", "Vind: gjennomsnittlig potensial per analysecelle", "Vind: gennemsnitligt potentiale per analysecelle", "Wind: mean potential per analysis cell"),
    "analysis.reset_filters": ("Nollställ filter", "Nullstill filtre", "Nulstil filtre", "Reset filters"),
    "analysis.clear_wind_filters": ("Ta bort alla vindfilter", "Fjern alle vindfiltre", "Fjern alle vindfiltre", "Remove all wind filters"),
    "analysis.clear_solar_filters": ("Ta bort alla solfilter", "Fjern alle solfiltre", "Fjern alle solfiltre", "Remove all solar filters"),
    "analysis.restore_start_values": ("Återställ startvärden", "Gjenopprett startverdier", "Gendan startværdier", "Restore initial settings"),
    "analysis.active_filters": ("{p0} aktiva filter.", "{p0} aktive filtre.", "{p0} aktive filtre.", "{p0} active filters."),
    "analysis.filter_binding": ("Ändringarna kunde inte bindas till analysmanifestet. Den senast tillämpade konfigurationen behålls.", "Endringene kunne ikke knyttes til analysemanifestet. Den sist anvendte konfigurasjonen beholdes.", "Ændringerne kunne ikke knyttes til analysemanifestet. Den senest anvendte konfiguration bevares.", "Changes could not be bound to the analysis manifest. The last applied configuration is retained."),
    "analysis.source_selection_empty": ("Ingen datakälla valdes för {p0}. Öppna Datakällor i gruppen, välj minst en datakälla och tryck sedan på Använd ändringar.", "Ingen datakilde er valgt for {p0}. Åpne Datakilder i gruppen, velg minst én datakilde og trykk deretter på Bruk endringer.", "Ingen datakilde er valgt for {p0}. Åbn Datakilder i gruppen, vælg mindst én datakilde og tryk derefter på Anvend ændringer.", "No data source was selected for {p0}. Open Data sources in the group, select at least one source and then press Apply changes."),
    "analysis.no_changes": ("Inga ändringar tillämpades. Välj minst en grupp och minst en datakälla i gruppen innan du använder ändringarna.", "Ingen endringer ble anvendt. Velg minst én gruppe og minst én datakilde i gruppen før du bruker endringene.", "Ingen ændringer blev anvendt. Vælg mindst én gruppe og mindst én datakilde i gruppen, før du anvender ændringerne.", "No changes were applied. Select at least one group and at least one data source in that group before applying changes."),
    "analysis.step_one": ("Steg 1 av 3: kartan visar den neutrala R{p0}-domänen. Steg 2 är att fylla i formuläret; kartan ändras först när Använd ändringar skickar en manifestbunden request.", "Trinn 1 av 3: kartet viser det nøytrale R{p0}-domenet. Trinn 2 er å fylle ut skjemaet; kartet endres først når Bruk endringer sender en manifestbundet forespørsel.", "Trin 1 af 3: kortet viser det neutrale R{p0}-domæne. Trin 2 er at udfylde formularen; kortet ændres først, når Anvend ændringer sender en manifestbundet forespørgsel.", "Step 1 of 3: the map shows the neutral R{p0} domain. Step 2 is completing the form; the map changes only when Apply changes sends a manifest-bound request."),
    "analysis.review_status": (":material/warning: Granskningsstatus", ":material/warning: Granskningsstatus", ":material/warning: Granskningsstatus", ":material/warning: Review status"),
    "analysis.shared_pipeline": ("Källor och resultat kommer från samma manifestbundna request-, motor- och kartkedja som programytan i övrigt.", "Kilder og resultater kommer fra den samme manifestbundne forespørsels-, motor- og kartkjeden som resten av programmet.", "Kilder og resultater kommer fra den samme manifestbundne forespørgsels-, motor- og kortkæde som resten af programmet.", "Sources and results use the same manifest-bound request, engine and map pipeline as the rest of the application."),
    "analysis.map_locked": ("Regionens kartdomän är inte tekniskt klar för den här arbetsytan. Kartan förblir låst.", "Regionens kartdomene er ikke teknisk klart for denne arbeidsflaten. Kartet forblir låst.", "Regionens kortdomæne er ikke teknisk klart til denne arbejdsflade. Kortet forbliver låst.", "The region's map domain is not technically ready for this workspace. The map remains locked."),
    "analysis.workspace_invalid": ("Den deklarerade arbetsytevyn kunde inte valideras. Ingen annan regions geometri eller standardberäkning används.", "Den deklarerte arbeidsflatevisningen kunne ikke valideres. Ingen annen regions geometri eller standardberegning brukes.", "Den deklarerede arbejdsfladevisning kunne ikke valideres. Ingen anden regions geometri eller standardberegning bruges.", "The declared workspace view could not be validated. No other region's geometry or default calculation is used."),
    "analysis.technical_results": ("Tekniska resultat", "Tekniske resultater", "Tekniske resultater", "Technical results"),
    "analysis.remaining_area": ("Etableringsytan visar hur stor del av den modellerade landytan som återstår efter valda filter. Delvis täckta celler behåller sin återstående andel; överlappande buffertar räknas en gång.", "Etableringsarealet viser hvor mye av det modellerte landarealet som gjenstår etter valgte filtre. Delvis dekkede celler beholder sin gjenværende andel; overlappende buffere telles én gang.", "Etableringsarealet viser, hvor meget af det modellerede landareal der er tilbage efter valgte filtre. Delvist dækkede celler beholder deres resterende andel; overlappende buffere tælles én gang.", "Establishment area shows how much modelled land remains after selected filters. Partly covered cells retain their remaining share; overlapping buffers are counted once."),
    "analysis.cell_tables": ("Resultatens celltabeller", "Resultatenes celletabeller", "Resultaternes celletabeller", "Result cell tables"),
    "analysis.cell_tables_help": ("Tabellerna är signerade mot samma request och geometri som kartan. Detaljvyn visar ett begränsat utsnitt; totalsiffrorna ovan bygger på hela resultatet.", "Tabellene er signert mot samme forespørsel og geometri som kartet. Detaljvisningen viser et begrenset utsnitt; totalsummene ovenfor bygger på hele resultatet.", "Tabellerne er signeret mod samme forespørgsel og geometri som kortet. Detaljevisningen viser et begrænset udsnit; totalsummerne ovenfor bygger på hele resultatet.", "Tables are signed against the same request and geometry as the map. The detail view shows a limited sample; the totals above use the complete result."),
    "analysis.filter_diagnostics": ("Teknisk filterdiagnostik", "Teknisk filterdiagnostikk", "Teknisk filterdiagnostik", "Technical filter diagnostics"),
    "analysis.filter_diagnostics_help": ("Dessa mått klassar hela celler efter filtervillkor och avstånd. De visar inte hur mycket etableringsyta som återstår.", "Disse målene klassifiserer hele celler etter filtervilkår og avstander. De viser ikke hvor mye etableringsareal som gjenstår.", "Disse mål klassificerer hele celler efter filtervilkår og afstande. De viser ikke, hvor meget etableringsareal der er tilbage.", "These measures classify whole cells by filter conditions and distances. They do not show remaining establishment area."),
    "analysis.rooftop_layers": ("Kartlager: schablonhexar och gemensam potentiell etableringsyta.", "Kartlag: estimathex og felles potensielt etableringsareal.", "Kortlag: estimathex og fælles potentielt etableringsareal.", "Map layers: schematic estimate hexes and shared potential establishment area."),
    "analysis.apply_rooftop": ("Använd ändringar för taksol", "Bruk endringer for sol på tak", "Anvend ændringer for sol på tag", "Apply rooftop solar changes"),
    "analysis.rooftop_help": ("{p0} Småskalig sol är en schablon från befolkning per hex. Den visas som små gula schablonhexar, inte som faktiska takpolygoner eller sammanhängande markyta.", "{p0} Småskala sol er et estimat fra befolkning per hex. Den vises som små gule estimathex, ikke som faktiske takpolygoner eller sammenhengende landareal.", "{p0} Småskala sol er et estimat fra befolkning per hex. Den vises som små gule estimathex, ikke som faktiske tagpolygoner eller sammenhængende landareal.", "{p0} Small-scale solar is a population-based estimate per hex. It is shown as small yellow schematic hexes, not actual rooftop polygons or contiguous land area."),
    "analysis.rooftop_saved_invalid": ("Det sparade taksolvalet kunde inte valideras. Ingen beräkning eller fallback används.", "Det lagrede taksolvalget kunne ikke valideres. Ingen beregning eller reserve brukes.", "Det gemte tag-solvalg kunne ikke valideres. Ingen beregning eller reserve bruges.", "The saved rooftop solar selection could not be validated. No calculation or fallback is used."),
    "analysis.rooftop_changes_invalid": ("Taksoländringarna kunde inte bindas till manifestet. Det senast tillämpade valet behålls.", "Taksolendringene kunne ikke knyttes til manifestet. Det sist anvendte valget beholdes.", "Tag-solændringerne kunne ikke knyttes til manifestet. Det senest anvendte valg bevares.", "Rooftop solar changes could not be bound to the manifest. The last applied selection is retained."),
    "analysis.scenario_locked": ("Scenario, markintensitet och teknikandelar förblir låsta tills regionens kontrakt är komplett och validerat.", "Scenario, arealintensitet og teknologiandeler forblir låst til regionens kontrakt er komplett og validert.", "Scenarie, arealintensitet og teknologiandele forbliver låst, indtil regionens kontrakt er komplet og valideret.", "Scenario, land intensity and technology shares remain locked until the region's contract is complete and validated."),
    "analysis.year": ("Årtal", "Årstall", "Årstal", "Year"),
    "analysis.scenario_saved_invalid": ("Det sparade scenariovalet kunde inte valideras. Ingen beräkning eller fallback används.", "Det lagrede scenariovalget kunne ikke valideres. Ingen beregning eller reserve brukes.", "Det gemte scenarievalg kunne ikke valideres. Ingen beregning eller reserve bruges.", "The saved scenario selection could not be validated. No calculation or fallback is used."),
    "analysis.year_help": ("Årtalet laddar modellens kapacitet och vind/sol-fördelning. Reglaget under kartan låter dig prova en egen mix.", "Årstallet laster modellens kapasitet og vind/sol-fordeling. Skyveknappen under kartet lar deg prøve en egen miks.", "Årstallet indlæser modellens kapacitet og vind/sol-fordeling. Skyderen under kortet lader dig afprøve et eget mix.", "The year loads the model's capacity and wind/solar split. The slider below the map lets you try a custom mix."),
    "analysis.energy_mix_help": ("Energimixen styrs med reglaget direkt under kartan. Vind och sol är kopplade och summerar alltid till exakt 100 %.", "Energimiksen styres med skyveknappen rett under kartet. Vind og sol er koblet og summerer alltid til nøyaktig 100 %.", "Energimixet styres med skyderen direkte under kortet. Vind og sol er koblet og summerer altid til præcis 100 %.", "The energy mix is controlled by the slider directly below the map. Wind and solar are linked and always sum to exactly 100 %."),
    "analysis.capacity_mix": ("Kapacitetsmix", "Kapasitetsmiks", "Kapacitetsmix", "Capacity mix"),
    "analysis.installed_capacity": ("Installerad effekt", "Installert effekt", "Installeret effekt", "Installed capacity"),
    "analysis.independent_capacity_help": (
        "Välj total effekt för vindkraft och marksol oberoende av varandra. Befintlig kapacitet ingår i referensvärdena.",
        "Velg samlet effekt for vindkraft og sol på bakken uavhengig av hverandre. Eksisterende kapasitet inngår i referanseverdiene.",
        "Vælg samlet effekt for vindkraft og sol på land uafhængigt af hinanden. Eksisterende kapacitet indgår i referenceværdierne.",
        "Choose total wind and ground-mounted solar capacity independently. The reference values include existing capacity.",
    ),
    "analysis.wind_capacity_mw": ("Vindkraft (MW)", "Vindkraft (MW)", "Vindkraft (MW)", "Wind power (MW)"),
    "analysis.ground_solar_capacity_mw": ("Marksol (MW)", "Sol på bakken (MW)", "Sol på land (MW)", "Ground-mounted solar (MW)"),
    "analysis.capacity_reference_help": (
        "Markeringarna visar EML:s referensår. Resultaten uppdateras när du tillämpar värdena.",
        "Markeringene viser EMLs referanseår. Resultatene oppdateres når du bruker verdiene.",
        "Markeringerne viser EML's referenceår. Resultaterne opdateres, når du anvender værdierne.",
        "The markers show EML's reference years. Results update when you apply the values.",
    ),
    "analysis.capacity_applied": (
        "Tillämpat: {p0:g} MW vind · {p1:g} MW marksol · totalt {p2:g} MW.",
        "Anvendt: {p0:g} MW vind · {p1:g} MW sol på bakken · totalt {p2:g} MW.",
        "Anvendt: {p0:g} MW vind · {p1:g} MW sol på land · i alt {p2:g} MW.",
        "Applied: {p0:g} MW wind · {p1:g} MW ground-mounted solar · total {p2:g} MW.",
    ),
    "analysis.capacity_no_demand": (
        "Ingen kapacitet vald – inget ytbehov. Årsproduktion saknas i underlaget.",
        "Ingen kapasitet valgt – intet arealbehov. Årsproduksjon mangler i datagrunnlaget.",
        "Ingen kapacitet valgt – intet arealbehov. Årsproduktion mangler i datagrundlaget.",
        "No capacity selected – no area demand. Annual generation is unavailable in the inputs.",
    ),
    "analysis.reset_capacity": ("Återställ standardvärden", "Gjenopprett standardverdier", "Gendan standardværdier", "Restore default values"),
    "analysis.capacity_changes_invalid": (
        "Kapacitetsändringarna kunde inte tillämpas. De senast tillämpade värdena behålls.",
        "Kapasitetsendringene kunne ikke anvendes. De sist anvendte verdiene beholdes.",
        "Kapacitetsændringerne kunne ikke anvendes. De senest anvendte værdier bevares.",
        "Capacity changes could not be applied. The last applied values are retained.",
    ),
    "analysis.custom_capacity_help": (
        "Egen kapacitet · modellens arealfaktorer används. Årsproduktion saknas.",
        "Egen kapasitet · modellens arealfaktorer brukes. Årsproduksjon mangler.",
        "Egen kapacitet · modellens arealfaktorer anvendes. Årsproduktion mangler.",
        "Custom capacity · the model's area factors are used. Annual generation is unavailable.",
    ),
    "analysis.custom_capacity": ("Egen kapacitet", "Egen kapasitet", "Egen kapacitet", "Custom capacity"),
    "analysis.selected_capacity": (
        "Vald kapacitet · {p0:g} MW vind / {p1:g} MW marksol · källa {p2}",
        "Valgt kapasitet · {p0:g} MW vind / {p1:g} MW sol på bakken · kilde {p2}",
        "Valgt kapacitet · {p0:g} MW vind / {p1:g} MW sol på land · kilde {p2}",
        "Selected capacity · {p0:g} MW wind / {p1:g} MW ground-mounted solar · source {p2}",
    ),
    "analysis.latest_capacity": (
        "Senaste kapacitetsberäkning: {p0} · {p1:g} MW vind / {p2:g} MW marksol.",
        "Siste kapasitetsberegning: {p0} · {p1:g} MW vind / {p2:g} MW sol på bakken.",
        "Seneste kapacitetsberegning: {p0} · {p1:g} MW vind / {p2:g} MW sol på land.",
        "Latest capacity calculation: {p0} · {p1:g} MW wind / {p2:g} MW ground-mounted solar.",
    ),
    "analysis.capacity_mix_help": ("Fördela årets totala installerade effekt mellan vind och sol. Årsproduktion saknas i underlaget.", "Fordel årets samlede installerte effekt mellom vind og sol. Årsproduksjon mangler i datagrunnlaget.", "Fordel årets samlede installerede effekt mellem vind og sol. Årsproduktion mangler i datagrundlaget.", "Split the year's total installed power between wind and solar. Annual generation is unavailable in the inputs."),
    "analysis.energy_split_help": ("Fördela scenariots totala energimängd mellan vind och sol. Andelarna är kopplade och summerar alltid till 100 %.", "Fordel scenarioets samlede energimengde mellom vind og sol. Andelene er koblet og summerer alltid til 100 %.", "Fordel scenariets samlede energimængde mellem vind og sol. Andelene er koblet og summerer altid til 100 %.", "Split the scenario's total energy between wind and solar. The shares are linked and always sum to 100 %."),
    "analysis.wind_capacity_share": ("Vindandel av installerad effekt (%)", "Vindandel av installert effekt (%)", "Vindandel af installeret effekt (%)", "Wind share of installed power (%)"),
    "analysis.linked_shares": ("När vindandelen ökar minskar solandelen lika mycket.", "Når vindandelen øker, minker solandelen like mye.", "Når vindandelen øges, mindskes solandelen lige så meget.", "When wind share increases, solar share decreases by the same amount."),
    "analysis.use_custom_mix": ("Använd egen mix", "Bruk egen miks", "Anvend eget mix", "Apply custom mix"),
    "analysis.model_mix": ("Modellens fördelning", "Modellens fordeling", "Modellens fordeling", "Model allocation"),
    "analysis.custom_mix_fixed": ("Egen mix – årets totala MW är oförändrat.", "Egen miks – årets samlede MW er uendret.", "Eget mix – årets samlede MW er uændret.", "Custom mix – the year's total MW is unchanged."),
    "analysis.reset_mix": ("Återställ modellens mix", "Gjenopprett modellens miks", "Gendan modellens mix", "Restore model mix"),
    "analysis.mix_unavailable": ("Energimixen är inte tillgänglig för den valda regionen.", "Energimiksen er ikke tilgjengelig for den valgte regionen.", "Energimixet er ikke tilgængeligt for den valgte region.", "The energy mix is unavailable for the selected region."),
    "analysis.scenario_selected": ("Valt: {p0} · markintensitet {p1} · modellkälla {p2}, {p3}.", "Valgt: {p0} · arealintensitet {p1} · modellkilde {p2}, {p3}.", "Valgt: {p0} · arealintensitet {p1} · modelkilde {p2}, {p3}.", "Selected: {p0} · land intensity {p1} · model source {p2}, {p3}."),
    "analysis.total_demand": ("Totalt: {p0:.2f} TWh · bruttoytbehov {p1:.2f} km².", "Totalt: {p0:.2f} TWh · bruttoarealbehov {p1:.2f} km².", "I alt: {p0:.2f} TWh · bruttoarealbehov {p1:.2f} km².", "Total: {p0:.2f} TWh · gross area demand {p1:.2f} km²."),
    "analysis.capacity_factors": ("Vind: {p0:g} MW/km². Marksol: {p1:g} m²/MW. Årsproduktion saknas i underlaget.", "Vind: {p0:g} MW/km². Sol på bakken: {p1:g} m²/MW. Årsproduksjon mangler i datagrunnlaget.", "Vind: {p0:g} MW/km². Sol på land: {p1:g} m²/MW. Årsproduktion mangler i datagrundlaget.", "Wind: {p0:g} MW/km². Ground-mounted solar: {p1:g} m²/MW. Annual generation is unavailable in the inputs."),
    "analysis.source_status": (":material/warning: Källstatus och begränsningar", ":material/warning: Kildestatus og begrensninger", ":material/warning: Kildestatus og begrænsninger", ":material/warning: Source status and limitations"),
    "analysis.source_trust": ("Status: {p0} · användning: {p1} · regionalt accepterad: {p2}.", "Status: {p0} · bruk: {p1} · regionalt akseptert: {p2}.", "Status: {p0} · brug: {p1} · regionalt accepteret: {p2}.", "Status: {p0} · use: {p1} · regionally accepted: {p2}."),
    "analysis.source_identity": ("Källa: {p0} (`{p1}`).", "Kilde: {p0} (`{p1}`).", "Kilde: {p0} (`{p1}`).", "Source: {p0} (`{p1}`)."),
    "analysis.reset_acceptance": ("Nollställ social acceptans", "Nullstill sosial aksept", "Nulstil social accept", "Reset social acceptance"),
    "analysis.acceptance_locked": ("Social acceptans förblir låst tills regionen deklarerar och validerar sitt eget datakontrakt.", "Sosial aksept forblir låst til regionen deklarerer og validerer sin egen datakontrakt.", "Social accept forbliver låst, indtil regionen deklarerer og validerer sin egen datakontrakt.", "Social acceptance remains locked until the region declares and validates its own data contract."),
    "analysis.acceptance_scenario": ("Acceptansscenario", "Akseptscenario", "Acceptscenarie", "Acceptance scenario"),
    "analysis.acceptance_allocation": ("Acceptansstyrning av scenarioyta inom potentialen", "Akseptstyring av scenarioareal innenfor potensialet", "Acceptstyring af scenarieareal inden for potentialet", "Acceptance influence on scenario area within the potential"),
    "analysis.acceptance_saved_invalid": ("Det sparade acceptansvalet kunde inte valideras. Ingen äldre state eller fallback används.", "Det lagrede akseptvalget kunne ikke valideres. Ingen tidligere tilstand eller reserve brukes.", "Det gemte acceptvalg kunne ikke valideres. Ingen tidligere tilstand eller reserve bruges.", "The saved acceptance selection could not be validated. No previous state or fallback is used."),
    "analysis.acceptance_changes_invalid": ("Acceptansändringarna kunde inte bindas till manifestet. Det senast tillämpade valet behålls.", "Akseptendringene kunne ikke knyttes til manifestet. Det sist anvendte valget beholdes.", "Acceptændringerne kunne ikke knyttes til manifestet. Det senest anvendte valg bevares.", "Acceptance changes could not be bound to the manifest. The last applied selection is retained."),
    "analysis.replacement": ("Ersättningsvillkor: {p0}", "Vilkår for erstatning: {p0}", "Betingelser for erstatning: {p0}", "Replacement condition: {p0}"),
    "analysis.loading": ("Beräknar karta och potential...", "Beregner kart og potensial...", "Beregner kort og potentiale...", "Calculating map and potential..."),
    "analysis.loading_help": ("Visar klara beräkningssteg, inte procent av väntetiden. Tiden uppdateras när ett steg avslutas; långa steg kan stå still. Vid längre väntan: kaffe, teknisk paus, frisk luft eller kort meditation.", "Viser fullførte beregningstrinn, ikke prosent av ventetiden. Tiden oppdateres når et trinn avsluttes; lange trinn kan stå stille. Ved lengre ventetid: kaffe, teknisk pause, frisk luft eller kort meditasjon.", "Viser afsluttede beregningstrin, ikke procent af ventetiden. Tiden opdateres, når et trin afsluttes; lange trin kan stå stille. Ved længere ventetid: kaffe, teknisk pause, frisk luft eller kort meditation.", "Shows completed calculation steps, not a percentage of waiting time. Time updates when a step finishes; long steps may appear stationary. During longer waits: coffee, a technical break, fresh air or brief meditation."),
    "analysis.landscape_zoom": ("Landskapstyper tänds och släcks i kartans lagerkontroll. Hexupplösningen zoomanpassas inom regionens deklarerade nivåer.", "Landskapstyper slås på og av i kartets lagkontroll. Hexoppløsningen tilpasses zoom innenfor regionens deklarerte nivåer.", "Landskabstyper slås til og fra i kortets lagkontrol. Hexopløsningen tilpasses zoom inden for regionens deklarerede niveauer.", "Landscape types are switched on and off in the map layer control. Hex resolution adapts to zoom within the region's declared levels."),
    "analysis.future_ivl": ("Planerad framtida regional dataleverantör: [IVL Svenska Miljöinstitutet]({p0})", "Planlagt framtidig regional dataleverandør: [IVL Svenska Miljöinstitutet]({p0})", "Planlagt fremtidig regional dataleverandør: [IVL Svenska Miljöinstitutet]({p0})", "Planned future regional data provider: [IVL Svenska Miljöinstitutet]({p0})"),
    "analysis.landscape_not_shown": ("Landskapstyper kunde inte valideras och visas inte i kartan.", "Landskapstyper kunne ikke valideres og vises ikke i kartet.", "Landskabstyper kunne ikke valideres og vises ikke i kortet.", "Landscape types could not be validated and are not shown on the map."),
    "analysis.solar_shared_path": ("Solens standardgrupper kommer från regionens solmanifest och använder samma formulär-, apply- och resetväg som övriga analyser.", "Solens standardgrupper kommer fra regionens solmanifest og bruker samme vei for skjema, anvendelse og nullstilling som øvrige analyser.", "Solens standardgrupper kommer fra regionens solmanifest og bruger samme vej for formular, anvendelse og nulstilling som øvrige analyser.", "Solar standard groups come from the region's solar manifest and use the same form, apply and reset path as other analyses."),
    "analysis.performance_help": ("Prestandadiagnostik för optimering. Faktisk tid visas per steg och jämförs med historisk median när appen har hunnit samla körhistorik.", "Ytelsesdiagnostikk for optimalisering. Faktisk tid vises per trinn og sammenlignes med historisk median når appen har samlet kjøringshistorikk.", "Ydeevnediagnostik til optimering. Faktisk tid vises per trin og sammenlignes med historisk median, når appen har samlet kørselshistorik.", "Performance diagnostics for optimization. Actual time is shown per step and compared with the historical median once the app has collected run history."),
    "analysis.slowest_step": ("Långsammaste steg denna körning: {p0} ({p1:.1f} s).", "Tregeste trinn denne kjøringen: {p0} ({p1:.1f} s).", "Langsomste trin denne kørsel: {p0} ({p1:.1f} s).", "Slowest step this run: {p0} ({p1:.1f} s)."),
    "analysis.latest_energy": ("Senaste energiberäkning: {p0} · scenario {p1} · mix {p2:.0f}% vind / {p3:.0f}% sol.", "Siste energiberegning: {p0} · scenario {p1} · miks {p2:.0f}% vind / {p3:.0f}% sol.", "Seneste energiberegning: {p0} · scenarie {p1} · mix {p2:.0f}% vind / {p3:.0f}% sol.", "Latest energy calculation: {p0} · scenario {p1} · mix {p2:.0f}% wind / {p3:.0f}% solar."),
    "analysis.active_label": ("Aktiv {p0}", "Aktiv {p0}", "Aktiv {p0}", "Active {p0}"),
    "analysis.solar_polygon": ("{p0} visas som solpolygon och kan ingå i {p1}.", "{p0} vises som solpolygon og kan inngå i {p1}.", "{p0} vises som solpolygon og kan indgå i {p1}.", "{p0} is shown as a solar polygon and may be included in {p1}."),
    "analysis.wind_unfiltered": ("Inga vindfilter är valda: ofiltrerad vindpotential används som startläge.", "Ingen vindfiltre er valgt: ufiltrert vindpotensial brukes som utgangspunkt.", "Ingen vindfiltre er valgt: ufiltreret vindpotentiale bruges som udgangspunkt.", "No wind filters are selected: unfiltered wind potential is used as the starting point."),
    "analysis.latest_html_layers": ("Kartlager i senaste HTML-renderingen.", "Kartlag i siste HTML-visning.", "Kortlag i seneste HTML-visning.", "Map layers in the latest HTML rendering."),
    "analysis.small_solar_total": ("Total småskalig solyta: {p0:.2f} km²; solbehov efter tak: {p1:.2f} km².", "Samlet småskala solareal: {p0:.2f} km²; solbehov etter tak: {p1:.2f} km².", "Samlet småskala solareal: {p0:.2f} km²; solbehov efter tag: {p1:.2f} km².", "Total small-scale solar area: {p0:.2f} km²; solar demand after rooftop solar: {p1:.2f} km²."),
    "analysis.solar_population_distance": ("Avstånd till befolkning är {p0:.0f} m för storskalig sol.", "Avstand til befolkning er {p0:.0f} m for storskala sol.", "Afstand til befolkning er {p0:.0f} m for storskala sol.", "Distance to population is {p0:.0f} m for large-scale solar."),
    "analysis.active_sublayers": ("{p0}: {p1} del-lager är aktiva med {p2:.0f} m buffert{p3}.", "{p0}: {p1} dellag er aktive med {p2:.0f} m buffer{p3}.", "{p0}: {p1} dellag er aktive med {p2:.0f} m buffer{p3}.", "{p0}: {p1} sublayers are active with a {p2:.0f} m buffer{p3}."),
})

# Map controls, legends and lazy popup presentation.
MESSAGES.update({'map.copy_001': ('Teckenförklaring', 'Tegnforklaring', 'Signaturforklaring', 'Legend'),
 'map.copy_002': ('Panorera kartan', 'Panorer kartet', 'Panorer kortet', 'Pan the map'),
 'map.copy_003': ('Granska potentiell etableringsyta',
                  'Undersøk potensielt etableringsareal',
                  'Undersøg potentielt etableringsareal',
                  'Inspect potential development area'),
 'map.copy_004': ('Zooma in', 'Zoom inn', 'Zoom ind', 'Zoom in'),
 'map.copy_005': ('Zooma ut', 'Zoom ut', 'Zoom ud', 'Zoom out'),
 'map.copy_006': ('Satellit', 'Satellitt', 'Satellit', 'Satellite'),
 'map.copy_007': ('Kartan kunde inte laddas', 'Kartet kunne ikke lastes', 'Kortet kunne ikke indlæses', 'The map could not be loaded'),
 'map.copy_008': ('Den här webbläsaren kan inte läsa kartans komprimerade data',
                  'Denne nettleseren kan ikke lese kartets komprimerte data',
                  'Denne browser kan ikke læse kortets komprimerede data',
                  'This browser cannot read the compressed map data'),
 'map.copy_009': ('Kartans överföring är ogiltig', 'Kartoverføringen er ugyldig', 'Kortoverførslen er ugyldig', 'The map transfer is invalid'),
 'map.copy_010': ('Kartans datalängd stämmer inte', 'Kartets datalengde stemmer ikke', 'Kortets datalængde stemmer ikke', 'The map data length does not match'),
 'map.copy_011': ('Kartans kontrollsumma stämmer inte',
                  'Kartets kontrollsum stemmer ikke',
                  'Kortets kontrolsum stemmer ikke',
                  'The map checksum does not match'),
 'map.copy_012': ('Samlad potential', 'Samlet potensial', 'Samlet potentiale', 'Combined potential'),
 'map.copy_013': ('Aktiva lager styrs i appen och kan även slås av/på i kartkontrollen.',
                  'Aktive lag styres i appen og kan også slås av/på i kartkontrollen.',
                  'Aktive lag styres i appen og kan også slås fra/til i kortkontrollen.',
                  'Active layers are controlled in the app and can also be toggled in the map control.'),
 'map.copy_015': ('Landskapskontext', 'Landskapskontekst', 'Landskabskontekst', 'Landscape context'),
 'map.copy_016': ('Potential efter filter', 'Potensial etter filtre', 'Potentiale efter filtre', 'Potential after filters'),
 'map.copy_017': ('Potentiell yta', 'Potensielt areal', 'Potentielt areal', 'Potential area'),
 'map.copy_018': ('Efter acceptanspåverkan', 'Etter akseptpåvirkning', 'Efter acceptpåvirkning', 'After acceptance adjustment'),
 'map.copy_019': ('Acceptansjusterad potentiell yta',
                  'Akseptjustert potensielt areal',
                  'Acceptjusteret potentielt areal',
                  'Acceptance-adjusted potential area'),
 'map.copy_020': ('Scenarioenergi', 'Scenarioenergi', 'Scenarieenergi', 'Scenario energy'),
 'map.copy_021': ('Scenarioyta utanför potential',
                  'Scenarioareal utenfor potensialet',
                  'Scenarieareal uden for potentialet',
                  'Scenario area outside the potential'),
 'map.copy_022': ('Acceptansvärde', 'Akseptverdi', 'Acceptværdi', 'Acceptance value'),
 'map.copy_023': ('Datastatus', 'Datastatus', 'Datastatus', 'Data status'),
 'map.copy_025': ('Färgvikt', 'Fargevekt', 'Farvevægt', 'Colour weight'),
 'map.copy_026': ('Källhex', 'Kildehex', 'Kildehex', 'Source hexagons'),
 'map.copy_027': ('Klassning', 'Klassifisering', 'Klassificering', 'Classification'),
 'map.copy_028': ('Klass', 'Klasse', 'Klasse', 'Class'),
 'map.copy_031': ('vind', 'vind', 'vind', 'wind'),
 'map.copy_032': ('sol', 'sol', 'sol', 'solar'),
 'map.copy_033': ('Vindpotential', 'Vindpotensial', 'Vindpotentiale', 'Wind potential'),
 'map.copy_034': ('Solpotential', 'Solpotensial', 'Solpotentiale', 'Solar potential'),
 'map.copy_035': ('ja', 'ja', 'ja', 'yes'),
 'map.copy_036': ('nej', 'nei', 'nej', 'no'),
 'map.copy_037': ('appens standardutbredning', 'appens standardutstrekning', 'appens standardudstrækning', "the app's default extent"),
 'map.copy_038': ('full LABLAB-källa', 'full LABLAB-kilde', 'fuld LABLAB-kilde', 'the full LABLAB source'),
 'map.copy_039': ('delvis bedömd', 'delvis vurdert', 'delvist vurderet', 'partially assessed'),
 'map.copy_040': ('inte bedömd', 'ikke vurdert', 'ikke vurderet', 'not assessed'),
 'map.copy_041': ('Kontextdata saknas för denna teknikcell.',
                  'Kontekstdata mangler for denne teknologicellen.',
                  'Kontekstdata mangler for denne teknologicelle.',
                  'Context data is missing for this technology cell.'),
 'map.copy_042': ('Teknik', 'Teknologi', 'Teknologi', 'Technology'),
 'map.copy_043': ('Schematisk yta', 'Skjematisk areal', 'Skematisk areal', 'Schematic area'),
 'map.copy_044': ('Schematisk jämförelseyta', 'Skjematisk sammenligningsareal', 'Skematisk sammenligningsareal', 'Schematic comparison area'),
 'map.copy_045': ('inte föreslagen placering', 'ikke foreslått plassering', 'ikke foreslået placering', 'not a proposed location'),
 'map.copy_046': ('Schematisk jämförelseyta – visar ytbehov, inte föreslagen placering.',
                  'Skjematisk sammenligningsareal – viser arealbehov, ikke foreslått plassering.',
                  'Skematisk sammenligningsareal – viser arealbehov, ikke foreslået placering.',
                  'Schematic comparison area – shows area demand, not a proposed location.'),
 'map.copy_047': ('Båda teknikerna i samma visningshex, inte säkerställd fysisk överlappning. Cellens storlek visar inte allokerad yta.', 'Begge teknologiene i samme visningshex, ikke bekreftet fysisk overlapping. Cellens størrelse viser ikke allokert areal.', 'Begge teknologier i samme visningshex, ikke bekræftet fysisk overlap. Cellens størrelse viser ikke allokeret areal.', 'Both technologies in the same display hexagon, not confirmed physical overlap. Cell size does not represent allocated area.'),
 'map.copy_048': ('Visnings- och granskningslager; används inte numeriskt.',
                  'Visnings- og vurderingslag; brukes ikke numerisk.',
                  'Visnings- og vurderingslag; bruges ikke numerisk.',
                  'Display and review layer; not used numerically.'),
 'map.copy_049': ('Manifestbundet visningslager; används inte i beräkningen.',
                  'Manifestbundet visningslag; brukes ikke i beregningen.',
                  'Manifestbundet visningslag; bruges ikke i beregningen.',
                  'Manifest-bound display layer; not used in the calculation.'),
 'map.copy_050': ('Låg acceptans', 'Lav aksept', 'Lav accept', 'Low acceptance'),
 'map.copy_051': ('Hög acceptans', 'Høy aksept', 'Høj accept', 'High acceptance'),
 'map.copy_052': ('Mellanacceptans', 'Middels aksept', 'Middel accept', 'Medium acceptance'),
 'map.copy_053': ('Värde', 'Verdi', 'Værdi', 'Value'),
 'map.copy_054': ('Landskapstyp', 'Landskapstype', 'Landskabstype', 'Landscape type'),
 'map.copy_055': ('Landskapsstruktur', 'Landskapsstruktur', 'Landskabsstruktur', 'Landscape structure'),
 'map.copy_056': ('Säkerhet', 'Sikkerhet', 'Sikkerhed', 'Confidence'),
 'map.copy_057': ('Landskaps-/teknikranking', 'Landskaps-/teknologirangering', 'Landskabs-/teknologirangering', 'Landscape/technology ranking'),
 'map.copy_058': ('Slutlig ranking', 'Endelig rangering', 'Endelig rangering', 'Final ranking'),
 'map.copy_059': ('Förklaring', 'Forklaring', 'Forklaring', 'Explanation'),
 'map.copy_060': ('Vindyta inom landskapspotential',
                  'Vindareal innenfor landskapspotensialet',
                  'Vindareal inden for landskabspotentialet',
                  'Wind area within landscape potential'),
 'map.copy_061': ('Solyta inom landskapspotential',
                  'Solareal innenfor landskapspotensialet',
                  'Solareal inden for landskabspotentialet',
                  'Solar area within landscape potential'),
 'map.copy_062': ('Inte lämplig', 'Ikke egnet', 'Ikke egnet', 'Unsuitable'),
 'map.copy_063': ('Endast vind', 'Kun vind', 'Kun vind', 'Wind only'),
 'map.copy_064': ('Endast sol', 'Kun sol', 'Kun sol', 'Solar only'),
 'map.copy_065': ('Vind och sol', 'Vind og sol', 'Vind og sol', 'Wind and solar'),
 'map.copy_066': ('Scenarioyta: vind', 'Scenarioareal: vind', 'Scenarieareal: vind', 'Scenario area: wind'),
 'map.copy_067': ('Scenarioyta: sol', 'Scenarioareal: sol', 'Scenarieareal: sol', 'Scenario area: solar'),
 'map.copy_068': ('Scenarioyta: vind + sol i samma kartcell',
                  'Scenarioareal: vind + sol i samme kartcelle',
                  'Scenarieareal: vind + sol i samme kortcelle',
                  'Scenario area: wind + solar in the same map cell'),
 'map.copy_069': ('potential efter aktiva filter', 'potensial etter aktive filtre', 'potentiale efter aktive filtre', 'potential after active filters'),
 'map.copy_070': ('Parent-hex', 'Foreldrehex', 'Overordnet hex', 'Parent hexagon'),
 'map.copy_071': ('Child-hex', 'Barnehex', 'Underordnet hex', 'Child hexagon'),
 'map.copy_072': ('Scenarioyta i hex: {area} km² ({share}% av hex){priority}',
                  'Scenarioareal i hex: {area} km² ({share}% av hex){priority}',
                  'Scenarieareal i hex: {area} km² ({share}% af hex){priority}',
                  'Scenario area in hexagon: {area} km² ({share}% of hexagon){priority}'),
 'map.copy_073': ('· prioritet {rank}', '· prioritet {rank}', '· prioritet {rank}', '· priority {rank}'),
 'map.copy_074': ('{technology}: varför här?', '{technology}: hvorfor her?', '{technology}: hvorfor her?', '{technology}: why here?'),
 'map.copy_075': ('Slutlig ranking efter social acceptans ({share}%): {value}%',
                  'Endelig rangering etter sosial aksept ({share}%): {value}%',
                  'Endelig rangering efter social accept ({share}%): {value}%',
                  'Final ranking after social acceptance ({share}%): {value}%'),
 'map.copy_076': ('Vind {wind_area} km² · sol {solar_area} km²',
                  'Vind {wind_area} km² · sol {solar_area} km²',
                  'Vind {wind_area} km² · sol {solar_area} km²',
                  'Wind {wind_area} km² · solar {solar_area} km²'),
 'map.copy_077': ('Vindpotential: {wind} % · Solpotential: {solar} %',
                  'Vindpotensial: {wind} % · Solpotensial: {solar} %',
                  'Vindpotentiale: {wind} % · Solpotentiale: {solar} %',
                  'Wind potential: {wind} % · Solar potential: {solar} %'),
 'map.copy_078': ('Efter acceptanspåverkan: vind {wind} % · sol {solar} %',
                  'Etter akseptpåvirkning: vind {wind} % · sol {solar} %',
                  'Efter acceptpåvirkning: vind {wind} % · sol {solar} %',
                  'After acceptance adjustment: wind {wind} % · solar {solar} %'),
 'map.copy_079': ('Schematisk jämförelseyta: {technology}',
                  'Skjematisk sammenligningsareal: {technology}',
                  'Skematisk sammenligningsareal: {technology}',
                  'Schematic comparison area: {technology}'),
 'map.copy_080': ('{area} km² · inte föreslagen placering',
                  '{area} km² · ikke foreslått plassering',
                  '{area} km² · ikke foreslået placering',
                  '{area} km² · not a proposed location'),
 'map.copy_081': ('Social acceptans · {class_label}', 'Sosial aksept · {class_label}', 'Social accept · {class_label}', 'Social acceptance · {class_label}'),
 'map.copy_082': ('{label} R{resolution}', '{label} R{resolution}', '{label} R{resolution}', '{label} R{resolution}'),
 'map.copy_083': ('{label}: {area} m2', '{label}: {area} m2', '{label}: {area} m2', '{label}: {area} m2'),
 'map.copy_084': ('Landskapspotential Vind {share}%',
                  'Landskapspotensial vind {share}%',
                  'Landskabspotentiale vind {share}%',
                  'Wind landscape potential {share}%'),
 'map.copy_085': ('Mörkgrön fyllning visar att både vind och sol har scenarioyta i samma visningshex. Markören visar inte exakt fysisk överlappning inom hexen.', 'Mørkegrønn fylling viser at både vind og sol har scenarioareal i samme visningshex. Markøren viser ikke nøyaktig fysisk overlapping innenfor hexen.', 'Mørkegrøn fyldning viser, at både vind og sol har scenarieareal i samme visningshex. Markøren viser ikke præcist fysisk overlap inden for hexen.', 'Dark green fill shows that both wind and solar have scenario area in the same display hexagon. The marker does not show exact physical overlap within the hexagon.'),
 'map.copy_086': ('Markören visar scenariots placering från den mest lämpade ytan först enligt aktiva filter och prioriteringar.',
                  'Markøren viser scenarioets plassering fra det best egnede arealet først, etter aktive filtre og prioriteringer.',
                  'Markøren viser scenariets placering fra det bedst egnede areal først efter aktive filtre og prioriteringer.',
                  'The marker shows scenario allocation from the most suitable area first, according to active filters and priorities.'),
 'map.copy_088': ('Landskapspotential Vind hexagon',
                  'Landskapspotensial vind hexagon',
                  'Landskabspotentiale vind hexagon',
                  'Wind landscape potential hexagons'),
 'map.copy_096': ('Landskapspotential Sol hexagon', 'Landskapspotensial sol hexagon', 'Landskabspotentiale sol hexagon', 'Solar landscape potential hexagons'),
 'map.copy_099': ('Potentialklasser', 'Potensialklasser', 'Potentialeklasser', 'Potential classes'),
 'map.copy_100': ('Schematisk vindyta utanför potential',
                  'Skjematisk vindareal utenfor potensialet',
                  'Skematisk vindareal uden for potentialet',
                  'Schematic wind area outside the potential'),
 'map.copy_101': ('Schematisk solyta utanför potential',
                  'Skjematisk solareal utenfor potensialet',
                  'Skematisk solareal uden for potentialet',
                  'Schematic solar area outside the potential'),
 'map.copy_103': ('Analysdomän', 'Analysedomene', 'Analysedomæne', 'Analysis domain'),
 'map.copy_104': ('Småskalig solyta (schablon)',
                  'Småskala solareal (standardanslag)',
                  'Småskala solareal (standardestimat)',
                  'Small-scale solar area (standard estimate)'),
 'map.copy_105': ('Hex med hög/mycket hög LP Sol',
                  'Hex med høyt/svært høyt solpotensial',
                  'Hex med højt/meget højt solpotentiale',
                  'Hexagons with high/very high solar landscape potential'),
 'map.copy_106': ('Andel av visad yta', 'Andel av vist areal', 'Andel af vist areal', 'Share of displayed area'),
 'map.copy_107': ('Medelpoäng i polygonlagret', 'Gjennomsnittsscore i polygonlaget', 'Gennemsnitsscore i polygonlaget', 'Mean score in the polygon layer')})

# source presentation copy.
MESSAGES['source.skaraborg_capacity_placeholder'] = (
    'Demonstrationsdata för Skaraborg: Bornholms preliminära kapaciteter ×20 / ×100 / ×250 för Low / Base / High. Faktorerna illustrerar ytbrist, inte en regional prognos. Ytbehov per MW är oförändrat. Årsproduktion saknas; MW är installerad effekt, inte TWh.',
    'Demonstrasjonsdata for Skaraborg: Bornholms foreløpige kapasiteter ×20 / ×100 / ×250 for Low / Base / High. Faktorene illustrerer arealmangel, ikke en regional prognose. Arealbehov per MW er uendret. Årsproduksjon mangler; MW er installert effekt, ikke TWh.',
    'Demonstrationsdata for Skaraborg: Bornholms foreløbige kapaciteter ×20 / ×100 / ×250 for Low / Base / High. Faktorerne illustrerer arealmangel, ikke en regional prognose. Arealbehov pr. MW er uændret. Årsproduktion mangler; MW er installeret effekt, ikke TWh.',
    'Skaraborg demonstration levels: preliminary Bornholm capacities ×20 / ×100 / ×250 for Low / Base / High. Factors illustrate area shortage, not a regional forecast. Land demand per MW is unchanged. Annual production is unavailable; MW is installed capacity, not TWh.',
)
MESSAGES['source.skaraborg_capacity_provenance'] = (
    '20260924_Capacities (1).xlsx, Area need. Preliminära förenklade kapaciteter för Bornholm och korrigerade ytfaktorer enligt Kenneth Karlssons underlag den 30 september och Henriks instruktion den 8 oktober. För visualisering i Skaraborg tillämpas Henriks instruktion den 26 oktober som Low ×20, Base ×100 och High ×250 relativt det oskalade källåret. Faktorerna beräknades mot GIS-potentialen med nuvarande standardfilter innan de valdes: High ×200 ryms fortfarande med modellens mix; ×250 visar vindens ytbrist direkt. Exakta källobservationer och faktorer för markbehov per MW bevaras.',
    '20260924_Capacities (1).xlsx, Area need. Foreløpige forenklede kapasiteter for Bornholm og korrigerte arealfaktorer etter Kenneth Karlssons innspill 30. september og Henriks instruks 8. oktober. For visualisering i Skaraborg gjennomføres Henriks instruks 26. oktober som Low ×20, Base ×100 og High ×250 relativt det uskalerte kildeåret. Faktorene ble beregnet mot GIS-potensialet med gjeldende standardfiltre før de ble valgt: High ×200 får fortsatt plass med modellens miks; ×250 viser vindens arealmangel direkte. Eksakte kildeobservasjoner og faktorer for arealbehov per MW beholdes.',
    '20260924_Capacities (1).xlsx, Area need. Foreløbige forenklede kapaciteter for Bornholm og korrigerede arealfaktorer efter Kenneth Karlssons input den 30. september og Henriks instruktion den 8. oktober. Til visualisering i Skaraborg gennemføres Henriks instruktion den 26. oktober som Low ×20, Base ×100 og High ×250 i forhold til det uskalerede kildeår. Faktorerne blev beregnet mod GIS-potentialet med de nuværende standardfiltre, før de blev valgt: High ×200 kan stadig rummes med modellens mix; ×250 viser vindens arealmangel direkte. Præcise kildeobservationer og faktorer for arealbehov pr. MW bevares.',
    '20260924_Capacities (1).xlsx, Area need. Preliminary simplified Bornholm capacities and corrected area factors following Kenneth Karlsson’s September 30 input and Henrik’s October 8 instruction. For Skaraborg visualization, Henrik’s October 26 instruction is implemented as Low ×20, Base ×100 and High ×250 relative to the unscaled source year. Factors were calculated against current default-filter GIS potential before selection: High ×200 still fits at its model mix; ×250 demonstrates wind-area shortfall directly. Exact source observations and land-per-MW factors are retained.',
)
MESSAGES['source.skaraborg_capacity_limitation'] = (
    'Demonstrationsnivåer enbart för visualisering i Skaraborg, inte en kalibrerad eller validerad regional prognos eller observerad installerad effekt. Faktorerna 20 / 100 / 250 är valda för att visa tillgänglig yta och ytbrist och är inte härledda från regional energiefterfrågan eller produktion. Årtalen är Bornholms cp-ei-referensår; både år och illustrativ skala skiljer sig mellan nivåerna. En ändrad mix bevarar endast den nivåns skalade MW. Årsproduktion saknas och markbehov per MW är oförändrat. Faktisk ytbrist beror på tillämpade GIS-filter och mix.',
    'Demonstrasjonsnivåer bare for visualisering i Skaraborg, ikke en kalibrert eller validert regional prognose eller observert installert effekt. Faktorene 20 / 100 / 250 er valgt for å vise tilgjengelig areal og arealmangel og er ikke utledet fra regional energietterspørsel eller produksjon. Årstallene er Bornholms cp-ei-referanseår; både år og illustrativ skala varierer mellom nivåene. En endret miks bevarer bare dette nivåets skalerte MW. Årsproduksjon mangler og arealbehov per MW er uendret. Faktisk arealmangel avhenger av anvendte GIS-filtre og miks.',
    'Demonstrationsniveauer kun til visualisering i Skaraborg, ikke en kalibreret eller valideret regional prognose eller observeret installeret effekt. Faktorerne 20 / 100 / 250 er valgt for at vise tilgængeligt areal og arealmangel og er ikke udledt af regional energiefterspørgsel eller produktion. Årstallene er Bornholms cp-ei-referenceår; både år og illustrativ skala varierer mellem niveauerne. Et ændret mix bevarer kun dette niveaus skalerede MW. Årsproduktion mangler og arealbehov pr. MW er uændret. Den faktiske arealmangel afhænger af anvendte GIS-filtre og mix.',
    'Visualization-only demonstration levels for Skaraborg, not a calibrated or validated regional forecast or observed installed capacity. Factors 20 / 100 / 250 are chosen to demonstrate area headroom and shortage, not derived from regional energy demand or generation. The years are Bornholm cp-ei source reference years; both year and illustrative scale differ across levels. Changing the mix conserves that level’s scaled MW only. Annual generation is unavailable and land demand per MW is unchanged. Actual shortfall depends on applied GIS filters and mix.',
)
MESSAGES['scenario.demonstration_level'] = (
    'Demonstrationsnivå',
    'Demonstrasjonsnivå',
    'Demonstrationsniveau',
    'Demonstration level',
)
MESSAGES['scenario.demonstration_years'] = (
    'Årtalen är källmodellens referensår. Skalningen är vald för att visa ytbehov och ytbrist, inte som en regional prognos.',
    'Årstallene er kildemodellens referanseår. Skaleringen er valgt for å vise arealbehov og arealmangel, ikke som en regional prognose.',
    'Årstallene er kildemodellens referenceår. Skaleringen er valgt for at vise arealbehov og arealmangel, ikke som en regional prognose.',
    'The years are the source model’s reference years. Scaling was chosen to show land demand and shortage, not as a regional forecast.',
)
MESSAGES['scenario.demonstration_applied'] = (
    'Tillämpat: {p0} · skalning ×{p1:g} av källmodellens kapacitet.',
    'Tatt i bruk: {p0} · skalering ×{p1:g} av kildemodellens kapasitet.',
    'Anvendt: {p0} · skalering ×{p1:g} af kildemodellens kapacitet.',
    'Applied: {p0} · scaling ×{p1:g} of the source model’s capacity.',
)
MESSAGES['source.skaraborg_capacity_replacement'] = (
    'Ersätt demonstrationsvärdena med checksumskyddade och regionalt granskade kapaciteter, ytbehovsfaktorer och eventuell årsproduktion för Skaraborg genom en ny validerad kontextrevision.',
    'Erstatt demonstrasjonsverdiene med kontrollsumbeskyttede og regionalt gjennomgåtte kapasiteter, arealbehovsfaktorer og eventuell årsproduksjon for Skaraborg gjennom en ny validert kontekstrevisjon.',
    'Erstat demonstrationsværdierne med kontrolsumbeskyttede og regionalt gennemgåede kapaciteter, arealbehovsfaktorer og eventuel årsproduktion for Skaraborg gennem en ny valideret kontekstrevision.',
    'Replace the demonstration values with checksum-protected and regionally reviewed capacities, land-demand factors and any available annual generation for Skaraborg through a new validated context revision.',
)
MESSAGES.update({'source.copy_001': ('Utforskande modellunderlag: Bornholm cp-ei. Kapacitet och ytbehov; årsproduktion saknas. Kartan föreslår inga placeringar.',
                     'Modellgrunnlag for utforsking: Bornholm cp-ei. Kapasitet og arealbehov; årsproduksjon mangler. Kartet foreslår ingen plasseringer.',
                     'Modelgrundlag til udforskning: Bornholm cp-ei. Kapacitet og arealbehov; årsproduktion mangler. Kortet foreslår ikke placeringer.',
                     'Exploratory model input: Bornholm cp-ei. Capacity and land demand; annual production is unavailable. The map does not propose sites.'),
 'source.copy_002': ('Provisorisk energi: Skaraborg använder Bornholm TIMES/AreaDemand för utforskning; inte regionalt accepterade planeringsvärden.',
                     'Foreløpig energi: Skaraborg bruker Bornholm TIMES/AreaDemand til utforsking; ikke regionalt godkjente planleggingsverdier.',
                     'Foreløbig energi: Skaraborg bruger Bornholm TIMES/AreaDemand til udforskning; ikke regionalt godkendte planlægningsværdier.',
                     'Provisional energy: skaraborg uses Bornholm TIMES/AreaDemand for exploration; not regionally accepted planning values.'),
 'source.copy_003': ('Provisorisk scenariokälla: Trøndelag-vyn använder tills vidare Bornholm-data för planeringsutforskning. Värdena är inte regionalt accepterade för Trøndelag.',
                     'Foreløpig scenariokilde: Trøndelag-visningen bruker inntil videre Bornholm-data til planleggingsutforsking. Verdiene er ikke regionalt godkjent for '
                     'Trøndelag.',
                     'Foreløbig scenariekilde: Trøndelag-visningen bruger indtil videre Bornholm-data til udforskning af planlægning. Værdierne er ikke regionalt godkendt for '
                     'Trøndelag.',
                     'Provisional scenario source: the Trøndelag view currently uses Bornholm data for planning exploration. The values are not regionally accepted for '
                     'Trøndelag.'),
 'source.copy_004': ('Syntetiska demovärden utan empiriskt underlag eller landskapsfaktorer. Visar beteende; inte regional acceptansevidens.',
                     'Syntetiske demoverdier uten empirisk grunnlag eller landskapsfaktorer. Viser atferd; ikke regionalt kunnskapsgrunnlag om aksept.',
                     'Syntetiske demoværdier uden empirisk grundlag eller landskabsfaktorer. Viser adfærd; ikke regional dokumentation for accept.',
                     'Synthetic demo values without empirical inputs or landscape factors. Demonstrates behavior; not regional acceptance evidence.'),
 'source.copy_005': ('Provisorisk acceptanskälla: Trøndelag-vyn använder syntetiskt testdata för att prova beteendet. Värdena är inte forskningsresultat eller regionalt '
                     'accepterade.',
                     'Foreløpig akseptkilde: Trøndelag-visningen bruker syntetiske testdata for å prøve funksjonen. Verdiene er ikke forskningsresultater eller regionalt '
                     'godkjent.',
                     'Foreløbig acceptkilde: Trøndelag-visningen bruger syntetiske testdata til at afprøve adfærden. Værdierne er ikke forskningsresultater eller regionalt '
                     'godkendt.',
                     'Provisional acceptance source: the Trøndelag view uses synthetic test data to exercise the behavior. The values are not research results or regionally '
                     'accepted.'),
 'source.copy_006': ('20260924_Capacities (1).xlsx, Area need. Förenklade kapaciteter och korrigerade ytfaktorer enligt Kenneth Karlssons e-post den 30 september 2026 och Henriks '
                     'instruktion den 8 oktober 2026. Råa VAR_Cap-totaler finns kvar i källfilen men ersätter inte dessa preliminära underlag.',
                     '20260924_Capacities (1).xlsx, Area need. Forenklede kapasiteter og korrigerte arealfaktorer etter Kenneth Karlssons e-post 30. september 2026 og Henriks '
                     'instruksjon 8. oktober 2026. Rå VAR_Cap-totaler er bevart i kildefilen, men erstatter ikke disse foreløpige inngangsverdiene.',
                     '20260924_Capacities (1).xlsx, Area need. Forenklede kapaciteter og korrigerede arealfaktorer efter Kenneth Karlssons e-mail den 30. september 2026 og '
                     'Henriks instruktion den 8. oktober 2026. Rå VAR_Cap-totaler er bevaret i kildefilen, men erstatter ikke disse foreløbige input.',
                     '20260924_Capacities (1).xlsx, Area need. Simplified capacities and corrected area factors, following Kenneth Karlsson’s 2026-09-30 email and Henrik’s '
                     '2026-10-08 instruction. Raw VAR_Cap totals are retained in the source workbook but do not replace these preliminary inputs.'),
 'source.copy_007': ('Tre namngivna referensår inom ett cp-ei-scenario med preliminära totalkapaciteter inklusive befintliga anläggningar. Årsproduktion saknas; egna mixar '
                     'bevarar endast MW. Ersätt med slutliga scenarier från energimodelleringen när de levereras.',
                     'Tre navngitte referanseår innenfor ett cp-ei-scenario med foreløpige totalkapasiteter inkludert eksisterende anlegg. Årsproduksjon mangler; egne blandinger '
                     'bevarer bare MW. Erstatt med endelige scenarioer fra energimodelleringen når de leveres.',
                     'Tre navngivne referenceår inden for ét cp-ei-scenarie med foreløbige totalkapaciteter inklusive eksisterende anlæg. Årsproduktion mangler; egne blandinger '
                     'bevarer kun MW. Erstat med endelige scenarier fra energimodelleringen, når de leveres.',
                     'Three named reference years within one cp-ei scenario, using preliminary total capacities including existing assets. Annual generation is unavailable; '
                     'custom mixes conserve MW only. Replace with final modeller scenarios when supplied.'),
 'source.copy_008': ('Importera en checksumskyddad regional kapacitetsfil och publicera dess validerade kontextrevision.',
                     'Importer en regional kapasitetsfil sikret med kontrollsum, og publiser dens validerte kontekstrevisjon.',
                     'Importér en regional kapacitetsfil sikret med kontrolsum, og publicér dens validerede kontekstrevision.',
                     'Import a checksum-protected regional capacity file and publish its validated context revision.'),
 'source.copy_009': ('Checksumskyddade Bornholm TIMES- och AreaDemand-filer från det frysta externa V2-arkivet.',
                     'Bornholm TIMES- og AreaDemand-filer sikret med kontrollsum fra det fryste eksterne V2-arkivet.',
                     'Bornholm TIMES- og AreaDemand-filer sikret med kontrolsum fra det frosne eksterne V2-arkiv.',
                     'Checksum-protected Bornholm TIMES and AreaDemand files from the frozen external V2 archive.'),
 'source.copy_010': ('Provisoriska Bornholm TIMES/AreaDemand-underlag endast för planeringsutforskning. Värdena är inte regionalt granskade eller accepterade för denna region.',
                     'Foreløpige Bornholm TIMES/AreaDemand-inngangsverdier bare for planleggingsutforsking. Verdiene er ikke regionalt gjennomgått eller godkjent for denne '
                     'regionen.',
                     'Foreløbige Bornholm TIMES/AreaDemand-input kun til udforskning af planlægning. Værdierne er ikke regionalt gennemgået eller godkendt for denne region.',
                     'Provisional Bornholm TIMES/AreaDemand inputs for planning exploration only. These values have not been regionally reviewed or accepted for this delivery '
                     'region.'),
 'source.copy_011': ('Ersätt med regionala energi- och ytbehovsunderlag med låsta checksummor genom den befintliga deklarerade adaptern och valideringsgränsen.',
                     'Erstatt med regionale energi- og arealbehovsdata med fastsatte kontrollsummer gjennom den eksisterende deklarerte adapteren og valideringsgrensen.',
                     'Erstat med regionale energi- og arealbehovsdata med fastlagte kontrolsummer gennem den eksisterende deklarerede adapter og valideringsgrænse.',
                     'Replace with checksum-pinned regional energy and area-demand inputs through the existing declared adapter and validation boundary.'),
 'source.copy_012': ('Energinivåerna och markintensiteterna är inte kalibrerade eller accepterade för Trøndelag och får endast användas för att prova den generella scenario- och '
                     'allokeringskedjan.',
                     'Energinivåene og arealintensitetene er ikke kalibrert eller godkjent for Trøndelag og kan bare brukes til å prøve den generelle scenario- og '
                     'allokeringskjeden.',
                     'Energiniveauerne og arealintensiteterne er ikke kalibreret eller godkendt for Trøndelag og må kun bruges til at afprøve den generelle scenarie- og '
                     'allokeringskæde.',
                     'Energy levels and land intensities are not calibrated or accepted for Trøndelag and may only be used to test the generic scenario and allocation chain.'),
 'source.copy_013': ('Ersätt fallbacken när en granskad norsk eller Trøndelag-specifik scenarioexport med vind, sol, planeringsår och arealintensitet har pinnats och validerats.',
                     'Erstatt reservekilden når en gjennomgått norsk eller Trøndelag-spesifikk scenarioeksport med vind, sol, planleggingsår og arealintensitet er bundet til '
                     'kontrollsummer og validert.',
                     'Erstat reservekilden, når en gennemgået norsk eller Trøndelag-specifik scenarieeksport med vind, sol, planlægningsår og arealintensitet er bundet til '
                     'kontrolsummer og valideret.',
                     'Replace the fallback when a reviewed Norwegian or Trøndelag-specific scenario export with wind, solar, planning years and land intensity has been '
                     'checksum-pinned and validated.'),
 'source.copy_014': ('Deterministisk syntetisk import över verkliga godkända H3-celler för teknikstöd i bornholm, genererad med sha256_region_h3_demo_v1 och seed 20260907.',
                     'Deterministisk syntetisk import over faktiske godkjente H3-celler for teknologistøtte i bornholm, generert med sha256_region_h3_demo_v1 og seed 20260907.',
                     'Deterministisk syntetisk import over faktiske godkendte H3-celler for teknologistøtte i bornholm, genereret med sha256_region_h3_demo_v1 og seed 20260907.',
                     'Deterministic synthetic import over actual approved bornholm technology-support H3 cells, generated by sha256_region_h3_demo_v1 with seed 20260907.'),
 'source.copy_015': ('Deterministisk syntetisk import över verkliga godkända H3-celler för teknikstöd i skaraborg, genererad med sha256_region_h3_demo_v1 och seed 20260907.',
                     'Deterministisk syntetisk import over faktiske godkjente H3-celler for teknologistøtte i skaraborg, generert med sha256_region_h3_demo_v1 og seed 20260907.',
                     'Deterministisk syntetisk import over faktiske godkendte H3-celler for teknologistøtte i skaraborg, genereret med sha256_region_h3_demo_v1 og seed 20260907.',
                     'Deterministic synthetic import over actual approved skaraborg technology-support H3 cells, generated by sha256_region_h3_demo_v1 with seed 20260907.'),
 'source.copy_016': ('Inga empiriska acceptansobservationer, regional kalibrering, rumsliga samband eller landskapsfaktorer ingår. Värdena visar endast programmets beteende.',
                     'Ingen empiriske akseptobservasjoner, regional kalibrering, romlige sammenhenger eller landskapsfaktorer inngår. Verdiene viser bare programmets atferd.',
                     'Ingen empiriske acceptobservationer, regional kalibrering, rumlige sammenhænge eller landskabsfaktorer indgår. Værdierne viser kun programmets adfærd.',
                     'No empirical acceptance observations, regional calibration, spatial relationships or landscape factors are represented. Values demonstrate program behavior '
                     'only.'),
 'source.copy_017': ('Ersätt kandidaten med granskade regionalt ägda värden genom det befintliga CSV/geometrikontraktet, med uttrycklig täckning och checksummevalidering.',
                     'Erstatt kandidaten med gjennomgåtte regionalt eide verdier gjennom den eksisterende CSV/geometrikontrakten, med eksplisitt dekning og kontrollsumvalidering.',
                     'Erstat kandidaten med gennemgåede regionalt ejede værdier gennem den eksisterende CSV/geometrikontrakt, med eksplicit dækning og validering af '
                     'kontrolsummer.',
                     'Replace this candidate with reviewed region-owned values using the existing CSV/geometry contract, explicit coverage and checksum validation.'),
 'source.copy_018': ("sha256_region_h3_demo_v1: SHA256 av UTF-8 'sha256_region_h3_demo_v1|20260907|region_id|H3_id\\n'; tolka de första 8 hashbyten som ett osignerat "
                     'big-endian-heltal; medium=(250+integer%501)/1000, low=medium-0.200, high=medium+0.200. Inga empiriska samband eller landskapssamband. Detta skiljer sig från '
                     'den bevarade faktorbaserade syntetiska metoden för Trøndelag.',
                     "sha256_region_h3_demo_v1: SHA256 av UTF-8 'sha256_region_h3_demo_v1|20260907|region_id|H3_id\\n'; tolk de første 8 hashbytene som et usignert "
                     'big-endian-heltall; medium=(250+integer%501)/1000, low=medium-0.200, high=medium+0.200. Ingen empiriske sammenhenger eller landskapssammenhenger. Dette '
                     'skiller seg fra den bevarte faktorbaserte syntetiske metoden for Trøndelag.',
                     "sha256_region_h3_demo_v1: SHA256 af UTF-8 'sha256_region_h3_demo_v1|20260907|region_id|H3_id\\n'; fortolk de første 8 hashbyte som et usigneret "
                     'big-endian-heltal; medium=(250+integer%501)/1000, low=medium-0.200, high=medium+0.200. Ingen empiriske sammenhænge eller landskabssammenhænge. Dette '
                     'adskiller sig fra den bevarede faktorbaserede syntetiske metode for Trøndelag.',
                     "sha256_region_h3_demo_v1: SHA256 of UTF-8 'sha256_region_h3_demo_v1|20260907|region_id|H3_id\\n'; take first 8 digest bytes as unsigned big-endian integer; "
                     'medium=(250+integer%501)/1000, low=medium-0.200, high=medium+0.200. No empirical or landscape relationship. This differs from the preserved Trondelag '
                     'factor-based synthetic method.'),
 'source.copy_019': ('Deterministiskt syntetiskt testlager med seed 20260519 från det frysta externa V2-arkivet. Landskapsfaktorer används som proxykomponenter för att prova UI- '
                     'och integrationskedjan.',
                     'Deterministisk syntetisk testlag med seed 20260519 fra det fryste eksterne V2-arkivet. Landskapsfaktorer brukes som proxykomponenter for å prøve UI- og '
                     'integrasjonskjeden.',
                     'Deterministisk syntetisk testlag med seed 20260519 fra det frosne eksterne V2-arkiv. Landskabsfaktorer bruges som proxykomponenter til at afprøve UI- og '
                     'integrationskæden.',
                     'Deterministic synthetic test layer with seed 20260519 from the frozen external V2 archive. Landscape factors are used as proxy components to test the UI and '
                     'integration chain.'),
 'source.copy_020': ('Värdena är inte observationer, IVL-resultat eller regionalt accepterad evidens och får endast användas för beteende- och integrationsutforskning.',
                     'Verdiene er ikke observasjoner, IVL-resultater eller regionalt godkjent kunnskapsgrunnlag og kan bare brukes til utforsking av atferd og integrasjon.',
                     'Værdierne er ikke observationer, IVL-resultater eller regionalt godkendt dokumentation og må kun bruges til udforskning af adfærd og integration.',
                     'The values are not observations, IVL results or regionally accepted evidence and may only be used for behavior and integration exploration.'),
 'source.copy_021': ('Ersätt fallbacken när en granskad regional källa med dokumenterad metod, fullständig täckningspolicy, scenariosemantik, checksummor och regional acceptans '
                     'har validerats.',
                     'Erstatt reservekilden når en gjennomgått regional kilde med dokumentert metode, fullstendig dekningspolicy, scenariosemantikk, kontrollsummer og regional '
                     'aksept er validert.',
                     'Erstat reservekilden, når en gennemgået regional kilde med dokumenteret metode, fuldstændig dækningspolitik, scenariesemantik, kontrolsummer og regional '
                     'accept er valideret.',
                     'Replace the fallback when a reviewed regional source with documented method, complete coverage policy, scenario semantics, checksums and regional acceptance '
                     'has been validated.'),
 'source.copy_022': ('Deterministiskt syntetiskt testdata för UI och integration. Inte observationer, IVL-forskningsresultat eller regional acceptansevidens.',
                     'Deterministiske syntetiske testdata for UI og integrasjon. Ikke observasjoner, IVL-forskningsresultater eller regionalt kunnskapsgrunnlag om aksept.',
                     'Deterministiske syntetiske testdata til UI og integration. Ikke observationer, IVL-forskningsresultater eller regional dokumentation for accept.',
                     'Deterministic synthetic test data for UI and integration. Not observations, IVL research results or regional acceptance evidence.'),
 'source.copy_023': ('Kartan uppdateras när du klickar på Använd ändringar. Det gör att geometrimotorn inte kör om för varje sliderrörelse.',
                     'Kartet oppdateres når du klikker på Bruk endringer. Det hindrer at geometrimotoren kjører på nytt ved hver bevegelse av glidebryteren.',
                     'Kortet opdateres, når du klikker på Anvend ændringer. Det forhindrer, at geometrimotoren kører igen ved hver bevægelse af skyderen.',
                     'The map updates when you click Apply changes. This avoids rerunning the geometry engine on every slider move.'),
 'source.copy_024': ('Analysvärde. Det här ändrar den verkliga buffert- eller genomförbarhetsgeometrin.',
                     'Analyseverdi. Denne verdien endrer den faktiske buffer- eller gjennomførbarhetsgeometrien.',
                     'Analyseværdi. Denne værdi ændrer den faktiske buffer- eller gennemførlighedsgeometri.',
                     'Analysis only. This value changes the real buffer or feasibility geometry.'),
 'source.copy_025': ('Visa / blanda', 'Vis / bland', 'Vis / bland', 'Display / blend'),
 'source.copy_026': ('Visning endast. 0 = källager, 100 = grupplager.',
                     'Bare visning. 0 = kildelag, 100 = gruppelag.',
                     'Kun visning. 0 = kildelag, 100 = gruppelag.',
                     'Display only. 0 = source layers, 100 = group layer.'),
 'source.copy_027': ('Gruppen är inaktiv. Välj ett eller flera källager ovan.',
                     'Gruppen er inaktiv. Velg ett eller flere kildelag ovenfor.',
                     'Gruppen er inaktiv. Vælg ét eller flere kildelag ovenfor.',
                     'Group inactive. Select one or more source layers above.'),
 'source.copy_029': ('Geometrikörningen misslyckades', 'Geometrikjøringen mislyktes', 'Geometrikørslen mislykkedes', 'Geometry runtime failed'),
 'source.copy_030': ('Uppdaterar geometri...', 'Oppdaterer geometri...', 'Opdaterer geometri...', 'Updating geometry...'),
 'source.copy_031': ('Konflikt', 'Konflikt', 'Konflikt', 'Conflict'),
 'source.copy_032': ('Genomförbar', 'Gjennomførbar', 'Gennemførlig', 'Feasible'),
 'source.copy_033': ('Av', 'Av', 'Fra', 'Off'),
 'source.copy_034': ('Inga', 'Ingen', 'Ingen', 'None')})

# group presentation copy.
MESSAGES.update({'group.copy_001': ('Bebyggelse / befolkning / byggd miljö',
                    'Bebyggelse / befolkning / bygd miljø',
                    'Bebyggelse / befolkning / bygget miljø',
                    'Settlement / population / built environment'),
 'group.copy_002': ('Transportinfrastruktur', 'Transportinfrastruktur', 'Transportinfrastruktur', 'Transport infrastructure'),
 'group.copy_004': ('Värdefulla kulturmiljöer', 'Verdifulle kulturmiljøer', 'Værdifulde kulturmiljøer', 'Valuable cultural environments'),
 'group.copy_005': ('Skyddade områden', 'Vernede områder', 'Beskyttede områder', 'Protected areas'),
 'group.copy_006': ('Minsta avstånd', 'Minste avstand', 'Mindste afstand', 'Minimum distance'),
 'group.copy_007': ('Största anslutningsavstånd', 'Største tilknytningsavstand', 'Største tilslutningsafstand', 'Maximum connection distance'),
 'group.copy_008': ('Valfri buffert', 'Valgfri buffer', 'Valgfri buffer', 'Optional buffer'),
 'group.copy_009': ('Yta inom valt minsta avstånd från valda befolknings- och bebyggelsekällor tas bort från den beräknade '
 'potentialen. En redan inbyggd buffert ingår i avståndet och läggs inte på igen.',
 'Areal innenfor valgt minsteavstand fra valgte befolknings- og bebyggelseskilder fjernes fra det '
 'beregnede potensialet. En allerede innebygd buffer inngår i avstanden og legges ikke til på nytt.',
 'Areal inden for den valgte minimumsafstand fra valgte befolknings- og bebyggelseskilder fjernes fra det '
 'beregnede potentiale. En allerede indbygget buffer indgår i afstanden og tilføjes ikke igen.',
 'Area within the selected minimum distance of selected population and settlement sources is removed from '
 'the calculated potential. Any existing built-in buffer is included in that distance and is not added '
 'again.'),
 'group.copy_010': ('För nära är dåligt. Transportlagret är uppdelat i små, mellan och stora vägar utifrån den befintliga vägklassningen i det semi-manuella flödet.',
                    'For nært er dårlig. Transportlaget er delt i små, mellomstore og store veier ut fra den eksisterende veiklassifiseringen i den delvis manuelle prosessen.',
                    'For tæt på er dårligt. Transportlaget er opdelt i små, mellemstore og store veje ud fra den eksisterende vejklassificering i den delvist manuelle proces.',
                    'Too close is unfavorable. The transport layer is split into small, medium and large roads using the existing road classification in the partly manual '
                    'process.'),
 'group.copy_011': ('Yta utanför valt anslutningsavstånd ingår inte i den beräknade potentialen. Avståndet mäts till valda '
 'ledningar, kablar och punktobjekt. Närhet innebär inte att det finns ledig anslutningskapacitet.',
 'Areal utenfor valgt tilknytningsavstand inngår ikke i det beregnede potensialet. Avstanden måles til '
 'valgte ledninger, kabler og punktobjekter. Nærhet betyr ikke at det finnes ledig tilknytningskapasitet.',
 'Areal uden for den valgte tilslutningsafstand indgår ikke i det beregnede potentiale. Afstanden måles '
 'til valgte ledninger, kabler og punktobjekter. Nærhed betyder ikke, at der er ledig '
 'tilslutningskapacitet.',
 'Area outside the selected connection distance is excluded from the calculated potential. Distance is '
 'measured to selected lines, cables and point features. Proximity does not imply available grid '
 'connection capacity.'),
 'group.copy_012': ('Valda kulturkällor och eventuell buffert minskar den tillgängliga ytan inom varje hexagon. Endast den '
 'del som överlappar tas bort. Vid 0 m buffert används kulturkällornas egna geometrier.',
 'Valgte kulturkilder og eventuell buffer reduserer tilgjengelig areal i hvert heksagon. Bare den '
 'overlappende delen fjernes. Ved 0 m buffer brukes kulturkildenes egne geometrier.',
 'Valgte kulturkilder og en eventuel buffer reducerer det tilgængelige areal i hver sekskant. Kun den '
 'overlappende del fjernes. Ved 0 m buffer bruges kulturkildernes egne geometrier.',
 'Selected cultural sources and any buffer reduce the available area within each hexagon. Only the '
 'overlapping portion is removed. At 0 m buffer, the cultural sources’ own geometries are used.'),
 'group.copy_013': ('Valda naturkällor och eventuell buffert minskar den tillgängliga ytan inom varje hexagon. Endast den del '
 'som överlappar tas bort. Vid 0 m buffert används naturkällornas egna ytor. Kartans gemensamma '
 'potentialprocent visar resultatet av alla aktiva begränsningar.',
 'Valgte naturkilder og eventuell buffer reduserer tilgjengelig areal i hvert heksagon. Bare den '
 'overlappende delen fjernes. Ved 0 m buffer brukes naturkildenes egne arealer. Kartets felles '
 'potensialprosent viser resultatet av alle aktive begrensninger.',
 'Valgte naturkilder og en eventuel buffer reducerer det tilgængelige areal i hver sekskant. Kun den '
 'overlappende del fjernes. Ved 0 m buffer bruges naturkildernes egne arealer. Kortets fælles '
 'potentialeprocent viser resultatet af alle aktive begrænsninger.',
 'Selected nature sources and any buffer reduce the available area within each hexagon. Only the '
 'overlapping portion is removed. At 0 m buffer, the nature sources’ own areas are used. The map’s '
 'combined potential percentage reflects all active constraints.'),
 'group.copy_014': ('Exkluderad', 'Ekskludert', 'Udelukket', 'Excluded'),
 'group.copy_015': ('Låg', 'Lav', 'Lav', 'Low'),
 'group.copy_016': ('Medel', 'Middels', 'Middel', 'Medium'),
 'group.copy_017': ('Hög', 'Høy', 'Høj', 'High'),
 'group.copy_018': ('Mycket hög', 'Svært høy', 'Meget høj', 'Very high'),
 'group.copy_019': ('Avståndskonflikt', 'Avstandskonflikt', 'Afstandskonflikt', 'Distance conflict'),
 'group.copy_020': ('Närhetsgenomförbarhet', 'Gjennomførbarhet ved nærhet', 'Gennemførlighed ved nærhed', 'Proximity feasibility'),
 'group.copy_021': ('Hård exkludering', 'Hard ekskludering', 'Hård udelukkelse', 'Hard exclusion'),
 'group.copy_022': ('Mjuk viktad känslighet', 'Myk vektet følsomhet', 'Blød vægtet følsomhed', 'Soft weighted sensitivity')})

# map.extra presentation copy.
MESSAGES.update({'map.extra.copy_001': ('Datakälla', 'Datakilde', 'Datakilde', 'Data source'),
 'map.extra.copy_002': ('Buffertområde', 'Bufferområde', 'Bufferområde', 'Buffer area'),
 'map.extra.copy_003': ('Område', 'Område', 'Område', 'Area'),
 'map.extra.copy_004': ('Resultat', 'Resultat', 'Resultat', 'Result'),
 'map.extra.copy_005': ('Saknad täckning', 'Manglende dekning', 'Manglende dækning', 'Missing coverage'),
 'map.extra.copy_006': ('Utesluten', 'Utelukket', 'Udelukket', 'Excluded'),
 'map.extra.copy_007': ('Kvar efter filter', 'Gjenstår etter filtre', 'Tilbage efter filtre', 'Remaining after filters'),
 'map.extra.copy_008': ('Ingen etableringsyta', 'Intet etableringsareal', 'Intet etableringsareal', 'No development area'),
 'map.extra.copy_009': ('Låg etableringsyta', 'Lavt etableringsareal', 'Lavt etableringsareal', 'Low development area'),
 'map.extra.copy_010': ('Medelhög etableringsyta', 'Middels etableringsareal', 'Middel etableringsareal', 'Medium development area'),
 'map.extra.copy_011': ('Hög etableringsyta', 'Høyt etableringsareal', 'Højt etableringsareal', 'High development area'),
 'map.extra.copy_012': ('Full etableringsyta', 'Fullt etableringsareal', 'Fuldt etableringsareal', 'Full development area'),
 'map.extra.copy_013': ('Blockerade celler utesluts.', 'Blokkerte celler utelukkes.', 'Blokerede celler udelukkes.', 'Blocked cells are excluded.'),
 'map.extra.copy_014': ('Blockerade celler ligger utanför krävt närhetsavstånd.',
                        'Blokkerte celler ligger utenfor påkrevd nærhetsavstand.',
                        'Blokerede celler ligger uden for den krævede nærhedsafstand.',
                        'Blocked cells lie outside the required proximity distance.'),
 'map.extra.copy_015': ('Återstående andel av den lämpliga stödytan.',
                        'Gjenværende andel av det egnede støttearealet.',
                        'Tilbageværende andel af det egnede støtteareal.',
                        'Remaining share of the suitable support area.'),
 'map.extra.copy_016': ('Teknisk cellklassning. Återstående area visas i Etableringsyta.',
                        'Teknisk celleklassifisering. Gjenværende areal vises i Etableringsareal.',
                        'Teknisk celleklassificering. Tilbageværende areal vises i Etableringsareal.',
                        'Technical cell classification. Remaining area is shown in Development area.'),
 'map.extra.copy_017': ('Ingen (0 %)', 'Ingen (0 %)', 'Ingen (0 %)', 'None (0 %)'),
 'map.extra.copy_018': ('Låg (>0–<33,3 %)', 'Lav (>0–<33,3 %)', 'Lav (>0–<33,3 %)', 'Low (>0–<33,3 %)'),
 'map.extra.copy_019': ('Medel (33,3–<66,7 %)', 'Middels (33,3–<66,7 %)', 'Middel (33,3–<66,7 %)', 'Medium (33,3–<66,7 %)'),
 'map.extra.copy_020': ('Hög (66,7–<100 %)', 'Høy (66,7–<100 %)', 'Høj (66,7–<100 %)', 'High (66,7–<100 %)'),
 'map.extra.copy_021': ('Full (100 %)', 'Full (100 %)', 'Fuld (100 %)', 'Full (100 %)'),
 'map.extra.copy_022': ('Max avstånd', 'Maksimal avstand', 'Maksimal afstand', 'Maximum distance'),
 'map.extra.copy_023': ('Buffert', 'Buffer', 'Buffer', 'Buffer'),
 'map.extra.copy_024': ('Genomförbar modellarea inom analysdomänen',
                        'Gjennomførbart modellareal innenfor analysedomenet',
                        'Gennemførligt modelareal inden for analysedomænet',
                        'Feasible model area within the analysis domain'),
 'map.extra.copy_025': ('Buffertyta inom analysdomänen', 'Bufferareal innenfor analysedomenet', 'Bufferareal inden for analysedomænet', 'Buffer area within the analysis domain'),
 'map.extra.copy_026': ('Inom {distance} m · {area} km²', 'Innenfor {distance} m · {area} km²', 'Inden for {distance} m · {area} km²', 'Within {distance} m · {area} km²'),
 'map.extra.copy_027': ('{distance} m buffert · {area} km²', '{distance} m buffer · {area} km²', '{distance} m buffer · {area} km²', '{distance} m buffer · {area} km²'),
 'map.extra.copy_028': ('Schablon från {source} per hex',
                        'Standardanslag fra {source} per hex',
                        'Standardestimat fra {source} per hex',
                        'Standard estimate from {source} per hexagon'),
 'map.extra.copy_029': ('Visas som liten schablonhex, inte som faktisk takpolygon.',
                        'Vises som en liten standardhex, ikke som en faktisk takpolygon.',
                        'Vises som en lille standardhex, ikke som en faktisk tagpolygon.',
                        'Shown as a small standard-estimate hexagon, not an actual roof polygon.'),
 'map.extra.copy_030': ('personer', 'personer', 'personer', 'people'),
 'map.extra.copy_031': ('Vindpotentialyta', 'Vindpotensialareal', 'Vindpotentialeareal', 'Wind potential area'),
 'map.extra.copy_032': ('H3-kalla', 'H3-kilde', 'H3-kilde', 'H3 source'),
 'map.extra.copy_033': ('Potential', 'Potensial', 'Potentiale', 'Potential'),
 'map.extra.copy_034': ('Regelacceptans', 'Regelaksept', 'Regelaccept', 'Rule acceptance'),
 'map.extra.copy_035': ('Blockerande grupper', 'Blokkerende grupper', 'Blokerende grupper', 'Blocking groups')})

# Authored HTML shells; every visible label is a localized parameter.
MESSAGES.update({'format.html_005': ("<h3 data-potential-tutorial-anchor='right-geographies'>{p0}</h3>",
                     "<h3 data-potential-tutorial-anchor='right-geographies'>{p0}</h3>",
                     "<h3 data-potential-tutorial-anchor='right-geographies'>{p0}</h3>",
                     "<h3 data-potential-tutorial-anchor='right-geographies'>{p0}</h3>"),
 'format.html_083': ("<div class='change-table-wrap' data-potential-tutorial-anchor='results-table'><table "
                     "class='change-table'>{p0}<thead><tr>{p1}</tr></thead><tbody>{p2}</tbody></table></div><style>.change-table-wrap{{display:block;width:100%;max-width:100%;overflow-x:auto;border:1px "
                     'solid '
                     'rgba(49,51,63,0.14);border-radius:6px;margin-top:0.35rem;}}.change-table{{width:100%;min-width:645px;border-collapse:collapse;font-size:0.68rem;line-height:1.12;table-layout:fixed;}}.change-table '
                     '.change-col-tech{{width:6%;}}.change-table .change-col-energy{{width:10%;}}.change-table .change-col-area{{width:10%;}}.change-table '
                     '.change-col-filter{{width:13%;}}.change-table .change-col-acceptance{{width:15%;}}.change-table .change-col-unused{{width:13%;}}.change-table '
                     '.change-col-outside{{width:13%;}}.change-table .change-col-share{{width:10%;}}.change-table '
                     'th{{background:#f8fafc;color:#475569;text-align:left;font-weight:600;padding:0.22rem 0.3rem;border-bottom:1px solid '
                     'rgba(49,51,63,0.12);white-space:normal;overflow-wrap:anywhere;line-height:1.12;}}.change-table td{{padding:0.22rem 0.3rem;border-top:1px solid '
                     'rgba(49,51,63,0.08);vertical-align:top;white-space:normal;overflow-wrap:anywhere;}}.change-table td div{{gap:0!important;min-width:0;}}.change-table td '
                     'span:first-child{{white-space:nowrap;}}@media (max-width:900px){{.change-table{{font-size:0.66rem;}}.change-table-wrap{{width:100%;}}}}</style>',
                     "<div class='change-table-wrap' data-potential-tutorial-anchor='results-table'><table "
                     "class='change-table'>{p0}<thead><tr>{p1}</tr></thead><tbody>{p2}</tbody></table></div><style>.change-table-wrap{{display:block;width:100%;max-width:100%;overflow-x:auto;border:1px "
                     'solid '
                     'rgba(49,51,63,0.14);border-radius:6px;margin-top:0.35rem;}}.change-table{{width:100%;min-width:645px;border-collapse:collapse;font-size:0.68rem;line-height:1.12;table-layout:fixed;}}.change-table '
                     '.change-col-tech{{width:6%;}}.change-table .change-col-energy{{width:10%;}}.change-table .change-col-area{{width:10%;}}.change-table '
                     '.change-col-filter{{width:13%;}}.change-table .change-col-acceptance{{width:15%;}}.change-table .change-col-unused{{width:13%;}}.change-table '
                     '.change-col-outside{{width:13%;}}.change-table .change-col-share{{width:10%;}}.change-table '
                     'th{{background:#f8fafc;color:#475569;text-align:left;font-weight:600;padding:0.22rem 0.3rem;border-bottom:1px solid '
                     'rgba(49,51,63,0.12);white-space:normal;overflow-wrap:anywhere;line-height:1.12;}}.change-table td{{padding:0.22rem 0.3rem;border-top:1px solid '
                     'rgba(49,51,63,0.08);vertical-align:top;white-space:normal;overflow-wrap:anywhere;}}.change-table td div{{gap:0!important;min-width:0;}}.change-table td '
                     'span:first-child{{white-space:nowrap;}}@media (max-width:900px){{.change-table{{font-size:0.66rem;}}.change-table-wrap{{width:100%;}}}}</style>',
                     "<div class='change-table-wrap' data-potential-tutorial-anchor='results-table'><table "
                     "class='change-table'>{p0}<thead><tr>{p1}</tr></thead><tbody>{p2}</tbody></table></div><style>.change-table-wrap{{display:block;width:100%;max-width:100%;overflow-x:auto;border:1px "
                     'solid '
                     'rgba(49,51,63,0.14);border-radius:6px;margin-top:0.35rem;}}.change-table{{width:100%;min-width:645px;border-collapse:collapse;font-size:0.68rem;line-height:1.12;table-layout:fixed;}}.change-table '
                     '.change-col-tech{{width:6%;}}.change-table .change-col-energy{{width:10%;}}.change-table .change-col-area{{width:10%;}}.change-table '
                     '.change-col-filter{{width:13%;}}.change-table .change-col-acceptance{{width:15%;}}.change-table .change-col-unused{{width:13%;}}.change-table '
                     '.change-col-outside{{width:13%;}}.change-table .change-col-share{{width:10%;}}.change-table '
                     'th{{background:#f8fafc;color:#475569;text-align:left;font-weight:600;padding:0.22rem 0.3rem;border-bottom:1px solid '
                     'rgba(49,51,63,0.12);white-space:normal;overflow-wrap:anywhere;line-height:1.12;}}.change-table td{{padding:0.22rem 0.3rem;border-top:1px solid '
                     'rgba(49,51,63,0.08);vertical-align:top;white-space:normal;overflow-wrap:anywhere;}}.change-table td div{{gap:0!important;min-width:0;}}.change-table td '
                     'span:first-child{{white-space:nowrap;}}@media (max-width:900px){{.change-table{{font-size:0.66rem;}}.change-table-wrap{{width:100%;}}}}</style>',
                     "<div class='change-table-wrap' data-potential-tutorial-anchor='results-table'><table "
                     "class='change-table'>{p0}<thead><tr>{p1}</tr></thead><tbody>{p2}</tbody></table></div><style>.change-table-wrap{{display:block;width:100%;max-width:100%;overflow-x:auto;border:1px "
                     'solid '
                     'rgba(49,51,63,0.14);border-radius:6px;margin-top:0.35rem;}}.change-table{{width:100%;min-width:645px;border-collapse:collapse;font-size:0.68rem;line-height:1.12;table-layout:fixed;}}.change-table '
                     '.change-col-tech{{width:6%;}}.change-table .change-col-energy{{width:10%;}}.change-table .change-col-area{{width:10%;}}.change-table '
                     '.change-col-filter{{width:13%;}}.change-table .change-col-acceptance{{width:15%;}}.change-table .change-col-unused{{width:13%;}}.change-table '
                     '.change-col-outside{{width:13%;}}.change-table .change-col-share{{width:10%;}}.change-table '
                     'th{{background:#f8fafc;color:#475569;text-align:left;font-weight:600;padding:0.22rem 0.3rem;border-bottom:1px solid '
                     'rgba(49,51,63,0.12);white-space:normal;overflow-wrap:anywhere;line-height:1.12;}}.change-table td{{padding:0.22rem 0.3rem;border-top:1px solid '
                     'rgba(49,51,63,0.08);vertical-align:top;white-space:normal;overflow-wrap:anywhere;}}.change-table td div{{gap:0!important;min-width:0;}}.change-table td '
                     'span:first-child{{white-space:nowrap;}}@media (max-width:900px){{.change-table{{font-size:0.66rem;}}.change-table-wrap{{width:100%;}}}}</style>'),
 'format.html_240': ('\n'
                     '        <div class="workspace-header" data-potential-tutorial-anchor="workspace-header">\n'
                     '          <div>\n'
                     '            <div class="workspace-eyebrow">{p0} · scenario {p1} · H3 {p2}</div>\n'
                     '            <div class="workspace-title-row">\n'
                     '              <h1>{p3}</h1>\n'
                     '              <span class="workspace-beta-badge">{p4}</span>\n'
                     '            </div>\n'
                     '            <div class="workspace-beta-note">{p5}</div>\n'
                     '          </div>\n'
                     '          <div class="workspace-pill">CRS: {p6}</div>\n'
                     '        </div>\n'
                     '        ',
                     '\n'
                     '        <div class="workspace-header" data-potential-tutorial-anchor="workspace-header">\n'
                     '          <div>\n'
                     '            <div class="workspace-eyebrow">{p0} · scenario {p1} · H3 {p2}</div>\n'
                     '            <div class="workspace-title-row">\n'
                     '              <h1>{p3}</h1>\n'
                     '              <span class="workspace-beta-badge">{p4}</span>\n'
                     '            </div>\n'
                     '            <div class="workspace-beta-note">{p5}</div>\n'
                     '          </div>\n'
                     '          <div class="workspace-pill">CRS: {p6}</div>\n'
                     '        </div>\n'
                     '        ',
                     '\n'
                     '        <div class="workspace-header" data-potential-tutorial-anchor="workspace-header">\n'
                     '          <div>\n'
                     '            <div class="workspace-eyebrow">{p0} · scenario {p1} · H3 {p2}</div>\n'
                     '            <div class="workspace-title-row">\n'
                     '              <h1>{p3}</h1>\n'
                     '              <span class="workspace-beta-badge">{p4}</span>\n'
                     '            </div>\n'
                     '            <div class="workspace-beta-note">{p5}</div>\n'
                     '          </div>\n'
                     '          <div class="workspace-pill">CRS: {p6}</div>\n'
                     '        </div>\n'
                     '        ',
                     '\n'
                     '        <div class="workspace-header" data-potential-tutorial-anchor="workspace-header">\n'
                     '          <div>\n'
                     '            <div class="workspace-eyebrow">{p0} · scenario {p1} · H3 {p2}</div>\n'
                     '            <div class="workspace-title-row">\n'
                     '              <h1>{p3}</h1>\n'
                     '              <span class="workspace-beta-badge">{p4}</span>\n'
                     '            </div>\n'
                     '            <div class="workspace-beta-note">{p5}</div>\n'
                     '          </div>\n'
                     '          <div class="workspace-pill">CRS: {p6}</div>\n'
                     '        </div>\n'
                     '        ')})

# Shared guide copy; references the same authored controls in every locale.
MESSAGES.update({'tutorial.prototype_title': ('Hitta potential för ny vind och sol',
                              'Finn potensial for ny vind og sol',
                              'Find potentiale for ny vind og sol',
                              'Find potential for new wind and solar'),
 'tutorial.prototype_body': ('Det här är en prototyp som hjälper dig att utforska var ny vind- och solenergi kan passa. Du kan pröva olika energibehov och se '
                             'hur landskap, avstånd och social acceptans påverkar möjliga etableringar, så att viktiga vägval blir lättare att förstå.',
                             'Dette er en prototype som hjelper deg å utforske hvor ny vind- og solenergi kan passe. Du kan prøve ulike energibehov og se '
                             'hvordan landskap, avstander og sosial aksept påvirker mulige etableringer, slik at viktige veivalg blir lettere å forstå.',
                             'Denne prototype hjælper dig med at udforske, hvor ny vind- og solenergi kan passe. Du kan teste energibehov og se hvordan '
                             'landskab, afstande og social accept påvirker mulige etableringer, så vigtige valg bliver lettere at forstå.',
                             'This prototype helps you explore where new wind and solar energy may fit. You can test energy needs and see how landscape, '
                             'distances and social acceptance affect possible establishments, so important choices become easier to understand.'),
 'tutorial.geography_title': ('Börja med geografin', 'Begynn med geografien', 'Begynd med geografien', 'Start with geography'),
 'tutorial.geography_body': ('Startläget visar analysens resultat: den potentiella etableringsytan för vind och sol. Alla GIS-lager som används i analysen '
                             'visas inte i kartan från start, men de kan öppnas under avancerade inställningar när du vill se vilka antaganden som påverkar '
                             'ytan.',
                             'Utgangspunktet viser analysens resultater: det potensielle etableringsarealet for vind og sol. Ikke alle GIS-lag som brukes i '
                             'analysen, vises i kartet fra start, men de kan åpnes under avanserte innstillinger når du vil se hvilke antakelser som påvirker '
                             'arealet.',
                             'Startpunktet viser analysens resultat: det potentielle etableringsareal for vind og sol. Ikke alle GIS-lag, der bruges i '
                             'analysen, vises på kortet fra start, men de kan åbnes under avancerede indstillinger, når du vil se hvilke antagelser der '
                             'påvirker arealet.',
                             'The starting point shows the analysis result: the potential establishment area for wind and solar. Not every GIS layer used in '
                             'the analysis is shown on the map by default, but they can be opened under advanced settings when you want to see which '
                             'assumptions shape the area.'),
 'tutorial.energy_title': ('Koppla yta till energi', 'Knytt areal til energi', 'Kobl areal til energi', 'Connect area to energy'),
 'tutorial.energy_body': ('Energimixen i huvudytan låter dig pröva balansen mellan vind och sol. Energimodelleringen översätter valt scenario till ett '
                          'ytanspråk.',
                          'Energimiksen i hovedflaten lar deg prøve balansen mellom vind og sol. Energimodelleringen omregner valgt scenario til et '
                          'arealbehov.',
                          'Energimix-kontrollen i hovedvisningen lader dig teste balancen mellem vind og sol. Energimodelleringen oversætter valgt scenarie '
                          'til et arealkrav.',
                          'The energy mix control in the main view lets you test the balance between wind and solar. Energy modelling translates the selected '
                          'scenario into an area claim.'),
 'tutorial.scenario_title': ('Energiscenario och markintensitet',
                             'Energiscenario og arealintensitet',
                             'Energiscenarie og arealintensitet',
                             'Energy scenario and land intensity'),
 'tutorial.scenario_body': ('Energiscenario styr hur mycket energi som ska testas i modellen. Markintensitet styr hur mycket mark som behövs per TWh och kan '
                            'väljas låg, mellan eller hög oberoende av energiscenariot. Därför kan du till exempel testa hög energinivå med mellan '
                            'markintensitet.',
                            'Energiscenarioet styrer hvor mye energi som skal testes i modellen. Arealintensiteten styrer hvor mye land som trengs per TWh og '
                            'kan velges lav, middels eller høy uavhengig av energiscenarioet. Derfor kan du for eksempel teste et høyt energinivå med middels '
                            'arealintensitet.',
                            'Energiscenariet styrer hvor meget energi der testes i modellen. Arealintensitet styrer hvor meget areal der behøves per TWh og '
                            'kan vælges lav, mellem eller høj uafhængigt af energiscenariet. Derfor kan du for eksempel teste et højt energiniveau med mellem '
                            'arealintensitet.',
                            'The energy scenario controls how much energy is tested in the model. Land intensity controls how much land is needed per TWh and '
                            'can be low, medium or high independently of the energy scenario. For example, you can test a high energy level with medium land '
                            'intensity.'),
 'tutorial.acceptance_title': ('Lägg till social acceptans', 'Legg til sosial aksept', 'Tilføj social accept', 'Add social acceptance'),
 'tutorial.acceptance_body': ('Social acceptans hjälper dig förstå var potentialen kan vara mer eller mindre realistisk utifrån landskapets användning, värden '
                              'och möjliga konflikter. Syntetiskt eller provisoriskt underlag ska alltid framgå av den aktiva regionens manifest och '
                              'datastatus.',
                              'Sosial aksept hjelper deg å forstå hvor potensialet kan være mer eller mindre realistisk ut fra landskapets bruk, verdier og '
                              'mulige konflikter. Syntetiske eller foreløpige data skal alltid framgå av den aktive regionens manifest og datastatus.',
                              'Social accept hjælper dig med at forstå hvor potentialet kan være mere eller mindre realistisk ud fra landskabets anvendelse, '
                              'værdier og mulige konflikter. Syntetiske eller foreløbige data skal altid fremgå af den aktive regions manifest og datastatus.',
                              'Social acceptance helps you understand where the potential may be more or less realistic given landscape use, values and '
                              "possible conflicts. Synthetic or provisional inputs must always be identified by the active region's manifest and data status."),
 'tutorial.acceptance_suggestion': ('Dra i reglaget Acceptanspåverkan och följ hur energilandskapet förändras i kartan och i tabellen till höger.',
                                    'Dra i skyveknappen Akseptpåvirkning og følg hvordan energilandskapet endres i kartet og i tabellen til høyre.',
                                    'Træk i skyderen Acceptpåvirkning og følg hvordan energilandskabet ændrer sig på kortet og i tabellen til højre.',
                                    'Drag the Acceptance impact slider and watch how the energy landscape changes on the map and in the table to the right.'),
 'tutorial.establishment_body': ('Kartan visar den sammanvägda etableringspotentialen: grön betyder både vind och sol, gul bara sol, blå bara vind och röd ej '
                                 'lämpligt. Det är potential utifrån de geografiska antaganden och filter som är aktiva just nu.',
                                 'Kartet viser det samlede etableringspotensialet: grønt betyr både vind og sol, gult bare sol, blått bare vind og rødt ikke '
                                 'egnet. Dette er potensialet ut fra de geografiske antakelsene og filtrene som er aktive nå.',
                                 'Kortet viser det samlede etableringspotentiale: grøn betyder både vind og sol, gul kun sol, blå kun vind og rød ikke egnet. '
                                 'Det er potentialet ud fra de geografiske antagelser og filtre som er aktive lige nu.',
                                 'The map shows the combined establishment potential: green means both wind and solar, yellow solar only, blue wind only and '
                                 'red not suitable. It is the potential under the geographic assumptions and filters that are active right now.'),
 'tutorial.allocation_body': ('Scenarioyta inom potentialen visar var modellens vind- och solyta placeras. Blått är vind och gulorange är sol. Mörkgrön betyder att båda teknikerna har yta i samma visningshex, inte att exakt fysisk överlappning har beräknats.', 'Scenarioareal innenfor potensialet viser hvor modellens vind- og solareal plasseres. Blått er vind og guloransje er sol. Mørkegrønn betyr at begge teknologier har areal i samme visningshex, ikke at nøyaktig fysisk overlapping er beregnet.', 'Scenariefordelingen viser hvor modellen placerer vind- og solareal inden for den mulige etableringsflade. Blå betyder vind og gulorange betyder sol. Mørkegrøn betyder at begge teknologier har areal i samme viste hex, ikke at et præcist fysisk overlap er beregnet.', 'The scenario allocation shows where the model places wind and solar area within the possible establishment area. Blue means wind and yellow-orange means solar. Dark green means both technologies have area in the same displayed hex, not that exact physical overlap was calculated.'),
 'tutorial.outside_body': ('Ytbehov utanför landskapets potential visar schematisk vind- eller solyta som behövs när scenariot inte ryms i den beräknade '
                           'potentialen. Det gör skillnaden mellan landskapets möjliga yta och scenariots efterfrågan synlig.',
                           'Arealbehov utenfor landskapets potensial viser skjematisk vind- eller solareal som trengs når scenarioet ikke får plass innenfor '
                           'det beregnede potensialet. Det synliggjør forskjellen mellom landskapets mulige areal og scenarioets etterspørsel.',
                           'Arealbehov udenfor landskabets potentiale viser skematisk vind- eller solareal som behøves, når scenariet ikke kan rummes i det '
                           'beregnede potentiale. Det gør forskellen mellem landskabets mulige areal og scenariets efterspørgsel synlig.',
                           'Area demand outside landscape potential shows schematic wind or solar area needed when the scenario does not fit inside the '
                           'calculated potential. It makes the gap between possible landscape area and scenario demand visible.'),
 'tutorial.green_title': ('Startläget är försiktigt', 'Utgangspunktet er forsiktig', 'Startpunktet er forsigtigt', 'The starting point is cautious'),
 'tutorial.green_body': ('Kartan startar med ett restriktivt potentialläge så att antaganden och bortval syns direkt. Grönt betyder möjligt enligt nuvarande '
                         'filter, inte ett färdigt rekommenderat område.',
                         'Kartet starter med et restriktivt potensialnivå slik at antakelser og fravalg blir synlige straks. Grønt betyr mulig etter gjeldende '
                         'filtre, ikke et ferdig anbefalt område.',
                         'Kortet starter i en restriktiv potentialtilstand, så antagelser og fravalg ses direkte. Grøn betyder muligt med nuværende filtre, '
                         'ikke et færdigt anbefalet område.',
                         'The map starts in a restrictive potential mode so assumptions and exclusions are visible immediately. Green means possible under the '
                         'current filters, not a final recommended area.'),
 'tutorial.wind_solar_title': ('Vind och sol styrs under Geografier',
                               'Vind og sol styres under Geografier',
                               'Vind og sol styres under Geografier',
                               'Wind and solar are controlled under Geographies'),
 'tutorial.wind_solar_body': ('Under Geografier finns Landskapspotential Vind och Landskapspotential Sol. Där kan du ändra de förvalda filtren, buffertarna '
                              'och nätantagandena. Analysen använder valen även när GIS-lagren är dolda i kartan.',
                              'Under Geografier finnes Landskapspotensial vind og Landskapspotensial sol. Her kan du endre de forhåndsvalgte filtrene, '
                              'bufferne og nettantakelsene. Analysen bruker valgene også når GIS-lagene er skjult i kartet.',
                              'Under Geografier findes Landskabspotentiale vind og Landskabspotentiale sol. Her kan du ændre de forvalgte filtre, buffere og '
                              'netantagelser. Analysen bruger valgene, selv når GIS-lagene er skjult på kortet.',
                              'Under Geographies you will find Wind landscape potential and Solar landscape potential. This is where you can change the preset '
                              'filters, buffers and grid assumptions. The analysis uses those choices even when the GIS layers are hidden on the map.'),
 'tutorial.wind_apply_title': ('Ändra vindantaganden och använd dem',
                               'Endre vindantakelser og bruk dem',
                               'Ændr vindantagelser og anvend dem',
                               'Change wind assumptions and apply them'),
 'tutorial.wind_apply_body': ('Öppna vindpotentialen om du vill ändra startlägets filter, till exempel Befolkning och bebyggelse eller vägar. Klicka sedan '
                              'Använd ändringar för att räkna om kartan och resultatet med de valda antagandena.',
                              'Åpne vindpotensialet hvis du vil endre utgangspunktets filtre, for eksempel Befolkning og bebyggelse eller veier. Klikk '
                              'deretter Bruk endringer for å beregne kartet og resultatet på nytt med valgte antakelser.',
                              'Åbn vindpotentialet, hvis du vil ændre startfiltrene, for eksempel Befolkning og bebyggelse eller veje. Klik derefter Anvend '
                              'ændringer for at beregne kortet og resultatet igen med de valgte antagelser.',
                              'Open wind potential if you want to change the starting filters, for example Population and settlement or roads. Then click '
                              'Apply changes to recalculate the map and result using the selected assumptions.'),
 'tutorial.action_open_geography_todo': ('Öppna Geografier och Landskap för att se vilka antaganden som formar kartan.',
                                         'Åpne Geografier og Landskap for å se hvilke antakelser som former kartet.',
                                         'Åbn Geografier og Landskab for at se hvilke antagelser som former kortet.',
                                         'Open Geographies and Landscape to see which assumptions shape the map.'),
 'tutorial.action_open_geography_done': ('Bra, nu är landskapsvalen synliga. Fortsätt med energimodelleringen eller testa egna filter.',
                                         'Bra, nå er landskapsvalgene synlige. Fortsett med energimodelleringen eller prøv egne filtre.',
                                         'Godt, nu er landskabsvalgene synlige. Fortsæt med energimodelleringen eller test egne filtre.',
                                         'Good, the landscape choices are visible. Continue with energy modelling or try your own filters.'),
 'tutorial.action_open_wind_todo': ('Öppna vind- och solpotentialen för att se vilka antaganden du kan ändra.',
                                    'Åpne vind- og solpotensialet for å se hvilke antakelser du kan endre.',
                                    'Åbn vind- og solpotentialet for at se hvilke antagelser du kan ændre.',
                                    'Open wind and solar potential to see which assumptions you can change.'),
 'tutorial.action_open_wind_done': ('Bra, nu är potentialkontrollerna synliga. Testa ett filter eller fortsätt till omräkningen.',
                                    'Bra, nå er potensialkontrollene synlige. Prøv et filter eller fortsett til ny beregning.',
                                    'Godt, nu er potentialekontrollerne synlige. Test et filter eller fortsæt til genberegningen.',
                                    'Good, the potential controls are visible. Try a filter or continue to recalculation.'),
 'tutorial.action_apply_wind_todo': ('Klicka på Använd ändringar när du vill räkna om kartan och resultatet med filtervalen.',
                                     'Klikk på Bruk endringer når du vil beregne kartet og resultatet på nytt med filtervalgene.',
                                     'Klik på Anvend ændringer når du vil beregne kortet og resultatet igen med filtervalgene.',
                                     'Click Apply changes when you want to recalculate the map and result using the filter choices.'),
 'tutorial.action_apply_wind_done': ('Bra, appen har fått en apply-signal. Kontrollera kartan och resultatpanelen innan du går vidare.',
                                     'Bra, appen har fått et signal om å bruke endringene. Kontroller kartet og resultatpanelet før du fortsetter.',
                                     'Godt, appen har fået et apply-signal. Kontrollér kortet og resultatpanelet før du går videre.',
                                     'Good, the app received an apply signal. Check the map and result panel before continuing.'),
 'tutorial.table_title': ('Läs resultatet i tabellen', 'Les resultatet i tabellen', 'Læs resultatet i tabellen', 'Read the result table'),
 'tutorial.table_body': ('Tabellen visar om energimixen ryms inom den beräknade potentialen. Totalraden är en tekniksumma: samma fysiska hex kan räknas för '
                         'både vind och sol när ytan kan samnyttjas.',
                         'Tabellen viser om energimiksen får plass innenfor det beregnede potensialet. Totalraden er en teknologisum: samme fysiske hex kan '
                         'telles for både vind og sol når arealet kan deles.',
                         'Tabellen viser om energimixet kan rummes inden for det beregnede potentiale. Totalrækken er en teknologisum: samme fysiske hex kan '
                         'tælle for både vind og sol, når arealet kan deles.',
                         'The table shows whether the energy mix fits within the calculated potential. The total row is a technology sum: the same physical '
                         'hex can count for both wind and solar when the area can be shared.'),
 'tutorial.right_geographies_title': ('Geografier visar antagandena',
                                      'Geografier viser antakelsene',
                                      'Geografier viser antagelserne',
                                      'Geographies show the assumptions'),
 'tutorial.right_geographies_body': ('Här sammanfattas vilka GIS-lager och filter som formar kartan, till exempel befolkning, vägar, naturvärden och '
                                     'kulturmiljöer.',
                                     'Her oppsummeres hvilke GIS-lag og filtre som former kartet, for eksempel befolkning, veier, naturverdier og '
                                     'kulturmiljøer.',
                                     'Her sammenfattes hvilke GIS-lag og filtre der former kortet, for eksempel befolkning, veje, naturværdier og '
                                     'kulturmiljøer.',
                                     'This section summarizes which GIS layers and filters shape the map, such as population, roads, nature values and '
                                     'cultural environments.'),
 'tutorial.landscape_distribution_title': ('Potential per landskapstyp',
                                           'Potensial per landskapstype',
                                           'Potentiale per landskabstype',
                                           'Potential by landscape type'),
 'tutorial.landscape_distribution_body': ('De två expandrarna visar hur vind- och solpotentialen fördelas mellan landskapstyper. Det hjälper dig se vilken typ '
                                          'av landskap potentialen hamnar i.',
                                          'De to utvidbare panelene viser hvordan vind- og solpotensialet fordeles mellom landskapstyper. Det hjelper deg å se '
                                          'hvilke landskapstyper potensialet ligger i.',
                                          'De to expandere viser hvordan vind- og solpotentialet fordeles mellem landskabstyper. Det hjælper dig med at se '
                                          'hvilken type landskab potentialet havner i.',
                                          'The two expanders show how wind and solar potential are distributed across landscape types. This helps you see '
                                          'which kinds of landscape the potential falls within.'),
 'tutorial.reopen_title': ('Du kan alltid öppna guiden igen',
                           'Du kan alltid åpne veiledningen igjen',
                           'Du kan altid åbne guiden igen',
                           'You can always open the guide again'),
 'tutorial.reopen_body': ('Starta om den korta guiden med Visa guide. Kryssa i Öppna inte automatiskt igen om du vill att appen ska hoppa över introduktionen '
                          'nästa gång.',
                          'Start den korte veiledningen på nytt med Vis veiledning. Kryss av for Ikke åpne automatisk igjen hvis du vil at appen skal hoppe '
                          'over introduksjonen neste gang.',
                          'Start den korte guide igen med Vis guide. Marker Åbn ikke automatisk igen hvis du vil have appen til at springe introduktionen over '
                          'næste gang.',
                          'Restart the short guide with Show guide. Tick Do not open automatically again if you want the app to skip the introduction next '
                          'time.')})

# Role-specific map labels. Raw scenario/provider fields retain their identities.
MESSAGES.update({
    'map.acceptance_low_compact': ('Lågacceptans', 'Lav aksept', 'Lav accept', 'Low acceptance'),
    'map.acceptance_high_compact': ('Högacceptans', 'Høy aksept', 'Høj accept', 'High acceptance'),
    'map.acceptance_layer_name': (
        'Social acceptans: {class_label}', 'Sosial aksept: {class_label}',
        'Social accept: {class_label}', 'Social acceptance: {class_label}',
    ),
    'map.wind_core_single': ('Enskild hex', 'Enkelt hex', 'Enkelt hex', 'Single hex'),
    'map.wind_core_deep': ('Djup kärna', 'Dyp kjerne', 'Dyb kerne', 'Deep core'),
    'map.wind_core_middle': ('Mellanläge', 'Mellomposisjon', 'Mellemposition', 'Intermediate position'),
    'map.wind_core_edge': ('Kantzon', 'Kantsone', 'Kantzone', 'Edge zone'),
    'map.wind_core_legend': (
        'Mörkare blå = djupare kärnområde', 'Mørkere blå = dypere kjerneområde',
        'Mørkere blå = dybere kerneområde', 'Darker blue = deeper core area',
    ),
    'form.source_not_ready': (
        'Datakällan är inte redo: {p0}', 'Datakilden er ikke klar: {p0}',
        'Datakilden er ikke klar: {p0}', 'The data source is not ready: {p0}',
    ),
})

# Generic source categories and authored help from active regional form manifests.
# Organisation, dataset, legislative and region names inside notes stay original.
MESSAGES.update({'form.manifest.bornholm.roads.interpretation': ('Valt minsta avstånd gäller för alla valda väglager.',
                                                 'Valgt minsteavstand gjelder alle valgte veilag.',
                                                 'Den valgte minimumsafstand gælder alle valgte vejlag.',
                                                 'The chosen minimum distance applies to every selected road layer.'),
 'form.manifest.bornholm.population.interpretation': ('Yta inom valt minsta avstånd från valda befolknings- och bebyggelsekällor tas bort från den beräknade '
 'potentialen. En redan inbyggd buffert ingår i avståndet och läggs inte på igen.',
 'Areal innenfor valgt minsteavstand fra valgte befolknings- og bebyggelseskilder fjernes fra det '
 'beregnede potensialet. En allerede innebygd buffer inngår i avstanden og legges ikke til på nytt.',
 'Areal inden for den valgte minimumsafstand fra valgte befolknings- og bebyggelseskilder fjernes fra det '
 'beregnede potentiale. En allerede indbygget buffer indgår i afstanden og tilføjes ikke igen.',
 'Area within the selected minimum distance of selected population and settlement sources is removed from '
 'the calculated potential. Any existing built-in buffer is included in that distance and is not added '
 'again.'),
 'form.manifest.bornholm.nature.interpretation': ('Valda naturkällor och eventuell buffert minskar den tillgängliga ytan inom varje hexagon. Endast den del '
 'som överlappar tas bort. Vid 0 m buffert används naturkällornas egna ytor.',
 'Valgte naturkilder og eventuell buffer reduserer tilgjengelig areal i hvert heksagon. Bare den '
 'overlappende delen fjernes. Ved 0 m buffer brukes naturkildenes egne arealer.',
 'Valgte naturkilder og en eventuel buffer reducerer det tilgængelige areal i hver sekskant. Kun den '
 'overlappende del fjernes. Ved 0 m buffer bruges naturkildernes egne arealer.',
 'Selected nature sources and any buffer reduce the available area within each hexagon. Only the '
 'overlapping portion is removed. At 0 m buffer, the nature sources’ own areas are used.'),
 'form.manifest.bornholm.culture.interpretation': ('Valda kulturkällor och eventuell buffert minskar den tillgängliga ytan inom varje hexagon. Endast den '
 'del som överlappar tas bort. Vid 0 m buffert används kulturkällornas egna geometrier.',
 'Valgte kulturkilder og eventuell buffer reduserer tilgjengelig areal i hvert heksagon. Bare den '
 'overlappende delen fjernes. Ved 0 m buffer brukes kulturkildenes egne geometrier.',
 'Valgte kulturkilder og en eventuel buffer reducerer det tilgængelige areal i hver sekskant. Kun den '
 'overlappende del fjernes. Ved 0 m buffer bruges kulturkildernes egne geometrier.',
 'Selected cultural sources and any buffer reduce the available area within each hexagon. Only the '
 'overlapping portion is removed. At 0 m buffer, the cultural sources’ own geometries are used.'),
 'form.manifest.bornholm.grid_infrastructure.interpretation': ('Yta utanför valt anslutningsavstånd ingår inte i den beräknade potentialen. Avståndet mäts till valda '
 'ledningar, kablar och punktobjekt. Närhet innebär inte att det finns ledig anslutningskapacitet.',
 'Areal utenfor valgt tilknytningsavstand inngår ikke i det beregnede potensialet. Avstanden måles til '
 'valgte ledninger, kabler og punktobjekter. Nærhet betyr ikke at det finnes ledig tilknytningskapasitet.',
 'Areal uden for den valgte tilslutningsafstand indgår ikke i det beregnede potentiale. Afstanden måles '
 'til valgte ledninger, kabler og punktobjekter. Nærhed betyder ikke, at der er ledig '
 'tilslutningskapacitet.',
 'Area outside the selected connection distance is excluded from the calculated potential. Distance is '
 'measured to selected lines, cables and point features. Proximity does not imply available grid '
 'connection capacity.'),
 'form.manifest.bornholm.roads_large.label': ('Stora vägar', 'Store veier', 'Store veje', 'Major roads'),
 'form.manifest.bornholm.roads_large.note': ('GeoDanmark-kategorierna Stor vej, Fordelingsrute och Gennemfartsrute i den deklarerade '
                                             'Bornholm-snapshoten.',
                                             'GeoDanmark-kategoriene Stor vej, Fordelingsrute og Gennemfartsrute i det deklarerte '
                                             'Bornholm-øyeblikksbildet.',
                                             'GeoDanmark-kategorierne Stor vej, Fordelingsrute og Gennemfartsrute i det deklarerede '
                                             'Bornholm-øjebliksbillede.',
                                             'GeoDanmark categories Stor vej, Fordelingsrute and Gennemfartsrute in the declared Bornholm snapshot.'),
 'form.manifest.bornholm.roads_medium.label': ('Mellanvägar', 'Mellomstore veier', 'Mellemstore veje', 'Intermediate roads'),
 'form.manifest.bornholm.roads_medium.note': ('GeoDanmark-kategorin Mellem vej i den deklarerade Bornholm-snapshoten.',
                                              'GeoDanmark-kategorien Mellem vej i det deklarerte Bornholm-øyeblikksbildet.',
                                              'GeoDanmark-kategorien Mellem vej i det deklarerede Bornholm-øjebliksbillede.',
                                              'GeoDanmark category Mellem vej in the declared Bornholm snapshot.'),
 'form.manifest.bornholm.built_centre.label': ('Tät bebyggelse', 'Tett bebyggelse', 'Tæt bebyggelse', 'Dense settlement'),
 'form.manifest.bornholm.built_centre.note': ('GeoDanmark: Bykärna, historiskt V1-underlag. Tekniskt startvärde: 100 m; detta är inte en regional '
                                              'rekommendation.',
                                              'GeoDanmark: Bykärna, historisk V1-grunnlag. Teknisk startverdi: 100 m; dette er ikke en regional '
                                              'anbefaling.',
                                              'GeoDanmark: Bykärna, historisk V1-grundlag. Teknisk startværdi: 100 m; dette er ikke en regional '
                                              'anbefaling.',
                                              'GeoDanmark: Bykärna, historical V1 data. Technical starting value: 100 m; this is not a regional '
                                              'recommendation.'),
 'form.manifest.bornholm.built_low_selection.label': ('Låg bebyggelse', 'Lav bebyggelse', 'Lav bebyggelse', 'Low-rise settlement'),
 'form.manifest.bornholm.built_low_selection.note': ('GeoDanmark: Låg bebyggelse, historiskt V1-underlag. Tekniskt startvärde: 100 m; detta är inte '
                                                     'en regional rekommendation.',
                                                     'GeoDanmark: Låg bebyggelse, historisk V1-grunnlag. Teknisk startverdi: 100 m; dette er ikke en '
                                                     'regional anbefaling.',
                                                     'GeoDanmark: Låg bebyggelse, historisk V1-grundlag. Teknisk startværdi: 100 m; dette er ikke en '
                                                     'regional anbefaling.',
                                                     'GeoDanmark: Låg bebyggelse, historical V1 data. Technical starting value: 100 m; this is not a '
                                                     'regional recommendation.'),
 'form.manifest.bornholm.protected_areas.label': ('Fredade områden', 'Fredete områder', 'Fredede områder', 'Protected areas'),
 'form.manifest.bornholm.protected_areas.note': ('Miljøstyrelsen / Danmarks Miljøportal: Fredede områder. Tekniskt startvärde: 0 m; detta är inte en '
                                                 'regional rekommendation.',
                                                 'Miljøstyrelsen / Danmarks Miljøportal: Fredede områder. Teknisk startverdi: 0 m; dette er ikke en '
                                                 'regional anbefaling.',
                                                 'Miljøstyrelsen / Danmarks Miljøportal: Fredede områder. Teknisk startværdi: 0 m; dette er ikke en '
                                                 'regional anbefaling.',
                                                 'Miljøstyrelsen / Danmarks Miljøportal: Fredede områder. Technical starting value: 0 m; this is not '
                                                 'a regional recommendation.'),
 'form.manifest.bornholm.cultural_preservation.label': ('Kulturhistoriska bevarandevärden',
                                                        'Kulturhistoriske bevaringsverdier',
                                                        'Kulturhistoriske bevaringsværdier',
                                                        'Cultural heritage conservation values'),
 'form.manifest.bornholm.cultural_preservation.note': ('Bornholms Regionskommune / Plandata.dk: Kulturhistoriske bevaringsværdier, Bornholms '
                                                       'Kommuneplan 2020. Tekniskt startvärde: 0 m; detta är inte en regional rekommendation.',
                                                       'Bornholms Regionskommune / Plandata.dk: Kulturhistoriske bevaringsværdier, Bornholms '
                                                       'Kommuneplan 2020. Teknisk startverdi: 0 m; dette er ikke en regional anbefaling.',
                                                       'Bornholms Regionskommune / Plandata.dk: Kulturhistoriske bevaringsværdier, Bornholms '
                                                       'Kommuneplan 2020. Teknisk startværdi: 0 m; dette er ikke en regional anbefaling.',
                                                       'Bornholms Regionskommune / Plandata.dk: Kulturhistoriske bevaringsværdier, Bornholms '
                                                       'Kommuneplan 2020. Technical starting value: 0 m; this is not a regional recommendation.'),
 'form.manifest.bornholm.valuable_cultural_environment.note': ('Bornholms Regionskommune / Plandata.dk: Værdifulde kulturmiljøer, Bornholms '
                                                               'Kommuneplan 2020. Tekniskt startvärde: 0 m; detta är inte en regional '
                                                               'rekommendation.',
                                                               'Bornholms Regionskommune / Plandata.dk: Værdifulde kulturmiljøer, Bornholms '
                                                               'Kommuneplan 2020. Teknisk startverdi: 0 m; dette er ikke en regional anbefaling.',
                                                               'Bornholms Regionskommune / Plandata.dk: Værdifulde kulturmiljøer, Bornholms '
                                                               'Kommuneplan 2020. Teknisk startværdi: 0 m; dette er ikke en regional anbefaling.',
                                                               'Bornholms Regionskommune / Plandata.dk: Værdifulde kulturmiljøer, Bornholms '
                                                               'Kommuneplan 2020. Technical starting value: 0 m; this is not a regional '
                                                               'recommendation.'),
 'form.manifest.bornholm.high_voltage_lines.label': ('Högspänningsledningar', 'Høyspentledninger', 'Højspændingsledninger', 'High-voltage lines'),
 'form.manifest.bornholm.high_voltage_lines.note': ('OpenStreetMap contributors: OSM 60 kV overhead lines, Overpass 2026-09-05. Tekniskt startvärde: '
                                                    '2000 m; detta är inte en regional rekommendation.',
                                                    'OpenStreetMap contributors: OSM 60 kV overhead lines, Overpass 2026-09-05. Teknisk startverdi: '
                                                    '2000 m; dette er ikke en regional anbefaling.',
                                                    'OpenStreetMap contributors: OSM 60 kV overhead lines, Overpass 2026-09-05. Teknisk startværdi: '
                                                    '2000 m; dette er ikke en regional anbefaling.',
                                                    'OpenStreetMap contributors: OSM 60 kV overhead lines, Overpass 2026-09-05. Technical starting '
                                                    'value: 2000 m; this is not a regional recommendation.'),
 'form.manifest.bornholm.underground_cables.label': ('Markkablar', 'Jordkabler', 'Jordkabler', 'Underground cables'),
 'form.manifest.bornholm.underground_cables.note': ('OpenStreetMap contributors: OSM 60 kV underground cables, Overpass 2026-09-05. Tekniskt '
                                                    'startvärde: 2000 m; detta är inte en regional rekommendation.',
                                                    'OpenStreetMap contributors: OSM 60 kV underground cables, Overpass 2026-09-05. Teknisk '
                                                    'startverdi: 2000 m; dette er ikke en regional anbefaling.',
                                                    'OpenStreetMap contributors: OSM 60 kV underground cables, Overpass 2026-09-05. Teknisk '
                                                    'startværdi: 2000 m; dette er ikke en regional anbefaling.',
                                                    'OpenStreetMap contributors: OSM 60 kV underground cables, Overpass 2026-09-05. Technical '
                                                    'starting value: 2000 m; this is not a regional recommendation.'),
 'form.manifest.bornholm.power_substations.label': ('Transformatorstationer', 'Transformatorstasjoner', 'Transformatorstationer', 'Substations'),
 'form.manifest.bornholm.power_substations.note': ('OpenStreetMap contributors: OSM 60 kV distribution substations, Overpass 2026-09-05. Tekniskt '
                                                   'startvärde: 2000 m; detta är inte en regional rekommendation.',
                                                   'OpenStreetMap contributors: OSM 60 kV distribution substations, Overpass 2026-09-05. Teknisk '
                                                   'startverdi: 2000 m; dette er ikke en regional anbefaling.',
                                                   'OpenStreetMap contributors: OSM 60 kV distribution substations, Overpass 2026-09-05. Teknisk '
                                                   'startværdi: 2000 m; dette er ikke en regional anbefaling.',
                                                   'OpenStreetMap contributors: OSM 60 kV distribution substations, Overpass 2026-09-05. Technical '
                                                   'starting value: 2000 m; this is not a regional recommendation.'),
 'form.manifest.bornholm.natura_bird_protection.label': ('Natura 2000 – fågelskydd',
                                                         'Natura 2000 – fuglevern',
                                                         'Natura 2000 – fuglebeskyttelse',
                                                         'Natura 2000 – bird protection'),
 'form.manifest.bornholm.natura_bird_protection.note': ('Miljøstyrelsen / Danmarks Miljøportal: Natura 2000 – fuglebeskyttelsesområder. Kompletterar '
                                                        'Fredade områden; överlapp räknas en gång.',
                                                        'Miljøstyrelsen / Danmarks Miljøportal: Natura 2000 – fuglebeskyttelsesområder. Supplerer '
                                                        'Fredede områder; overlapp telles én gang.',
                                                        'Miljøstyrelsen / Danmarks Miljøportal: Natura 2000 – fuglebeskyttelsesområder. Supplerer '
                                                        'Fredede områder; overlap tælles én gang.',
                                                        'Miljøstyrelsen / Danmarks Miljøportal: Natura 2000 – fuglebeskyttelsesområder. Supplements '
                                                        'Fredede områder; overlap is counted once.'),
 'form.manifest.bornholm.natura_habitat_areas.label': ('Natura 2000 – habitatområden',
                                                       'Natura 2000 – habitatområder',
                                                       'Natura 2000 – habitatområder',
                                                       'Natura 2000 – habitat areas'),
 'form.manifest.bornholm.natura_habitat_areas.note': ('Miljøstyrelsen / Danmarks Miljøportal: Natura 2000 – habitatområder. Kompletterar Fredade '
                                                      'områden; överlapp räknas en gång.',
                                                      'Miljøstyrelsen / Danmarks Miljøportal: Natura 2000 – habitatområder. Supplerer Fredede '
                                                      'områder; overlapp telles én gang.',
                                                      'Miljøstyrelsen / Danmarks Miljøportal: Natura 2000 – habitatområder. Supplerer Fredede '
                                                      'områder; overlap tælles én gang.',
                                                      'Miljøstyrelsen / Danmarks Miljøportal: Natura 2000 – habitatområder. Supplements Fredede '
                                                      'områder; overlap is counted once.'),
 'form.manifest.bornholm.wind_turbines_osm.label': ('Befintliga vindkraftverk (OSM)',
                                                    'Eksisterende vindturbiner (OSM)',
                                                    'Eksisterende vindmøller (OSM)',
                                                    'Existing wind turbines (OSM)'),
 'form.manifest.bornholm.wind_turbines_osm.note': ('OpenStreetMap contributors: OSM mapped wind generators, Overpass 2026-10-08. Registrerade lägen '
                                                   'som anslutningsproxy; driftsstatus och ledig nätkapacitet är inte verifierade.',
                                                   'OpenStreetMap contributors: OSM mapped wind generators, Overpass 2026-10-08. Registrerte '
                                                   'plasseringer brukes som tilknytningsproxy; driftsstatus og ledig nettkapasitet er ikke '
                                                   'verifisert.',
                                                   'OpenStreetMap contributors: OSM mapped wind generators, Overpass 2026-10-08. Registrerede '
                                                   'placeringer bruges som tilslutningsproxy; driftsstatus og ledig netkapacitet er ikke '
                                                   'verificeret.',
                                                   'OpenStreetMap contributors: OSM mapped wind generators, Overpass 2026-10-08. Recorded locations '
                                                   'serve as a connection proxy; operating status and spare grid capacity are unverified.'),
 'form.manifest.bornholm.solar_parks_osm.label': ('Befintliga solanläggningar (OSM)',
                                                  'Eksisterende solanlegg (OSM)',
                                                  'Eksisterende solanlæg (OSM)',
                                                  'Existing solar installations (OSM)'),
 'form.manifest.bornholm.solar_parks_osm.note': ('OpenStreetMap contributors: OSM mapped photovoltaic plant boundaries, Overpass 2026-10-08. '
                                                 'Registrerade lägen som anslutningsproxy; driftsstatus och ledig nätkapacitet är inte verifierade.',
                                                 'OpenStreetMap contributors: OSM mapped photovoltaic plant boundaries, Overpass 2026-10-08. '
                                                 'Registrerte plasseringer brukes som tilknytningsproxy; driftsstatus og ledig nettkapasitet er ikke '
                                                 'verifisert.',
                                                 'OpenStreetMap contributors: OSM mapped photovoltaic plant boundaries, Overpass 2026-10-08. '
                                                 'Registrerede placeringer bruges som tilslutningsproxy; driftsstatus og ledig netkapacitet er ikke '
                                                 'verificeret.',
                                                 'OpenStreetMap contributors: OSM mapped photovoltaic plant boundaries, Overpass 2026-10-08. '
                                                 'Recorded locations serve as a connection proxy; operating status and spare grid capacity are '
                                                 'unverified.'),
 'form.manifest.bornholm.population_points.label': ('Fastboende befolkning – buffertyta',
                                                    'Fastboende befolkning – bufferareal',
                                                    'Fastboende befolkning – bufferareal',
                                                    'Resident population – buffer area'),
 'form.manifest.bornholm.population_points.note': ('Befintlig, sammanslagen 100-metersbuffert runt befolkningspunkter. Avståndsreglaget anger det '
                                                   'totala avståndet. Endast buffertytan visas.',
                                                   'Eksisterende, sammenslått 100-metersbuffer rundt befolkningspunkter. Avstandsreguleringen angir '
                                                   'den totale avstanden. Bare bufferarealet vises.',
                                                   'Eksisterende, sammenlagt 100-metersbuffer omkring befolkningspunkter. Afstandsreguleringen '
                                                   'angiver den samlede afstand. Kun bufferarealet vises.',
                                                   'Existing merged 100-metre buffer around population points. The distance control specifies the '
                                                   'total distance. Only the buffer area is shown.'),
 'form.manifest.bornholm.coastal_proximity_zone.label': ('Kustnärhetszon – planeringshänsyn',
                                                         'Kystnærhetssone – planleggingshensyn',
                                                         'Kystnærhedszone – planlægningshensyn',
                                                         'Coastal proximity zone – planning consideration'),
 'form.manifest.bornholm.coastal_proximity_zone.note': ('Planeringszon för kusthänsyn. När vald räknas zonen bort i denna analys; det är ett '
                                                        'modellval, inte ett generellt byggförbud. Polygonen visar den befintliga zonen. '
                                                        'Avståndsreglaget anger en eventuell tilläggsbuffert.',
                                                        'Planleggingssone for kysthensyn. Når valgt trekkes sonen fra i denne analysen; dette er et '
                                                        'modellvalg, ikke et generelt byggeforbud. Polygonet viser den eksisterende sonen. '
                                                        'Avstandsreguleringen angir en eventuell tilleggsbuffer.',
                                                        'Planlægningszone for kysthensyn. Når valgt trækkes zonen fra i denne analyse; det er et '
                                                        'modelvalg, ikke et generelt byggeforbud. Polygonen viser den eksisterende zone. '
                                                        'Afstandsreguleringen angiver en eventuel tillægsbuffer.',
                                                        'Planning zone for coastal considerations. When selected, the zone is excluded in this '
                                                        'analysis; this is a model choice, not a general building prohibition. The polygon shows the '
                                                        'existing zone. The distance control specifies any additional buffer.'),
 'form.manifest.skaraborg.roads.interpretation': ('För nära är dåligt. Valda väglager kombineras till en gemensam avståndsrestriktion.',
                                                  'For nær er ugunstig. Valgte veilag kombineres til en felles avstandsrestriksjon.',
                                                  'For tæt på er ugunstigt. Valgte vejlag kombineres til en fælles afstandsrestriktion.',
                                                  'Being too close is unfavorable. Selected road layers are combined into a shared distance '
                                                  'restriction.'),
 'form.manifest.skaraborg.roads_large.label': ('Nationellt och regionalt huvudnät',
                                               'Nasjonalt og regionalt hovedveinett',
                                               'Nationalt og regionalt hovedvejnet',
                                               'National and regional main road network'),
 'form.manifest.skaraborg.roads_large.note': ('Owner-approved NVDB functional road classes 0-3; 100 m is a technical review value, not a regional '
                                              'recommendation. Tekniskt startvärde: 100 m; detta är inte en regional rekommendation. Ingen '
                                              'accepterad regional rekommendation: Skaraborg has not adopted a regional recommended road distance; '
                                              '100 m is only an owner-approved technical review start value.',
                                              'Eiergodkjente NVDB-funksjonsklasser 0-3 for veier; 100 m er en teknisk granskningsverdi, ikke en '
                                              'regional anbefaling. Teknisk startverdi: 100 m; dette er ikke en regional anbefaling. Ingen akseptert '
                                              'regional anbefaling: Skaraborg har ikke vedtatt en regionalt anbefalt veiavstand; 100 m er bare en '
                                              'eiergodkjent teknisk startverdi for granskning.',
                                              'Ejergodkendte NVDB-funktionsklasser 0-3 for veje; 100 m er en teknisk gennemgangsværdi, ikke en '
                                              'regional anbefaling. Teknisk startværdi: 100 m; dette er ikke en regional anbefaling. Ingen '
                                              'accepteret regional anbefaling: Skaraborg har ikke vedtaget en regionalt anbefalet vejafstand; 100 m '
                                              'er kun en ejergodkendt teknisk startværdi til gennemgang.',
                                              'Owner-approved NVDB functional road classes 0-3; 100 m is a technical review value, not a regional '
                                              'recommendation. Technical starting value: 100 m; this is not a regional recommendation. No accepted '
                                              'regional recommendation: Skaraborg has not adopted a regional recommended road distance; 100 m is '
                                              'only an owner-approved technical review start value.'),
 'form.manifest.skaraborg.roads_medium.label': ('Övrigt huvud- och uppsamlingsnät',
                                                'Øvrig hoved- og samleveinett',
                                                'Øvrigt hoved- og samlevejnet',
                                                'Other main and collector road network'),
 'form.manifest.skaraborg.roads_medium.note': ('Owner-approved NVDB functional road classes 4-6; 100 m is a technical review value, not a regional '
                                               'recommendation. Tekniskt startvärde: 100 m; detta är inte en regional rekommendation. Ingen '
                                               'accepterad regional rekommendation: Skaraborg has not adopted a regional recommended road distance; '
                                               '100 m is only an owner-approved technical review start value.',
                                               'Eiergodkjente NVDB-funksjonsklasser 4-6 for veier; 100 m er en teknisk granskningsverdi, ikke en '
                                               'regional anbefaling. Teknisk startverdi: 100 m; dette er ikke en regional anbefaling. Ingen '
                                               'akseptert regional anbefaling: Skaraborg har ikke vedtatt en regionalt anbefalt veiavstand; 100 m er '
                                               'bare en eiergodkjent teknisk startverdi for granskning.',
                                               'Ejergodkendte NVDB-funktionsklasser 4-6 for veje; 100 m er en teknisk gennemgangsværdi, ikke en '
                                               'regional anbefaling. Teknisk startværdi: 100 m; dette er ikke en regional anbefaling. Ingen '
                                               'accepteret regional anbefaling: Skaraborg har ikke vedtaget en regionalt anbefalet vejafstand; 100 m '
                                               'er kun en ejergodkendt teknisk startværdi til gennemgang.',
                                               'Owner-approved NVDB functional road classes 4-6; 100 m is a technical review value, not a regional '
                                               'recommendation. Technical starting value: 100 m; this is not a regional recommendation. No accepted '
                                               'regional recommendation: Skaraborg has not adopted a regional recommended road distance; 100 m is '
                                               'only an owner-approved technical review start value.'),
 'form.manifest.skaraborg.urban_areas.label': ('Tätort', 'Tettsted', 'Byområde', 'Urban locality'),
 'form.manifest.skaraborg.urban_areas.note': ('Statistiska centralbyrån (SCB): Tätorter 2023. Tekniskt startvärde: 100 m; detta är inte en regional '
                                              'rekommendation.',
                                              'Statistiska centralbyrån (SCB): Tätorter 2023. Teknisk startverdi: 100 m; dette er ikke en regional '
                                              'anbefaling.',
                                              'Statistiska centralbyrån (SCB): Tätorter 2023. Teknisk startværdi: 100 m; dette er ikke en regional '
                                              'anbefaling.',
                                              'Statistiska centralbyrån (SCB): Tätorter 2023. Technical starting value: 100 m; this is not a '
                                              'regional recommendation.'),
 'form.manifest.skaraborg.small_settlements.label': ('Småort', 'Lite tettsted', 'Mindre byområde', 'Small locality'),
 'form.manifest.skaraborg.small_settlements.note': ('Statistiska centralbyrån (SCB): Småorter 2023. Tekniskt startvärde: 100 m; detta är inte en '
                                                    'regional rekommendation.',
                                                    'Statistiska centralbyrån (SCB): Småorter 2023. Teknisk startverdi: 100 m; dette er ikke en '
                                                    'regional anbefaling.',
                                                    'Statistiska centralbyrån (SCB): Småorter 2023. Teknisk startværdi: 100 m; dette er ikke en '
                                                    'regional anbefaling.',
                                                    'Statistiska centralbyrån (SCB): Småorter 2023. Technical starting value: 100 m; this is not a '
                                                    'regional recommendation.'),
 'form.manifest.skaraborg.holiday_home_areas.label': ('Fritidshusområde', 'Fritidsboligområde', 'Sommerhusområde', 'Holiday-home area'),
 'form.manifest.skaraborg.holiday_home_areas.note': ('Statistiska centralbyrån (SCB): Statistiska fritidshusområden 2020. Tekniskt startvärde: 100 '
                                                     'm; detta är inte en regional rekommendation.',
                                                     'Statistiska centralbyrån (SCB): Statistiska fritidshusområden 2020. Teknisk startverdi: 100 m; '
                                                     'dette er ikke en regional anbefaling.',
                                                     'Statistiska centralbyrån (SCB): Statistiska fritidshusområden 2020. Teknisk startværdi: 100 m; '
                                                     'dette er ikke en regional anbefaling.',
                                                     'Statistiska centralbyrån (SCB): Statistiska fritidshusområden 2020. Technical starting value: '
                                                     '100 m; this is not a regional recommendation.'),
 'form.manifest.skaraborg.nature_reserves.label': ('Naturreservat', 'Naturreservater', 'Naturreservater', 'Nature reserves'),
 'form.manifest.skaraborg.nature_reserves.note': ('Naturvårdsverket: Naturvårdsregistret / Naturreservat. Tekniskt startvärde: 0 m; detta är inte en '
                                                  'regional rekommendation.',
                                                  'Naturvårdsverket: Naturvårdsregistret / Naturreservat. Teknisk startverdi: 0 m; dette er ikke en '
                                                  'regional anbefaling.',
                                                  'Naturvårdsverket: Naturvårdsregistret / Naturreservat. Teknisk startværdi: 0 m; dette er ikke en '
                                                  'regional anbefaling.',
                                                  'Naturvårdsverket: Naturvårdsregistret / Naturreservat. Technical starting value: 0 m; this is not '
                                                  'a regional recommendation.'),
 'form.manifest.skaraborg.nature_conservation_areas.label': ('Naturvårdsområden',
                                                             'Naturvernområder',
                                                             'Naturbeskyttelsesområder',
                                                             'Nature conservation areas'),
 'form.manifest.skaraborg.nature_conservation_areas.note': ('Naturvårdsverket: Naturvårdsregistret / Naturvårdsområden. Tekniskt startvärde: 0 m; '
                                                            'detta är inte en regional rekommendation.',
                                                            'Naturvårdsverket: Naturvårdsregistret / Naturvårdsområden. Teknisk startverdi: 0 m; '
                                                            'dette er ikke en regional anbefaling.',
                                                            'Naturvårdsverket: Naturvårdsregistret / Naturvårdsområden. Teknisk startværdi: 0 m; '
                                                            'dette er ikke en regional anbefaling.',
                                                            'Naturvårdsverket: Naturvårdsregistret / Naturvårdsområden. Technical starting value: 0 '
                                                            'm; this is not a regional recommendation.'),
 'form.manifest.skaraborg.cultural_environment_national_interest.label': ('Riksintresse för kulturmiljövård',
                                                                          'Nasjonal interesse for kulturmiljøvern',
                                                                          'National interesse for kulturmiljøbeskyttelse',
                                                                          'National interest for cultural heritage conservation'),
 'form.manifest.skaraborg.cultural_environment_national_interest.note': ('Riksantikvarieämbetet: Riksintresse kulturmiljövård, miljöbalken 3 kap. 6 '
                                                                         '§. Tekniskt startvärde: 0 m; detta är inte en regional rekommendation.',
                                                                         'Riksantikvarieämbetet: Riksintresse kulturmiljövård, miljöbalken 3 kap. 6 '
                                                                         '§. Teknisk startverdi: 0 m; dette er ikke en regional anbefaling.',
                                                                         'Riksantikvarieämbetet: Riksintresse kulturmiljövård, miljöbalken 3 kap. 6 '
                                                                         '§. Teknisk startværdi: 0 m; dette er ikke en regional anbefaling.',
                                                                         'Riksantikvarieämbetet: Riksintresse kulturmiljövård, miljöbalken 3 kap. 6 '
                                                                         '§. Technical starting value: 0 m; this is not a regional recommendation.'),
 'form.manifest.skaraborg.high_voltage_lines.note': ('Lantmäteriet: Topografi 250 Nedladdning, vektor / ledningslinje. Tekniskt startvärde: 2000 m; '
                                                     'detta är inte en regional rekommendation.',
                                                     'Lantmäteriet: Topografi 250 Nedladdning, vektor / ledningslinje. Teknisk startverdi: 2000 m; '
                                                     'dette er ikke en regional anbefaling.',
                                                     'Lantmäteriet: Topografi 250 Nedladdning, vektor / ledningslinje. Teknisk startværdi: 2000 m; '
                                                     'dette er ikke en regional anbefaling.',
                                                     'Lantmäteriet: Topografi 250 Nedladdning, vektor / ledningslinje. Technical starting value: '
                                                     '2000 m; this is not a regional recommendation.'),
 'form.manifest.skaraborg.existing_wind_turbines.label': ('Befintliga vindkraftverk',
                                                          'Eksisterende vindturbiner',
                                                          'Eksisterende vindmøller',
                                                          'Existing wind turbines'),
 'form.manifest.skaraborg.existing_wind_turbines.note': ('Länsstyrelserna / Vindbrukskollen: Vindbrukskollen – vindkraftverk. Tekniskt startvärde: '
                                                         '2000 m; detta är inte en regional rekommendation.',
                                                         'Länsstyrelserna / Vindbrukskollen: Vindbrukskollen – vindkraftverk. Teknisk startverdi: '
                                                         '2000 m; dette er ikke en regional anbefaling.',
                                                         'Länsstyrelserna / Vindbrukskollen: Vindbrukskollen – vindkraftverk. Teknisk startværdi: '
                                                         '2000 m; dette er ikke en regional anbefaling.',
                                                         'Länsstyrelserna / Vindbrukskollen: Vindbrukskollen – vindkraftverk. Technical starting '
                                                         'value: 2000 m; this is not a regional recommendation.'),
 'form.manifest.trondelag.roads_large.note': ('Härledd från norska N500 vägkategorier E och R.',
                                              'Avledet fra norske N500-veikategorier E og R.',
                                              'Afledt af norske N500-vejkategorier E og R.',
                                              'Derived from Norwegian N500 road categories E and R.'),
 'form.manifest.trondelag.roads_medium.note': ('Härledd från norsk N500 vägkategori F.',
                                               'Avledet fra norsk N500-veikategori F.',
                                               'Afledt af norsk N500-vejkategori F.',
                                               'Derived from Norwegian N500 road category F.'),
 'form.manifest.trondelag.population_points.label': ('Befolkning 250 m-rutor',
                                                     'Befolkning i 250 m-ruter',
                                                     'Befolkning i 250 m-felter',
                                                     'Population in 250 m cells'),
 'form.manifest.trondelag.population_points.note': ('Upplöst polygonproxy för bebodda 250 m-rutor. Avstånd och intersektion beräknas direkt mot '
                                                    'analysdomänens R7-hexagoner.',
                                                    'Oppløst polygonproxy for bebodde 250 m-ruter. Avstand og skjæring beregnes direkte mot '
                                                    'analysedomenets R7-hex.',
                                                    'Opløst polygonproxy for beboede 250 m-felter. Afstand og skæring beregnes direkte mod '
                                                    'analysedomænets R7-hex.',
                                                    'Dissolved polygon proxy for inhabited 250 m cells. Distance and intersection are calculated '
                                                    "directly against the analysis domain's R7 hexes."),
 'form.manifest.trondelag.built_centre.label': ('Bebyggelsekärnor', 'Bebyggelseskjerner', 'Bebyggelseskerner', 'Settlement cores'),
 'form.manifest.trondelag.built_centre.note': ('Polygoner för tätorter och sammanhängande bebyggelsekärnor.',
                                               'Polygoner for tettsteder og sammenhengende bebyggelseskjerner.',
                                               'Polygoner for byområder og sammenhængende bebyggelseskerner.',
                                               'Polygons for urban localities and contiguous settlement cores.'),
 'form.manifest.trondelag.protected_areas.label': ('Naturvernområden', 'Naturvernområder', 'Naturbeskyttelsesområder', 'Nature conservation areas'),
 'form.manifest.trondelag.protected_areas.note': ('NEA Naturvern, klippt och upplöst som första källa för skyddad natur.',
                                                  'NEA Naturvern, klippet og oppløst som første kilde for vernet natur.',
                                                  'NEA Naturvern, klippet og opløst som første kilde til beskyttet natur.',
                                                  'NEA Naturvern, clipped and dissolved as the first protected-nature source.'),
 'form.manifest.trondelag.cultural_preservation.label': ('Kulturmiljöer och kulturminnen',
                                                         'Kulturmiljøer og kulturminner',
                                                         'Kulturmiljøer og kulturminder',
                                                         'Cultural environments and heritage sites'),
 'form.manifest.trondelag.cultural_preservation.note': ('Kulturmiljöer och kulturminnen från norska Riksantikvaren.',
                                                        'Kulturmiljøer og kulturminner fra norske Riksantikvaren.',
                                                        'Kulturmiljøer og kulturminder fra norske Riksantikvaren.',
                                                        "Cultural environments and heritage sites from Norway's Riksantikvaren."),
 'form.manifest.trondelag.valuable_cultural_environment.label': ('Värdefulla kulturlandskap',
                                                                 'Verdifulle kulturlandskap',
                                                                 'Værdifulde kulturlandskaber',
                                                                 'Valuable cultural landscapes'),
 'form.manifest.trondelag.valuable_cultural_environment.note': ('Värdefulla kulturlandskap från norska Miljødirektoratet.',
                                                                'Verdifulle kulturlandskap fra norske Miljødirektoratet.',
                                                                'Værdifulde kulturlandskaber fra norske Miljødirektoratet.',
                                                                "Valuable cultural landscapes from Norway's Miljødirektoratet."),
 'form.manifest.trondelag.high_voltage_lines.note': ('NVE:s transmissionsnät från den verifierade källan i UTM 32.',
                                                     'NVEs transmisjonsnett fra den verifiserte kilden i UTM 32.',
                                                     "NVE's transmissionsnet fra den verificerede kilde i UTM 32.",
                                                     "NVE's transmission grid from the verified source in UTM 32."),
 'form.manifest.trondelag.underground_cables.note': ('Den verifierade Trøndelag-källan innehåller NVE:s sjö- och undervattenskablar.',
                                                     'Den verifiserte Trøndelag-kilden inneholder NVEs sjø- og undervannskabler.',
                                                     "Den verificerede Trøndelag-kilde indeholder NVE's sø- og undervandskabler.",
                                                     "The verified Trøndelag source contains NVE's marine and submarine cables."),
 'form.manifest.trondelag.existing_wind_turbines.note': ('NVE:s punktlager med befintliga vindkraftverk som möjlig anslutningsproxy.',
                                                         'NVEs punktlag med eksisterende vindturbiner som mulig tilknytningsproxy.',
                                                         "NVE's punktlag med eksisterende vindmøller som mulig tilslutningsproxy.",
                                        "NVE's point layer of existing wind turbines as a possible connection proxy.")})

# Shared profile copy remains independent of regional source/contract identities.
MESSAGES.update({
    'form.profile.population_interpretation': ('Yta inom valt minsta avstånd från valda befolknings- och bebyggelsekällor tas bort från den beräknade '
 'potentialen. En redan inbyggd buffert ingår i avståndet och läggs inte på igen.',
 'Areal innenfor valgt minsteavstand fra valgte befolknings- og bebyggelseskilder fjernes fra det '
 'beregnede potensialet. En allerede innebygd buffer inngår i avstanden og legges ikke til på nytt.',
 'Areal inden for den valgte minimumsafstand fra valgte befolknings- og bebyggelseskilder fjernes fra det '
 'beregnede potentiale. En allerede indbygget buffer indgår i afstanden og tilføjes ikke igen.',
 'Area within the selected minimum distance of selected population and settlement sources is removed from '
 'the calculated potential. Any existing built-in buffer is included in that distance and is not added '
 'again.'),
    'form.profile.nature_label': ('Natur', 'Natur', 'Natur', 'Nature'),
    'form.profile.nature_interpretation': ('Valda naturkällor och eventuell buffert minskar den tillgängliga ytan inom varje hexagon. Endast den del '
 'som överlappar tas bort. Vid 0 m buffert används naturkällornas egna ytor.',
 'Valgte naturkilder og eventuell buffer reduserer tilgjengelig areal i hvert heksagon. Bare den '
 'overlappende delen fjernes. Ved 0 m buffer brukes naturkildenes egne arealer.',
 'Valgte naturkilder og en eventuel buffer reducerer det tilgængelige areal i hver sekskant. Kun den '
 'overlappende del fjernes. Ved 0 m buffer bruges naturkildernes egne arealer.',
 'Selected nature sources and any buffer reduce the available area within each hexagon. Only the '
 'overlapping portion is removed. At 0 m buffer, the nature sources’ own areas are used.'),
    'form.profile.culture_label': ('Kulturmiljöer', 'Kulturmiljøer', 'Kulturmiljøer', 'Cultural environments'),
    'form.profile.culture_interpretation': ('Valda kulturkällor och eventuell buffert minskar den tillgängliga ytan inom varje hexagon. Endast den '
 'del som överlappar tas bort. Vid 0 m buffert används kulturkällornas egna geometrier.',
 'Valgte kulturkilder og eventuell buffer reduserer tilgjengelig areal i hvert heksagon. Bare den '
 'overlappende delen fjernes. Ved 0 m buffer brukes kulturkildenes egne geometrier.',
 'Valgte kulturkilder og en eventuel buffer reducerer det tilgængelige areal i hver sekskant. Kun den '
 'overlappende del fjernes. Ved 0 m buffer bruges kulturkildernes egne geometrier.',
 'Selected cultural sources and any buffer reduce the available area within each hexagon. Only the '
 'overlapping portion is removed. At 0 m buffer, the cultural sources’ own geometries are used.'),
    'form.profile.grid_label': ('Elnät', 'Strømnett', 'Elnet', 'Power grid'),
    'form.profile.grid_interpretation': ('Yta utanför valt anslutningsavstånd ingår inte i den beräknade potentialen. Avståndet mäts till valda '
 'ledningar, kablar och punktobjekt. Närhet innebär inte att det finns ledig anslutningskapacitet.',
 'Areal utenfor valgt tilknytningsavstand inngår ikke i det beregnede potensialet. Avstanden måles til '
 'valgte ledninger, kabler og punktobjekter. Nærhet betyr ikke at det finnes ledig tilknytningskapasitet.',
 'Areal uden for den valgte tilslutningsafstand indgår ikke i det beregnede potentiale. Afstanden måles '
 'til valgte ledninger, kabler og punktobjekter. Nærhed betyder ikke, at der er ledig '
 'tilslutningskapacitet.',
 'Area outside the selected connection distance is excluded from the calculated potential. Distance is '
 'measured to selected lines, cables and point features. Proximity does not imply available grid '
 'connection capacity.'),
    'form.availability.locally_validated': (
        'Kontrakt och data är validerade för denna lokala interaktion.',
        'Kontrakt og data er validert for denne lokale interaksjonen.',
        'Kontrakt og data er valideret for denne lokale interaktion.',
        'Contract and data are validated for this local interaction.',
    ),
    'form.availability.unvalidated_access': (
        'Deklarationen finns men är inte validerad för denna åtkomstnivå.',
        'Deklarasjonen finnes, men er ikke validert for dette tilgangsnivået.',
        'Deklarationen findes, men er ikke valideret for dette adgangsniveau.',
        'The declaration exists but is not validated for this access level.',
    ),
    'form.availability.missing_source': (
        'Deklarerad källdata saknas eller klarar inte integritetskontrollen.',
        'Deklarerte kildedata mangler eller består ikke integritetskontrollen.',
        'Deklarerede kildedata mangler eller består ikke integritetskontrollen.',
        'Declared source data are missing or fail the integrity check.',
    ),
    'form.availability.missing_consumer': (
        'Konsumenten är ännu inte implementerad.', 'Konsumenten er ennå ikke implementert.',
        'Konsumenten er endnu ikke implementeret.', 'The consumer is not yet implemented.',
    ),
    'form.availability.missing_field': (
        'Ett obligatoriskt kontraktsfält saknas.', 'Et obligatorisk kontraktsfelt mangler.',
        'Et obligatorisk kontraktfelt mangler.', 'A required contract field is missing.',
    ),
    'form.availability.missing_group_layers': (
        '{p0}-manifestet deklarerar inga giltiga lager för {p1}.',
        '{p0}-manifestet deklarerer ingen gyldige lag for {p1}.',
        '{p0}-manifestet deklarerer ingen gyldige lag for {p1}.',
        'The {p0} manifest declares no valid layers for {p1}.',
    ),
    'form.availability.missing_declared_layers': (
        '{p0}-manifestet saknar giltiga deklarerade lager för {p1}.',
        '{p0}-manifestet mangler gyldige deklarerte lag for {p1}.',
        '{p0}-manifestet mangler gyldige deklarerede lag for {p1}.',
        'The {p0} manifest has no valid declared layers for {p1}.',
    ),
    'form.availability.contract_unreadable': (
        ' Kontraktet kunde inte läsas ({p0}).', ' Kontrakten kunne ikke leses ({p0}).',
        ' Kontrakten kunne ikke læses ({p0}).', ' The contract could not be read ({p0}).',
    ),
    'form.availability.no_generic_consumer': (
        'Gruppen är deklarerad men saknar en registrerad generell workspace-konsument.',
        'Gruppen er deklarert, men mangler en registrert generell arbeidsområdekonsument.',
        'Gruppen er deklareret, men mangler en registreret generel arbejdsområdekonsument.',
        'The group is declared but has no registered generic workspace consumer.',
    ),
    'form.availability.analysis_undeclared': (
        'Analysdomänen eller den efterfrågade gruppen är inte deklarerad.',
        'Analysedomenet eller den etterspurte gruppen er ikke deklarert.',
        'Analysedomænet eller den efterspurgte gruppe er ikke deklareret.',
        'Analysis domain or requested group is not declared.',
    ),
    'form.availability.layers_undeclared': (
        'Grupplager eller gemensamma UI-metadata är inte deklarerade.',
        'Gruppelag eller felles UI-metadata er ikke deklarert.',
        'Gruppelag eller fælles UI-metadata er ikke deklareret.',
        'Group layers or shared UI metadata are not declared.',
    ),
    'form.availability.unsupported_operations': (
        'Operationer som inte stöds: {p0}.', 'Operasjoner som ikke støttes: {p0}.',
        'Operationer, der ikke understøttes: {p0}.', 'Unsupported operations: {p0}.',
    ),
    'form.availability.validated_projection': (
        'Domän, valda källor, operation, kartdata och resultat är godkända.',
        'Domene, valgte kilder, operasjon, kartdata og resultat er godkjent.',
        'Domæne, valgte kilder, operation, kortdata og resultat er godkendt.',
        'Domain, selected sources, operation, map bytes, and result passed.',
    ),
    'form.availability.review_classification': (
        'Granskningsåtkomst och tillitsklassning {p0!r} är godkända enligt katalogens policy.',
        'Granskningstilgang og tillitsklassifisering {p0!r} er godkjent etter katalogens policy.',
        'Gennemgangsadgang og tillidsklassifikation {p0!r} er godkendt efter katalogets politik.',
        'Review access and trust classification {p0!r} passed the catalog policy.',
    ),
    'form.availability.exact_geography': (
        'Exakt geografi och analysdomän är verifierade: ', 'Nøyaktig geografi og analysedomene er verifisert: ',
        'Præcis geografi og analysedomæne er verificeret: ', 'Exact geography and analysis domain are verified: ',
    ),
    'form.availability.exact_geography_details': (
        'Exakt geografi och analysdomän är verifierade: {p0}', 'Nøyaktig geografi og analysedomene er verifisert: {p0}',
        'Præcis geografi og analysedomæne er verificeret: {p0}', 'Exact geography and analysis domain are verified: {p0}',
    ),
    'form.availability.contract_error_declared_layers': (
        '{p0}-manifestet saknar giltiga deklarerade lager för {p1}. Kontraktet kunde inte läsas ({p2}).',
        '{p0}-manifestet mangler gyldige deklarerte lag for {p1}. Kontrakten kunne ikke leses ({p2}).',
        '{p0}-manifestet mangler gyldige deklarerede lag for {p1}. Kontrakten kunne ikke læses ({p2}).',
        'The {p0} manifest has no valid declared layers for {p1}. The contract could not be read ({p2}).',
    ),
    'form.availability.contract_error_group_layers': (
        '{p0}-manifestet deklarerar inga giltiga lager för {p1}. Kontraktet kunde inte läsas ({p2}).',
        '{p0}-manifestet deklarerer ingen gyldige lag for {p1}. Kontrakten kunne ikke leses ({p2}).',
        '{p0}-manifestet deklarerer ingen gyldige lag for {p1}. Kontrakten kunne ikke læses ({p2}).',
        'The {p0} manifest declares no valid layers for {p1}. The contract could not be read ({p2}).',
    ),
})

# Authored readiness prefixes translate; captured IDs and technical reasons stay exact.
MESSAGES.update({'form.readiness.copy_001': ('Det repoägda {p0} är deklarerat och läsbart, men capabilityns generiska data- och konsumentgate återstår.',
                             'Kodearkivets {p0} er deklarert og lesbart, men funksjonens generiske data- og konsumentkontroller gjenstår.',
                             'Kodearkivets {p0} er deklareret og læsbart, men funktionens generiske data- og konsumentkontroller udestår.',
                             "The repository-owned {p0} is declared and readable, but the capability's generic data and consumer validation gates "
                             'remain.'),
 'form.readiness.copy_002': ('Area-resultat och checksumspinnad etableringsyta är verifierade ({p0}).',
                             'Arealresultat og etableringsareal bundet til kontrollsum er verifisert ({p0}).',
                             'Arealresultat og etableringsareal bundet til kontrolsum er verificeret ({p0}).',
                             'Area results and checksum-pinned establishment area are verified ({p0}).'),
 'form.readiness.copy_003': ('Tagsolens manifestbundna request/result och befolkningsbokföring är verifierade ({p0} celler; {p1}).',
                             'Taksolens manifestbundne request/result og befolkningsregnskap er verifisert ({p0} celler; {p1}).',
                             'Tagsolens manifestbundne request/result og befolkningsregnskab er verificeret ({p0} celler; {p1}).',
                             "Rooftop solar's manifest-bound request/result and population accounting are verified ({p0} cells; {p1})."),
 'form.readiness.copy_004': ('Tagsolsunderlag saknas. Den explicit verifierade no-credit-policyn behåller hela solmålet för marksol utan avdrag för '
                             'tagsol.',
                             'Taksoldata mangler. Den eksplisitt verifiserte no-credit-policyen beholder hele solmålet for bakkemontert sol uten '
                             'fradrag for taksol.',
                             'Tagsoldata mangler. Den eksplicit verificerede no-credit-politik bevarer hele solmålet for jordmonteret sol uden '
                             'fradrag for tagsol.',
                             'Rooftop solar data is unavailable. The explicitly verified no-credit policy retains the entire solar target for '
                             'ground-mounted solar without a rooftop solar deduction.'),
 'form.readiness.copy_005': ('Scenariots typade kontrakt, checksumspinnade indata och deterministiska request/result-kedja är verifierade. '
                             'Datatilliten är en separat, oförändrad dimension.',
                             'Scenarioets typede kontrakt, inngangsdata bundet til kontrollsummer og deterministiske request/result-kjede er '
                             'verifisert. Datatilliten er en separat, uendret dimensjon.',
                             'Scenariets typede kontrakt, input bundet til kontrolsummer og deterministiske request/result-kæde er verificeret. '
                             'Datatilliden er en separat, uændret dimension.',
                             "The scenario's typed contract, checksum-pinned inputs and deterministic request/result chain are verified. Data trust "
                             'remains a separate, unchanged dimension.'),
 'form.readiness.copy_006': ('Det explicita policykontraktet, den checksummebundna allokeringspolicyn och separat exekverings-/paritetsevidens är '
                             'sammanbundna av samma rena runtime-konsument.',
                             'Den eksplisitte policykontrakten, allokeringspolicyen bundet til kontrollsum og separat dokumentasjon for '
                             'kjøring/paritet er knyttet sammen av den samme rene runtime-konsumenten.',
                             'Den eksplicitte politikkontrakt, allokeringspolitikken bundet til kontrolsum og særskilt dokumentation for '
                             'kørsel/paritet er knyttet sammen af den samme rene runtime-konsument.',
                             'The explicit policy contract, checksum-bound allocation policy and separate execution/parity evidence are linked by '
                             'the same pure runtime consumer.'),
 'form.readiness.copy_007': ('Alla deklarerade beroenden för det kombinerade resultatet är verifierade, men den rena kombinerade resultatkonsumenten '
                             'är ännu inte materialiserad och exekverad.',
                             'Alle deklarerte avhengigheter for det kombinerte resultatet er verifisert, men den rene kombinerte resultatkonsumenten '
                             'er ennå ikke materialisert og kjørt.',
                             'Alle deklarerede afhængigheder for det kombinerede resultat er verificeret, men den rene kombinerede resultatkonsument '
                             'er endnu ikke materialiseret og kørt.',
                             'All declared dependencies for the combined result are verified, but the pure combined-result consumer has not yet been '
                             'materialized and executed.'),
 'form.readiness.copy_008': ('{p0} Nästa steg: {p1}', '{p0} Neste steg: {p1}', '{p0} Næste trin: {p1}', '{p0} Next step: {p1}'),
 'form.readiness.copy_009': ('Geografimanifestet deklarerar ingen standardanalysdomän.',
                             'Geografimanifestet deklarerer ikke noe standardanalysedomene.',
                             'Geografimanifestet deklarerer intet standardanalysedomæne.',
                             'The geography manifest declares no standard analysis domain.'),
 'form.readiness.copy_010': ('Regionmanifestet deklarerar inte {p0}.',
                             'Regionmanifestet deklarerer ikke {p0}.',
                             'Regionsmanifestet deklarerer ikke {p0}.',
                             'The region manifest does not declare {p0}.'),
 'form.readiness.copy_011': ('{p0} lämnar repositoryt.',
                             '{p0} ligger utenfor kodearkivet.',
                             '{p0} ligger uden for kodearkivet.',
                             '{p0} escapes the repository.'),
 'form.readiness.copy_012': ('Det deklarerade manifestet finns inte: {p0}.',
                             'Det deklarerte manifestet finnes ikke: {p0}.',
                             'Det deklarerede manifest findes ikke: {p0}.',
                             'The declared manifest does not exist: {p0}.'),
 'form.readiness.copy_013': ('Det deklarerade manifestet måste vara ett JSON-objekt.',
                             'Det deklarerte manifestet må være et JSON-objekt.',
                             'Det deklarerede manifest skal være et JSON-objekt.',
                             'The declared manifest must be a JSON object.'),
 'form.readiness.copy_014': ('{p0}-manifestet deklarerar inget area_result-kontrakt.',
                             '{p0}-manifestet deklarerer ingen area_result-kontrakt.',
                             '{p0}-manifestet deklarerer ingen area_result-kontrakt.',
                             'The {p0} manifest declares no area_result contract.'),
 'form.readiness.copy_015': ('Solmanifestet deklarerar inget rooftop_solar-kontrakt.',
                             'Solmanifestet deklarerer ingen rooftop_solar-kontrakt.',
                             'Solmanifestet deklarerer ingen rooftop_solar-kontrakt.',
                             'The solar manifest declares no rooftop_solar contract.'),
 'form.readiness.copy_016': ('Regionmanifestet deklarerar inget scenario_manifest.',
                             'Regionmanifestet deklarerer ikke noe scenario_manifest.',
                             'Regionsmanifestet deklarerer intet scenario_manifest.',
                             'The region manifest declares no scenario_manifest.'),
 'form.readiness.copy_017': ('Regionmanifestet deklarerar inget social_acceptance_manifest.',
                             'Regionmanifestet deklarerer ikke noe social_acceptance_manifest.',
                             'Regionsmanifestet deklarerer intet social_acceptance_manifest.',
                             'The region manifest declares no social_acceptance_manifest.'),
 'form.readiness.copy_018': ('Regionens geografimanifest eller standarddomän är ogiltig: {p0}',
                             'Regionens geografimanifest eller standarddomene er ugyldig: {p0}',
                             'Regionens geografimanifest eller standarddomæne er ugyldigt: {p0}',
                             "The region's geography manifest or standard domain is invalid: {p0}"),
 'form.readiness.copy_019': ('Den deklarerade analysdomänens artefakt saknas: {p0}',
                             'Artefakten for det deklarerte analysedomenet mangler: {p0}',
                             'Artefakten for det deklarerede analysedomæne mangler: {p0}',
                             'The declared analysis-domain artifact is missing: {p0}'),
 'form.readiness.copy_020': ('Den exakta analysdomänen klarar inte integritetskontrollen: {p0}',
                             'Det eksakte analysedomenet består ikke integritetskontrollen: {p0}',
                             'Det eksakte analysedomæne består ikke integritetskontrollen: {p0}',
                             'The exact analysis domain fails its integrity check: {p0}'),
 'form.readiness.copy_021': ('Det deklarerade manifestet kan inte läsas: {p0}',
                             'Det deklarerte manifestet kan ikke leses: {p0}',
                             'Det deklarerede manifest kan ikke læses: {p0}',
                             'The declared manifest cannot be read: {p0}'),
 'form.readiness.copy_022': ('Etableringsytans deklarerade artefakt saknas: {p0}',
                             'Etableringsarealets deklarerte artefakt mangler: {p0}',
                             'Etableringsarealets deklarerede artefakt mangler: {p0}',
                             "The establishment area's declared artifact is missing: {p0}"),
 'form.readiness.copy_023': ('Etableringsytan klarar inte integritetskontrollen: {p0}',
                             'Etableringsarealet består ikke integritetskontrollen: {p0}',
                             'Etableringsarealet består ikke integritetskontrollen: {p0}',
                             'The establishment area fails its integrity check: {p0}'),
 'form.readiness.copy_024': ('Tagsolens deklarerade artefakt saknas: {p0}',
                             'Taksolens deklarerte artefakt mangler: {p0}',
                             'Tagsolens deklarerede artefakt mangler: {p0}',
                             "Rooftop solar's declared artifact is missing: {p0}"),
 'form.readiness.copy_025': ('Tagsolens kontrakt eller resultat klarar inte integritetskontrollen: {p0}',
                             'Taksolens kontrakt eller resultat består ikke integritetskontrollen: {p0}',
                             'Tagsolens kontrakt eller resultat består ikke integritetskontrollen: {p0}',
                             "Rooftop solar's contract or result fails its integrity check: {p0}"),
 'form.readiness.copy_026': ('Tagsolens unavailable/no-credit-policy kan inte verifieras: {p0}',
                             'Taksolens unavailable/no-credit-policy kan ikke verifiseres: {p0}',
                             'Tagsolens unavailable/no-credit-politik kan ikke verificeres: {p0}',
                             "Rooftop solar's unavailable/no-credit policy cannot be verified: {p0}"),
 'form.readiness.copy_027': ('Scenariots deklarerade adapter saknar generell konsument: {p0}',
                             'Scenarioets deklarerte adapter mangler en generell konsument: {p0}',
                             'Scenariets deklarerede adapter mangler en generel konsument: {p0}',
                             "The scenario's declared adapter has no generic consumer: {p0}"),
 'form.readiness.copy_028': ('Scenariokontraktet är ogiltigt: {p0}',
                             'Scenariokontrakten er ugyldig: {p0}',
                             'Scenariekontrakten er ugyldig: {p0}',
                             'The scenario contract is invalid: {p0}'),
 'form.readiness.copy_029': ('Scenariots deklarerade artefakt saknas: {p0}',
                             'Scenarioets deklarerte artefakt mangler: {p0}',
                             'Scenariets deklarerede artefakt mangler: {p0}',
                             "The scenario's declared artifact is missing: {p0}"),
 'form.readiness.copy_030': ('Scenarioartefakten klarar inte integritetskontrollen: {p0}',
                             'Scenarioartefakten består ikke integritetskontrollen: {p0}',
                             'Scenarieartefakten består ikke integritetskontrollen: {p0}',
                             'The scenario artifact fails its integrity check: {p0}'),
 'form.readiness.copy_031': ('Combined-resultets installerade policy kan inte verifieras: {p0}',
                             'Det kombinerte resultatets installerte policy kan ikke verifiseres: {p0}',
                             'Det kombinerede resultats installerede politik kan ikke verificeres: {p0}',
                             "The combined result's installed policy cannot be verified: {p0}"),
 'form.readiness.copy_032': ('Beroendet {p0} är inte klart: {p1}',
                             'Avhengigheten {p0} er ikke klar: {p1}',
                             'Afhængigheden {p0} er ikke klar: {p1}',
                             'Dependency {p0} is not ready: {p1}'),
 'form.readiness.copy_033': ('Profilen deklarerar capabilityn men ingen generell readiness-konsument är registrerad.',
                             'Profilen deklarerer funksjonen, men ingen generell readiness-konsument er registrert.',
                             'Profilen deklarerer funktionen, men ingen generel readiness-konsument er registreret.',
                             'The profile declares the capability, but no generic readiness consumer is registered.'),
 'form.readiness.copy_034': ('{p0}-analysens kontrakt är ogiltigt: {p1}',
                             'Kontrakten for {p0}-analysen er ugyldig: {p1}',
                             'Kontrakten for {p0}-analysen er ugyldig: {p1}',
                             'The {p0} analysis contract is invalid: {p1}')})

# Display projections of technical table keys; stored frames and IDs are unchanged.
MESSAGES.update({
    'table.layer_lower': ('lager', 'lag', 'lag', 'layer'),
    'table.name_lower': ('namn', 'navn', 'navn', 'name'),
    'table.type_lower': ('typ', 'type', 'type', 'type'),
    'table.features': ('features', 'kartobjekter', 'kortobjekter', 'map features'),
    'table.default_visibility': ('default', 'synlig fra start', 'synlig fra start', 'visible initially'),
    'table.elapsed_seconds': ('tid_s', 'tid (s)', 'tid (s)', 'time (s)'),
    'table.median_seconds': ('historisk_median_s', 'historisk median (s)', 'historisk median (s)', 'historical median (s)'),
    'table.deviation_seconds': ('avvikelse_s', 'avvik (s)', 'afvigelse (s)', 'difference (s)'),
    'table.count_lower': ('antal', 'antall', 'antal', 'count'),
    'table.wind_proposal_hex_count': ('vindförslag hex', 'vindforslag, hex', 'vindforslag, hex', 'wind proposal hexes'),
    'table.solar_proposal_hex_count': ('solförslag hex', 'solforslag, hex', 'solforslag, hex', 'solar proposal hexes'),
    'table.rooftop_schematic_row_count': ('småskalig schablon rader', 'småskala sjablong, rader', 'småskala skabelon, rækker', 'small-scale schematic rows'),
    'table.rooftop_schematic_feature_count': (
        'småskalig schablon features i karta', 'småskala sjablong, kartobjekter',
        'småskala skabelon, kortobjekter', 'small-scale schematic map features',
    ),
    'table.opacity_lower': ('opacitet', 'opasitet', 'opacitet', 'opacity'),
    'table.direct': ('Direkt', 'Direkte', 'Direkte', 'Direct'),
})

# Whole authored names for cached source/buffer layers, with role-owned labels.
MESSAGES.update({
    'map.solar_source_name': ('Solkälla: {label}', 'Solkilde: {label}', 'Solkilde: {label}', 'Solar source: {label}'),
    'map.solar_buffer_name': ('Solbuffert: {label}', 'Solbuffer: {label}', 'Solbuffer: {label}', 'Solar buffer: {label}'),
    'map.solar_grid_proximity_name': ('Sol nära nät: {label}', 'Sol nær nett: {label}', 'Sol tæt på net: {label}', 'Solar near grid: {label}'),
    'map.group_buffer_name': ('{label} · buffert', '{label} · buffer', '{label} · buffer', '{label} · buffer'),
    'map.group_result_name': ('{label} · resultat', '{label} · resultat', '{label} · resultat', '{label} · result'),
})

# Operator-authorized review is a visible route, with the same language contract.
MESSAGES.update({
    'review.trust.diagnostic_label': ('Endast diagnostik', 'Bare diagnostikk', 'Kun diagnostik', 'Diagnostic only'),
    'review.trust.diagnostic_note': (
        'Underlaget är inte regionalt accepterat beslutstöd.', 'Grunnlaget er ikke regionalt akseptert beslutningsstøtte.',
        'Grundlaget er ikke regionalt accepteret beslutningsstøtte.', 'The data are not regionally accepted decision support.',
    ),
    'review.trust.candidate_label': ('Kandidat', 'Kandidat', 'Kandidat', 'Candidate'),
    'review.trust.candidate_note': (
        'Underlaget är kandidatmaterial och väntar på teknisk validering.', 'Grunnlaget er kandidatmateriale og venter på teknisk validering.',
        'Grundlaget er kandidatmateriale og afventer teknisk validering.', 'The data are candidate material awaiting technical validation.',
    ),
    'review.trust.technically_validated_note': (
        'Teknisk validering är klar; regional acceptans är en separat gate.',
        'Teknisk validering er ferdig; regional aksept er et eget steg.',
        'Teknisk validering er afsluttet; regional accept er et særskilt trin.',
        'Technical validation is complete; regional acceptance is a separate gate.',
    ),
    'review.trust.regionally_accepted_note': (
        'Underlaget är regionalt accepterat enligt åtkomstkontraktet.', 'Grunnlaget er regionalt akseptert i henhold til tilgangskontrakten.',
        'Grundlaget er regionalt accepteret i henhold til adgangskontrakten.', 'The data are regionally accepted under the access contract.',
    ),
    'review.entry_label': ('Öppna lokal arbetsyta', 'Åpne lokalt arbeidsområde', 'Åbn lokalt arbejdsområde', 'Open local workspace'),
    'review.bornholm.entry_note': (
        'Samma manifeststyrda programvy som för andra regioner, öppnad för lokal stegvis granskning. Saknade eller ovaliderade delar visas tydligt och förblir låsta; detta är inte regionalt beslutstöd.',
        'Samme manifeststyrte programvisning som for andre regioner, åpnet for lokal trinnvis granskning. Manglende eller uvaliderte deler vises tydelig og forblir låst; dette er ikke regional beslutningsstøtte.',
        'Samme manifeststyrede programvisning som for andre regioner, åbnet til lokal trinvis gennemgang. Manglende eller ikke-validerede dele vises tydeligt og forbliver låst; dette er ikke regional beslutningsstøtte.',
        'The same manifest-driven program view as for other regions, opened for a local step-by-step review. Missing or unvalidated parts are clearly shown and remain locked; this is not regional decision support.',
    ),
    'review.bornholm.warning_title': (
        'Bornholm är öppnat för lokal granskning.', 'Bornholm er åpnet for lokal granskning.',
        'Bornholm er åbnet til lokal gennemgang.', 'Bornholm is open for local review.',
    ),
    'review.bornholm.warning_body': (
        'Underlaget är fortfarande klassificerat som diagnostic_only och bygger delvis på V1-härlett material som ännu inte är regionalt validerat. Använd vyn endast för teknisk granskning och integrationstest – inte som grund för planering eller beslut.',
        'Grunnlaget er fortsatt klassifisert som diagnostic_only og bygger delvis på V1-avledet materiale som ennå ikke er regionalt validert. Bruk visningen bare til teknisk granskning og integrasjonstesting – ikke som grunnlag for planlegging eller beslutninger.',
        'Grundlaget er stadig klassificeret som diagnostic_only og bygger delvist på V1-afledt materiale, som endnu ikke er regionalt valideret. Brug kun visningen til teknisk gennemgang og integrationstest – ikke som grundlag for planlægning eller beslutninger.',
        'The data remain classified as diagnostic_only and partly rely on V1-derived material that is not yet regionally validated. Use this view only for technical review and integration testing, not as a basis for planning or decisions.',
    ),
    'review.bornholm.allowed_use': (
        'Tillåten användning: teknisk provning och integrationskontroll.', 'Tillatt bruk: teknisk utprøving og integrasjonskontroll.',
        'Tilladt anvendelse: teknisk afprøvning og integrationskontrol.', 'Allowed use: technical testing and integration checks.',
    ),
    'review.bornholm.forbidden_use': (
        'Inte tillåtet: regional planering, jämförelser med ett godkänt Bornholm-resultat eller beslutstöd.',
        'Ikke tillatt: regional planlegging, sammenligning med et godkjent Bornholm-resultat eller beslutningsstøtte.',
        'Ikke tilladt: regional planlægning, sammenligning med et godkendt Bornholm-resultat eller beslutningsstøtte.',
        'Not allowed: regional planning, comparison with an approved Bornholm result or decision support.',
    ),
    'review.skaraborg.entry_note': (
        'Gemensam manifeststyrd arbetsyta för lokal, operatörstillåten granskning.',
        'Felles manifeststyrt arbeidsområde for lokal, operatørtillatt granskning.',
        'Fælles manifeststyret arbejdsområde til lokal, operatørtilladt gennemgang.',
        'Shared manifest-driven workspace for local, operator-authorized review.',
    ),
    'review.skaraborg.warning_title': (
        'Regionpaketet är öppnat i lokal review.', 'Regionpakken er åpnet for lokal granskning.',
        'Regionspakken er åbnet til lokal gennemgang.', 'The region package is open for local review.',
    ),
    'review.skaraborg.warning_body': (
        'Tillitsnivån är diagnostic_only. Landingkortet är avstängt; denna vy är inte en publicerad produktrutt.',
        'Tillitsnivået er diagnostic_only. Kortet på startsiden er deaktivert; denne visningen er ikke en publisert produktrute.',
        'Tillidsniveauet er diagnostic_only. Kortet på startsiden er deaktiveret; denne visning er ikke en offentliggjort produktrute.',
        'The trust level is diagnostic_only. The landing card is disabled; this view is not a published product route.',
    ),
    'review.skaraborg.allowed_use': (
        'Lokal granskning av uttryckligen deklarerade capabilities.', 'Lokal granskning av uttrykkelig deklarerte funksjoner.',
        'Lokal gennemgang af udtrykkeligt deklarerede funktioner.', 'Local review of explicitly declared capabilities.',
    ),
    'review.skaraborg.forbidden_use': (
        'Offentlig produktåtkomst; review får inte tolkas som publicering.', 'Offentlig produkttilgang; granskning må ikke tolkes som publisering.',
        'Offentlig produktadgang; gennemgang må ikke fortolkes som offentliggørelse.', 'Public product access; review must not be interpreted as publication.',
    ),
})

# Explicit immutable source anchors where the authored contract is not Swedish
# or English. These preserve contract identity while allowing Swedish UI copy.
SOURCE_TEXT_ALIASES = {
    "För nära är dåligt. Valda väglager kombineras till en gemensam avståndsrestriktion utan regionspecifik kod.": "form.manifest.bornholm.roads.interpretation",
    "Being too close is unfavorable. Selected road layers are combined into a shared distance restriction without region-specific code.": "form.manifest.bornholm.roads.interpretation",
    'Bornholm er åbnet til lokal gennemgang.': 'review.bornholm.warning_title',
    'Tilladt anvendelse: teknisk afprøvning og integrationskontrol.': 'review.bornholm.allowed_use',
    'Ikke tilladt: regional planlægning, sammenligning med et godkendt Bornholm-resultat eller beslutningsstøtte.': 'review.bornholm.forbidden_use',
}

# Typed landscape display classifications. Category IDs and physical data stay
# in the source contract; these are authored labels for legend/popup roles only.
MESSAGES.update({
    'legend.landscape.rocky_coast': ('Klippigt kustlandskap', 'Klipperikt kystlandskap', 'Klipperigt kystlandskab', 'Rocky coastal landscape'),
    'legend.landscape.sandy_coast': ('Sandigt kustlandskap', 'Sandpreget kystlandskap', 'Sandet kystlandskab', 'Sandy coastal landscape'),
    'legend.landscape.agriculture_fracture_valleys': (
        'Jordbruks- och sprickdalslandskap', 'Jordbruks- og sprekkedalslandskap',
        'Landbrugs- og sprækkedalslandskab', 'Agricultural and fracture-valley landscape',
    ),
    'legend.landscape.forests_fracture_valleys': (
        'Skogs- och sprickdalslandskap', 'Skog- og sprekkedalslandskap',
        'Skov- og sprækkedalslandskab', 'Forest and fracture-valley landscape',
    ),
    'legend.landscape.plains_agriculture': (
        'Slätt- och jordbrukslandskap', 'Slette- og jordbrukslandskap',
        'Slette- og landbrugslandskab', 'Plain and agricultural landscape',
    ),
    'legend.landscape.outer_coast': ('Ytterkustlandskap', 'Ytre kystlandskap', 'Ydre kystlandskab', 'Outer coastal landscape'),
    'legend.landscape.fjord': ('Fjordlandskap', 'Fjordlandskap', 'Fjordlandskab', 'Fjord landscape'),
    'legend.landscape.fjord_agriculture': (
        'Fjordnära jordbrukslandskap', 'Fjordnært jordbrukslandskap',
        'Landbrugslandskab nær fjorde', 'Agricultural landscape near fjords',
    ),
    'legend.landscape.forest_near_mountains': (
        'Fjällnära skogslandskap', 'Fjellnært skoglandskap',
        'Skovlandskab nær fjelde', 'Forest landscape near mountains',
    ),
    'legend.landscape.valley': ('Dalgångslandskap', 'Dalførelandskap', 'Dallandskab', 'Valley landscape'),
    'legend.landscape.low_mountain': ('Lågfjällslandskap', 'Lavfjellslandskap', 'Lavfjeldslandskab', 'Low-mountain landscape'),
    'legend.landscape.high_mountain': ('Högfjällslandskap', 'Høyfjellslandskap', 'Højfjeldslandskab', 'High-mountain landscape'),
    'legend.landscape.lakes_wetlands': (
        'Sjö- och våtmarkslandskap', 'Innsjø- og våtmarkslandskap',
        'Sø- og vådområdelandskab', 'Lake and wetland landscape',
    ),
    'legend.landscape.extensive_mountain': ('Vidsträckt fjällandskap', 'Vidstrakt fjellandskap', 'Vidstrakt fjeldlandskab', 'Extensive mountain landscape'),
    'legend.landscape.not_assessed': ('Ej bedömd', 'Ikke vurdert', 'Ikke vurderet', 'Not assessed'),
    'legend.landscape.bornholm_layer': (
        'Bornholm LABLAB landskapstyper', 'Bornholm LABLAB landskapstyper',
        'Bornholm LABLAB landskabstyper', 'Bornholm LABLAB landscape types',
    ),
    'legend.landscape.trondelag_layer': (
        'Trøndelag LABLAB landskapstyper', 'Trøndelag LABLAB landskapstyper',
        'Trøndelag LABLAB landskabstyper', 'Trøndelag LABLAB landscape types',
    ),
    'legend.landscape.sandy_agriculture': (
        'Sandigt jordbrukslandskap', 'Sandpreget jordbrukslandskap',
        'Sandet landbrugslandskab', 'Sandy agricultural landscape',
    ),
    'map.landscape_type_category': (
        'Landskapstyp: {category}', 'Landskapstype: {category}',
        'Landskabstype: {category}', 'Landscape type: {category}',
    ),
    'map.landscape_type_id_category': (
        'Landskapstyp: {id} - {category}', 'Landskapstype: {id} - {category}',
        'Landskabstype: {id} - {category}', 'Landscape type: {id} - {category}',
    ),
    'map.landscape_context_category': (
        'Landskapskontext: {category}', 'Landskapskontekst: {category}',
        'Landskabskontekst: {category}', 'Landscape context: {category}',
    ),
})

# Current work phase, shared by native feedback and the browser map handoff.
MESSAGES.update({
    'loading.inputs': ('Kontrollerar underlag…', 'Kontrollerer grunnlag…', 'Kontrollerer grundlag…', 'Checking inputs…'),
    'loading.preparing': ('Förbereder analyser…', 'Forbereder analyser…', 'Forbereder analyser…', 'Preparing analyses…'),
    'loading.geography': (
        'Beräknar geografiska begränsningar…', 'Beregner geografiske begrensninger…',
        'Beregner geografiske begrænsninger…', 'Calculating geographic constraints…',
    ),
    'loading.allocation': (
        'Beräknar scenario och etableringsyta…', 'Beregner scenario og etableringsareal…',
        'Beregner scenarie og etableringsareal…', 'Calculating scenario and establishment area…',
    ),
    'loading.map': ('Förbereder kartan…', 'Forbereder kartet…', 'Forbereder kortet…', 'Preparing the map…'),
    'loading.results': ('Förbereder resultaten…', 'Forbereder resultatene…', 'Forbereder resultaterne…', 'Preparing results…'),
    'loading.browser': ('Ritar kartan…', 'Tegner kartet…', 'Tegner kortet…', 'Drawing the map…'),
    'loading.language': (
        'Uppdaterar språk och visning…', 'Oppdaterer språk og visning…',
        'Opdaterer sprog og visning…', 'Updating language and display…',
    ),
    'loading.ready': ('Karta och resultat är redo.', 'Kart og resultater er klare.', 'Kort og resultater er klar.', 'Map and results are ready.'),
    'loading.unavailable': (
        'Analysen kunde inte slutföras. Se meddelandet på sidan.', 'Analysen kunne ikke fullføres. Se meldingen på siden.',
        'Analysen kunne ikke fuldføres. Se meddelelsen på siden.', 'The analysis could not be completed. See the message on the page.',
    ),
    'loading.failed': (
        'Laddningen avbröts. Se felmeddelandet på sidan.', 'Lastingen ble avbrutt. Se feilmeldingen på siden.',
        'Indlæsningen blev afbrudt. Se fejlmeddelelsen på siden.', 'Loading was interrupted. See the error message on the page.',
    ),
    'loading.map_failed': (
        'Kartan kunde inte visas. Ladda om sidan eller försök igen.', 'Kartet kunne ikke vises. Last inn siden på nytt eller prøv igjen.',
        'Kortet kunne ikke vises. Genindlæs siden, eller prøv igen.', 'The map could not be displayed. Reload the page or try again.',
    ),
    'loading.help': (
        'Visar aktuell arbetsfas. Väntetiden kan inte anges i procent.', 'Viser gjeldende arbeidsfase. Ventetiden kan ikke angis i prosent.',
        'Viser den aktuelle arbejdsfase. Ventetiden kan ikke angives i procent.', 'Shows the current work phase. Waiting time cannot be expressed as a percentage.',
    ),
    'loading.completed_steps': (
        '{done}/{total} beräkningssteg klara.', '{done}/{total} beregningssteg fullført.',
        '{done}/{total} beregningstrin afsluttet.', '{done}/{total} calculation steps complete.',
    ),
})

# Authored legacy help is retained as an alias; analytical manifests stay byte-exact.
SOURCE_TEXT_ALIASES.update({'Skyddad natur är en binär restriktion. En hexagon utesluts när vald naturkälla skär den eller ligger inom den valda bufferten.': 'form.manifest.bornholm.nature.interpretation',
 'Skyddad natur är en binär restriktion när en deklarerad källa skär analysytan eller dess buffert.': 'form.profile.nature_interpretation',
 'Kulturmiljöer är en binär restriktion. En hexagon utesluts när någon vald kulturkälla skär den eller ligger inom den valda bufferten.': 'form.manifest.bornholm.culture.interpretation',
 'Kulturmiljöer är en binär restriktion när en deklarerad källa skär analysytan eller dess buffert.': 'form.profile.culture_interpretation',
 'För nära är dåligt. Valda grid-, polygon- och punktkällor kombineras till en gemensam avståndsrestriktion.': 'form.manifest.bornholm.population.interpretation',
 'För nära är dåligt. Valda befolknings- och bebyggelselager kombineras till en gemensam avståndsrestriktion.': 'form.profile.population_interpretation',
 'För långt bort är dåligt. Valda lednings-, kabel- och punktkällor kombineras till en gemensam närhetsbaserad genomförbarhet.': 'form.manifest.bornholm.grid_infrastructure.interpretation',
 'För långt bort är dåligt. Deklarerad nätinfrastruktur används som en närhetsbaserad genomförbarhetsrestriktion.': 'form.profile.grid_interpretation',
 'För nära är dåligt. Prototypen använder minsta avstånd över valda bebyggelseproxyer så att överlappande lager inte naivt läggs ihop.': 'group.copy_009',
 'För långt bort är dåligt. Grupplagret visar mark som ligger inom valt maximalt anslutningsavstånd till vald elinfrastruktur, inklusive ledningar, kablar, stationer och befintliga vindkraftverk om de valts.': 'group.copy_011',
 'Hantera som hård exkludering i denna första prototyp eftersom det ligger nära nuvarande scenariologik.': 'group.copy_012',
 'Hård exkludering. Det håller lagstadgade naturskydd separata från bebyggelse och transport så att det kombinerade resultatet kan skära dem rent.': 'group.copy_013'})
