"""
Tablero de palabras clave editoriales (Google Trends)
Lee el master file de Google Sheets (o copias CSV locales) y se actualiza
solo cada vez que se agregan lotes nuevos.

Ejecutar:  streamlit run app.py
"""

from __future__ import annotations

import io
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pycountry
import requests
import streamlit as st

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
SHEET_ID = "1YE0iUqr26R34AUxbAEhRSPce4rxJbk6sbjmlasExvUY"
GIDS = {"tendencia": 399244680, "region": 317923059, "lotes": 967699280}
LOCAL_DIR = Path(__file__).parent / "data"
CACHE_TTL = 600  # segundos; el tablero vuelve a leer el sheet cada 10 min

THEMES = {
    "Bosque y ocre": dict(
        primary="#1F4D3F", accent="#C98A22", up="#2E7D5B", down="#A23B3B",
        neutral="#7B847F", text="#1C2321", muted="#6A726E", line="#E4E6E2",
        bg="#FAFAF8", sidebar="#F1F2EE", note="#F3F4EF", land="#ECEEEA",
        palette=["#1F4D3F", "#C98A22", "#7C3E5C", "#6F8F7F", "#8A8F3A", "#4A4F4C", "#B98F6A", "#2E8577"],
        seq=["#F4F1E6", "#E2CF97", "#B99A4A", "#5E7A4E", "#1F4D3F"],
    ),
    "CMYK imprenta": dict(
        primary="#15171A", accent="#C2185B", up="#00838F", down="#C2185B",
        neutral="#7A7F87", text="#15171A", muted="#666B73", line="#E6E7EA",
        bg="#FCFCFD", sidebar="#F2F3F5", note="#F5F0F3", land="#EEEFF1",
        palette=["#15171A", "#C2185B", "#00838F", "#E0A800", "#6D6F75", "#8E44AD", "#43A047", "#EF6C00"],
        seq=["#FFFDE7", "#FFE082", "#F48FB1", "#AD1457", "#3A0A1F"],
    ),
    "Grafito y vino": dict(
        primary="#2F3033", accent="#8C2F39", up="#4F7A5A", down="#8C2F39",
        neutral="#8F877C", text="#232326", muted="#6E6A66", line="#E7E4E0",
        bg="#FAF9F8", sidebar="#F0EEEC", note="#F4EFEE", land="#ECEAE7",
        palette=["#2F3033", "#8C2F39", "#A88B5C", "#4F7A5A", "#6C5B7B", "#9C9387", "#C06C4A", "#3E6B6B"],
        seq=["#F7F3EF", "#E4CFC2", "#C58F84", "#8C2F39", "#3B1519"],
    ),
}
MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]

st.set_page_config(
    page_title="Tendencias editoriales",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    theme_name = st.selectbox("Tema de color", list(THEMES), index=0)
T = THEMES[theme_name]
INK, GOLD, GREEN, OXBLOOD, SLATE = T["primary"], T["accent"], T["up"], T["down"], T["neutral"]
MUTED, LINE, PALETTE = T["muted"], T["line"], T["palette"]
SEQ_SCALE = [[i / (len(T["seq"]) - 1), c] for i, c in enumerate(T["seq"])]


def hex_rgba(h: str, a: float) -> str:
    h = h.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


# ---------------------------------------------------------------------------
# Estilo
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,600&display=swap');
    .stApp {{ background: {T['bg']}; }}
    section[data-testid="stSidebar"] {{ background: {T['sidebar']}; border-right: 1px solid {LINE}; }}
    span[data-baseweb="tag"] {{ background: {hex_rgba(INK, .10)} !important; color: {INK} !important; }}
    span[data-baseweb="tag"] svg {{ fill: {INK} !important; }}
    html, body, [class*="css"], .stMarkdown, .stDataFrame, button, input {{
        font-family: 'Source Sans 3', system-ui, sans-serif;
        font-feature-settings: "tnum" 1;
    }}
    .block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }}
    h1.title {{
        font-family: 'Source Serif 4', Georgia, serif; font-weight: 600;
        font-size: 2.05rem; color: {INK}; margin: 0 0 .15rem 0; letter-spacing: -.01em;
    }}
    p.subtitle {{ color: {MUTED}; font-size: .98rem; margin: 0 0 1.2rem 0; max-width: 72ch; }}
    .kpi-row {{ display: grid; grid-template-columns: repeat(5, minmax(0,1fr));
               border-top: 2px solid {INK}; border-bottom: 1px solid {LINE}; margin-bottom: 1.2rem; }}
    .kpi {{ padding: .8rem 1rem .9rem 0; }}
    .kpi + .kpi {{ padding-left: 1rem; border-left: 1px solid {LINE}; }}
    .kpi .v {{ font-size: 1.75rem; font-weight: 600; color: {INK}; line-height: 1.1; }}
    .kpi .l {{ font-size: .86rem; color: {MUTED}; margin-top: .2rem; }}
    .kpi .d {{ font-size: .82rem; margin-top: .15rem; }}
    .up {{ color: {GREEN}; }} .down {{ color: {OXBLOOD}; }}
    .note {{ background: {T['note']}; border-left: 3px solid {GOLD}; padding: .65rem .9rem;
             font-size: .9rem; color: {T['text']}; margin: .2rem 0 1rem 0; }}
    .insight {{ border-bottom: 1px solid {LINE}; padding: .6rem 0; font-size: .95rem; color: {T['text']}; }}
    .insight b {{ color: {INK}; }}
    .insight:last-child {{ border-bottom: none; }}
    .section-h {{ font-weight: 600; font-size: 1.08rem; color: {INK}; margin: .4rem 0 .5rem 0; }}
    div[data-testid="stTabs"] button p {{ font-size: .98rem; }}
    div[data-testid="stTabs"] button[aria-selected="true"] p {{ color: {INK}; font-weight: 600; }}
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background-color: {GOLD}; }}
    .chip {{ display: inline-block; padding: .12rem .55rem; border-radius: 3px; font-size: .82rem;
             font-weight: 600; margin-right: .35rem; }}
    .card {{ border: 1px solid {LINE}; background: #FFFFFF; padding: .9rem 1rem; }}
    .card .v {{ font-size: 1.45rem; font-weight: 600; color: {INK}; }}
    .card .l {{ font-size: .84rem; color: {MUTED}; }}
    .mover {{ display: flex; justify-content: space-between; padding: .35rem 0;
              border-bottom: 1px solid {LINE}; font-size: .93rem; }}
    .mover:last-child {{ border-bottom: none; }}
    @media (max-width: 900px) {{ .kpi-row {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
        .kpi + .kpi {{ border-left: none; padding-left: 0; }} }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Plantilla de gráficos
TEMPLATE = go.layout.Template(
    layout=dict(
        font=dict(family="Source Sans 3, system-ui, sans-serif", size=13, color=T["text"]),
        colorway=PALETTE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(showgrid=False, linecolor=LINE, ticks="outside", tickcolor=LINE),
        yaxis=dict(gridcolor=LINE, zeroline=False),
        legend=dict(orientation="h", y=-0.18, x=0, title=None),
        hoverlabel=dict(bgcolor="white", font_size=13),
    )
)


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
def _sheet_url(gid: int) -> str:
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"


@st.cache_data(ttl=CACHE_TTL, show_spinner="Leyendo el master file…")
def load_raw(source: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    if source == "sheet":
        frames = {}
        for key, gid in GIDS.items():
            r = requests.get(_sheet_url(gid), timeout=30)
            r.raise_for_status()
            if "text/html" in r.headers.get("Content-Type", ""):
                raise PermissionError("El sheet no es público para lectura.")
            frames[key] = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
        origin = "Google Sheets (en vivo)"
    else:
        frames = {
            "tendencia": pd.read_csv(LOCAL_DIR / "Raw_Tendencia.csv"),
            "region": pd.read_csv(LOCAL_DIR / "Raw_Region.csv"),
            "lotes": pd.read_csv(LOCAL_DIR / "Lotes.csv"),
        }
        origin = "Archivos locales (carpeta data/)"
    return frames["tendencia"], frames["region"], frames["lotes"], origin


def categoria(kw: str) -> str:
    k = kw.lower()
    if "cover" in k or "jacket" in k or "illustrat" in k:
        return "Portadas"
    if any(w in k for w in ["edit", "proofread"]):
        return "Edición y corrección"
    if any(w in k for w in ["format", "typeset", "layout", "interior", "epub", "conversion"]):
        return "Maquetación y formato"
    if any(w in k for w in ["launch", "distribution", "market", "promot"]):
        return "Lanzamiento y distribución"
    if "print" in k:
        return "Impresión"
    if any(w in k for w in ["self publish", "indie", "hybrid", "kdp", "kindle"]):
        return "Autopublicación"
    return "Servicios editoriales"


def intencion(kw: str) -> str:
    k = f" {kw.lower()} "
    if any(w in k for w in [" how ", " what ", " why ", "guide", "tips", "checklist", " vs ",
                            "for beginners", "ideas", "template"]):
        return "Informativa"
    if any(w in k for w in ["cost", "price", "cheap", "affordable", " best ", "companies", "platforms"]):
        return "Comparativa"
    if any(w in k for w in ["service", "designer", "hire", "company", "editor", "consultant",
                            "packages", "publish my", "get my"]):
        return "Contratación"
    return "Genérica"


@st.cache_data(ttl=CACHE_TTL)
def prepare(t: pd.DataFrame, r: pd.DataFrame, lotes: pd.DataFrame):
    t = t.copy()
    r = r.copy()
    for df in (t, r):
        df.columns = [c.strip() for c in df.columns]
        df["Palabra_clave"] = df["Palabra_clave"].astype(str).str.strip()
        df["Lote_ID"] = df["Lote_ID"].astype(str).str.strip()
        df["Interes_0_100"] = pd.to_numeric(df["Interes_0_100"], errors="coerce").fillna(0)
    t["Mes"] = pd.to_datetime(t["Mes"].astype(str).str.lstrip("'"), errors="coerce")
    t = t.dropna(subset=["Mes"])
    r["Region"] = r["Region"].astype(str).str.strip()

    # Factor de escala por lote (opcional). Cuando exista la columna
    # "Factor_escala" en la pestaña Lotes, se usa para llevar todo a una escala común.
    factors = pd.Series(1.0, index=sorted(t["Lote_ID"].unique()))
    if "Factor_escala" in lotes.columns:
        f = lotes.set_index("Lote_ID")["Factor_escala"]
        f = pd.to_numeric(f, errors="coerce").dropna()
        factors.update(f)
    escala_comun = bool((factors != 1).any())
    t["Interes"] = t["Interes_0_100"] * t["Lote_ID"].map(factors).fillna(1)
    t["Categoria"] = t["Palabra_clave"].map(categoria)
    r["Categoria"] = r["Palabra_clave"].map(categoria)
    t["Intencion"] = t["Palabra_clave"].map(intencion)
    r["Intencion"] = r["Palabra_clave"].map(intencion)
    return t, r, escala_comun


def iso3(name: str) -> str | None:
    overrides = {
        "Türkiye": "TUR", "St. Helena": "SHN", "Myanmar (Burma)": "MMR",
        "Côte d’Ivoire": "CIV", "Côte d'Ivoire": "CIV", "South Korea": "KOR",
        "Russia": "RUS", "Iran": "IRN", "Vietnam": "VNM", "Taiwan": "TWN",
        "Czechia": "CZE", "Hong Kong": "HKG", "Laos": "LAO", "Bolivia": "BOL",
        "Venezuela": "VEN", "Tanzania": "TZA", "Syria": "SYR", "Moldova": "MDA",
    }
    if name in overrides:
        return overrides[name]
    try:
        return pycountry.countries.lookup(name).alpha_3
    except LookupError:
        return None


# ---------------------------------------------------------------------------
# Métricas e interpretación
# ---------------------------------------------------------------------------
def keyword_metrics(ts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (lote, kw), g in ts.groupby(["Lote_ID", "Palabra_clave"]):
        g = g.sort_values("Mes")
        s = g.set_index("Mes")["Interes"]
        last12 = s.iloc[-12:]
        prev12 = s.iloc[-24:-12] if len(s) >= 24 else s.iloc[: max(len(s) - 12, 0)]
        m12 = last12.mean()
        mp = prev12.mean() if len(prev12) else np.nan
        # Con una base muy baja el % se dispara y engaña: se marca como "nueva"
        if mp is not None and np.isfinite(mp) and mp >= 2:
            yoy = (m12 - mp) / mp
        else:
            yoy = np.inf if m12 >= 3 else np.nan
        slope = np.polyfit(np.arange(len(last12)), last12.values, 1)[0] if len(last12) > 2 else 0
        peak_val = s.max()
        peak_m = s.idxmax() if peak_val > 0 else pd.NaT
        if peak_val <= 3:
            estado = "Sin volumen"
        elif np.isfinite(yoy) and yoy >= 0.25:
            estado = "En alza"
        elif np.isfinite(yoy) and yoy <= -0.2:
            estado = "En baja"
        elif yoy == np.inf:
            estado = "Nueva"
        else:
            estado = "Estable"
        rows.append(dict(
            Lote_ID=lote, Palabra_clave=kw, Categoria=g["Categoria"].iloc[0],
            Intencion=g["Intencion"].iloc[0],
            Promedio_12m=m12, Promedio_prev=mp, Crecimiento=yoy, Pendiente=slope,
            Pico=peak_val, Mes_pico=peak_m, Estado=estado,
            Serie=s.iloc[-24:].round(1).tolist(),
        ))
    m = pd.DataFrame(rows)
    if m.empty:
        return m
    # Puntuación: nivel reciente dentro del lote (60%) + impulso (40%)
    m["Nivel_rel"] = m.groupby("Lote_ID")["Promedio_12m"].transform(
        lambda x: 100 * x / x.max() if x.max() > 0 else 0)
    g = m["Crecimiento"].replace([np.inf, -np.inf], np.nan).clip(-1, 3).fillna(0)
    m["Impulso"] = 100 * (g + 1) / 4
    m["Puntaje"] = (0.6 * m["Nivel_rel"] + 0.4 * m["Impulso"]).round(1)

    def reco(row):
        if row.Estado == "Sin volumen":
            return "Descartar"
        grows = row.Crecimiento == np.inf or (np.isfinite(row.Crecimiento) and row.Crecimiento >= 0.25)
        big = row.Nivel_rel >= 50
        if big and grows:
            return "Priorizar"
        if big:
            return "Mantener"
        if grows:
            return "Explorar"
        return "Baja prioridad"

    m["Recomendacion"] = m.apply(reco, axis=1)
    return m


RECO_TXT = {
    "Priorizar": "Mucho interés y en crecimiento. Merece página propia, contenido y presupuesto de anuncios.",
    "Mantener": "Mucho interés pero estable. Conviene tenerla cubierta en la web sin invertir de más.",
    "Explorar": "Volumen todavía bajo pero creciendo rápido. Buena apuesta temprana para contenido.",
    "Baja prioridad": "Poco interés y sin impulso. Solo como keyword secundaria.",
    "Descartar": "Casi no se busca. No vale la pena trabajarla.",
}


def movers(ts: pd.DataFrame, n: int = 5):
    """Cambio de los últimos 3 meses frente a los 3 anteriores."""
    rows = []
    for kw, g in ts.groupby("Palabra_clave"):
        s = g.sort_values("Mes")["Interes"]
        if len(s) < 6:
            continue
        a, b = s.iloc[-3:].mean(), s.iloc[-6:-3].mean()
        if b >= 2:
            rows.append((kw, (a - b) / b))
    d = pd.DataFrame(rows, columns=["kw", "chg"]).sort_values("chg", ascending=False)
    return d.head(n), d.tail(n).sort_values("chg")


def level_shift(ts: pd.DataFrame, window: int = 6):
    """Mes con el mayor cambio de nivel (promedio 6m después vs. antes) por keyword."""
    out = []
    for kw, g in ts.groupby("Palabra_clave"):
        s = g.sort_values("Mes").set_index("Mes")["Interes"]
        if len(s) < 2 * window + 1 or s.max() <= 3:
            continue
        best, best_m = 0, None
        for i in range(window, len(s) - window):
            before, after = s.iloc[i - window:i].mean(), s.iloc[i:i + window].mean()
            ratio = (after + 1) / (before + 1)
            if ratio > best:
                best, best_m = ratio, s.index[i]
        if best >= 1.8:
            out.append((kw, best_m, best))
    return out


def seasonal_profile(ts: pd.DataFrame) -> pd.Series:
    """Índice estacional promedio (1 = mes normal) usando años completos."""
    # Se divide cada mes por su media móvil centrada de 13 meses, así los
    # cambios de nivel (como el salto de ago 2025) no se confunden con estacionalidad.
    d = ts.sort_values("Mes").copy()
    d["base"] = d.groupby("Palabra_clave")["Interes"].transform(
        lambda x: x.rolling(13, center=True, min_periods=13).mean())
    d = d[(d["base"] >= 3)]
    if d.empty:
        return pd.Series(dtype=float)
    d["idx"] = d["Interes"] / d["base"]
    d["mes"] = d["Mes"].dt.month
    return d.groupby("mes")["idx"].median()


def seasonal_by_group(ts: pd.DataFrame, col: str) -> pd.DataFrame:
    out = {}
    for grp, g in ts.groupby(col):
        p = seasonal_profile(g)
        if len(p) == 12:
            out[grp] = p
    return pd.DataFrame(out).T


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def forecast(values: tuple, dates: tuple, horizon: int):
    s = pd.Series(values, index=pd.to_datetime(list(dates))).asfreq("MS").fillna(0)
    idx = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(), periods=horizon, freq="MS")
    method = "Holt-Winters (tendencia amortiguada + estacionalidad)"
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        if len(s) >= 30 and s.sum() > 0:
            model = ExponentialSmoothing(s, trend="add", damped_trend=True,
                                         seasonal="add", seasonal_periods=12,
                                         initialization_method="estimated").fit()
        else:
            model = ExponentialSmoothing(s, trend="add", damped_trend=True,
                                         initialization_method="estimated").fit()
            method = "Holt (tendencia amortiguada)"
        fc = np.asarray(model.forecast(horizon))
        resid = np.asarray(s - model.fittedvalues)
    except Exception:
        x = np.arange(len(s))
        coef = np.polyfit(x[-18:], s.values[-18:], 1)
        fc = np.polyval(coef, np.arange(len(s), len(s) + horizon))
        resid = s.values[-18:] - np.polyval(coef, x[-18:])
        method = "Tendencia lineal (18 meses)"
    sd = np.nanstd(resid[-24:])
    band = 1.28 * sd * np.sqrt(np.arange(1, horizon + 1))  # ~80%
    fc = np.clip(fc, 0, None)
    return pd.DataFrame({
        "Mes": idx, "Pronostico": fc,
        "Min": np.clip(fc - band, 0, None), "Max": fc + band,
    }), method


def fmt_pct(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    if np.isinf(x):
        return "nueva"
    return f"{x:+.0%}"


def mes_txt(d) -> str:
    return f"{MESES[d.month - 1]} {d.year}" if pd.notna(d) else "–"


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Datos")
    src_label = st.radio(
        "Fuente", ["Google Sheets (en vivo)", "Archivos locales"],
        help="Google Sheets lee el master file directamente. Requiere que el archivo "
             "se pueda ver con el enlace. 'Archivos locales' usa la carpeta data/.",
    )
    if st.button("Actualizar datos", width="stretch"):
        st.cache_data.clear()

source = "sheet" if src_label.startswith("Google") else "local"
try:
    raw_t, raw_r, lotes, origin = load_raw(source)
except Exception as e:  # noqa: BLE001
    if source == "sheet" and (LOCAL_DIR / "Raw_Tendencia.csv").exists():
        st.warning(
            "No se pudo leer el Google Sheet. Revisa que esté compartido como "
            "'Cualquier persona con el enlace puede ver'. Mientras tanto se muestran "
            f"los archivos locales. Detalle: {e}"
        )
        raw_t, raw_r, lotes, origin = load_raw("local")
    else:
        st.error(f"No se pudieron cargar los datos: {e}")
        st.stop()

ts_all, reg_all, escala_comun = prepare(raw_t, raw_r, lotes)

# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Filtros")
    years = sorted(ts_all["Mes"].dt.year.unique())
    y0, y1 = st.select_slider("Años", options=years, value=(years[0], years[-1]))

    cats = sorted(ts_all["Categoria"].unique())
    sel_cats = st.multiselect("Categoría", cats, default=cats)

    intents = ["Informativa", "Comparativa", "Contratación", "Genérica"]
    sel_int = st.multiselect("Intención de búsqueda", intents, default=intents,
                             help="Informativa: cómo hacerlo. Comparativa: precios y opciones. "
                                  "Contratación: busca un proveedor. Genérica: término amplio.")

    lote_ids = sorted(ts_all["Lote_ID"].unique())
    lote_labels = {
        row.Lote_ID: f"{row.Lote_ID} ({str(row.Palabras_clave_del_lote).split(',')[0]}…)"
        for row in lotes.itertuples() if row.Lote_ID in lote_ids
    }
    sel_lotes = st.multiselect(
        "Lotes", lote_ids, default=lote_ids,
        format_func=lambda x: lote_labels.get(x, x),
    )

    countries = sorted(reg_all["Region"].unique())
    sel_country = st.selectbox("País", ["Todos los países"] + countries)

    hide_dead = st.checkbox("Ocultar keywords sin volumen", value=True,
                            help="Keywords cuyo máximo en 5 años no pasa de 3.")

mask = (
    ts_all["Mes"].dt.year.between(y0, y1)
    & ts_all["Categoria"].isin(sel_cats)
    & ts_all["Lote_ID"].isin(sel_lotes)
    & ts_all["Intencion"].isin(sel_int)
)
ts = ts_all[mask].copy()
if hide_dead:
    alive = ts_all.groupby("Palabra_clave")["Interes"].max()
    ts = ts[ts["Palabra_clave"].isin(alive[alive > 3].index)]

reg = reg_all[reg_all["Lote_ID"].isin(sel_lotes) & reg_all["Categoria"].isin(sel_cats)
              & reg_all["Intencion"].isin(sel_int)]
if hide_dead:
    reg = reg[reg["Palabra_clave"].isin(ts["Palabra_clave"].unique())]

if ts.empty:
    st.info("No hay datos con estos filtros. Amplía el rango de años o agrega categorías.")
    st.stop()

metrics = keyword_metrics(ts)

# ---------------------------------------------------------------------------
# Encabezado y KPIs
# ---------------------------------------------------------------------------
last_month = ts["Mes"].max()
st.markdown('<h1 class="title">Tendencias de búsqueda editoriales</h1>', unsafe_allow_html=True)
st.markdown(
    f'<p class="subtitle">{ts["Palabra_clave"].nunique()} palabras clave en '
    f'{ts["Lote_ID"].nunique()} lotes de Google Trends, {mes_txt(ts["Mes"].min())} a '
    f'{mes_txt(last_month)}. Fuente: {origin}.</p>',
    unsafe_allow_html=True,
)

if not escala_comun:
    st.markdown(
        '<div class="note">Cada lote de Google Trends usa su propia escala de 0 a 100. '
        "Las comparaciones son exactas dentro de un mismo lote; entre lotes distintos son "
        "orientativas hasta cargar los factores de escala de los puentes "
        "(columna <b>Factor_escala</b> en la pestaña Lotes).</div>",
        unsafe_allow_html=True,
    )

n_up = (metrics["Estado"] == "En alza").sum()
n_dead = (keyword_metrics(ts_all[ts_all["Lote_ID"].isin(sel_lotes)])["Estado"] == "Sin volumen").sum()
top = metrics.sort_values("Puntaje", ascending=False).iloc[0]
riser = metrics[np.isfinite(metrics["Crecimiento"])].sort_values("Crecimiento", ascending=False)
riser = riser.iloc[0] if len(riser) else top

st.markdown(
    f"""
    <div class="kpi-row">
      <div class="kpi"><div class="v">{ts['Palabra_clave'].nunique()}</div>
        <div class="l">Palabras clave analizadas</div></div>
      <div class="kpi"><div class="v">{reg['Region'].nunique()}</div>
        <div class="l">Países con datos</div></div>
      <div class="kpi"><div class="v">{n_up}</div>
        <div class="l">En alza vs. año anterior</div>
        <div class="d up">{n_up / max(len(metrics), 1):.0%} del total</div></div>
      <div class="kpi"><div class="v" style="font-size:1.25rem">{top['Palabra_clave']}</div>
        <div class="l">Mejor puntaje de oportunidad</div>
        <div class="d">Lote {top['Lote_ID']}, puntaje {top['Puntaje']:.0f}</div></div>
      <div class="kpi"><div class="v" style="font-size:1.25rem">{riser['Palabra_clave']}</div>
        <div class="l">Mayor crecimiento anual</div>
        <div class="d up">{fmt_pct(riser['Crecimiento'])}</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_res, tab_kw, tab_trend, tab_map, tab_rank, tab_fc, tab_data = st.tabs(
    ["Resumen", "Ficha de keyword", "Interés en el tiempo", "Mapa por país", "Ranking",
     "Proyecciones", "Datos"]
)
RECO_COLORS = {"Priorizar": GREEN, "Mantener": INK, "Explorar": GOLD,
               "Baja prioridad": SLATE, "Descartar": hex_rgba(SLATE, .5)}

# ---------------------------------------------------------------------------
# Resumen: lectura automática
# ---------------------------------------------------------------------------
with tab_res:
    c1, c2 = st.columns([1.1, 1], gap="large")
    with c1:
        st.markdown('<div class="section-h">Lectura automática de los datos</div>', unsafe_allow_html=True)
        ins = []
        best = metrics.sort_values("Puntaje", ascending=False).head(3)
        ins.append("Las keywords con mejor combinación de volumen e impulso son "
                   + ", ".join(f"<b>{k}</b>" for k in best["Palabra_clave"]) + ".")
        risers = metrics[(metrics["Estado"] == "En alza") & np.isfinite(metrics["Crecimiento"])]
        if len(risers):
            r0 = risers.sort_values("Crecimiento", ascending=False).iloc[0]
            ins.append(f"<b>{r0['Palabra_clave']}</b> es la que más creció: "
                       f"{fmt_pct(r0['Crecimiento'])} en los últimos 12 meses frente a los 12 anteriores.")
        fallers = metrics[metrics["Estado"] == "En baja"]
        if len(fallers):
            f0 = fallers.sort_values("Crecimiento").iloc[0]
            ins.append(f"<b>{f0['Palabra_clave']}</b> pierde interés ({fmt_pct(f0['Crecimiento'])}). "
                       "Conviene no priorizarla en contenido ni anuncios.")
        shifts = level_shift(ts)
        if shifts:
            by_month = pd.Series([m for _, m, _ in shifts]).dt.to_period("M").value_counts()
            mm, cnt = by_month.index[0], by_month.iloc[0]
            if cnt >= 3:
                ins.append(f"<b>{cnt} de {metrics['Palabra_clave'].nunique()}</b> keywords muestran "
                           f"un salto de nivel en <b>{MESES[mm.month - 1]} {mm.year}</b>. Si también "
                           "aparece en el término de control, es un efecto de medición de Google Trends.")
        prof = seasonal_profile(ts)
        if len(prof) == 12:
            hi, lo = prof.idxmax(), prof.idxmin()
            ins.append(f"Estacionalidad: el interés suele ser más alto en <b>{MESES[hi - 1]}</b> "
                       f"({prof.max() - 1:+.0%} sobre un mes promedio) y más bajo en "
                       f"<b>{MESES[lo - 1]}</b> ({prof.min() - 1:+.0%}). Buen dato para planificar campañas.")
        if n_dead:
            ins.append(f"<b>{n_dead}</b> keywords de los lotes elegidos no tienen volumen real "
                       "(máximo de 3 o menos en 5 años) y pueden descartarse.")
        if sel_country != "Todos los países":
            rc = reg[reg["Region"] == sel_country].sort_values("Interes_0_100", ascending=False)
            if len(rc):
                ins.append(f"En <b>{sel_country}</b>, la keyword con más peso dentro de su lote es "
                           f"<b>{rc.iloc[0]['Palabra_clave']}</b> ({rc.iloc[0]['Interes_0_100']:.0f}%).")
        st.markdown("".join(f'<div class="insight">{i}</div>' for i in ins), unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="section-h">Estado de las keywords</div>', unsafe_allow_html=True)
        order = ["En alza", "Nueva", "Estable", "En baja", "Sin volumen"]
        colors = {"En alza": GREEN, "Nueva": PALETTE[2], "Estable": SLATE,
                  "En baja": OXBLOOD, "Sin volumen": hex_rgba(SLATE, .45)}
        est = metrics["Estado"].value_counts().reindex(order).dropna()
        fig = go.Figure(go.Bar(
            x=est.values, y=est.index, orientation="h",
            marker_color=[colors[i] for i in est.index], text=est.values, textposition="outside",
        ))
        fig.update_layout(template=TEMPLATE, height=230, yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
                          xaxis=dict(visible=False))
        st.plotly_chart(fig, width="stretch")

        st.markdown('<div class="section-h">Interés promedio por categoría</div>', unsafe_allow_html=True)
        cat = (ts.groupby(["Mes", "Categoria"])["Interes"].mean().reset_index())
        cat = cat.sort_values("Mes")
        cat["Suav"] = cat.groupby("Categoria")["Interes"].transform(
            lambda x: x.rolling(3, min_periods=1).mean())
        fig = px.line(cat, x="Mes", y="Suav", color="Categoria",
                      labels={"Suav": "Interés (media 3 meses)", "Mes": ""})
        fig.update_layout(template=TEMPLATE, height=300)
        st.plotly_chart(fig, width="stretch")

    # --- Matriz de oportunidad + movimientos recientes
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1], gap="large")
    with c1:
        st.markdown('<div class="section-h">Matriz de oportunidad</div>', unsafe_allow_html=True)
        mx = metrics[metrics["Estado"] != "Sin volumen"].copy()
        mx["Crec_plot"] = (mx["Crecimiento"].replace([np.inf], 3).clip(-1, 3).fillna(0) * 100)
        mx["Tamano"] = mx["Pico"].clip(lower=5)
        fig = px.scatter(
            mx, x="Nivel_rel", y="Crec_plot", size="Tamano", color="Recomendacion",
            color_discrete_map=RECO_COLORS, hover_name="Palabra_clave",
            hover_data={"Lote_ID": True, "Nivel_rel": ":.0f", "Crec_plot": ":.0f",
                        "Tamano": False, "Recomendacion": False},
            labels={"Nivel_rel": "Interés reciente (relativo a su lote)",
                    "Crec_plot": "Crecimiento anual (%)", "Recomendacion": ""},
            size_max=26,
        )
        fig.add_vline(x=50, line=dict(color=LINE, width=1.5, dash="dot"))
        fig.add_hline(y=25, line=dict(color=LINE, width=1.5, dash="dot"))
        for x, y, t in [(97, 290, "Priorizar"), (3, 290, "Explorar"),
                        (97, -90, "Mantener"), (3, -90, "Baja prioridad")]:
            fig.add_annotation(x=x, y=y, text=t, showarrow=False, font=dict(color=MUTED, size=12),
                               xanchor="right" if x > 50 else "left")
        fig.update_traces(marker=dict(line=dict(width=1, color="white"), opacity=.9))
        fig.update_layout(template=TEMPLATE, height=430, xaxis=dict(range=[-2, 102], showgrid=False),
                          yaxis=dict(range=[-105, 310]))
        st.plotly_chart(fig, width="stretch")
        st.caption("Cada punto es una keyword; el tamaño es su pico histórico. Arriba a la derecha "
                   "están las que tienen mucho interés y siguen creciendo.")
    with c2:
        up, down = movers(ts)
        st.markdown('<div class="section-h">Suben en los últimos 3 meses</div>', unsafe_allow_html=True)
        st.markdown("".join(
            f'<div class="mover"><span>{r.kw}</span><span class="up">{r.chg:+.0%}</span></div>'
            for r in up.itertuples()) or "Sin datos suficientes.", unsafe_allow_html=True)
        st.markdown('<br><div class="section-h">Bajan en los últimos 3 meses</div>', unsafe_allow_html=True)
        st.markdown("".join(
            f'<div class="mover"><span>{r.kw}</span><span class="down">{r.chg:+.0%}</span></div>'
            for r in down.itertuples()) or "Sin datos suficientes.", unsafe_allow_html=True)
        st.caption("Promedio de los últimos 3 meses frente a los 3 anteriores.")

    # --- Mapa de categorías + intención
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown('<div class="section-h">Dónde está el interés</div>', unsafe_allow_html=True)
        tm = metrics[metrics["Promedio_12m"] > 0]
        fig = px.treemap(tm, path=[px.Constant("Todas"), "Categoria", "Palabra_clave"],
                         values="Promedio_12m", color="Categoria",
                         color_discrete_sequence=PALETTE)
        fig.update_traces(root_color=T["bg"], marker=dict(line=dict(width=1.5, color="white")),
                          hovertemplate="%{label}<br>Interés 12 m: %{value:.1f}<extra></extra>",
                          textfont=dict(color="white"))
        fig.update_layout(template=TEMPLATE, height=380, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown('<div class="section-h">Interés según la intención de búsqueda</div>',
                    unsafe_allow_html=True)
        it = (metrics[metrics["Estado"] != "Sin volumen"].groupby("Intencion")
              .agg(Interes=("Nivel_rel", "mean"), Keywords=("Palabra_clave", "count"),
                   Alza=("Estado", lambda x: (x == "En alza").mean())).reset_index()
              .sort_values("Interes"))
        fig = go.Figure(go.Bar(
            x=it["Interes"], y=it["Intencion"], orientation="h",
            marker_color=[PALETTE[i % len(PALETTE)] for i in range(len(it))],
            text=[f"{v:.0f}  ({k} kw, {a:.0%} en alza)" for v, k, a in
                  zip(it["Interes"], it["Keywords"], it["Alza"])],
            textposition="outside", cliponaxis=False,
        ))
        fig.update_layout(template=TEMPLATE, height=380, xaxis=dict(visible=False, range=[0, 130]),
                          yaxis=dict(gridcolor="rgba(0,0,0,0)"))
        st.plotly_chart(fig, width="stretch")
        st.caption("Interés relativo promedio dentro de cada lote. Sirve para ver qué tipo de "
                   "búsqueda conviene atacar con contenido (informativa) o con ventas (contratación).")

    # --- Calendario de campañas
    st.markdown('<div class="section-h">Calendario de campañas por categoría</div>', unsafe_allow_html=True)
    cal = seasonal_by_group(ts, "Categoria")
    if len(cal):
        z = (cal.values - 1) * 100
        fig = go.Figure(go.Heatmap(
            z=z, x=MESES, y=cal.index, zmid=0,
            colorscale=[[0, hex_rgba(SLATE, .9)], [0.5, "#FFFFFF"], [1, GOLD]],
            text=np.vectorize(lambda v: f"{v:+.0f}%")(z), texttemplate="%{text}",
            hovertemplate="%{y}, %{x}: %{text} vs. un mes promedio<extra></extra>",
            xgap=2, ygap=2, colorbar=dict(thickness=10, outlinewidth=0, ticksuffix="%"),
        ))
        fig.update_layout(template=TEMPLATE, height=80 + 42 * len(cal),
                          yaxis=dict(gridcolor="rgba(0,0,0,0)"))
        st.plotly_chart(fig, width="stretch")
        st.caption("Meses en dorado: el interés sube respecto a un mes normal. "
                   "Buenos momentos para lanzar campañas de esa categoría.")

# ---------------------------------------------------------------------------
# Ficha de keyword
# ---------------------------------------------------------------------------
with tab_kw:
    kw_list = metrics.sort_values("Puntaje", ascending=False)["Palabra_clave"].tolist()
    kw_d = st.selectbox("Elige una palabra clave", kw_list, key="ficha_kw")
    row = metrics[metrics["Palabra_clave"] == kw_d].iloc[0]
    serie = ts_all[ts_all["Palabra_clave"] == kw_d].sort_values("Mes")
    prof_kw = seasonal_profile(serie)
    best_month = MESES[prof_kw.idxmax() - 1] if len(prof_kw) == 12 else "–"
    rkw = reg_all[reg_all["Palabra_clave"] == kw_d].sort_values("Interes_0_100", ascending=False)
    best_country = rkw.iloc[0]["Region"] if len(rkw) and rkw.iloc[0]["Interes_0_100"] > 0 else "–"
    fc6, _ = forecast(tuple(serie["Interes"]), tuple(serie["Mes"].astype(str)), 6)
    now3 = serie["Interes"].iloc[-3:].mean()
    fut3 = fc6["Pronostico"].iloc[-3:].mean()
    chg6 = (fut3 - now3) / now3 if now3 > 0 else np.nan
    reco_c = RECO_COLORS[row["Recomendacion"]]

    st.markdown(
        f'<div style="margin:.3rem 0 .8rem 0">'
        f'<span class="chip" style="background:{hex_rgba(reco_c, .14)};color:{reco_c}">{row["Recomendacion"]}</span>'
        f'<span class="chip" style="background:{hex_rgba(SLATE, .12)};color:{T["text"]}">{row["Categoria"]}</span>'
        f'<span class="chip" style="background:{hex_rgba(SLATE, .12)};color:{T["text"]}">Intención {row["Intencion"].lower()}</span>'
        f'<span class="chip" style="background:{hex_rgba(SLATE, .12)};color:{T["text"]}">Lote {row["Lote_ID"]}</span>'
        f'</div><p style="max-width:75ch;margin:0 0 1rem 0">{RECO_TXT[row["Recomendacion"]]}</p>',
        unsafe_allow_html=True)

    cards = [
        (f"{now3:.0f}", "Interés actual (prom. 3 meses)"),
        (f"{row['Pico']:.0f}", f"Pico histórico, {mes_txt(row['Mes_pico'])}"),
        (fmt_pct(row["Crecimiento"]), "Crecimiento anual"),
        (best_month, "Mes más fuerte del año"),
        (best_country, "País donde más pesa"),
        (fmt_pct(chg6) if np.isfinite(chg6) else "–", "Proyección a 6 meses"),
    ]
    cols = st.columns(6)
    for c, (v, l) in zip(cols, cards):
        c.markdown(f'<div class="card"><div class="v">{v}</div><div class="l">{l}</div></div>',
                   unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1], gap="large")
    with c1:
        st.markdown('<div class="section-h">Evolución y proyección</div>', unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=serie["Mes"], y=serie["Interes"], name="Mensual",
                                 line=dict(color=hex_rgba(INK, .35), width=1.4)))
        fig.add_trace(go.Scatter(x=serie["Mes"], y=serie["Interes"].rolling(6, min_periods=1).mean(),
                                 name="Tendencia (media 6 meses)", line=dict(color=INK, width=2.6)))
        fig.add_trace(go.Scatter(x=pd.concat([fc6["Mes"], fc6["Mes"][::-1]]),
                                 y=pd.concat([fc6["Max"], fc6["Min"][::-1]]), fill="toself",
                                 fillcolor=hex_rgba(GOLD, .18), line=dict(width=0),
                                 name="Rango probable", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fc6["Mes"], y=fc6["Pronostico"], name="Proyección",
                                 line=dict(color=GOLD, width=2.4, dash="dot")))
        if pd.notna(row["Mes_pico"]):
            fig.add_annotation(x=row["Mes_pico"], y=row["Pico"], text="Pico", showarrow=True,
                               arrowhead=0, ay=-28, font=dict(color=MUTED))
        fig.update_layout(template=TEMPLATE, height=380, hovermode="x unified")
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown('<div class="section-h">Países con más peso</div>', unsafe_allow_html=True)
        tc = rkw[rkw["Interes_0_100"] > 0].head(10)
        if len(tc):
            fig = go.Figure(go.Bar(x=tc["Interes_0_100"], y=tc["Region"], orientation="h",
                                   marker_color=GOLD, text=tc["Interes_0_100"].round(0),
                                   textposition="outside", cliponaxis=False))
            fig.update_layout(template=TEMPLATE, height=380, xaxis=dict(visible=False, range=[0, 115]),
                              yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig, width="stretch")
        else:
            st.caption("Sin datos por país para esta keyword.")

    # Keywords con comportamiento parecido
    same = ts_all[ts_all["Lote_ID"] == row["Lote_ID"]].pivot_table(
        index="Mes", columns="Palabra_clave", values="Interes")
    if kw_d in same and same.shape[1] > 1:
        corr = same.corr()[kw_d].drop(kw_d).dropna().sort_values(ascending=False).head(3)
        if len(corr):
            st.markdown('<div class="section-h">Se mueven parecido (mismo lote)</div>',
                        unsafe_allow_html=True)
            st.markdown(" ".join(
                f'<span class="chip" style="background:{hex_rgba(INK, .08)};color:{INK}">'
                f'{k} ({v:.0%})</span>' for k, v in corr.items()), unsafe_allow_html=True)
            st.caption("Correlación de las curvas mensuales. Sirven como keywords secundarias "
                       "en la misma página o campaña.")

# ---------------------------------------------------------------------------
# Interés en el tiempo
# ---------------------------------------------------------------------------
with tab_trend:
    kws = metrics.sort_values("Puntaje", ascending=False)["Palabra_clave"].tolist()
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        pick = st.multiselect("Palabras clave a comparar", kws, default=kws[:5], max_selections=8)
    with c2:
        smooth = st.selectbox("Suavizado", ["Sin suavizar", "Media 3 meses", "Media 6 meses"])
    with c3:
        mode = st.selectbox("Escala", ["Valores de Trends", "Índice (máx. = 100)"])
    if pick:
        d = ts[ts["Palabra_clave"].isin(pick)].sort_values("Mes").copy()
        w = {"Sin suavizar": 1, "Media 3 meses": 3, "Media 6 meses": 6}[smooth]
        d["Valor"] = d.groupby("Palabra_clave")["Interes"].transform(
            lambda x: x.rolling(w, min_periods=1).mean())
        if mode.startswith("Índice"):
            d["Valor"] = d.groupby("Palabra_clave")["Valor"].transform(
                lambda x: 100 * x / x.max() if x.max() > 0 else x)
        if d["Lote_ID"].nunique() > 1 and not escala_comun:
            st.caption("Estás comparando keywords de lotes distintos: la altura relativa entre "
                       "ellas es orientativa. Usa 'Índice' para comparar solo la forma de la curva.")
        fig = px.line(d, x="Mes", y="Valor", color="Palabra_clave",
                      labels={"Valor": "Interés", "Mes": "", "Palabra_clave": ""},
                      hover_data={"Lote_ID": True})
        fig.update_traces(line_width=2.2)
        fig.update_layout(template=TEMPLATE, height=430, hovermode="x unified")
        st.plotly_chart(fig, width="stretch")

        st.markdown('<div class="section-h">Estacionalidad</div>', unsafe_allow_html=True)
        kw_s = st.selectbox("Palabra clave", pick, key="season_kw")
        s = ts[ts["Palabra_clave"] == kw_s].copy()
        s["Año"] = s["Mes"].dt.year
        s["M"] = s["Mes"].dt.month
        piv = s.pivot_table(index="Año", columns="M", values="Interes", aggfunc="mean")
        piv = piv.reindex(columns=range(1, 13))
        fig = go.Figure(go.Heatmap(
            z=piv.values, x=MESES, y=piv.index.astype(str), colorscale=SEQ_SCALE,
            hovertemplate="%{x} %{y}: %{z:.0f}<extra></extra>", xgap=2, ygap=2,
            colorbar=dict(thickness=10, outlinewidth=0),
        ))
        fig.update_layout(template=TEMPLATE, height=260, yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"))
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Elige al menos una palabra clave.")

# ---------------------------------------------------------------------------
# Mapa por país
# ---------------------------------------------------------------------------
with tab_map:
    st.markdown(
        '<div class="note">Los valores por país indican qué parte del interés del lote se lleva '
        "cada keyword dentro de ese país (como en Google Trends). Sirven para ver qué domina en cada "
        "mercado, no para comparar volumen entre países.</div>",
        unsafe_allow_html=True,
    )
    kws_r = (reg.groupby("Palabra_clave")["Interes_0_100"].sum()
             .sort_values(ascending=False).index.tolist())
    if not kws_r:
        st.info("No hay datos por país con estos filtros.")
    else:
        c1, c2 = st.columns([2.2, 1], gap="large")
        with c1:
            kw_m = st.selectbox("Palabra clave", kws_r)
            dm = reg[reg["Palabra_clave"] == kw_m].copy()
            dm["ISO3"] = dm["Region"].map(iso3)
            fig = px.choropleth(
                dm.dropna(subset=["ISO3"]), locations="ISO3", color="Interes_0_100",
                hover_name="Region", color_continuous_scale=SEQ_SCALE, range_color=(0, 100),
                labels={"Interes_0_100": "Interés"},
            )
            fig.update_geos(showframe=False, showcoastlines=False, projection_type="natural earth",
                            showland=True, landcolor=T["land"], showcountries=True,
                            countrycolor="#FFFFFF", bgcolor="rgba(0,0,0,0)")
            fig.update_layout(template=TEMPLATE, height=470, margin=dict(l=0, r=0, t=10, b=0),
                              coloraxis_colorbar=dict(thickness=10, outlinewidth=0, title=None))
            st.plotly_chart(fig, width="stretch")
        with c2:
            st.markdown('<div class="section-h">Países donde más pesa</div>', unsafe_allow_html=True)
            topc = dm.sort_values("Interes_0_100", ascending=False).head(12)
            fig = go.Figure(go.Bar(
                x=topc["Interes_0_100"], y=topc["Region"], orientation="h", marker_color=INK,
                text=topc["Interes_0_100"].round(0), textposition="outside",
            ))
            fig.update_layout(template=TEMPLATE, height=440,
                              yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
                              xaxis=dict(visible=False, range=[0, 115]))
            st.plotly_chart(fig, width="stretch")

        st.markdown('<div class="section-h">Mapa de calor: keywords por país</div>', unsafe_allow_html=True)
        lote_h = st.selectbox("Lote", sorted(reg["Lote_ID"].unique()),
                              format_func=lambda x: lote_labels.get(x, x), key="heat_lote")
        dh = reg[reg["Lote_ID"] == lote_h]
        top_countries = (dh.groupby("Region")["Interes_0_100"].sum()
                         .sort_values(ascending=False).head(25).index)
        if sel_country != "Todos los países" and sel_country not in top_countries:
            top_countries = top_countries.append(pd.Index([sel_country]))
        hm = dh[dh["Region"].isin(top_countries)].pivot_table(
            index="Palabra_clave", columns="Region", values="Interes_0_100")
        hm = hm.loc[hm.sum(axis=1).sort_values(ascending=False).index]
        fig = go.Figure(go.Heatmap(
            z=hm.values, x=hm.columns, y=hm.index, colorscale=SEQ_SCALE, zmin=0, zmax=100,
            xgap=1, ygap=1, hovertemplate="%{y}, %{x}: %{z:.0f}<extra></extra>",
            colorbar=dict(thickness=10, outlinewidth=0),
        ))
        fig.update_layout(template=TEMPLATE, height=90 + 34 * len(hm),
                          xaxis=dict(tickangle=-45), yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"))
        st.plotly_chart(fig, width="stretch")

        st.markdown('<div class="section-h">Comparar dos países</div>', unsafe_allow_html=True)
        cc = sorted(dh["Region"].unique())
        d1, d2 = st.columns(2)
        default_a = cc.index("United States") if "United States" in cc else 0
        default_b = cc.index("Ireland") if "Ireland" in cc else min(1, len(cc) - 1)
        pa = d1.selectbox("País A", cc, index=default_a, key="pa")
        pb = d2.selectbox("País B", cc, index=default_b, key="pb")
        cmp_ = dh[dh["Region"].isin([pa, pb])].pivot_table(
            index="Palabra_clave", columns="Region", values="Interes_0_100").fillna(0)
        cmp_ = cmp_.loc[cmp_.sum(axis=1).sort_values().index]
        fig = go.Figure()
        for ctry, colr in [(pa, INK), (pb, GOLD)]:
            if ctry in cmp_:
                fig.add_trace(go.Bar(y=cmp_.index, x=cmp_[ctry], name=ctry, orientation="h",
                                     marker_color=colr))
        fig.update_layout(template=TEMPLATE, barmode="group", height=120 + 44 * len(cmp_),
                          yaxis=dict(gridcolor="rgba(0,0,0,0)"), xaxis=dict(title="Peso en el lote (%)"))
        st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
with tab_rank:
    c1, c2 = st.columns([1, 2])
    with c1:
        rank_by = st.selectbox("Ordenar por", ["Puntaje de oportunidad", "Interés últimos 12 meses",
                                               "Crecimiento anual", "Pico histórico"])
    with c2:
        estados = st.multiselect("Estado", ["En alza", "Nueva", "Estable", "En baja", "Sin volumen"],
                                 default=["En alza", "Nueva", "Estable", "En baja"])
    col = {"Puntaje de oportunidad": "Puntaje", "Interés últimos 12 meses": "Promedio_12m",
           "Crecimiento anual": "Crecimiento", "Pico histórico": "Pico"}[rank_by]
    rk = metrics[metrics["Estado"].isin(estados)].copy()
    rk["_sort"] = rk[col].replace([np.inf], 1e9)
    rk = rk.sort_values("_sort", ascending=False).reset_index(drop=True)
    rk.index = rk.index + 1
    rk["Crec_txt"] = rk["Crecimiento"].map(fmt_pct)
    rk["Pico_txt"] = rk["Mes_pico"].map(mes_txt)
    st.dataframe(
        rk[["Palabra_clave", "Recomendacion", "Categoria", "Intencion", "Lote_ID", "Puntaje",
            "Promedio_12m", "Crec_txt", "Pico_txt", "Estado", "Serie"]],
        width="stretch", height=min(38 * (len(rk) + 1), 720),
        column_config={
            "Palabra_clave": st.column_config.TextColumn("Palabra clave", width="medium"),
            "Recomendacion": st.column_config.TextColumn("Acción", width="small"),
            "Categoria": "Categoría",
            "Intencion": st.column_config.TextColumn("Intención", width="small"),
            "Lote_ID": st.column_config.TextColumn("Lote", width="small"),
            "Puntaje": st.column_config.ProgressColumn("Puntaje", min_value=0, max_value=100, format="%.0f"),
            "Promedio_12m": st.column_config.NumberColumn("Interés 12 m", format="%.1f"),
            "Crec_txt": st.column_config.TextColumn("Crec. anual", width="small"),
            "Pico_txt": st.column_config.TextColumn("Mes pico", width="small"),
            "Estado": st.column_config.TextColumn("Estado", width="small"),
            "Serie": st.column_config.LineChartColumn("Últimos 24 meses", width="medium"),
        },
    )
    st.caption("Puntaje de oportunidad = 60% interés reciente (relativo al máximo de su lote) "
               "+ 40% impulso (crecimiento de los últimos 12 meses frente a los 12 anteriores).")

    st.download_button("Descargar ranking (CSV)",
                       rk.drop(columns=["Serie", "_sort"]).to_csv(index=False).encode("utf-8"),
                       "ranking_keywords.csv", "text/csv")

    if sel_country != "Todos los países":
        st.markdown(f'<div class="section-h">Ranking en {sel_country}</div>', unsafe_allow_html=True)
        rc = (reg[reg["Region"] == sel_country]
              .sort_values("Interes_0_100", ascending=False)[["Palabra_clave", "Lote_ID", "Interes_0_100"]])
        st.dataframe(rc.reset_index(drop=True), width="stretch", column_config={
            "Palabra_clave": "Palabra clave", "Lote_ID": "Lote",
            "Interes_0_100": st.column_config.ProgressColumn("Peso en el lote", min_value=0,
                                                             max_value=100, format="%.0f"),
        })

# ---------------------------------------------------------------------------
# Proyecciones
# ---------------------------------------------------------------------------
with tab_fc:
    c1, c2 = st.columns([3, 1])
    with c1:
        kw_f = st.selectbox("Palabra clave", kws, key="fc_kw")
    with c2:
        horizon = st.select_slider("Meses a proyectar", options=[3, 6, 9, 12], value=6)
    full = ts_all[ts_all["Palabra_clave"] == kw_f].sort_values("Mes")
    fc, method = forecast(tuple(full["Interes"]), tuple(full["Mes"].astype(str)), horizon)
    hist = full[full["Mes"].dt.year >= y0]

    now = full["Interes"].iloc[-3:].mean()
    fut = fc["Pronostico"].iloc[-3:].mean()
    chg = (fut - now) / now if now > 0 else np.nan
    k1, k2, k3 = st.columns(3)
    k1.metric("Promedio últimos 3 meses", f"{now:.1f}")
    k2.metric(f"Promedio proyectado (meses {horizon - 2}–{horizon})", f"{fut:.1f}",
              delta=fmt_pct(chg) if np.isfinite(chg) else None)
    k3.metric("Mes con mayor valor proyectado",
              mes_txt(fc.loc[fc["Pronostico"].idxmax(), "Mes"]))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist["Mes"], y=hist["Interes"], name="Histórico",
                             line=dict(color=INK, width=2.2)))
    fig.add_trace(go.Scatter(
        x=pd.concat([fc["Mes"], fc["Mes"][::-1]]),
        y=pd.concat([fc["Max"], fc["Min"][::-1]]),
        fill="toself", fillcolor=hex_rgba(GOLD, .18), line=dict(width=0),
        name="Rango probable (80%)", hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=pd.concat([hist["Mes"].iloc[-1:], fc["Mes"]]),
        y=pd.concat([hist["Interes"].iloc[-1:], fc["Pronostico"]]),
        name="Proyección", line=dict(color=GOLD, width=2.4, dash="dot")))
    fig.update_layout(template=TEMPLATE, height=420, hovermode="x unified")
    st.plotly_chart(fig, width="stretch")
    st.caption(f"Método: {method}. La proyección asume que el patrón reciente continúa; "
               "no anticipa cambios de algoritmo, campañas ni eventos externos.")

    st.markdown('<div class="section-h">Proyección de todas las keywords filtradas</div>',
                unsafe_allow_html=True)
    if st.toggle("Calcular tabla de proyecciones", value=False,
                 help="Ajusta un modelo por keyword; puede tardar unos segundos con muchas keywords."):
        rows = []
        for kw in kws:
            f = ts_all[ts_all["Palabra_clave"] == kw].sort_values("Mes")
            p, _ = forecast(tuple(f["Interes"]), tuple(f["Mes"].astype(str)), horizon)
            a = f["Interes"].iloc[-3:].mean()
            b = p["Pronostico"].iloc[-3:].mean()
            rows.append(dict(Palabra_clave=kw, Lote=f["Lote_ID"].iloc[0], Actual=a, Proyectado=b,
                             Cambio=(b - a) / a if a > 0 else np.nan))
        pt = pd.DataFrame(rows).sort_values("Cambio", ascending=False)
        pt["Cambio"] = pt["Cambio"].map(fmt_pct)
        st.dataframe(pt.reset_index(drop=True), width="stretch", column_config={
            "Palabra_clave": "Palabra clave",
            "Actual": st.column_config.NumberColumn("Últimos 3 meses", format="%.1f"),
            "Proyectado": st.column_config.NumberColumn(f"Proyección a {horizon} meses", format="%.1f"),
            "Cambio": "Cambio esperado",
        })

# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
with tab_data:
    st.markdown('<div class="section-h">Lotes cargados</div>', unsafe_allow_html=True)
    show_cols = [c for c in ["Lote_ID", "Fecha_extraccion", "Palabras_clave_del_lote",
                             "Filas_tendencia", "Filas_region", "Notas"] if c in lotes.columns]
    st.dataframe(lotes[show_cols], width="stretch", hide_index=True)
    st.markdown('<div class="section-h">Serie mensual filtrada</div>', unsafe_allow_html=True)
    st.dataframe(ts.drop(columns=["Interes_0_100"]).sort_values(["Lote_ID", "Palabra_clave", "Mes"]),
                 width="stretch", hide_index=True, height=360)
    st.download_button("Descargar serie filtrada (CSV)", ts.to_csv(index=False).encode("utf-8"),
                       "serie_filtrada.csv", "text/csv")
