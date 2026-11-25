"use client";

import { useLang } from "./LangProvider";

// The static export does not prefix plain <img> paths, so GitHub Pages needs the base path added here.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const REPOSITORY = "https://github.com/Putinun-te/Temp_PM25_Predict";

export default function HowItWorks() {
  const { t } = useLang();
  return (
    <>
      <h1>{t("howTitle")}</h1>
      <p>{t("howIntro")}</p>
      <figure className="diagram">
        <div className="diagram-scroll">
          {/* Drawn by docs/architecture.py; it follows the light or dark theme of the system. */}
          <img src={`${BASE_PATH}/architecture.svg`} alt={t("howDiagramAlt")} width={1200} height={620} />
        </div>
        <figcaption className="note diagram-hint">{t("howScroll")}</figcaption>
      </figure>
      <h2>{t("howStepsTitle")}</h2>
      <ul className="steps">
        <li>{t("howDaily")}</li>
        <li>{t("howPowerBi")}</li>
        <li>{t("howHourly")}</li>
        <li>{t("howHealth")}</li>
        <li>{t("howWeekly")}</li>
      </ul>
      <p className="note">
        {t("howSource")} <a href={REPOSITORY}>github.com/Putinun-te/Temp_PM25_Predict</a>
      </p>
    </>
  );
}
