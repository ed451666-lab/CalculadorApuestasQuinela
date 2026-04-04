from __future__ import annotations

from datetime import date
from statistics import median

import pandas as pd
import streamlit as st

from live_odds import UNAVAILABLE_MESSAGE, fetch_live_quinella_probables


TRACK_OPTIONS = {
    "HCH": "Hipódromo Chile",
    "CHS": "Club Hípico de Santiago",
    "VSC": "Valparaíso Sporting",
    "CHC": "Club Hípico de Concepción",
}
BET_OPTIONS = (200, 400, 600, 1200)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #07111d;
            --panel: #0d1b2a;
            --panel-soft: #13263b;
            --line: rgba(148, 163, 184, 0.18);
            --text: #e8eef7;
            --muted: #9fb0c6;
            --accent: #5eead4;
            --green-bg: #dff7e7;
            --green-fg: #14532d;
            --yellow-bg: #fff7db;
            --yellow-fg: #854d0e;
            --red-bg: #fbe4e6;
            --red-fg: #9f1239;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(94, 234, 212, 0.12), transparent 24%),
                radial-gradient(circle at top right, rgba(250, 204, 21, 0.10), transparent 22%),
                linear-gradient(180deg, #040a12 0%, #07111d 45%, #0b1725 100%);
            color: var(--text);
        }
        [data-testid="stHeader"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 3rem !important;
        }
        .hero {
            padding: 1.5rem 1.6rem;
            border-radius: 24px;
            background: linear-gradient(135deg, rgba(19, 38, 59, 0.95), rgba(13, 27, 42, 0.95));
            border: 1px solid var(--line);
            box-shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
            margin-bottom: 1rem;
        }
        .hero-kicker {
            color: var(--accent);
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            margin-bottom: 0.55rem;
        }
        .hero-title {
            color: var(--text);
            font-size: clamp(2rem, 3vw, 2.9rem);
            font-weight: 800;
            line-height: 1.04;
            margin-bottom: 0.45rem;
        }
        .hero-copy {
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.55;
        }
        .legend {
            display: flex;
            gap: 0.6rem;
            flex-wrap: wrap;
            margin: 0.35rem 0 0.75rem;
        }
        .legend-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.36rem 0.72rem;
            border-radius: 999px;
            font-size: 0.84rem;
            font-weight: 700;
            border: 1px solid var(--line);
            background: rgba(148, 163, 184, 0.08);
            color: var(--text);
        }
        .legend-green { background: rgba(34, 197, 94, 0.12); color: #bbf7d0; }
        .legend-yellow { background: rgba(250, 204, 21, 0.12); color: #fde68a; }
        .legend-red { background: rgba(244, 63, 94, 0.12); color: #fecdd3; }
        div[data-testid="stForm"] {
            border: 1px solid var(--line);
            border-radius: 22px;
            padding: 1rem 1rem 0.4rem 1rem;
            background: linear-gradient(180deg, rgba(13, 27, 42, 0.88), rgba(8, 18, 30, 0.94));
        }
        .stSelectbox label, .stDateInput label, .stNumberInput label, .stMarkdown, .stCaption {
            color: var(--text) !important;
        }
        .stSelectbox div[data-baseweb="select"] > div,
        .stDateInput input,
        .stNumberInput input {
            background: rgba(19, 38, 59, 0.92) !important;
            color: var(--text) !important;
            border: 1px solid rgba(148, 163, 184, 0.22) !important;
            border-radius: 14px !important;
        }
        .stButton > button, div[data-testid="stFormSubmitButton"] > button {
            min-height: 3rem;
            border-radius: 14px;
            border: 1px solid rgba(94, 234, 212, 0.26);
            background: linear-gradient(180deg, rgba(21, 44, 69, 0.96), rgba(12, 27, 42, 0.98));
            color: #f4fbff;
            font-weight: 800;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.25);
        }
        .stButton > button:hover, div[data-testid="stFormSubmitButton"] > button:hover {
            border-color: rgba(94, 234, 212, 0.45);
            color: #ffffff;
        }
        [data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(13, 27, 42, 0.92), rgba(10, 22, 36, 0.96));
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 0.85rem 0.95rem;
        }
        [data-testid="stMetricLabel"] {
            color: var(--muted) !important;
        }
        [data-testid="stMetricValue"] {
            color: var(--text) !important;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 18px;
            overflow: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def clean_selected_numbers(values: list[int]) -> list[int]:
    return [int(value) for value in values if int(value) > 0]


def classify_dividend(dividend: float) -> str:
    if dividend >= 21:
        return "Verde"
    if dividend >= 15:
        return "Amarillo"
    return "Rojo"


def format_currency(value: float | int) -> str:
    return f"${int(round(value)):,}".replace(",", ".")


def build_table(probables: dict[str, float], amount_per_combination: int) -> pd.DataFrame:
    total_bet = amount_per_combination * 15
    rows = []
    for combination, dividend in probables.items():
        dividend_value = float(dividend)
        retorno_bruto = dividend_value * amount_per_combination
        ganancia_neta = retorno_bruto - total_bet
        rows.append(
            {
                "Combinación": combination,
                "Dividendo actual": round(dividend_value, 2),
                "Categoría": classify_dividend(dividend_value),
                "Retorno bruto ($)": int(round(retorno_bruto)),
                "Ganancia neta ($)": int(round(ganancia_neta)),
            }
        )

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values(by="Dividendo actual", ascending=False, kind="stable").reset_index(drop=True)


def build_summary(values: list[float], amount_per_combination: int) -> dict[str, float]:
    total = len(values)
    total_bet = amount_per_combination * 15
    gt_10 = sum(1 for value in values if value > 10)
    gt_15 = sum(1 for value in values if value > 15)
    lt_10 = sum(1 for value in values if value < 10)
    net_gains = [(value * amount_per_combination) - total_bet for value in values]
    profitable = sum(1 for gain in net_gains if gain > 0)
    gt_10_pct_total = sum(1 for gain in net_gains if gain > total_bet * 0.10)
    gt_15_pct_total = sum(1 for gain in net_gains if gain > total_bet * 0.15)
    return {
        "total": total,
        "min": min(values),
        "max": max(values),
        "median": median(values),
        "gt_10": gt_10,
        "gt_15": gt_15,
        "lt_10": lt_10,
        "pct_gt_15": (gt_15 / total) * 100 if total else 0.0,
        "pct_lt_10": (lt_10 / total) * 100 if total else 0.0,
        "total_bet": total_bet,
        "best_net_gain": max(net_gains) if net_gains else 0.0,
        "worst_net_gain": min(net_gains) if net_gains else 0.0,
        "profitable": profitable,
        "high_value": sum(1 for value in values if value >= 21),
        "gt_10_pct_total": gt_10_pct_total,
        "gt_15_pct_total": gt_15_pct_total,
    }


def describe_scenario(summary: dict[str, float]) -> tuple[str, str]:
    if summary["pct_gt_15"] >= 50 and summary["pct_lt_10"] < 25:
        return "success", "Escenario favorable"
    if summary["pct_lt_10"] >= 50 or summary["pct_gt_15"] < 20:
        return "error", "Escenario poco atractivo"
    return "warning", "Escenario intermedio"


def render_scenario(summary: dict[str, float]) -> None:
    level, label = describe_scenario(summary)
    detail = (
        f"> 15: {summary['pct_gt_15']:.1f}% | "
        f"< 10: {summary['pct_lt_10']:.1f}% | "
        f"Rentables: {summary['profitable']} | "
        f"Alto valor: {summary['high_value']}"
    )
    if level == "success":
        st.success(f"{label}. {detail}")
    elif level == "error":
        st.error(f"{label}. {detail}")
    else:
        st.warning(f"{label}. {detail}")


def style_roi_table(frame: pd.DataFrame) -> pd.io.formats.style.Styler:
    def style_dividend_row(row: pd.Series) -> list[str]:
        category = str(row.get("Categoría", ""))
        if category == "Verde":
            bg = "background-color: #dff7e7; color: #14532d;"
        elif category == "Amarillo":
            bg = "background-color: #fff7db; color: #854d0e;"
        else:
            bg = "background-color: #fbe4e6; color: #9f1239;"
        return [bg if column in {"Categoría", "Dividendo actual"} else "" for column in row.index]

    return frame.style.apply(style_dividend_row, axis=1).format(
        {
            "Dividendo actual": lambda value: f"{float(value):.2f}",
            "Retorno bruto ($)": lambda value: format_currency(float(value)),
            "Ganancia neta ($)": lambda value: format_currency(float(value)),
        }
    )


def main() -> None:
    st.set_page_config(page_title="Calculador de Probables Quinela", page_icon="🏇", layout="centered")
    inject_styles()

    st.markdown(
        """
        <div class="hero">
          <div class="hero-kicker">Consulta rápida</div>
          <div class="hero-title">Calculador de Probables Quinela</div>
          <div class="hero-copy">
            Lectura inmediata de la Quinela Box con costo total, retorno bruto, ganancia neta
            y codificación visual por rangos de dividendo.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "Cada clic en 'Consultar Probables' hace una consulta nueva a Teletrak. "
        "Los dividendos corresponden al instante exacto de esa consulta, sin simulación y sin caché persistente.",
        icon="ℹ️",
    )

    with st.form("consulta_probables"):
        track_code = st.selectbox(
            "Hipódromo",
            options=list(TRACK_OPTIONS.keys()),
            format_func=lambda item: f"{item} · {TRACK_OPTIONS[item]}",
        )
        selected_date = st.date_input("Fecha", value=date.today(), format="YYYY-MM-DD")
        race_number = st.number_input("Carrera", min_value=1, step=1, value=1)
        amount_per_combination = st.selectbox(
            "Monto por combinación",
            options=list(BET_OPTIONS),
            index=1,
            format_func=lambda value: format_currency(value),
        )

        st.write("6 números de caballo")
        cols = st.columns(6)
        selected_numbers = []
        for index, col in enumerate(cols, start=1):
            with col:
                selected_numbers.append(
                    st.number_input(
                        f"N{index}",
                        min_value=1,
                        step=1,
                        value=index,
                    )
                )

        submitted = st.form_submit_button("Consultar Probables", use_container_width=True)

    if not submitted:
        return

    selected_numbers = clean_selected_numbers(selected_numbers)
    if len(selected_numbers) != 6 or len(set(selected_numbers)) != 6:
        st.error("Debes ingresar exactamente 6 números de caballo distintos.")
        return

    with st.spinner("Consultando Teletrak..."):
        try:
            result = fetch_live_quinella_probables(
                track_code.lower(),
                int(race_number),
                meeting_date=selected_date.isoformat(),
                selected_numbers=selected_numbers,
            )
        except Exception as exc:
            st.error(f"No fue posible consultar Teletrak: {exc}")
            return

    probables = result.get("probables") or {}
    if not probables:
        st.warning(UNAVAILABLE_MESSAGE)
        return

    values = sorted(float(value) for value in probables.values())
    summary = build_summary(values, amount_per_combination)

    st.subheader("Tabla de probables")
    st.markdown(
        """
        <div class="legend">
          <span class="legend-badge legend-red">Rojo · dividendo &lt; 15</span>
          <span class="legend-badge legend-yellow">Amarillo · 15 a 20.99</span>
          <span class="legend-badge legend-green">Verde · 21 o más</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    table = build_table(probables, amount_per_combination)
    st.dataframe(
        style_roi_table(table),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Resumen económico")
    econ_one = st.columns(3)
    econ_one[0].metric("Monto por combinación", format_currency(amount_per_combination))
    econ_one[1].metric("Costo total", format_currency(summary["total_bet"]))
    econ_one[2].metric("Mejor ganancia neta", format_currency(summary["best_net_gain"]))

    econ_two = st.columns(4)
    econ_two[0].metric("Peor ganancia neta", format_currency(summary["worst_net_gain"]))
    econ_two[1].metric("Ganancia > 0", str(summary["profitable"]))
    econ_two[2].metric("> 10% del total", str(summary["gt_10_pct_total"]))
    econ_two[3].metric("> 15% del total", str(summary["gt_15_pct_total"]))

    st.subheader("Semáforo informativo")
    render_scenario(summary)
    st.caption(
        f"Combinaciones rentables: {summary['profitable']} | "
        f"Combinaciones de alto valor: {summary['high_value']}"
    )

    st.subheader("Resumen rápido")
    row_one = st.columns(5)
    row_one[0].metric("Total combinaciones", str(summary["total"]))
    row_one[1].metric("Mínimo", f"{summary['min']:.2f}")
    row_one[2].metric("Máximo", f"{summary['max']:.2f}")
    row_one[3].metric("Mediana", f"{summary['median']:.2f}")
    row_one[4].metric("> 10", str(summary["gt_10"]))

    row_two = st.columns(4)
    row_two[0].metric("> 15", str(summary["gt_15"]))
    row_two[1].metric("< 10", str(summary["lt_10"]))
    row_two[2].metric("% > 15", f"{summary['pct_gt_15']:.1f}%")
    row_two[3].metric("% < 10", f"{summary['pct_lt_10']:.1f}%")

    fetched_at = result.get("fetched_at", "Sin timestamp")
    st.caption(f"Consulta realizada: {fetched_at}")
    st.caption(
        f"Costo total para 15 combinaciones: {format_currency(summary['total_bet'])}. "
        "Para actualizar los dividendos debes presionar nuevamente 'Consultar Probables'."
    )


if __name__ == "__main__":
    main()
