"""Presentation-only overview; the caller owns region access and navigation."""
from __future__ import annotations

from dataclasses import dataclass
import html
from typing import Callable

import streamlit as st

from .i18n import translate


@dataclass(frozen=True)
class LandingRegion:
    region_id: str
    title: str
    enabled: bool


# Editorial content and order do not select algorithms, data or access policy.
REGION_COPY = {
    "bornholm": ("landing.denmark", "landing.bornholm"),
    "trondelag": ("landing.norway", "landing.trondelag"),
    "skaraborg": ("landing.sweden", "landing.skaraborg"),
}


LANDING_CSS = """
/* Every rule is scoped to the overview so analysis styling is restored on exit. */
[data-testid="stAppViewContainer"]:has(.st-key-speedlocal_landing) {
  background: #f7f4ed;
}
[data-testid="stAppViewContainer"]:has(.st-key-speedlocal_landing) [data-testid="stSidebar"],
[data-testid="stAppViewContainer"]:has(.st-key-speedlocal_landing) [data-testid="stSidebarCollapsedControl"] {
  display: none;
}
[data-testid="stMainBlockContainer"]:has(.st-key-speedlocal_landing) {
  max-width: 1280px; padding: 4.5rem 2rem 4rem;
}
.st-key-speedlocal_landing {
  color: #151915; font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}
.st-key-speedlocal_landing h1, .st-key-speedlocal_landing h2,
.st-key-speedlocal_landing h3 { color: #151915; overflow-wrap: normal; }
.st-key-speedlocal_landing p { line-height: 1.65; }
.st-key-speedlocal_landing .sl-hero {
  background: linear-gradient(115deg, #101c15, #20392b);
  color: #fffdf8; padding: 4rem 3.5rem 3.5rem; border-radius: 10px 10px 0 0;
  border-bottom: 7px solid #c49a3c;
}
.st-key-speedlocal_landing .sl-kicker {
  font-size: .78rem; font-weight: 800; letter-spacing: .09em;
  text-transform: uppercase; margin: 0 0 1rem;
}
.st-key-speedlocal_landing .sl-hero h1 {
  color: #fffdf8; font-size: clamp(2.5rem, 5.8vw, 5.5rem);
  line-height: 1.03; letter-spacing: -.045em; margin: 0 0 1.4rem;
}
.st-key-speedlocal_landing .sl-lead {
  color: #dce3da; max-width: 66ch; font-size: 1.15rem; margin: 0;
}
.st-key-speedlocal_landing .sl-nav {
  display: flex; flex-wrap: wrap; gap: .75rem; margin-top: 1.75rem;
}
.st-key-speedlocal_landing .sl-nav a {
  display: inline-flex; align-items: center; min-height: 46px; padding: .65rem 1rem;
  border: 1px solid #a6b3a2; border-radius: 5px; color: #fffdf8;
  text-decoration: none; font-weight: 750;
}
.st-key-speedlocal_landing .sl-nav a:first-child { background: #fffdf8; color: #1f4938; }
.st-key-speedlocal_landing .sl-nav a:hover { background: #355b43; color: white; }
.st-key-speedlocal_landing .sl-section { padding-top: 2rem; scroll-margin-top: 3rem; }
.st-key-speedlocal_landing .sl-section h2 { font-size: clamp(1.8rem, 3vw, 2.6rem); margin: 0 0 .6rem; }
.st-key-speedlocal_landing .sl-section > p { color: #535d55; max-width: 75ch; }
.st-key-speedlocal_landing .sl-wait-note {
  background: #ece6da; border-left: 4px solid #c49a3c; border-radius: 5px;
  padding: 1rem 1.25rem; margin-top: 1rem;
}
.st-key-speedlocal_landing .sl-wait-note h3 { font-size: 1.1rem; margin: 0 0 .5rem; }
.st-key-speedlocal_landing .sl-wait-note p { color: #535d55; font-size: .95rem; margin: 0; }
.st-key-speedlocal_landing .sl-wait-note p + p { margin-top: .5rem; }
.st-key-speedlocal_landing [class*="st-key-landing_cards_"] { gap: 1rem; }
.st-key-speedlocal_landing [class*="st-key-landing_card_"] {
  background: #fffdf8; border: 1px solid #d4d4c9; border-top: 6px solid #2f6b4f;
  border-radius: 8px; padding: 1.4rem; min-height: 305px;
  box-shadow: 0 8px 24px rgba(21,25,21,.05);
}
.st-key-speedlocal_landing .st-key-landing_card_trondelag { border-top-color: #315f7d; }
.st-key-speedlocal_landing .st-key-landing_card_skaraborg { border-top-color: #b45e3c; }
.st-key-speedlocal_landing [class*="st-key-landing_card_"] h3 { font-size: 1.65rem; padding: 0; }
.st-key-speedlocal_landing .sl-card-country { color: #535d55; font-size: .8rem; margin: 0; }
.st-key-speedlocal_landing .sl-card-description { color: #535d55; min-height: 8rem; margin: 0; }
.st-key-speedlocal_landing [class*="st-key-landing_card_"] button {
  background: #182b20; border: 1px solid #182b20; color: #fffdf8;
  border-radius: 5px; min-height: 46px; font-weight: 750;
}
.st-key-speedlocal_landing [class*="st-key-landing_card_"] button:hover {
  background: #2f6b4f; border-color: #2f6b4f; color: white;
}
.st-key-speedlocal_landing [class*="st-key-landing_card_"] button:disabled {
  background: #e4e7df; color: #515c50; border-color: #c6cdc1;
}
.st-key-speedlocal_landing .sl-unavailable { color: #535d55; font-size: .85rem; margin: 0; }
.st-key-speedlocal_landing .sl-model {
  display: grid; grid-template-columns: minmax(0, 2.2fr) minmax(0, 1fr); gap: 2.5rem;
  border-top: 1px solid #d4d4c9; margin-top: 1.5rem;
}
.st-key-speedlocal_landing .sl-model p, .st-key-speedlocal_landing .sl-method p { color: #535d55; }
.st-key-speedlocal_landing .sl-model aside {
  align-self: start; background: #ece6da; border: 1px solid #d4d4c9;
  border-radius: 8px; padding: 1.25rem;
}
.st-key-speedlocal_landing .sl-model aside h3 { font-size: 1.15rem; margin: 0 0 .8rem; }
.st-key-speedlocal_landing .sl-model ol { padding-left: 1.2rem; line-height: 1.75; }
.st-key-speedlocal_landing .sl-method { border-top: 1px solid #d4d4c9; margin-top: 1.5rem; }
.st-key-speedlocal_landing .sl-method h3 { font-size: 1.2rem; }
.st-key-speedlocal_landing .sl-note { background: #ece6da; border-radius: 8px; padding: 1.25rem; }
.st-key-speedlocal_landing a:focus-visible, .st-key-speedlocal_landing button:focus-visible {
  outline: 3px solid #c49a3c; outline-offset: 4px;
}
.st-key-speedlocal_landing .st-key-landing_language { margin-bottom: 1.25rem; }
.st-key-speedlocal_landing .sl-footer { color: #535d55; font-size: .85rem; margin-top: 1rem; }
@media (max-width: 850px) {
  [data-testid="stMainBlockContainer"]:has(.st-key-speedlocal_landing) { padding: 4.5rem 1rem 2.5rem; }
  .st-key-speedlocal_landing .sl-hero { padding: 2.5rem 1.5rem; }
  .st-key-speedlocal_landing .sl-hero h1 { font-size: clamp(1.7rem, 8.2vw, 2.5rem); }
  .st-key-speedlocal_landing [class*="st-key-landing_cards_"] [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-speedlocal_landing [class*="st-key-landing_cards_"] [data-testid="stColumn"] {
    width: 100%; flex: 1 1 100%; min-width: 0;
  }
  .st-key-speedlocal_landing .sl-card-description { min-height: 0; }
  .st-key-speedlocal_landing [class*="st-key-landing_card_"] { min-height: 0; }
  .st-key-speedlocal_landing .sl-model { grid-template-columns: 1fr; gap: 1rem; }
}
"""


def render_landing(
    regions: list[LandingRegion],
    render_language_switcher: Callable[[], None],
    language: str = "sv",
) -> str | None:
    """Return a clicked region identity without opening or loading analysis data."""
    selected = None
    def text(message: str, **parameters: str) -> str:
        return html.escape(translate(message, language, **parameters))

    st.html(f"<style>{LANDING_CSS}</style>")
    with st.container(key="speedlocal_landing"):
        with st.container(key="landing_language"):
            render_language_switcher()
        st.html(f"""
          <header class="sl-hero">
            <p class="sl-kicker">{text('landing.kicker')}</p>
            <h1>SpeedLocal<br>{text('landing.title')}</h1>
            <p class="sl-lead">{text('landing.lead')}</p>
            <nav class="sl-nav" aria-label="{text('landing.navigation')}">
              <a href="#landing-regions">{text('landing.choose_region')}</a>
              <a href="#landing-model">{text('landing.see_model')}</a>
              <a href="#landing-method">{text('landing.see_method')}</a>
            </nav>
          </header>
          <section id="landing-regions" class="sl-section" aria-labelledby="landing-regions-title">
            <h2 id="landing-regions-title">{text('landing.choose_region')}</h2>
            <p>{text('landing.regions_intro')}</p>
            <aside class="sl-wait-note" aria-labelledby="landing-wait-title">
              <h3 id="landing-wait-title">{text('landing.wait_title')}</h3>
              <p>{text('landing.wait_evidence')}</p>
              <ul>
                <li>{text('landing.wait_opening')}</li>
                <li>{text('landing.wait_layers')}</li>
                <li>{text('landing.wait_apply')}</li>
              </ul>
              <p>{text('landing.wait_limits')}</p>
            </aside>
          </section>
        """)
        order = {region_id: index for index, region_id in enumerate(REGION_COPY)}
        ordered = sorted(regions, key=lambda region: order.get(region.region_id, len(order)))
        for start in range(0, len(ordered), 3):
            with st.container(key=f"landing_cards_{start}"):
                for col, region in zip(st.columns(3, gap="small"), ordered[start:start + 3]):
                    with col.container(key=f"landing_card_{region.region_id}"):
                        country, description = REGION_COPY.get(
                            region.region_id,
                            ("", "landing.generic_region"),
                        )
                        title = "Trøndelag" if region.region_id == "trondelag" else region.title
                        st.html(f'<p class="sl-card-country">{text(country)} · {text("landing.prototype")}</p>')
                        st.subheader(title)
                        st.html(f'<p class="sl-card-description">{text(description)}</p>')
                        if st.button(
                            translate("landing.open_region", language, region=title),
                            key=f"select_region_{region.region_id}",
                            disabled=not region.enabled,
                            width="stretch",
                        ):
                            selected = region.region_id
                        if not region.enabled:
                            st.html(f'<p class="sl-unavailable">{text("landing.unavailable")}</p>')
        st.html(f"""
          <section id="landing-model" class="sl-section sl-model" aria-labelledby="landing-model-title">
            <article>
              <p class="sl-kicker">{text('landing.model')}</p>
              <h2 id="landing-model-title">{text('landing.model_title')}</h2>
              <p>{text('landing.model_question')}</p>
              <p>{text('landing.model_geography')}</p>
              <p>{text('landing.model_energy')}</p>
              <p>{text('landing.model_compare')}</p>
              <p>{text('landing.model_results')}</p>
              <p>{text('landing.model_acceptance')}</p>
            </article>
            <aside aria-label="{text('landing.model_summary')}">
              <h3>{text('landing.model_summary')}</h3>
              <ol>
                <li>{text('landing.step1')}</li>
                <li>{text('landing.step2')}</li>
                <li>{text('landing.step3')}</li>
                <li>{text('landing.step4')}</li>
              </ol>
            </aside>
          </section>
          <section id="landing-method" class="sl-section sl-method" aria-labelledby="landing-method-title">
            <p class="sl-kicker">{text('landing.method')}</p>
            <h2 id="landing-method-title">{text('landing.method_title')}</h2>
            <h3>{text('landing.constraints_title')}</h3>
            <p>{text('landing.constraints')}</p>
            <h3>{text('landing.scenario_title')}</h3>
            <p>{text('landing.scenario')}</p>
            <div class="sl-note">
              <h3>{text('landing.uncertainty_title')}</h3>
              <p>{text('landing.uncertainty')}</p>
            </div>
          </section>
        """)
        st.html(f'<footer class="sl-footer">{text("landing.footer")}</footer>')
    return selected
