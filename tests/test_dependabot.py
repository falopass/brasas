"""CI-27: Dependabot agrupa menores/parches por ecosistema y limita sus PR abiertos.

Sin agrupar, cada lunes puede entrar una tanda de hasta 30 PR de una dependencia
cada uno y tapar el cupo de revisión del repositorio.
"""

from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent.parent / ".github" / "dependabot.yml"
ECOSISTEMAS = {"pip", "npm", "github-actions"}


def _updates() -> list[dict]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return {u["package-ecosystem"]: u for u in config["updates"]}


def test_los_tres_ecosistemas_estan_declarados():
    assert ECOSISTEMAS <= set(_updates()), "Falta un ecosistema en dependabot.yml"


def test_cada_ecosistema_agrupa_menores_y_parches():
    for nombre, update in _updates().items():
        grupos = update.get("groups") or {}
        assert any({"minor", "patch"} <= set(grupo.get("update-types") or []) for grupo in grupos.values()), (
            f"{nombre}: falta un grupo con update-types minor y patch (las mayores quedan fuera)"
        )


def test_cada_ecosistema_limita_sus_pr_abiertos():
    for nombre, update in _updates().items():
        limite = update.get("open-pull-requests-limit")
        assert limite is not None, f"{nombre}: falta open-pull-requests-limit"
        assert limite <= 5, f"{nombre}: open-pull-requests-limit={limite} debe ser ≤ 5"
