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


def clean_selected_numbers(values: list[int]) -> list[int]:
    cleaned = [int(value) for value in values if int(value) > 0]
    return cleaned


def build_table(probables: dict[str, float]) -> pd.DataFrame:
    rows = []
    for combination, dividend in probables.items():
        if dividend > 10:
            status = "valor"
        elif dividend < 3:
            status = "sobreapostado"
        else:
            status = ""
        rows.append(
            {
                "Combinación": combination,
                "Dividendo actual": round(float(dividend), 2),
                "Lectura": status,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    st.set_page_config(page_title="Calculador de Probables Quinela", page_icon="🏇", layout="centered")
    st.title("Calculador de Probables Quinela")
    st.caption("Consulta manual rápida de probables Quinela en vivo desde Teletrak")

    with st.form("consulta_probables"):
        track_code = st.selectbox(
            "Hipódromo",
            options=list(TRACK_OPTIONS.keys()),
            format_func=lambda item: f"{item} · {TRACK_OPTIONS[item]}",
        )
        selected_date = st.date_input("Fecha", value=date.today(), format="YYYY-MM-DD")
        race_number = st.number_input("Carrera", min_value=1, step=1, value=1)

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
    metrics = st.columns(6)
    metrics[0].metric("Combos", str(len(values)))
    metrics[1].metric("Mínimo", f"{min(values):.2f}")
    metrics[2].metric("Máximo", f"{max(values):.2f}")
    metrics[3].metric("Mediana", f"{median(values):.2f}")
    metrics[4].metric("> 10", str(sum(1 for value in values if value > 10)))
    metrics[5].metric("> 15", str(sum(1 for value in values if value > 15)))
    st.caption(f"< 10: {sum(1 for value in values if value < 10)}")

    table = build_table(probables)
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Dividendo actual": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    st.caption(f"Consulta realizada: {result.get('fetched_at', 'Sin timestamp')}")


if __name__ == "__main__":
    main()
