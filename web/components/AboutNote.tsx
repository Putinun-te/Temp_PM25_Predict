"use client";

import { useLang } from "./LangProvider";

export default function AboutNote() {
  const { t } = useLang();
  return (
    <>
      <h2>{t("howGood")}</h2>
      <p className="note">
        {t("howGoodText")} <a href="https://github.com/Putinun-te/Temp_PM25_Predict#model-card">{t("modelCard")}</a>
      </p>
      <p className="note">{t("sources")}</p>
      <p className="note">
        {t("apiNote")}{" "}
        <a href="https://func-pm25-api-d0b8.azurewebsites.net/api/help">func-pm25-api-d0b8.azurewebsites.net/api/help</a>
      </p>
    </>
  );
}
