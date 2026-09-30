"""
FinGuard AI — Шаг 7: дашборд для демо.
Запуск:  streamlit run 7_dashboard.py
"""

import streamlit as st
import pandas as pd
import json
import os

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

st.set_page_config(page_title="FinGuard AI", layout="wide")
st.title("FinGuard AI — Corporate Risk Intelligence & Credit Decision Platform")

with open(f"{DATA}/final_reports.json", encoding="utf-8") as f:
    reports = json.load(f)

names = {r["name"]: r for r in reports}
selected = st.selectbox("Выберите компанию", list(names.keys()))
r = names[selected]

color = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red"}[r["risk_level"]]
st.markdown(f"## {r['name']} — Overall Risk: :{color}[{r['risk_level']}]")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Financial Risk", r["financial_risk"])
c2.metric("Transaction Anomaly Risk", r["transaction_anomaly_risk"])
c3.metric("Forecast Risk", r["forecast_risk"])
c4.metric("PD (12 мес.)", f"{r['pd_12m_pct']}%")

st.markdown("### Прогноз риска")
fc = r["forecast_trend"]
st.line_chart(pd.DataFrame({"Risk score": [r["overall_risk_score"], fc["3m"], fc["6m"], fc["12m"]]},
                            index=["сейчас", "+3 мес.", "+6 мес.", "+12 мес."]))

col1, col2 = st.columns(2)
with col1:
    st.markdown("### Ключевые факторы риска")
    for f in r["top_risk_factors"]:
        st.write(f"- {f}")
with col2:
    st.markdown("### Кредитное решение")
    st.write(f"**Запрошенный лимит:** {r['requested_credit_limit']:,} KZT")
    st.write(f"**Рекомендованный лимит:** {r['recommended_credit_limit']:,} KZT")
    st.write(f"**Макс. допустимая экспозиция:** {r['max_acceptable_exposure']:,} KZT")
    st.write(f"**Уровень мониторинга:** {r['monitoring_level']}")

st.markdown("### Рекомендованные действия")
for a in r["recommended_actions"]:
    st.write(f"- {a}")
